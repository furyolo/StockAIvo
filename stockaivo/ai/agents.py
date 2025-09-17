"""
AI Agent Definitions for StockAIvo

This file defines the individual agent nodes for the LangGraph workflow.
Each function represents an agent and will be a node in the graph.
"""

import asyncio
import logging
import pandas as pd
from typing import Dict, Any, Optional, AsyncGenerator, NamedTuple
from datetime import date, timedelta, datetime
from stockaivo.data_service import get_stock_data, get_stock_news, PeriodType, get_market_aware_current_date, get_market_aware_minute_date, MarketStateManager
from stockaivo.cache_manager import _is_market_open
from sqlalchemy import select
from stockaivo.database import get_db
from stockaivo.models import UsStocksName
from stockaivo.ai.state import GraphState
from stockaivo.ai.llm_service import get_llm_service
from stockaivo.ai.tools import llm_tool
from stockaivo.ai.technical_indicator import TechnicalIndicator

# 配置日志
logger = logging.getLogger(__name__)

# ==================== 错误检查辅助函数 ====================

def _is_llm_error_result(result: str) -> bool:
    """
    检查LLM返回的结果是否是错误信息
    
    Args:
        result: LLM返回的字符串结果
    
    Returns:
        如果是错误信息返回True，否则返回False
    """
    if not isinstance(result, str):
        return False
    
    error_indicators = [
        "Error calling",
        "HTTP Error",
        "Error:",
        "所有重试都失败了",
        "LLM服务未正确配置",
        "失败:",
        "Blocked for",
        "LLM did not return any content"
    ]
    
    return any(indicator in result for indicator in error_indicators)

# ==================== 重构：统一市场分析接口 ====================

class MarketAnalysisResult(NamedTuple):
    """市场分析结果的数据结构"""
    market_aware_date: date
    target_friday: str              # 保持字符串格式（向后兼容）
    target_friday_date: date        # 新增：date格式（避免转换）
    trading_days_count: int
    calendar_days: int              # 新增：日历天数

# ==================== 重构：使用统一的MarketStateManager ====================

# 注意：原有的缓存层函数已被删除，现在使用data_service.py中的MarketStateManager
# 这避免了重复的NYSE日历获取和交易日集合缓存逻辑

def _get_nyse_calendar():
    """使用统一的NYSE日历获取（向后兼容）"""
    return MarketStateManager.get_nyse_calendar()

def _get_trading_schedule(start_date: date, end_date: date):
    """使用统一的交易时间表获取（向后兼容）"""
    calendar = MarketStateManager.get_nyse_calendar()
    return calendar.schedule(start_date=start_date, end_date=end_date)

def _get_trading_days_set(start_date: date, end_date: date) -> set[date]:
    """使用统一的交易日集合获取（向后兼容）"""
    return MarketStateManager.get_trading_days_set(start_date, end_date)



async def data_collection_agent(state: GraphState) -> Dict[str, Any]:
    """
    Data Collection Agent
    - Fetches raw data (e.g., stock prices, financial statements, news) from various sources.
    - This is the entry point for the workflow.
    - It interacts with the DataService to leverage the project's caching and data persistence layers.
    """
    ticker = state.get("ticker")
    if not ticker:
        raise ValueError("Ticker is not provided in the state.")

    print(f"\n=== Data Collection Agent: {ticker} ===")

    custom_date_range = state.get("custom_date_range")

    # 统一获取市场分析结果（用于日线和周线数据）
    # 如果用户提供了自定义日期，使用用户指定的日期，跳过市场感知处理
    user_specified_date = None
    if custom_date_range and custom_date_range.get('end_date'):
        user_specified_date = datetime.strptime(custom_date_range['end_date'], '%Y-%m-%d').date()
        print(f"📅 Using custom end date: {user_specified_date}")
    else:
        print("📅 Using default market-aware date logic")

    market_analysis = get_market_analysis(user_specified_date)
    print(f"📊 Market analysis: {market_analysis.market_aware_date} (target Friday: {market_analysis.target_friday}, {market_analysis.trading_days_count} trading days)")

    collected_data = {}
    db_session_gen = get_db()
    db = next(db_session_gen)

    try:
        # 为AI Agent添加新闻数据获取功能
        periods_to_fetch: list[PeriodType] = ["daily", "weekly"]

        # 智能判断是否获取10分钟线数据
        # 只有用户没有指定日期且在交易时间内才获取10分钟线数据
        user_specified_end_date_str = custom_date_range and custom_date_range.get('end_date')

        if not user_specified_end_date_str:
            # 用户没有指定日期，检查市场状态
            is_trading_time = _is_market_open()
            if is_trading_time:
                periods_to_fetch.append("10min")
                print("⏰ Market is open - including 10min data")
            else:
                print("🔒 Market is closed - skipping 10min data")
        else:
            print("📈 Historical date specified - skipping 10min data")

        # 1. 获取股票价格数据
        print(f"📈 Fetching price data: {', '.join(periods_to_fetch)}")
        price_tasks = []
        for period in periods_to_fetch:
            # 计算结束日期：优先使用自定义日期，否则使用默认值（None）
            end_date = None
            if custom_date_range and custom_date_range.get('end_date'):
                end_date = custom_date_range['end_date']

            task = get_stock_data(
                db=db,
                ticker=ticker,
                period=period,
                end_date=end_date,
                background_tasks=None, # No background tasks needed for agent context
                market_aware_date=None  # 让get_stock_data内部处理市场感知日期
            )
            price_tasks.append(task)

        # 2. 获取新闻数据
        print("📰 Fetching news data")
        news_task = get_stock_news(
            ticker=ticker,
            background_tasks=None,  # No background tasks needed for agent context
            end_date=end_date  # 使用与股票数据相同的截止日期
        )

        # 3. 并行执行所有数据获取任务
        all_tasks = price_tasks + [news_task]
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # 4. 处理价格数据结果
        price_results = results[:len(periods_to_fetch)]
        for period, result in zip(periods_to_fetch, price_results):
            if isinstance(result, Exception):
                print(f"❌ Error collecting {period} data: {result}")
            elif isinstance(result, pd.DataFrame) and not result.empty:
                # 特殊处理10分钟线数据的键名
                if period == "10min":
                    collected_data['tenmin_prices'] = result.to_dict(orient='split')
                else:
                    collected_data[f'{period}_prices'] = result.to_dict(orient='split')
                print(f"✅ {period} data: {len(result)} records")
            else:
                print(f"⚠️  No {period} data available")

        # 5. 处理新闻数据结果
        news_result = results[-1]
        if isinstance(news_result, Exception):
            print(f"❌ Error collecting news data: {news_result}")
        elif isinstance(news_result, pd.DataFrame) and not news_result.empty:
            collected_data['news'] = news_result.to_dict(orient='records')
            print(f"✅ News data: {len(news_result)} articles")
        else:
            print("⚠️  No news data available")

    finally:
        db.close()


    # 生成数据收集摘要
    total_datasets = len(collected_data)
    print(f"🎯 Data collection completed: {total_datasets} datasets collected")

    data_summary = f"数据收集完成 - 股票代码: {ticker}\n"
    for key, value in collected_data.items():
        if isinstance(value, dict) and 'data' in value:
            data_count = len(value['data'])
            data_summary += f"- {key}: {data_count} 条记录\n"
        elif isinstance(value, list):
            # 处理新闻数据（以records格式存储）
            data_count = len(value)
            data_summary += f"- {key}: {data_count} 条记录\n"
        else:
            data_summary += f"- {key}: 已收集\n"

    return {
        "raw_data": collected_data,
        "analysis_results": {"data_collector": data_summary},
        "market_analysis": market_analysis
    }


# ==================== 内部优化函数 ====================

def _calculate_target_friday_internal(market_aware_date: date) -> date:
    """内部函数：计算目标周五日期（返回date对象）"""
    try:
        today = datetime.combine(market_aware_date, datetime.min.time())
        nyse_calendar = _get_nyse_calendar()
        et_tz = nyse_calendar.tz

        # 获取当前美东时间
        now_et = datetime.now(et_tz)
        current_weekday = today.weekday()

        # 生成交易时间表（使用缓存）
        range_start = today.date() - timedelta(days=7)
        range_end = today.date() + timedelta(days=14)
        trading_days_set = _get_trading_days_set(range_start, range_end)

        if not trading_days_set:
            # 回退到简单逻辑
            return _get_fallback_target_friday_internal(today)

        # 判断市场交易状态（使用统一的MarketStateManager）
        current_date_et = now_et.date()
        is_historical_date = today.date() < current_date_et

        if is_historical_date:
            # 对于历史日期，假设交易已经结束
            is_market_open = False
        else:
            # 使用统一的市场开放状态检查
            is_market_open = MarketStateManager.check_market_open_status(today.date(), now_et)

        # 判断本周交易是否结束
        week_trading_ended = False
        if current_weekday < 5:  # 周一到周五
            if current_weekday == 4:  # 周五
                if is_historical_date:
                    # 历史周五，交易肯定已结束
                    week_trading_ended = True
                else:
                    # 当日周五，根据市场状态判断
                    week_trading_ended = not is_market_open
        else:  # 周末
            week_trading_ended = True

        # 计算目标周的开始日期
        if week_trading_ended:
            # 本周交易已结束，返回下周最后交易日
            days_until_next_monday = (7 - current_weekday) % 7
            if days_until_next_monday == 0:
                days_until_next_monday = 7
            target_week_start = today.date() + timedelta(days=days_until_next_monday)
        else:
            # 本周交易未结束，返回本周最后交易日
            days_since_monday = current_weekday
            target_week_start = today.date() - timedelta(days=days_since_monday)

        # 找到目标周的最后一个交易日
        return _find_last_trading_day_of_week_internal(target_week_start, trading_days_set)

    except Exception:
        # 异常回退
        today = datetime.combine(market_aware_date, datetime.min.time())
        return _get_fallback_target_friday_internal(today)

def _find_last_trading_day_of_week_internal(week_start: date, trading_days_set: set[date]) -> date:
    """
    内部函数：找到指定周的最后一个交易日（重构版本）

    重构改进：
    - 使用MarketStateManager的统一逻辑
    - 保持向后兼容的接口
    """
    # 计算周五日期作为目标日期
    week_friday = week_start + timedelta(days=4)

    # 使用MarketStateManager的统一逻辑
    return MarketStateManager.find_week_last_trading_day(week_friday, trading_days_set)

def _calculate_trading_days_internal(market_aware_date: date, target_date: date) -> int:
    """内部函数：计算交易日数量"""
    try:
        # 边界处理
        if target_date <= market_aware_date:
            return 1

        # 使用缓存的交易时间表
        schedule = _get_trading_schedule(market_aware_date + timedelta(days=1), target_date)
        return len(schedule)

    except Exception:
        # 异常回退：估算
        days_diff = (target_date - market_aware_date).days
        estimated_trading_days = int(days_diff * 5 / 7)
        return max(1, estimated_trading_days)

def _get_fallback_target_friday_internal(today: datetime) -> date:
    """内部回退逻辑：简单的周五计算"""
    current_weekday = today.weekday()

    if current_weekday < 4:  # 周一到周四
        days_until_friday = 4 - current_weekday
        target_date = today + timedelta(days=days_until_friday)
    else:  # 周五到周日
        days_until_next_friday = (4 - current_weekday) % 7
        if days_until_next_friday == 0:
            days_until_next_friday = 7
        target_date = today + timedelta(days=days_until_next_friday)

    return target_date.date()

# ==================== 统一市场分析接口 ====================

def get_market_analysis(market_aware_date: Optional[date] = None) -> MarketAnalysisResult:
    """
    获取完整的市场分析结果

    这是新的统一接口，一次性计算所有相关的市场分析数据，
    避免重复计算，提升性能。

    Args:
        market_aware_date: 可选的市场感知日期，如果不提供则内部调用获取

    Returns:
        MarketAnalysisResult: 包含所有市场分析数据的结构化结果
    """
    if market_aware_date is None:
        market_aware_date = get_market_aware_current_date()

    # 一次性计算所有需要的值
    target_friday_date = _calculate_target_friday_internal(market_aware_date)
    target_friday_str = target_friday_date.strftime("%Y-%m-%d")
    trading_days_count = _calculate_trading_days_internal(market_aware_date, target_friday_date)
    calendar_days = (target_friday_date - market_aware_date).days

    return MarketAnalysisResult(
        market_aware_date=market_aware_date,
        target_friday=target_friday_str,
        target_friday_date=target_friday_date,
        trading_days_count=trading_days_count,
        calendar_days=calendar_days
    )

# ==================== 共享的Prompt和逻辑函数 ====================

def _get_company_name(ticker: str) -> str:
    """
    获取ticker对应的公司英文名称

    Args:
        ticker: 股票代码

    Returns:
        公司英文名称，如果查询失败则返回ticker作为fallback
    """
    try:
        db_session_gen = get_db()
        db = next(db_session_gen)
        try:
            stmt = select(UsStocksName.name).where(UsStocksName.symbol == ticker)
            result = db.execute(stmt).scalar_one_or_none()
            if result:
                company_name = str(result)
                logger.info(f"成功为ticker '{ticker}'找到公司名称: '{company_name}'")
                return company_name
            else:
                logger.warning(f"无法为ticker '{ticker}'找到匹配的公司名称，使用ticker作为fallback")
                return ticker
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"获取{ticker}公司名称失败，使用ticker作为fallback: {e}")
        return ticker

# 注意：原有的向后兼容函数 _get_target_friday_date 和 _calculate_trading_days_to_target 已被删除
# 现在统一使用 get_market_analysis() 获取完整的市场分析结果
# 这避免了重复的计算逻辑和多个接口的维护负担

def _build_technical_analysis_prompt(ticker: str, daily_price_str: str, weekly_price_str: str, tenmin_price_str: str,
                                   daily_indicators: list[str] | None = None, weekly_indicators: list[str] | None = None, tenmin_indicators: list[str] | None = None,
                                   market_aware_date: Optional[date] = None) -> str:
    """构建技术分析的提示词，根据实际计算的指标动态调整"""
    # 使用新的统一接口，一次性获取所有市场分析数据
    market_analysis = get_market_analysis(market_aware_date)
    target_date = market_analysis.target_friday
    trading_days_count = market_analysis.trading_days_count

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

    # 获取日线、周线和10分钟线的指标描述
    daily_indicators_desc = build_indicators_description(daily_indicators or [])
    weekly_indicators_desc = build_indicators_description(weekly_indicators or [])

    # 10分钟线特殊处理：不计算技术指标，专注于价格波动分析
    if tenmin_indicators and len(tenmin_indicators) > 0:
        tenmin_indicators_desc = build_indicators_description(tenmin_indicators)
    else:
        tenmin_indicators_desc = "- 10分钟线数据专注于短期价格和成交量波动观察，不计算复杂技术指标以避免噪音信号"

    # 构建分析要求，根据可用指标调整
    analysis_requirements = []

    # 多时间框架价格分析（总是可用）
    if "无10分钟线数据" not in tenmin_price_str:
        analysis_requirements.append(f"1.  **多时间框架趋势分析:** 结合周线（大趋势确认）、日线（中期趋势判断）和10分钟线（短期波动观察），分析当前的趋势层次，并识别到 {target_date} 前{trading_days_count}个交易日可能的趋势变化。")
    else:
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

    # 10分钟线特定分析（如果有数据）
    if "无10分钟线数据" not in tenmin_price_str:
        analysis_requirements.append("5.  **10分钟线短期波动分析:** 基于10分钟线数据，识别短期价格波动模式、关键支撑阻力位、以及成交量的关键变化（例如放量突破或缩量回调），并结合这些信息寻找精确的入场时机。注意：10分钟线主要用于观察短期波动，不依赖技术指标。")

    # 短期前景（总是包含）
    final_req_num = len(analysis_requirements) + 1
    analysis_requirements.append(f"{final_req_num}.  **短期前景:** 提供一个简洁的总结，重点关注到 {target_date} 前{trading_days_count}个交易日的短期交易机会和风险点，并给出具体的进出场建议。")

    # 构建多时间框架的提示词
    if "无10分钟线数据" not in tenmin_price_str:
        # 包含10分钟线数据的完整分析
        return f"""
    你是一位专业的股票技术分析师。请根据以下为股票代码 {ticker} 提供的多时间框架价格、交易量数据以及已计算的技术指标，进行深入的短期技术分析。

    **分析时间范围:** 重点关注到 {target_date} 之前{trading_days_count}个交易日的短期走势和交易机会。

    **多时间框架分析框架:**
    - **周线:** 大趋势确认和长期支撑阻力位
    - **日线:** 中期趋势判断和主要技术指标分析
    - **10分钟线:** 短期波动观察和精确入场时机

    **日线数据技术指标:**
    {daily_indicators_desc}

    **周线数据技术指标:**
    {weekly_indicators_desc}

    **10分钟线数据说明:**
    {tenmin_indicators_desc}

    **分析要求:**
    {chr(10).join(f'    {req}' for req in analysis_requirements)}

    **日线数据（含技术指标）:**
    {daily_price_str}

    **周线数据（含技术指标）:**
    {weekly_price_str}

    **10分钟线数据（短期波动观察）:**
    {tenmin_price_str}

    请基于上述多时间框架数据提供你的专业技术分析报告，重点关注到 {target_date} 前{trading_days_count}个交易日的交易机会。
    """
    else:
        # 仅包含日线和周线的传统分析
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


def _process_technical_analysis_data(state: GraphState) -> tuple[str, str, str, str, list[str], list[str], list[str]]:
    """处理技术分析所需的数据，返回ticker、处理后的价格数据字符串和实际计算的技术指标列表"""

    ticker = state.get("ticker", "UNKNOWN_TICKER")
    raw_data = state.get("raw_data", {})

    # 从state中获取日线、周线和10分钟线数据
    daily_prices_data = raw_data.get("daily_prices")
    weekly_prices_data = raw_data.get("weekly_prices")
    tenmin_prices_data = raw_data.get("tenmin_prices")

    # 初始化技术指标计算器
    technical_indicator = TechnicalIndicator()

    daily_indicators = []
    weekly_indicators = []
    tenmin_indicators = []

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

    # 处理10分钟线数据 - 仅提供价格数据，不计算技术指标
    if tenmin_prices_data:
        tenmin_price_df = pd.DataFrame(tenmin_prices_data['data'], columns=tenmin_prices_data['columns'], index=tenmin_prices_data['index'])
        tenmin_price_str = tenmin_price_df.to_string()
        tenmin_indicators = []  # 不计算技术指标，避免短期噪音信号
        logger.info(f"10分钟线数据处理完成，提供价格数据用于短期波动观察")
    else:
        tenmin_price_str = "无10分钟线数据"
        tenmin_indicators = []

    return ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators


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


def _check_news_data_and_get_ticker(state: GraphState) -> tuple[bool, str, Optional[list]]:
    """检查新闻数据是否可用，返回数据可用性、ticker和新闻数据"""
    # 更新新闻数据检查函数以返回实际新闻数据
    raw_data = state.get("raw_data", {})
    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 检查是否有新闻数据
    news_data = raw_data.get('news')
    has_news_data = news_data is not None and len(news_data) > 0 if isinstance(news_data, list) else False

    return has_news_data, ticker, news_data if has_news_data else None


def _build_news_sentiment_analysis_prompt(ticker: str, news_data: Optional[list] = None) -> str:
    """构建新闻情感分析的提示词 - 基于时间序列情感演变分析"""
    # 获取公司名称
    company_name = _get_company_name(ticker)

    # 新闻情感分析prompt
    base_prompt = f"""
    作为一名专业的市场情绪分析师，请为股票 {ticker} ({company_name}) 提供基于时间演变的新闻情感分析。

    **目标分析股票：{ticker} - {company_name}**
    **重要提示：**新闻中提到的公司名称"{company_name}"与目标股票代码"{ticker}"是同一家公司。
    请在分析时将新闻中出现的"{company_name}"识别为与股票{ticker}相关的信息。

    **核心分析方法 - 情感演变时间线:**

    **分析要求:**
    - 新闻数据已重新排序为时间顺序（从最早到最新），请按此顺序分析情感演变
    - 构建从早期到最新的情感演变时间线，识别关键转折点
    - 重点关注最新消息的情感状态，确定当前市场真实情绪
    - 预测短期情感发展趋势
    """

    if news_data and len(news_data) > 0:
        # 限制新闻数量以避免prompt过长
        limited_news = news_data[:50]  # 减少到50条新闻以提高分析效率

        # 简单处理新闻数据，按时间排序（从最早到最新）
        processed_news = []
        for news in limited_news:
            title = news.get('title', '无标题')
            content = news.get('content', '无内容')
            publish_time = news.get('publish_time', '未知时间')

            processed_news.append({
                'title': title,
                'content': content,
                'publish_time': publish_time
            })


        # 按发布时间排序（从最早到最新）
        try:
            processed_news.sort(key=lambda x: x['publish_time'])
        except:
            # 如果排序失败，保持原顺序并反转（因为原数据是最新在前）
            processed_news.reverse()

        news_content = f"""
**新闻情感演变分析数据:**

**分析说明:**
- 数据包含 {len(processed_news)} 条新闻（美国东部时区）
- 新闻按时间顺序排列（从最早到最新）
- 请构建情感演变时间线，重点关注最新消息的情感状态

**新闻数据（按时间顺序排列）:**
"""

        # 显示按时间排序的新闻
        for i, news in enumerate(processed_news, 1):
            # 简单的时间标记
            if i <= len(processed_news) // 4:
                time_marker = "【早期】"
            elif i <= len(processed_news) // 2:
                time_marker = "【中期】"
            elif i <= len(processed_news) * 3 // 4:
                time_marker = "【近期】"
            else:
                time_marker = "【最新】"

            news_content += f"""
{i}. {time_marker} 标题: {news['title']}
   时间: {news['publish_time']}
   内容: {news['content']}
"""

        return base_prompt + news_content
    else:
        return base_prompt + "\n注意：当前没有可用的新闻数据，请基于一般市场认知提供分析。"


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
                           fundamental_result: str, news_result: str, available_analyses: list[str],
                           market_aware_date: Optional[date] = None) -> str:
    """构建综合分析的提示词"""
    # 使用新的统一接口，一次性获取所有市场分析数据
    market_analysis = get_market_analysis(market_aware_date)
    target_date = market_analysis.target_friday
    trading_days_count = market_analysis.trading_days_count

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
        5. **已持股投资者专项建议（强制清仓要求）**:
           - **强制清仓提醒**: 必须在 {target_date} 收盘前完成所有股票的卖出操作
           - **最佳卖出时机**: 基于技术指标（支撑位、阻力位、RSI、MACD等）确定到 {target_date} 前{trading_days_count}个交易日内的最优卖出时点
           - **清仓执行策略**: 结合成交量和市场流动性，制定平衡风险收益的分阶段清仓方案
           - **风险控制设置**: 设定紧急止损位和保护性措施，防范清仓期间的重大损失风险

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
        5. **已持股投资者专项建议（强制清仓要求）**:
           - **强制清仓提醒**: 必须在 {target_date} 收盘之前完成所有股票的卖出操作
           - **最佳卖出时机**: 综合技术面、基本面和市场情绪分析，确定到 {target_date} 前{trading_days_count}个交易日内的最优卖出时点
           - **清仓执行策略**: 基于多维度分析，结合市场流动性和价格波动，制定平衡风险收益的分阶段清仓方案
           - **风险控制设置**: 综合各项分析结果，设定紧急止损位和保护性措施，最大化保护投资者利益

        请提供专业、客观且实用的短期投资建议。
        """

# ==================== 非流式版本的Agents ====================

async def technical_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    技术分析 Agent
    - 分析价格和交易量数据以识别趋势和模式.
    """
    ticker = state.get("ticker", "UNKNOWN")
    print(f"\n=== Technical Analysis Agent: {ticker} ===")

    # 优先使用state中的market_analysis，避免重复计算
    market_analysis = state.get("market_analysis")
    if market_analysis is None:
        # 回退机制：如果state中没有market_analysis，则调用get_market_analysis()
        market_analysis = get_market_analysis()
        print("Warning: Using fallback market analysis in technical_analysis_agent")

    market_aware_date = market_analysis.market_aware_date
    print(f"Technical analysis using market date: {market_aware_date}")

    # 检查是否有任何价格数据可用
    raw_data = state.get("raw_data", {})
    has_any_price_data = any(key in raw_data and raw_data[key] for key in ['daily_prices', 'weekly_prices', 'tenmin_prices'])
    
    if not has_any_price_data:
        print("缺少所有价格数据（日线、周线、10分钟线），跳过技术分析")
        return {"analysis_results": {"technical_analyst": None}}

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators, market_aware_date)
    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": prompt, "agent_name": "technical_analysis_agent"}})

    # 检查是否是错误结果
    if _is_llm_error_result(analysis_result):
        print(f"技术分析LLM调用失败: {analysis_result}")
        return {"analysis_results": {"technical_analyst": analysis_result}}  # 技术分析失败时保留错误信息，因为它是必需的

    return {"analysis_results": {"technical_analyst": analysis_result}}


async def fundamental_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    基本面分析 Agent
    - 检查财务报表、行业趋势和经济状况.
    """
    # 使用共用函数检查数据和获取ticker
    has_fundamental_data, ticker = _check_fundamental_data_and_get_ticker(state)

    print(f"\n=== Fundamental Analysis Agent: {ticker} ===")

    if not has_fundamental_data:
        print("缺少基本面数据，跳过基本面分析")
        return {"analysis_results": {"fundamental_analyst": None}}

    # 使用共用函数构建prompt
    fundamental_prompt = _build_fundamental_analysis_prompt(ticker)

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": fundamental_prompt, "agent_name": "fundamental_analysis_agent"}})
    
    # 检查是否是错误结果
    if _is_llm_error_result(analysis_result):
        print(f"基本面分析LLM调用失败: {analysis_result}")
        return {"analysis_results": {"fundamental_analyst": None}}
    
    return {"analysis_results": {"fundamental_analyst": analysis_result}}


async def news_sentiment_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    新闻舆情分析 Agent
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    # 使用共用函数检查数据和获取ticker
    has_news_data, ticker, news_data = _check_news_data_and_get_ticker(state)

    print(f"\n=== News Sentiment Analysis Agent: {ticker} ===")

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        return {"analysis_results": {"news_sentiment_analyst": None}}

    # 使用共用函数构建prompt，传入实际新闻数据
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker, news_data)

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": sentiment_prompt, "agent_name": "news_sentiment_agent"}})
    
    # 检查是否是错误结果
    if _is_llm_error_result(analysis_result):
        print(f"新闻情感分析LLM调用失败: {analysis_result}")
        return {"analysis_results": {"news_sentiment_analyst": None}}
    
    return {"analysis_results": {"news_sentiment_analyst": analysis_result}}


async def synthesis_agent(state: GraphState) -> Dict[str, Any]:
    """
    决策合成 Agent
    - 整合所有分析师的见解以形成最终的投资报告.
    - 注意：只有技术分析成功时才会执行综合分析
    """
    ticker = state.get("ticker", "UNKNOWN")
    print(f"\n=== Synthesis Agent: {ticker} ===")

    # 检查技术分析是否成功 - 技术分析是synthesis的必需前提
    analysis_results = state.get("analysis_results", {})
    technical_result = analysis_results.get("technical_analyst")
    
    def is_valid_analysis_result(result):
        """检查分析结果是否有效"""
        if not result or not isinstance(result, str) or result.strip() == "":
            return False
        error_indicators = [
            "Error calling", "HTTP Error", "Error:",
            "所有重试都失败了", "LLM服务未正确配置", "失败:"
        ]
        return not any(indicator in result for indicator in error_indicators)
    
    if not is_valid_analysis_result(technical_result):
        print("技术分析未返回有效结果，跳过综合分析")
        return {"final_report": "技术分析未返回有效结果，无法进行综合分析。综合分析需要技术分析作为基础。"}

    # 优先使用state中的market_analysis，避免重复计算
    market_analysis = state.get("market_analysis")
    if market_analysis is None:
        # 回退机制：如果state中没有market_analysis，则调用get_market_analysis()
        market_analysis = get_market_analysis()
        print("Warning: Using fallback market analysis in synthesis_agent")

    market_aware_date = market_analysis.market_aware_date
    print(f"Synthesis using market date: {market_aware_date}")

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 使用共享的分析结果提取函数
    data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    synthesis_prompt = _build_synthesis_prompt(ticker, data_collector_result, technical_result,
                                             fundamental_result, news_result, available_analyses, market_aware_date)

    # 调用LLM生成综合分析
    synthesis_result = await llm_tool.ainvoke({"input_dict": {"prompt": synthesis_prompt, "agent_name": "synthesis_agent"}})

    return {"final_report": synthesis_result}


# ==================== 流式版本的Agents ====================

async def technical_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    技术分析 Agent - 流式版本
    """
    ticker = state.get("ticker", "UNKNOWN")
    print(f"\n=== Technical Analysis Agent (Stream): {ticker} ===")

    # 优先使用state中的market_analysis，避免重复计算
    market_analysis = state.get("market_analysis")
    if market_analysis is None:
        # 回退机制：如果state中没有market_analysis，则调用get_market_analysis()
        market_analysis = get_market_analysis()
        print("Warning: Using fallback market analysis in technical_analysis_agent_stream")

    market_aware_date = market_analysis.market_aware_date
    print(f"Technical analysis (stream) using market date: {market_aware_date}")

    # 检查是否有任何价格数据可用
    raw_data = state.get("raw_data", {})
    has_any_price_data = any(key in raw_data and raw_data[key] for key in ['daily_prices', 'weekly_prices', 'tenmin_prices'])
    
    if not has_any_price_data:
        print("缺少所有价格数据（日线、周线、10分钟线），跳过技术分析")
        yield {"analysis_results": {"technical_analyst": None}}
        return

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators, market_aware_date)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in get_llm_service().invoke_stream(prompt, "technical_analysis_agent"):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"technical_analyst": accumulated_result}}


async def synthesis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    决策合成 Agent - 流式版本
    """
    ticker = state.get("ticker", "UNKNOWN")
    print(f"\n=== Synthesis Agent (Stream): {ticker} ===")

    # 优先使用state中的market_analysis，避免重复计算
    market_analysis = state.get("market_analysis")
    if market_analysis is None:
        # 回退机制：如果state中没有market_analysis，则调用get_market_analysis()
        market_analysis = get_market_analysis()
        print("Warning: Using fallback market analysis in synthesis_agent_stream")

    market_aware_date = market_analysis.market_aware_date
    print(f"Synthesis (stream) using market date: {market_aware_date}")

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 使用共享的分析结果提取函数
    data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    synthesis_prompt = _build_synthesis_prompt(ticker, data_collector_result, technical_result,
                                             fundamental_result, news_result, available_analyses, market_aware_date)

    # 流式生成综合分析结果
    accumulated_result = ""
    async for chunk in get_llm_service().invoke_stream(synthesis_prompt, "synthesis_agent"):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"final_report": accumulated_result}


async def fundamental_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    基本面分析 Agent - 流式版本
    - 检查财务报表、行业趋势和经济状况.
    """
    # 使用共用函数检查数据和获取ticker
    has_fundamental_data, ticker = _check_fundamental_data_and_get_ticker(state)

    print(f"\n=== Fundamental Analysis Agent (Stream): {ticker} ===")

    if not has_fundamental_data:
        print("缺少基本面数据，跳过基本面分析")
        yield {"analysis_results": {"fundamental_analyst": None}}
        return

    # 使用共用函数构建prompt
    fundamental_prompt = _build_fundamental_analysis_prompt(ticker)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in get_llm_service().invoke_stream(fundamental_prompt, "fundamental_analysis_agent"):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"fundamental_analyst": accumulated_result}}


async def news_sentiment_analysis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    新闻舆情分析 Agent - 流式版本
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    # 使用共用函数检查数据和获取ticker
    has_news_data, ticker, news_data = _check_news_data_and_get_ticker(state)

    print(f"\n=== News Sentiment Analysis Agent (Stream): {ticker} ===")

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        yield {"analysis_results": {"news_sentiment_analyst": None}}
        return

    # 使用共用函数构建prompt，传入实际新闻数据
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker, news_data)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in get_llm_service().invoke_stream(sentiment_prompt, "news_sentiment_agent"):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"news_sentiment_analyst": accumulated_result}}


async def structured_prediction_agent(state: GraphState) -> Dict[str, Any]:
    """
    结构化预测 Agent - 生成概率化股价预测
    
    基于综合分析生成结构化的预测结果，输出包含：
    - 预测概率值（0.0-1.0）
    - 预测方向（UP/DOWN）
    - 置信度（HIGH/MEDIUM/LOW）
    - 推理说明
    
    注意：需要技术分析成功执行后才能进行结构化预测
    """
    from stockaivo.ai.prediction_models import StockPredictionResult
    from datetime import datetime
    
    ticker = state.get("ticker", "UNKNOWN")
    print(f"\n=== Structured Prediction Agent: {ticker} ===")
    
    # 检查技术分析是否成功 - 这是必需前提
    analysis_results = state.get("analysis_results", {})
    technical_analysis = analysis_results.get("technical_analyst")
    
    if not technical_analysis or "Error" in technical_analysis or "获取数据失败" in technical_analysis:
        logger.warning(f"技术分析失败或不完整，跳过结构化预测: {ticker}")
        return {
            "structured_prediction": {
                "error": "技术分析失败，无法进行结构化预测",
                "timestamp": datetime.now().isoformat()
            }
        }
    
    # 构建结构化预测提示词
    prediction_prompt = _build_structured_prediction_prompt(state)
    
    try:
        # 调用LLM进行结构化预测
        logger.info(f"开始为 {ticker} 生成结构化预测")
        
        prediction_result = await get_llm_service().invoke_structured(
            prediction_prompt, 
            StockPredictionResult,
            agent_name="synthesis_agent"  # 使用synthesis模型配置
        )
        
        if isinstance(prediction_result, StockPredictionResult):
            logger.info(f"结构化预测成功生成: {ticker}, 方向={prediction_result.direction}, 概率={prediction_result.prediction_probability:.2f}")
            
            return {
                "structured_prediction": {
                    "prediction_probability": prediction_result.prediction_probability,
                    "direction": prediction_result.direction,
                    "confidence_level": prediction_result.confidence_level,
                    "reasoning": prediction_result.reasoning,
                    "ticker": ticker,
                    "timestamp": datetime.now().isoformat(),
                    "success": True
                }
            }
        else:
            # LLM返回了错误字符串
            logger.error(f"结构化预测失败: {ticker}, 错误: {prediction_result}")
            return {
                "structured_prediction": {
                    "error": f"结构化预测生成失败: {prediction_result}",
                    "ticker": ticker,
                    "timestamp": datetime.now().isoformat(),
                    "success": False
                }
            }
            
    except Exception as e:
        logger.error(f"结构化预测Agent异常: {ticker}, 错误: {str(e)}")
        return {
            "structured_prediction": {
                "error": f"结构化预测Agent异常: {str(e)}",
                "ticker": ticker,
                "timestamp": datetime.now().isoformat(),
                "success": False
            }
        }


def _build_structured_prediction_prompt(state: GraphState) -> str:
    """构建结构化预测提示词"""
    ticker = state.get("ticker", "UNKNOWN")
    analysis_results = state.get("analysis_results", {})
    raw_data = state.get("raw_data", {})
    
    # 获取原始分析结果（专注于三个基础分析agent的输出）
    technical_analysis = analysis_results.get("technical_analyst")
    fundamental_analysis = analysis_results.get("fundamental_analyst") 
    news_sentiment = analysis_results.get("news_sentiment_analyst")
    
    # 获取市场分析数据，用于计算预测时间范围
    market_analysis = state.get("market_analysis")
    if market_analysis is None:
        # 回退机制：如果state中没有market_analysis，则调用get_market_analysis()
        market_analysis = get_market_analysis()
    
    target_date = market_analysis.target_friday
    trading_days_count = market_analysis.trading_days_count
    market_aware_date = market_analysis.market_aware_date
    
    # 获取当前价格数据（从市场感知日期的收盘价）
    current_price_info = ""
    latest_close = None
    upside_target = None
    downside_target = None
    
    try:
        daily_prices_data = raw_data.get("daily_prices")
        if daily_prices_data:
            daily_price_df = pd.DataFrame(daily_prices_data['data'], columns=daily_prices_data['columns'], index=daily_prices_data['index'])
            if not daily_price_df.empty:
                # 获取最近的收盘价（使用小写列名）
                if 'close' in daily_price_df.columns:
                    latest_close = daily_price_df['close'].iloc[-1]
                    # 计算目标价格水平
                    upside_target = latest_close * 1.03  # 上涨3%目标
                    downside_target = latest_close * 0.97  # 下跌3%目标
                    
                    current_price_info = f"""
**当前市场数据（{market_aware_date}）:**
- 当前收盘价: ${latest_close:.2f}
- 上涨目标价位（+3%）: ${upside_target:.2f}
- 下跌目标价位（-3%）: ${downside_target:.2f}
"""
    except Exception as e:
        current_price_info = f"\n**价格数据获取异常:** {e}"
    
    # 构建分析部分 - 专注于原始三个agent的分析结果
    analysis_sections = []
    available_analyses = []
    
    if technical_analysis and technical_analysis != "无技术分析":
        analysis_sections.append(f"### 技术分析结果：\n{technical_analysis}")
        available_analyses.append("技术面")
    
    if fundamental_analysis:
        analysis_sections.append(f"### 基本面分析结果：\n{fundamental_analysis}")
        available_analyses.append("基本面")
    
    if news_sentiment:
        analysis_sections.append(f"### 新闻情感分析结果：\n{news_sentiment}")
        available_analyses.append("新闻情感")
    
    # 动态生成第一步的文本描述
    if len(available_analyses) == 3:
        step1_text = "先分析技术面、基本面、新闻情感的综合信号，判断在预测时间范围内股价的主导趋势："
    elif len(available_analyses) == 2:
        step1_text = f"先分析{available_analyses[0]}、{available_analyses[1]}的综合信号，判断在预测时间范围内股价的主导趋势："
    elif len(available_analyses) == 1:
        step1_text = f"基于{available_analyses[0]}分析信号，判断在预测时间范围内股价的主导趋势："
    else:
        step1_text = "基于可用的市场数据分析，判断在预测时间范围内股价的主导趋势："
    
    # 动态生成第三步的置信度评估文本
    if len(available_analyses) == 3:
        confidence_text = """- **HIGH**: 三个分析维度高度一致，技术信号强烈，概率>0.75
- **MEDIUM**: 大部分分析支持，有少量冲突信号，概率0.6-0.75
- **LOW**: 信号混合，市场不确定性较高，概率0.5-0.6"""
    elif len(available_analyses) == 2:
        confidence_text = f"""- **HIGH**: 两个分析维度高度一致，信号强烈，概率>0.75
- **MEDIUM**: 分析结果大致支持，有少量不确定性，概率0.6-0.75
- **LOW**: 信号冲突或不确定性较高，概率0.5-0.6"""
    elif len(available_analyses) == 1:
        confidence_text = f"""- **HIGH**: {available_analyses[0]}信号非常强烈且明确，概率>0.75
- **MEDIUM**: {available_analyses[0]}信号相对明确，但存在一定不确定性，概率0.6-0.75
- **LOW**: {available_analyses[0]}信号模糊或冲突，不确定性较高，概率0.5-0.6"""
    else:
        confidence_text = """- **HIGH**: 基础市场数据显示明确信号，概率>0.75
- **MEDIUM**: 市场数据显示相对明确的方向，概率0.6-0.75
- **LOW**: 市场数据信号不明确，不确定性较高，概率0.5-0.6"""
    
    prompt = f"""
你是一个专业的股票量化分析师，需要基于多维度分析结果为股票 {ticker} 生成结构化的概率预测。

**预测时间范围:** 从 {market_aware_date} 到 {target_date} 前{trading_days_count}个交易日

{current_price_info}

## 分析数据输入

{chr(10).join(analysis_sections)}

## 概率预测任务要求

请基于以上原始分析结果，生成一个结构化的股价概率预测：

### 第一步：确定预测方向
{step1_text}
- **UP**: 预期上涨趋势占优
- **DOWN**: 预期下跌趋势占优

### 第二步：计算具体概率值
{f'''**如果预测方向为UP（上涨）:**
在接下来{trading_days_count}个交易日内（到{target_date}前），股价从当前的${latest_close:.2f}上涨至少3%，达到或超过${upside_target:.2f}的概率是多少？请给出0.0-1.0的概率值。

**如果预测方向为DOWN（下跌）:**
在接下来{trading_days_count}个交易日内（到{target_date}前），股价从当前的${latest_close:.2f}下跌至少3%，跌至或低于${downside_target:.2f}的概率是多少？请给出0.0-1.0的概率值。''' if latest_close is not None else '''**价格数据不可用，请基于分析信号估算概率:**
- UP方向：股价在预测期内上涨至少3%的概率
- DOWN方向：股价在预测期内下跌至少3%的概率'''}

### 第三步：评估置信度
{confidence_text}

### 第四步：生成推理说明
详细解释概率预测的逻辑（严格控制在1000字符以内）：
1. 基于{'、'.join([f"{analysis}" for analysis in available_analyses])}分析的关键信号识别
2. 说明概率值计算的依据和各维度权重考量
3. 指出影响预测的主要支撑和风险因素
4. 解释为什么选择该概率值和置信度等级


## 输出格式要求
请严格按照以下JSON结构输出：
- **prediction_probability**: 浮点数，0.0-1.0，表示目标价位达成的概率
- **direction**: 字符串，"UP"或"DOWN"
- **confidence_level**: 字符串，"HIGH"、"MEDIUM"或"LOW"
- **reasoning**: 字符串，详细推理说明

## 重要提醒
- 概率值应基于历史统计规律和当前分析信号的强度
- 避免极端概率值（<0.1或>0.9），除非有极强的确定性信号
- 重点关注{trading_days_count}个交易日的短期波动特征
- 考虑当前市场环境和股票特性的影响
"""
    
    return prompt.strip()