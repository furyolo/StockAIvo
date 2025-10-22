#!/usr/bin/env python3
"""
测试结构化预测Agent功能
"""

import pytest
from typing import Any, cast
from stockaivo.ai.state import GraphState
from stockaivo.ai.agents import structured_prediction_agent, _build_structured_prediction_prompt

def create_graph_state(**overrides: Any) -> GraphState:
    """创建包含必需字段的图状态基础对象，便于在测试中覆盖不同分支。"""
    state: dict[str, Any] = {
        "ticker": "UNKNOWN",
        "custom_date_range": None,
        "raw_data": {},
        "analysis_results": {},
        "final_report": "",
        "market_analysis": None,
    }
    state.update(overrides)
    return cast(GraphState, state)

def test_structured_prediction_agent_import():
    """测试结构化预测Agent导入"""
    from stockaivo.ai.agents import structured_prediction_agent
    assert callable(structured_prediction_agent)

def test_build_structured_prediction_prompt():
    """测试结构化预测提示词构建"""
    # 创建模拟状态数据
    mock_state = create_graph_state(
        ticker="AAPL",
        analysis_results={
            "technical_analyst": "技术分析显示上涨趋势，RSI=65，MACD金叉",
            "fundamental_analyst": "基本面良好，PE比率合理",
            "news_sentiment_analyst": "新闻情绪积极",
        },
        raw_data={
            "daily_prices": {
                "columns": ["date", "close", "volume"],
                "index": ["2024-10-21", "2024-10-22", "2024-10-23"],
                "data": [
                    ["2024-10-21", 150.0, 1000000],
                    ["2024-10-22", 152.0, 1200000],
                    ["2024-10-23", 155.0, 900000],
                ],
            }
        },
        market_data={
            "daily": {
                "close": [150.0, 152.0, 155.0],
                "volume": [1000000, 1200000, 900000]
            }
        }
    )
    
    # 构建提示词
    prompt = _build_structured_prediction_prompt(mock_state)
    
    # 验证提示词内容
    assert "AAPL" in prompt
    assert "技术分析显示上涨趋势" in prompt
    assert "基本面良好" in prompt
    assert "新闻情绪积极" in prompt
    assert "先分析技术面、基本面、新闻情感的综合信号" in prompt
    assert "prediction_probability" in prompt
    assert "direction" in prompt
    assert "confidence_level" in prompt
    assert "reasoning" in prompt
    assert "当前收盘价: $155.00" in prompt
    assert "上涨目标价位（+3%）: $159.65" in prompt
    assert "下跌目标价位（-3%）: $150.35" in prompt

def test_structured_prediction_agent_technical_analysis_missing():
    """测试技术分析缺失时的处理"""
    import asyncio
    
    async def run_test():
        # 创建没有技术分析的状态
        mock_state = create_graph_state(
            ticker="AAPL",
            analysis_results={
                # 缺少technical_analyst
                "fundamental_analyst": "基本面良好",
            }
        )
        
        # 调用Agent
        result = await structured_prediction_agent(mock_state)
        
        # 验证错误处理
        assert "structured_prediction" in result
        assert "error" in result["structured_prediction"]
        assert "技术分析失败" in result["structured_prediction"]["error"]
        
    asyncio.run(run_test())

def test_structured_prediction_agent_technical_analysis_error():
    """测试技术分析有错误时的处理"""
    import asyncio
    
    async def run_test():
        # 创建技术分析有错误的状态
        mock_state = create_graph_state(
            ticker="AAPL",
            analysis_results={
                "technical_analyst": "Error: 获取数据失败",
                "fundamental_analyst": "基本面良好",
            }
        )
        
        # 调用Agent
        result = await structured_prediction_agent(mock_state)
        
        # 验证错误处理
        assert "structured_prediction" in result
        assert "error" in result["structured_prediction"]
        assert "技术分析失败" in result["structured_prediction"]["error"]
        
    asyncio.run(run_test())

def test_prompt_edge_cases():
    """测试提示词构建的边缘情况"""
    # 测试空状态
    empty_state = create_graph_state()
    prompt = _build_structured_prediction_prompt(empty_state)
    assert "UNKNOWN" in prompt
    assert "价格数据不可用" in prompt
    assert "基于可用的市场数据分析" in prompt
    
    # 测试部分数据缺失
    partial_state = create_graph_state(
        ticker="TSLA",
        analysis_results={
            "technical_analyst": "技术分析结果"
            # 其他分析结果缺失
        }
    )
    
    prompt = _build_structured_prediction_prompt(partial_state)
    assert "TSLA" in prompt
    assert "技术分析结果" in prompt
    assert "基于技术面分析信号" in prompt

def test_market_data_parsing():
    """测试市场数据解析"""
    # 测试正常市场数据
    normal_state = create_graph_state(
        ticker="MSFT",
        raw_data={
            "daily_prices": {
                "columns": ["date", "close", "volume"],
                "index": ["2024-10-21", "2024-10-22", "2024-10-23"],
                "data": [
                    ["2024-10-21", 300.0, 800000],
                    ["2024-10-22", 305.0, 900000],
                    ["2024-10-23", 310.0, 1000000],
                ],
            }
        }
    )
    
    prompt = _build_structured_prediction_prompt(normal_state)
    assert "当前收盘价: $310.00" in prompt
    assert "上涨目标价位（+3%）: $319.30" in prompt
    assert "下跌目标价位（-3%）: $300.70" in prompt
    
    # 测试异常市场数据
    bad_state = create_graph_state(
        ticker="MSFT",
        raw_data={
            "daily_prices": {
                "columns": ["date", "close", "volume"],
                "index": [],
                "data": [],  # 空数组
            }
        }
    )
    
    prompt = _build_structured_prediction_prompt(bad_state)
    assert "价格数据不可用" in prompt

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
