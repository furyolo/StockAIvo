"""
AI Agent Definitions for StockAIvo

This file defines the individual agent nodes for the LangGraph workflow.
Each function represents an agent and will be a node in the graph.
"""

import asyncio
import pandas as pd
import pandas_market_calendars as mcal
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import date, timedelta, datetime
from stockaivo.data_service import get_stock_data, PeriodType
from stockaivo.database import get_db
from stockaivo.ai.state import GraphState
from stockaivo.ai.llm_service import llm_service
from stockaivo.ai.tools import llm_tool
from stockaivo.ai.technical_indicator import TechnicalIndicator

def _calculate_date_range(period: PeriodType, date_range_option: Optional[str], custom_date_range: Optional[dict]) -> tuple[Optional[str], Optional[str]]:
    """
    根据用户的选择和数据周期计算最终的开始和结束日期。
    """
    # 1. 优先使用自定义日期范围
    if custom_date_range and custom_date_range.get('start_date') and custom_date_range.get('end_date'):
        return custom_date_range['start_date'], custom_date_range['end_date']

    # 2. 处理预设选项
    today = date.today()
    yesterday = today - timedelta(days=1)
    start_date = None

    # 根据数据周期类型处理不同的日期范围选项
    if period == "daily":
        # 日线数据选项
        if date_range_option == 'past_30_days':
            start_date = today - timedelta(days=30)
        elif date_range_option == 'past_60_days':
            start_date = today - timedelta(days=60)
        elif date_range_option == 'past_90_days':
            start_date = today - timedelta(days=90)
        elif date_range_option == 'past_180_days':
            start_date = today - timedelta(days=180)
        elif date_range_option == 'past_1_year':
            start_date = today - timedelta(days=365)
    elif period == "weekly":
        # 周线数据选项
        if date_range_option == 'past_8_weeks':
            start_date = today - timedelta(weeks=8)
        elif date_range_option == 'past_16_weeks':
            start_date = today - timedelta(weeks=16)
        elif date_range_option == 'past_24_weeks':
            start_date = today - timedelta(weeks=24)
        elif date_range_option == 'past_52_weeks':
            start_date = today - timedelta(weeks=52)

    if start_date:
        return start_date.isoformat(), yesterday.isoformat()

    return None, None

async def data_collection_agent(state: GraphState) -> Dict[str, Any]:
    """
    Data Collection Agent
    - Fetches raw data (e.g., stock prices, financial statements, news) from various sources.
    - This is the entry point for the workflow.
    - It interacts with the DataService to leverage the project's caching and data persistence layers.
    """
    print("\n---Executing Data Collection Agent---")
    ticker = state.get("ticker")
    if not ticker:
        raise ValueError("Ticker is not provided in the state.")

    date_range_option = state.get("date_range_option")
    custom_date_range = state.get("custom_date_range")

    print(f"Collecting data for {ticker} with option: {date_range_option}")
    
    collected_data = {}
    db_session_gen = get_db()
    db = next(db_session_gen)
    
    try:
        periods_to_fetch: list[PeriodType] = ["daily", "weekly"]
        
        tasks = []
        for period in periods_to_fetch:
            # 为每个周期单独计算日期范围
            start_date, end_date = _calculate_date_range(period, date_range_option, custom_date_range)
            print(f"  - For {period} data, calculated range: {start_date or 'default start'} to {end_date or 'default end'}")
            
            task = get_stock_data(
                db=db,
                ticker=ticker,
                period=period,
                start_date=start_date,
                end_date=end_date,
                background_tasks=None, # No background tasks needed for agent context
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        for period, data_df in zip(periods_to_fetch, results):
            if data_df is not None and not data_df.empty:
                collected_data[f'{period}_prices'] = data_df.to_dict(orient='split')
                print(f"Successfully collected {period} data for {ticker}.")
            else:
                print(f"Could not find {period} data for {ticker}.")

    finally:
        db.close()


    # 生成数据收集摘要
    data_summary = f"数据收集完成 - 股票代码: {ticker}\n"
    for key, value in collected_data.items():
        if isinstance(value, dict) and 'data' in value:
            data_count = len(value['data'])
            data_summary += f"- {key}: {data_count} 条记录\n"
        else:
            data_summary += f"- {key}: 已收集\n"

    return {
        "raw_data": collected_data,
        "analysis_results": {"data_collector": data_summary}
    }


# ==================== 共享的Prompt和逻辑函数 ====================

def _get_target_friday_date() -> str:
    """
    计算目标分析日期：最近的周五（如果是交易日）

    规则：
    - 如果今天是周五，返回今天
    - 如果今天不是周五，返回未来最近的周五
    - 如果周五是休市日（周末），往前追溯到最近的非休市日（周四）

    Returns:
        格式化的日期字符串 (YYYY-MM-DD)
    """
    today = datetime.now()

    # 计算到下一个周五的天数 (周一=0, 周二=1, ..., 周日=6)
    days_until_friday = (4 - today.weekday()) % 7

    # 如果今天是周五，days_until_friday = 0
    target_date = today + timedelta(days=days_until_friday)

    # 如果目标日期是周六或周日（不太可能，但为了安全），往前调整到周五
    if target_date.weekday() == 5:  # 周六
        target_date = target_date - timedelta(days=1)
    elif target_date.weekday() == 6:  # 周日
        target_date = target_date - timedelta(days=2)

    return target_date.strftime("%Y-%m-%d")

def _calculate_trading_days_until_target(target_date_str: str) -> int:
    """
    计算从今天到目标日期的交易日总数（包括今天和目标日期）

    Args:
        target_date_str: 目标日期字符串 (YYYY-MM-DD)

    Returns:
        int: 交易日数量
    """
    try:
        today = datetime.now().date()
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        # 如果目标日期在今天之前，返回0
        if target_date < today:
            return 0

        # 使用NYSE日历获取交易日
        nyse_calendar = mcal.get_calendar('NYSE')

        # 获取从今天到目标日期的所有交易日（包括今天和目标日期）
        schedule = nyse_calendar.schedule(start_date=today, end_date=target_date)

        # 返回交易日总数
        return len(schedule)

    except Exception:
        # 如果出错，返回一个估算值（假设每周5个交易日）
        try:
            today = datetime.now().date()
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            days_diff = (target_date - today).days + 1  # +1 包括今天
            # 粗略估算：每7天约5个交易日
            estimated_trading_days = int(days_diff * 5 / 7)
            return max(1, estimated_trading_days)  # 至少返回1
        except:
            return 1  # 默认返回1

def _build_technical_analysis_prompt(ticker: str, daily_price_str: str, weekly_price_str: str,
                                   daily_indicators: list[str] | None = None, weekly_indicators: list[str] | None = None) -> str:
    """构建技术分析的提示词，根据实际计算的指标动态调整"""
    target_date = _get_target_friday_date()
    trading_days_count = _calculate_trading_days_until_target(target_date)

    # 构建技术指标说明
    def build_indicators_description(indicators: list[str]) -> str:
        if not indicators:
            return "- 由于数据量不足，未计算技术指标"

        descriptions = []

        # 移动平均线
        ma_indicators = [ind for ind in indicators if ind.startswith('MA')]
        if ma_indicators:
            ma_list = ', '.join(ma_indicators)
            descriptions.append(f"- **移动平均线:** {ma_list}")

        # RSI
        if 'RSI' in indicators:
            descriptions.append("- **RSI:** 相对强弱指标（14日周期）")

        # MACD
        macd_indicators = [ind for ind in indicators if ind in ['MACD', 'Signal', 'Histogram']]
        if macd_indicators:
            descriptions.append("- **MACD:** MACD线、信号线、柱状图")

        # 布林带
        bb_indicators = [ind for ind in indicators if ind.startswith('BB_')]
        if bb_indicators:
            descriptions.append("- **布林带:** 中轨（BB_Middle）、上轨（BB_Upper）、下轨（BB_Lower）")

        # ATR
        if 'ATR' in indicators:
            descriptions.append("- **ATR:** 平均真实波幅（14日周期）")

        # 成交量指标
        volume_indicators = [ind for ind in indicators if ind in ['Volume_MA', 'Volume_Ratio']]
        if volume_indicators:
            descriptions.append("- **成交量指标:** 成交量移动平均（Volume_MA）、成交量比率（Volume_Ratio）")

        # 波动率
        if 'Volatility' in indicators:
            descriptions.append("- **波动率:** 过去20日的价格波动率")

        return '\n    '.join(descriptions) if descriptions else "- 由于数据量不足，未计算技术指标"

    # 获取日线和周线的指标描述
    daily_indicators_desc = build_indicators_description(daily_indicators or [])
    weekly_indicators_desc = build_indicators_description(weekly_indicators or [])

    # 构建分析要求，根据可用指标调整
    analysis_requirements = []

    # 基础价格分析（总是可用）
    analysis_requirements.append(f"1.  **价格趋势分析:** 结合日线和周线图，分析当前的短期趋势（上升、下降、横盘），并识别到 {target_date} 前{trading_days_count}个交易日可能的趋势变化。")

    # 移动平均线分析
    if any(ind.startswith('MA') for ind in (daily_indicators or [])):
        analysis_requirements.append("2.  **移动平均线分析:** 利用移动平均线的排列和价格相对位置，判断趋势强度和方向。")

    # 技术指标分析
    available_indicators = set((daily_indicators or []) + (weekly_indicators or []))
    if available_indicators:
        indicator_analysis = ["3.  **技术指标分析:** 重点分析以下可用技术指标的信号："]

        if 'RSI' in available_indicators:
            indicator_analysis.append("       - RSI是否处于超买（>70）或超卖（<30）区域")

        if any(ind in available_indicators for ind in ['MACD', 'Signal', 'Histogram']):
            indicator_analysis.append("       - MACD线与信号线的交叉情况，柱状图的变化趋势")

        if any(ind.startswith('BB_') for ind in available_indicators):
            indicator_analysis.append("       - 价格与布林带的相对位置，是否触及上下轨")

        if any(ind.startswith('MA') for ind in available_indicators):
            indicator_analysis.append("       - 移动平均线的多头或空头排列")

        analysis_requirements.append('\n    '.join(indicator_analysis))

    # 成交量分析
    if any(ind in available_indicators for ind in ['Volume_MA', 'Volume_Ratio']):
        analysis_requirements.append("4.  **交易量分析:** 利用成交量比率（Volume_Ratio）分析近期交易量的异常变化，结合价格变动判断短期趋势的强度和可持续性。")

    # 波动率和风险分析
    if any(ind in available_indicators for ind in ['ATR', 'Volatility']):
        analysis_requirements.append("5.  **波动率和风险:** 分析ATR和波动率指标，评估当前市场的波动程度和风险水平。")

    # 短期前景（总是包含）
    analysis_requirements.append(f"6.  **短期前景:** 提供一个简洁的总结，重点关注到 {target_date} 前{trading_days_count}个交易日的短期交易机会和风险点，并给出具体的进出场建议。")

    return f"""
    你是一位专业的股票技术分析师。请根据以下为股票代码 {ticker} 提供的日线和周线价格、交易量数据以及已计算的技术指标，进行深入的短期技术分析。

    **分析时间范围:** 重点关注到 {target_date} 之前{trading_days_count}个交易日的短期走势和交易机会。

    **日线数据技术指标:**
    {daily_indicators_desc}

    **周线数据技术指标:**
    {weekly_indicators_desc}

    **分析要求:**
    {chr(10).join(f'    {req}' for req in analysis_requirements)}

    **日线数据（含技术指标）:**
    {daily_price_str}

    **周线数据（含技术指标）:**
    {weekly_price_str}

    请基于上述可用的技术指标数据提供你的专业短期技术分析报告，重点关注到 {target_date} 前{trading_days_count}个交易日的交易机会。
    """

def _process_technical_analysis_data(state: GraphState) -> tuple[str, str, str, list[str], list[str]]:
    """处理技术分析所需的数据，返回ticker、处理后的价格数据字符串和实际计算的技术指标列表"""
    import logging
    logger = logging.getLogger(__name__)

    ticker = state.get("ticker", "UNKNOWN_TICKER")
    raw_data = state.get("raw_data", {})

    # 从state中获取日线和周线数据
    daily_prices_data = raw_data.get("daily_prices")
    weekly_prices_data = raw_data.get("weekly_prices")

    # 初始化技术指标计算器
    technical_indicator = TechnicalIndicator()

    daily_indicators = []
    weekly_indicators = []

    # 处理日线数据 - 使用完整数据集
    if daily_prices_data:
        daily_price_df = pd.DataFrame(daily_prices_data['data'], columns=daily_prices_data['columns'], index=daily_prices_data['index'])

        # 计算技术指标
        try:
            logger.info(f"开始计算{ticker}日线数据的技术指标")
            daily_price_df = technical_indicator.calculate_indicators(daily_price_df)
            daily_indicators = technical_indicator.get_calculated_indicators(daily_price_df)
            logger.info(f"日线数据完成，共{len(daily_indicators)}个指标: {', '.join(daily_indicators)}")
        except Exception as e:
            logger.error(f"计算{ticker}日线技术指标时出错: {str(e)}")

        daily_price_str = daily_price_df.to_string()
    else:
        daily_price_str = "无日线数据"

    # 处理周线数据 - 使用完整数据集
    if weekly_prices_data:
        weekly_price_df = pd.DataFrame(weekly_prices_data['data'], columns=weekly_prices_data['columns'], index=weekly_prices_data['index'])

        # 计算技术指标
        try:
            logger.info(f"开始计算{ticker}周线数据的技术指标")
            weekly_price_df = technical_indicator.calculate_indicators(weekly_price_df)
            weekly_indicators = technical_indicator.get_calculated_indicators(weekly_price_df)
            logger.info(f"周线数据完成，共{len(weekly_indicators)}个指标: {', '.join(weekly_indicators)}")
        except Exception as e:
            logger.error(f"计算{ticker}周线技术指标时出错: {str(e)}")

        weekly_price_str = weekly_price_df.to_string()
    else:
        weekly_price_str = "无周线数据"

    return ticker, daily_price_str, weekly_price_str, daily_indicators, weekly_indicators


def _check_fundamental_data_and_get_ticker(state: GraphState) -> tuple[bool, str]:
    """检查基本面数据是否可用，返回数据可用性和ticker"""
    raw_data = state.get("raw_data", {})
    has_fundamental_data = any(key in raw_data for key in ['financials', 'company_info', 'earnings'])
    ticker = state.get("ticker", "UNKNOWN_TICKER")
    return has_fundamental_data, ticker


def _build_fundamental_analysis_prompt(ticker: str) -> str:
    """构建基本面分析的提示词"""
    return f"""
    作为一名专业的基本面分析师，请为股票 {ticker} 提供基本面分析。

    **分析要求:**
    1. **公司概况**: 简要介绍公司的主营业务和行业地位
    2. **财务健康状况**: 基于一般市场认知分析公司的财务状况
    3. **行业趋势**: 分析所在行业的发展趋势和前景
    4. **竞争优势**: 评估公司的核心竞争力
    5. **风险因素**: 识别可能影响公司业绩的主要风险

    请提供专业的基本面分析报告。
    """


def _check_news_data_and_get_ticker(state: GraphState) -> tuple[bool, str]:
    """检查新闻数据是否可用，返回数据可用性和ticker"""
    raw_data = state.get("raw_data", {})
    has_news_data = any(key in raw_data for key in ['news', 'sentiment', 'social_media'])
    ticker = state.get("ticker", "UNKNOWN_TICKER")
    return has_news_data, ticker


def _build_news_sentiment_analysis_prompt(ticker: str) -> str:
    """构建新闻情感分析的提示词"""
    return f"""
    作为一名专业的市场情绪分析师，请为股票 {ticker} 提供新闻情感分析。

    **分析要求:**
    1. **市场情绪概况**: 基于一般市场认知评估当前市场对该股票的整体情绪
    2. **关键事件影响**: 分析可能影响股价的重要事件或新闻
    3. **投资者关注点**: 识别投资者当前最关注的因素
    4. **情绪指标**: 评估市场情绪是偏向乐观、悲观还是中性
    5. **短期影响**: 预测情绪变化对短期股价的可能影响

    请提供专业的市场情绪分析报告。
    """


def _extract_analysis_results(state: GraphState) -> tuple[str, str, str, str, list[str]]:
    """提取各个分析师的结果并返回可用分析列表"""
    analysis_results = state.get("analysis_results", {})

    data_collector_result = analysis_results.get("data_collector", "无数据收集信息")
    technical_result = analysis_results.get("technical_analyst", "无技术分析")
    fundamental_result = analysis_results.get("fundamental_analyst") or ""
    news_result = analysis_results.get("news_sentiment_analyst") or ""

    # 检查哪些分析可用
    available_analyses = []
    if technical_result and technical_result != "无技术分析":
        available_analyses.append("技术分析")
    if fundamental_result:
        available_analyses.append("基本面分析")
    if news_result:
        available_analyses.append("新闻情感分析")

    return data_collector_result, technical_result, fundamental_result, news_result, available_analyses

def _build_synthesis_prompt(ticker: str, data_collector_result: str, technical_result: str,
                           fundamental_result: str, news_result: str, available_analyses: list[str]) -> str:
    """构建综合分析的提示词"""
    target_date = _get_target_friday_date()
    trading_days_count = _calculate_trading_days_until_target(target_date)

    # 构建分析部分
    analysis_sections = [f"**数据收集情况:**\n{data_collector_result}"]

    if technical_result and technical_result != "无技术分析":
        analysis_sections.append(f"**技术分析报告:**\n{technical_result}")

    if fundamental_result:
        analysis_sections.append(f"**基本面分析报告:**\n{fundamental_result}")

    if news_result:
        analysis_sections.append(f"**新闻情感分析报告:**\n{news_result}")

    # 根据可用的分析类型调整提示词
    if len(available_analyses) == 1 and "技术分析" in available_analyses:
        # 只有技术分析时的提示词
        return f"""
        作为一名资深的投资顾问，请基于以下技术分析报告，为股票 {ticker} 提供一份短期投资建议报告。

        **分析时间范围:** 重点关注到 {target_date} 之前{trading_days_count}个交易日的短期投资机会。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的短期分析:**
        1. **短期投资建议**: 基于技术分析，给出到 {target_date} 前{trading_days_count}个交易日的明确投资建议（买入/持有/卖出）
        2. **短期风险评估**: 识别到 {target_date} 前{trading_days_count}个交易日的主要技术风险因素和机会
        3. **关键技术观察点**: 投资者在 {target_date} 前{trading_days_count}个交易日应该重点关注的技术指标和价格水平
        4. **短期执行策略**: 到 {target_date} 前{trading_days_count}个交易日的具体买卖点位建议

        请提供专业、客观且实用的短期投资建议。注意：由于缺乏基本面和新闻数据，本分析主要基于技术面。
        """
    else:
        # 有多种分析时的提示词
        return f"""
        作为一名资深的投资顾问，请基于以下各专业分析师的报告，为股票 {ticker} 提供一份短期综合投资建议报告。

        **分析时间范围:** 重点关注到 {target_date} 之前{trading_days_count}个交易日的短期投资机会。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的短期综合分析:**
        1. **短期投资建议**: 基于所有可用分析，给出到 {target_date} 前{trading_days_count}个交易日的明确投资建议（买入/持有/卖出）
        2. **短期风险评估**: 识别到 {target_date} 前{trading_days_count}个交易日的主要风险因素和机会
        3. **关键观察点**: 投资者在 {target_date} 前{trading_days_count}个交易日应该重点关注的指标和事件
        4. **短期执行策略**: 到 {target_date} 前{trading_days_count}个交易日的具体买卖点位建议

        请提供专业、客观且实用的短期投资建议。
        """

# ==================== 非流式版本的Agents ====================

async def technical_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    技术分析 Agent
    - 分析价格和交易量数据以识别趋势和模式.
    """
    print("\n---Executing Technical Analysis Agent---")

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, daily_indicators, weekly_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, daily_indicators, weekly_indicators)
    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": prompt}})

    return {"analysis_results": {"technical_analyst": analysis_result}}


async def fundamental_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    基本面分析 Agent
    - 检查财务报表、行业趋势和经济状况.
    """
    print("\n---Executing Fundamental Analysis Agent---")

    # 使用共用函数检查数据和获取ticker
    has_fundamental_data, ticker = _check_fundamental_data_and_get_ticker(state)

    if not has_fundamental_data:
        print("缺少基本面数据，跳过基本面分析")
        return {"analysis_results": {"fundamental_analyst": None}}

    # 使用共用函数构建prompt
    fundamental_prompt = _build_fundamental_analysis_prompt(ticker)

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": fundamental_prompt}})
    return {"analysis_results": {"fundamental_analyst": analysis_result}}


async def news_sentiment_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    新闻舆情分析 Agent
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    print("\n---Executing News Sentiment Analysis Agent---")

    # 使用共用函数检查数据和获取ticker
    has_news_data, ticker = _check_news_data_and_get_ticker(state)

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        return {"analysis_results": {"news_sentiment_analyst": None}}

    # 使用共用函数构建prompt
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker)

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": sentiment_prompt}})
    return {"analysis_results": {"news_sentiment_analyst": analysis_result}}


async def synthesis_agent(state: GraphState) -> Dict[str, Any]:
    """
    决策合成 Agent
    - 整合所有分析师的见解以形成最终的投资报告.
    """
    print("\n---Executing Synthesis Agent---")

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 使用共享的分析结果提取函数
    data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(state)

    # 使用共享的prompt构建函数
    synthesis_prompt = _build_synthesis_prompt(ticker, data_collector_result, technical_result,
                                             fundamental_result, news_result, available_analyses)

    # 调用LLM生成综合分析
    synthesis_result = await llm_tool.ainvoke({"input_dict": {"prompt": synthesis_prompt}})

    return {"final_report": synthesis_result}


# ==================== 流式版本的Agents ====================

async def technical_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    技术分析 Agent - 流式版本
    """
    print("\n---Executing Technical Analysis Agent (Stream)---")

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, daily_indicators, weekly_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, daily_indicators, weekly_indicators)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"technical_analyst": accumulated_result}}


async def synthesis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    决策合成 Agent - 流式版本
    """
    print("\n---Executing Synthesis Agent (Stream)---")

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 使用共享的分析结果提取函数
    data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(state)

    # 使用共享的prompt构建函数
    synthesis_prompt = _build_synthesis_prompt(ticker, data_collector_result, technical_result,
                                             fundamental_result, news_result, available_analyses)

    # 流式生成综合分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(synthesis_prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"final_report": accumulated_result}


async def fundamental_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    基本面分析 Agent - 流式版本
    - 检查财务报表、行业趋势和经济状况.
    """
    print("\n---Executing Fundamental Analysis Agent (Stream)---")

    # 使用共用函数检查数据和获取ticker
    has_fundamental_data, ticker = _check_fundamental_data_and_get_ticker(state)

    if not has_fundamental_data:
        print("缺少基本面数据，跳过基本面分析")
        yield {"analysis_results": {"fundamental_analyst": None}}
        return

    # 使用共用函数构建prompt
    fundamental_prompt = _build_fundamental_analysis_prompt(ticker)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(fundamental_prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"fundamental_analyst": accumulated_result}}


async def news_sentiment_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    新闻舆情分析 Agent - 流式版本
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    print("\n---Executing News Sentiment Analysis Agent (Stream)---")

    # 使用共用函数检查数据和获取ticker
    has_news_data, ticker = _check_news_data_and_get_ticker(state)

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        yield {"analysis_results": {"news_sentiment_analyst": None}}
        return

    # 使用共用函数构建prompt
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(sentiment_prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"news_sentiment_analyst": accumulated_result}}