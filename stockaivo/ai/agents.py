"""
AI Agent Definitions for StockAIvo

This file defines the individual agent nodes for the LangGraph workflow.
Each function represents an agent and will be a node in the graph.
"""

import asyncio
import pandas as pd
import pandas_market_calendars as mcal
from typing import Dict, Any, Optional, AsyncGenerator, NamedTuple
from datetime import date, timedelta, datetime
from functools import lru_cache
from stockaivo.data_service import get_stock_data, get_stock_news, PeriodType, get_market_aware_current_date, get_market_aware_minute_date
from stockaivo.cache_manager import _is_market_open
from stockaivo.database import get_db
from stockaivo.ai.state import GraphState
from stockaivo.ai.llm_service import llm_service
from stockaivo.ai.tools import llm_tool
from stockaivo.ai.technical_indicator import TechnicalIndicator

# ==================== 重构：统一市场分析接口 ====================

class MarketAnalysisResult(NamedTuple):
    """市场分析结果的数据结构"""
    market_aware_date: date
    target_friday: str              # 保持字符串格式（向后兼容）
    target_friday_date: date        # 新增：date格式（避免转换）
    trading_days_count: int
    calendar_days: int              # 新增：日历天数

# ==================== 缓存层 ====================

@lru_cache(maxsize=32)
def _get_nyse_calendar():
    """缓存的NYSE日历获取"""
    return mcal.get_calendar('NYSE')

@lru_cache(maxsize=128)
def _get_trading_schedule(start_date: date, end_date: date):
    """缓存的交易时间表获取"""
    calendar = _get_nyse_calendar()
    return calendar.schedule(start_date=start_date, end_date=end_date)

@lru_cache(maxsize=64)
def _get_trading_days_set(start_date: date, end_date: date) -> set[date]:
    """缓存的交易日集合"""
    schedule = _get_trading_schedule(start_date, end_date)
    return {d.date() for d in schedule.index} if not schedule.empty else set()

def _calculate_date_range(period: PeriodType, date_range_option: Optional[str], custom_date_range: Optional[dict], market_aware_date: Optional[date] = None) -> tuple[Optional[str], Optional[str]]:
    """
    根据用户的选择和数据周期计算最终的开始和结束日期。

    Args:
        period: 数据周期类型
        date_range_option: 日期范围选项
        custom_date_range: 自定义日期范围
        market_aware_date: 可选的市场感知日期，如果不提供则内部调用获取
    """
    # 1. 优先使用自定义日期范围
    if custom_date_range and custom_date_range.get('start_date') and custom_date_range.get('end_date'):
        return custom_date_range['start_date'], custom_date_range['end_date']

    # 2. 处理预设选项
    if market_aware_date is None:
        # 根据数据周期选择合适的市场感知日期函数
        if period in ["10min", "minute"]:
            # 分钟线和10分钟线数据使用专门的市场感知日期函数
            market_aware_date = get_market_aware_minute_date()
        else:
            # 日线和周线数据使用通用的市场感知日期函数
            market_aware_date = get_market_aware_current_date()
    today = market_aware_date
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
        return start_date.isoformat(), today.isoformat()

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

    # 注意：不再在这里统一获取市场感知日期，而是让每个周期根据自己的需要选择合适的市场感知日期函数

    collected_data = {}
    db_session_gen = get_db()
    db = next(db_session_gen)

    try:
        # 为AI Agent添加新闻数据获取功能
        periods_to_fetch: list[PeriodType] = ["daily", "weekly"]

        # 智能判断是否获取10分钟线数据
        # 只有在交易时间内才获取10分钟线数据
        is_trading_time = _is_market_open()

        if is_trading_time:
            periods_to_fetch.append("10min")
            print(f"  - Market analysis: Including 10min data (market is open)")
        else:
            print(f"  - Market analysis: Skipping 10min data (market is closed)")

        # 1. 获取股票价格数据
        price_tasks = []
        for period in periods_to_fetch:
            # 为每个周期单独计算日期范围，让函数根据周期类型自动选择合适的市场感知日期
            start_date, end_date = _calculate_date_range(period, date_range_option, custom_date_range, None)
            print(f"  - For {period} data, calculated range: {start_date or 'default start'} to {end_date or 'default end'}")

            task = get_stock_data(
                db=db,
                ticker=ticker,
                period=period,
                start_date=start_date,
                end_date=end_date,
                background_tasks=None, # No background tasks needed for agent context
                market_aware_date=None  # 让get_stock_data函数根据周期自动选择合适的市场感知日期
            )
            price_tasks.append(task)

        # 2. 获取新闻数据
        print(f"  - Fetching news data for {ticker}")
        news_task = get_stock_news(
            ticker=ticker,
            background_tasks=None  # No background tasks needed for agent context
        )

        # 3. 并行执行所有数据获取任务
        all_tasks = price_tasks + [news_task]
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # 4. 处理价格数据结果
        price_results = results[:len(periods_to_fetch)]
        for period, result in zip(periods_to_fetch, price_results):
            if isinstance(result, Exception):
                print(f"Error collecting {period} data for {ticker}: {result}")
            elif isinstance(result, pd.DataFrame) and not result.empty:
                # 特殊处理10分钟线数据的键名
                if period == "10min":
                    collected_data['tenmin_prices'] = result.to_dict(orient='split')
                else:
                    collected_data[f'{period}_prices'] = result.to_dict(orient='split')
                print(f"Successfully collected {period} data for {ticker}.")
            else:
                print(f"Could not find {period} data for {ticker}.")

        # 5. 处理新闻数据结果
        news_result = results[-1]
        if isinstance(news_result, Exception):
            print(f"Error collecting news data for {ticker}: {news_result}")
        elif isinstance(news_result, pd.DataFrame) and not news_result.empty:
            collected_data['news'] = news_result.to_dict(orient='records')
            print(f"Successfully collected news data for {ticker}: {len(news_result)} articles.")
        else:
            print(f"Could not find news data for {ticker}.")

    finally:
        db.close()


    # 生成数据收集摘要
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
        "analysis_results": {"data_collector": data_summary}
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

        # 判断市场交易状态
        is_market_open = False

        # 🔧 FIX: 检查是否是历史日期
        current_date_et = now_et.date()
        is_historical_date = today.date() < current_date_et

        if is_historical_date:
            # 对于历史日期，假设交易已经结束
            is_market_open = False
        else:
            # 只有当日或未来日期才需要检查实时市场状态
            try:
                schedule = _get_trading_schedule(today.date(), today.date())
                if not schedule.empty:
                    is_market_open = nyse_calendar.open_at_time(schedule, now_et)
            except:
                # 简单时间判断回退
                market_hour = now_et.hour
                market_minute = now_et.minute
                is_market_open = (market_hour > 9 or (market_hour == 9 and market_minute >= 30)) and market_hour < 16

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
    """内部函数：找到指定周的最后一个交易日"""
    # 从周五开始往前找
    for i in range(5):  # 周五到周一
        check_date = week_start + timedelta(days=4-i)
        if check_date in trading_days_set:
            return check_date

    # 如果本周没有交易日，返回周五
    return week_start + timedelta(days=4)

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

def _get_target_friday_date(market_aware_date: Optional[date] = None) -> str:
    """
    计算周度最后一个交易日（向后兼容接口）

    规则：
    - 如果本周市场交易还未结束，返回本周最后一个交易日
    - 如果本周市场交易已经结束，返回下周最后一个交易日
    - 基于市场感知的基准日期和NYSE交易日历
    - 处理节假日情况，确保返回的是真实的交易日

    Args:
        market_aware_date: 可选的市场感知日期，如果不提供则内部调用获取

    Returns:
        格式化的日期字符串 (YYYY-MM-DD)

    Note:
        这是向后兼容接口，内部调用优化后的实现。
        推荐使用 get_market_analysis() 获取完整的市场分析结果。
    """
    # 使用新的统一接口，保持向后兼容
    result = get_market_analysis(market_aware_date)
    return result.target_friday


# 注意：旧的辅助函数已被内部优化函数替代
# _get_fallback_target_date 和 _find_last_trading_day_of_week
# 现在由 _get_fallback_target_friday_internal 和 _find_last_trading_day_of_week_internal 替代


def _calculate_trading_days_to_target(target_date_str: str, market_aware_date: Optional[date] = None) -> int:
    """
    计算从市场感知基准日期到目标日期的交易日总数（向后兼容接口）

    Args:
        target_date_str: 目标日期字符串 (YYYY-MM-DD)
        market_aware_date: 可选的市场感知日期，如果不提供则内部调用获取

    Returns:
        int: 交易日数量

    Note:
        这是向后兼容接口，内部调用优化后的实现。
        推荐使用 get_market_analysis() 获取完整的市场分析结果。
    """
    # 优化：如果可能，直接使用统一接口避免重复计算
    if market_aware_date is not None:
        result = get_market_analysis(market_aware_date)
        if result.target_friday == target_date_str:
            return result.trading_days_count

    # 回退到单独计算
    try:
        if market_aware_date is None:
            market_aware_date = get_market_aware_current_date()
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        return _calculate_trading_days_internal(market_aware_date, target_date)
    except Exception:
        # 最终回退
        return 1

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
        tenmin_indicators_desc = "- 10分钟线数据专注于短期价格波动观察，不计算技术指标以避免噪音信号"

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
        analysis_requirements.append("5.  **10分钟线短期波动分析:** 基于10分钟线数据，识别短期价格波动模式、关键支撑阻力位，以及精确的入场时机。注意：10分钟线主要用于观察短期波动，不依赖技术指标。")

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
    import logging
    logger = logging.getLogger(__name__)

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
    # 新闻情感分析prompt
    base_prompt = f"""
    作为一名专业的市场情绪分析师，请为股票 {ticker} 提供基于时间演变的新闻情感分析。

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
    print("\n---Executing Technical Analysis Agent---")

    # 获取市场感知日期（优化：只调用一次）
    market_aware_date = get_market_aware_current_date()

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators, market_aware_date)
    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": prompt, "agent_name": "technical_analysis_agent"}})

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
    has_news_data, ticker, news_data = _check_news_data_and_get_ticker(state)

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        return {"analysis_results": {"news_sentiment_analyst": None}}

    # 使用共用函数构建prompt，传入实际新闻数据
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker, news_data)

    analysis_result = await llm_tool.ainvoke({"input_dict": {"prompt": sentiment_prompt}})
    return {"analysis_results": {"news_sentiment_analyst": analysis_result}}


async def synthesis_agent(state: GraphState) -> Dict[str, Any]:
    """
    决策合成 Agent
    - 整合所有分析师的见解以形成最终的投资报告.
    """
    print("\n---Executing Synthesis Agent---")

    # 获取市场感知日期（优化：只调用一次）
    market_aware_date = get_market_aware_current_date()

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
    print("\n---Executing Technical Analysis Agent (Stream)---")

    # 获取市场感知日期（优化：只调用一次）
    market_aware_date = get_market_aware_current_date()

    # 使用共用函数处理数据
    ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    prompt = _build_technical_analysis_prompt(ticker, daily_price_str, weekly_price_str, tenmin_price_str, daily_indicators, weekly_indicators, tenmin_indicators, market_aware_date)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(prompt, "technical_analysis_agent"):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"technical_analyst": accumulated_result}}


async def synthesis_agent_stream(state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
    """
    决策合成 Agent - 流式版本
    """
    print("\n---Executing Synthesis Agent (Stream)---")

    # 获取市场感知日期（优化：只调用一次）
    market_aware_date = get_market_aware_current_date()

    ticker = state.get("ticker", "UNKNOWN_TICKER")

    # 使用共享的分析结果提取函数
    data_collector_result, technical_result, fundamental_result, news_result, available_analyses = _extract_analysis_results(state)

    # 使用共享的prompt构建函数，传递market_aware_date
    synthesis_prompt = _build_synthesis_prompt(ticker, data_collector_result, technical_result,
                                             fundamental_result, news_result, available_analyses, market_aware_date)

    # 流式生成综合分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(synthesis_prompt, "synthesis_agent"):
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
    has_news_data, ticker, news_data = _check_news_data_and_get_ticker(state)

    if not has_news_data:
        print("缺少新闻情感数据，跳过新闻情感分析")
        yield {"analysis_results": {"news_sentiment_analyst": None}}
        return

    # 使用共用函数构建prompt，传入实际新闻数据
    sentiment_prompt = _build_news_sentiment_analysis_prompt(ticker, news_data)

    # 流式生成分析结果
    accumulated_result = ""
    async for chunk in llm_service.invoke_stream(sentiment_prompt):
        accumulated_result += chunk
        # 实时返回累积的结果
        yield {"analysis_results": {"news_sentiment_analyst": accumulated_result}}