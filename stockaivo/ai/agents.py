"""
AI Agent Definitions for StockAIvo

This file defines the individual agent nodes for the LangGraph workflow.
Each function represents an agent and will be a node in the graph.
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import date, timedelta
from stockaivo.data_service import get_stock_data, PeriodType
from stockaivo.database import get_db
from stockaivo.ai.state import GraphState

def _calculate_date_range(period: PeriodType, date_range_option: Optional[str], custom_date_range: Optional[dict]) -> tuple[Optional[str], Optional[str]]:
    """
    根据用户的选择和数据周期计算最终的开始和结束日期。
    """
    # 1. 优先使用自定义日期范围
    if custom_date_range and custom_date_range.get('start_date') and custom_date_range.get('end_date'):
        return custom_date_range['start_date'], custom_date_range['end_date']

    # 2. 如果没有提供任何选项，则应用新的默认逻辑
    if not date_range_option:
        today = date.today()
        yesterday = today - timedelta(days=1)
        if period == 'daily':
            start_date = today - timedelta(days=30)
            return start_date.isoformat(), yesterday.isoformat()
        elif period == 'weekly':
            start_date = today - timedelta(days=180)
            return start_date.isoformat(), yesterday.isoformat()
        return None, None # 其他周期默认全历史

    # 3. 处理预设选项
    if date_range_option == 'full_history':
        return None, None

    today = date.today()
    yesterday = today - timedelta(days=1)
    start_date = None

    if date_range_option == 'past_30_days':
        start_date = today - timedelta(days=30)
    elif date_range_option == 'past_60_days':
        start_date = today - timedelta(days=60)
    elif date_range_option == 'past_8_weeks':
        start_date = today - timedelta(weeks=8)
    elif date_range_option == 'past_16_weeks':
        start_date = today - timedelta(weeks=16)
    elif date_range_option == 'past_24_weeks':
        start_date = today - timedelta(weeks=24)
    
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
            print(f"  - For {period} data, calculated range: {start_date or 'history start'} to {end_date or 'today'}")
            
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

        
    return {"raw_data": collected_data}


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


def fundamental_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    基本面分析 Agent
    - 检查财务报表、行业趋势和经济状况.
    """
    print("\n---Executing Fundamental Analysis Agent---")
    # 实际应用中会基于 state['financials'] 进行分析
    return {"analysis_results": {"fundamental_analyst": "Fundamental analysis summary."}}


def news_sentiment_analysis_agent(state: GraphState) -> Dict[str, Any]:
    """
    新闻舆情分析 Agent
    - 分析新闻文章和社交媒体以评估市场情绪.
    """
    print("\n---Executing News Sentiment Analysis Agent---")
    # 实际应用中会基于 state['news'] 进行分析
    return {"analysis_results": {"news_sentiment_analyst": "News sentiment analysis summary."}}


def synthesis_agent(state: GraphState) -> Dict[str, Any]:
    """
    决策合成 Agent
    - 整合所有分析师的见解以形成最终的投资报告.
    """
    print("\n---Executing Synthesis Agent---")
    
    final_report = "Final Investment Report:\n\n"
    analysis_results = state.get("analysis_results", {})
    for agent, result in analysis_results.items():
        final_report += f"- {agent}: {result}\n"
    
    return {"final_report": final_report}