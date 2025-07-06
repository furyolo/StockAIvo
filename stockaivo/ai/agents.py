"""
AI Agent Definitions for StockAIvo

This file defines the individual agent nodes for the LangGraph workflow.
Each function represents an agent and will be a node in the graph.
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import date, timedelta
from stockaivo.data_service import get_stock_data, PeriodType
from stockaivo.database import get_db
from stockaivo.ai.state import GraphState
from stockaivo.ai.llm_service import llm_service

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

    # 周线数据选项
    elif date_range_option == 'past_8_weeks':
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


from stockaivo.ai.tools import llm_tool
import pandas as pd # 导入pandas用于创建示例数据

async def technical_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    技术分析 Agent
    - 分析价格和交易量数据以识别趋势和模式.
    """
    print("\n---Executing Technical Analysis Agent---")
    
    # 模拟从 state 获取数据
    # 在实际应用中，这些数据将由 data_collection_agent 提供
    ticker = state.get("ticker", "UNKNOWN_TICKER")
    raw_data = state.get("raw_data", {})
    
    # 从state中获取日线和周线数据
    daily_prices_data = raw_data.get("daily_prices")
    weekly_prices_data = raw_data.get("weekly_prices")

    # 为避免Prompt过长，对数据进行截断
    # 处理日线数据
    if daily_prices_data:
        daily_price_df = pd.DataFrame(daily_prices_data['data'], columns=daily_prices_data['columns'], index=daily_prices_data['index'])
        # 仅使用最近60条日线数据
        daily_price_str = daily_price_df.tail(60).to_string()
    else:
        daily_price_str = "无日线数据"

    # 处理周线数据
    if weekly_prices_data:
        weekly_price_df = pd.DataFrame(weekly_prices_data['data'], columns=weekly_prices_data['columns'], index=weekly_prices_data['index'])
        # 仅使用最近30条周线数据
        weekly_price_str = weekly_price_df.tail(30).to_string()
    else:
        weekly_price_str = "无周线数据"

    prompt = f"""
    你是一位专业的股票技术分析师。请根据以下为股票代码 {ticker} 提供的日线和周线价格及交易量数据，进行深入的技术分析。

    **分析要求:**
    1.  **趋势分析:** 结合日线和周线图，判断当前的主要趋势（上升、下降、横盘），并识别任何潜在的趋势反转信号。
    2.  **关键水平:** 在周线图上找出长期的关键支撑位和阻力位，并在日线图上识别短期的关键水平。
    3.  **技术指标 (可选):** 如果可能，请提及一些常见的技术指标（如移动平均线, RSI）可能会如何解读这些数据。
    4.  **交易量分析:** 分析交易量与价格变动的关系，判断趋势的强度。
    5.  **总结:** 提供一个简洁的总结，概括你的分析结果和对短期前景的看法。

    **日线原始数据:**
    {daily_price_str}

    **周线原始数据:**
    {weekly_price_str}

    请提供你的分析报告。
    """

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": prompt}})
    
    return {"analysis_results": {"technical_analyst": analysis_result}}


async def fundamental_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    基本面分析 Agent
    - 检查财务报表、行业趋势和经济状况.
    """
    print("\n---Executing Fundamental Analysis Agent---")

    # 检查是否有基本面数据
    raw_data = state.get("raw_data", {})
    has_fundamental_data = any(key in raw_data for key in ['financials', 'company_info', 'earnings'])

    if not has_fundamental_data:
        print("缺少基本面数据，跳过基本面分析")
        return {"analysis_results": {"fundamental_analyst": None}}

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 构建基本面分析的提示词
    fundamental_prompt = f"""
    作为一名专业的基本面分析师，请为股票 {ticker} 提供基本面分析。

    **分析要求:**
    1. **公司概况**: 简要介绍公司的主营业务和行业地位
    2. **财务健康状况**: 基于一般市场认知分析公司的财务状况
    3. **行业趋势**: 分析所在行业的发展趋势和前景
    4. **竞争优势**: 评估公司的核心竞争力
    5. **风险因素**: 识别可能影响公司业绩的主要风险

    请提供专业的基本面分析报告。注意：由于缺乏实时财务数据，请基于公开信息和一般市场认知进行分析。
    """

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": fundamental_prompt}})
    return {"analysis_results": {"fundamental_analyst": analysis_result}}


async def news_sentiment_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    新闻舆情分析 Agent
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    print("\n---Executing News Sentiment Analysis Agent---")

    # 检查是否有新闻数据
    raw_data = state.get("raw_data", {})
    has_news_data = any(key in raw_data for key in ['news', 'sentiment', 'social_media'])

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        return {"analysis_results": {"news_sentiment_analyst": None}}

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 构建新闻情感分析的提示词
    sentiment_prompt = f"""
    作为一名专业的市场情绪分析师，请为股票 {ticker} 提供新闻情感分析。

    **分析要求:**
    1. **市场情绪概况**: 基于一般市场认知评估当前市场对该股票的整体情绪
    2. **关键事件影响**: 分析可能影响股价的重要事件或新闻
    3. **投资者关注点**: 识别投资者当前最关注的因素
    4. **情绪指标**: 评估市场情绪是偏向乐观、悲观还是中性
    5. **短期影响**: 预测情绪变化对短期股价的可能影响

    请提供专业的市场情绪分析报告。注意：由于缺乏实时新闻数据，请基于公开信息和一般市场认知进行分析。
    """

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": sentiment_prompt}})
    return {"analysis_results": {"news_sentiment_analyst": analysis_result}}


async def synthesis_agent(state: GraphState) -> Dict[str, Any]:
    """
    决策合成 Agent
    - 整合所有分析师的见解以形成最终的投资报告.
    """
    print("\n---Executing Synthesis Agent---")

    ticker = state.get("ticker", "UNKNOWN_TICKER")
    analysis_results = state.get("analysis_results", {})

    # 提取各个分析师的结果
    data_collector_result = analysis_results.get("data_collector", "无数据收集信息")
    technical_result = analysis_results.get("technical_analyst", "无技术分析")
    fundamental_result = analysis_results.get("fundamental_analyst")
    news_result = analysis_results.get("news_sentiment_analyst")

    # 检查哪些分析可用
    available_analyses = []
    if technical_result and technical_result != "无技术分析":
        available_analyses.append("技术分析")
    if fundamental_result:
        available_analyses.append("基本面分析")
    if news_result:
        available_analyses.append("新闻情感分析")

    # 构建综合分析的提示词
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
        synthesis_prompt = f"""
        作为一名资深的投资顾问，请基于以下技术分析报告，为股票 {ticker} 提供一份投资建议报告。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的分析:**
        1. **投资建议总结**: 基于技术分析，给出明确的投资建议（买入/持有/卖出）
        2. **技术面风险评估**: 识别主要的技术风险因素和机会
        3. **关键技术观察点**: 投资者应该重点关注的技术指标和价格水平
        4. **时间框架**: 建议的投资时间框架（短期/中期/长期）
        5. **执行策略**: 具体的买卖点位建议

        请提供专业、客观且实用的投资建议。注意：由于缺乏基本面和新闻数据，本分析主要基于技术面。
        """
    else:
        # 有多种分析时的提示词
        synthesis_prompt = f"""
        作为一名资深的投资顾问，请基于以下各专业分析师的报告，为股票 {ticker} 提供一份综合的投资建议报告。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的综合分析:**
        1. **投资建议总结**: 基于所有可用分析，给出明确的投资建议（买入/持有/卖出）
        2. **风险评估**: 识别主要风险因素和机会
        3. **关键观察点**: 投资者应该重点关注的指标和事件
        4. **时间框架**: 建议的投资时间框架（短期/中期/长期）
        5. **执行策略**: 具体的买卖点位建议

        请提供专业、客观且实用的投资建议。
        """

    # 调用LLM生成综合分析
    synthesis_result = await llm_tool.ainvoke({"input_dict": {"prompt": synthesis_prompt}})

    return {"final_report": synthesis_result}


# ==================== 流式版本的Agents ====================

async def technical_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    技术分析 Agent - 流式版本
    """
    print("\n---Executing Technical Analysis Agent (Stream)---")

    ticker = state.get("ticker", "UNKNOWN_TICKER")
    raw_data = state.get("raw_data", {})

    # 获取价格数据
    daily_prices = raw_data.get("daily_prices")
    weekly_prices = raw_data.get("weekly_prices")

    if not daily_prices or not weekly_prices:
        yield {"analysis_results": {"technical_analyst": "无法获取价格数据进行技术分析"}}
        return

    # 构建技术分析的提示词（与原版相同）
    daily_price_str = daily_prices.to_string(index=False) if hasattr(daily_prices, 'to_string') else str(daily_prices)
    weekly_price_str = weekly_prices.to_string(index=False) if hasattr(weekly_prices, 'to_string') else str(weekly_prices)

    prompt = f"""
    作为一名专业的股票技术分析师，请对股票 {ticker} 进行深入的技术分析。

    **日线数据:**
    {daily_price_str}

    **周线数据:**
    {weekly_price_str}

    请提供你的分析报告。
    """

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
    analysis_results = state.get("analysis_results", {})

    # 提取各个分析师的结果（与原版相同的逻辑）
    data_collector_result = analysis_results.get("data_collector", "无数据收集信息")
    technical_result = analysis_results.get("technical_analyst", "无技术分析")
    fundamental_result = analysis_results.get("fundamental_analyst")
    news_result = analysis_results.get("news_sentiment_analyst")

    # 检查哪些分析可用
    available_analyses = []
    if technical_result and technical_result != "无技术分析":
        available_analyses.append("技术分析")
    if fundamental_result:
        available_analyses.append("基本面分析")
    if news_result:
        available_analyses.append("新闻情感分析")

    # 构建综合分析的提示词
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
        synthesis_prompt = f"""
        作为一名资深的投资顾问，请基于以下技术分析报告，为股票 {ticker} 提供一份投资建议报告。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的分析:**
        1. **投资建议总结**: 基于技术分析，给出明确的投资建议（买入/持有/卖出）
        2. **技术面风险评估**: 识别主要的技术风险因素和机会
        3. **关键技术观察点**: 投资者应该重点关注的技术指标和价格水平
        4. **时间框架**: 建议的投资时间框架（短期/中期/长期）
        5. **执行策略**: 具体的买卖点位建议

        请提供专业、客观且实用的投资建议。注意：由于缺乏基本面和新闻数据，本分析主要基于技术面。
        """
    else:
        # 有多种分析时的提示词
        synthesis_prompt = f"""
        作为一名资深的投资顾问，请基于以下各专业分析师的报告，为股票 {ticker} 提供一份综合的投资建议报告。

        {chr(10).join(analysis_sections)}

        **请提供以下内容的综合分析:**
        1. **投资建议总结**: 基于所有可用分析，给出明确的投资建议（买入/持有/卖出）
        2. **风险评估**: 识别主要风险因素和机会
        3. **关键观察点**: 投资者应该重点关注的指标和事件
        4. **时间框架**: 建议的投资时间框架（短期/中期/长期）
        5. **执行策略**: 具体的买卖点位建议

        请提供专业、客观且实用的投资建议。
        """

    # 流式生成综合分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(synthesis_prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"final_report": accumulated_result}