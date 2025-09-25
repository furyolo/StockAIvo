#!/usr/bin/env python3
"""
测试结构化预测Agent功能
"""

import pytest
from datetime import datetime
from stockaivo.ai.state import GraphState
from stockaivo.ai.agents import structured_prediction_agent, _build_structured_prediction_prompt

def test_structured_prediction_agent_import():
    """测试结构化预测Agent导入"""
    from stockaivo.ai.agents import structured_prediction_agent
    assert callable(structured_prediction_agent)

def test_build_structured_prediction_prompt():
    """测试结构化预测提示词构建"""
    # 创建模拟状态数据
    mock_state = GraphState()
    mock_state.update({
        "ticker": "AAPL",
        "analysis_results": {
            "technical_analyst": "技术分析显示上涨趋势，RSI=65，MACD金叉",
            "fundamental_analyst": "基本面良好，PE比率合理",
            "news_sentiment_analyst": "新闻情绪积极",
            "synthesis_analyst": "综合分析建议买入"
        },
        "market_data": {
            "daily": {
                "close": [150.0, 152.0, 155.0],
                "volume": [1000000, 1200000, 900000]
            }
        }
    })
    
    # 构建提示词
    prompt = _build_structured_prediction_prompt(mock_state)
    
    # 验证提示词内容
    assert "AAPL" in prompt
    assert "技术分析显示上涨趋势" in prompt
    assert "基本面良好" in prompt
    assert "新闻情绪积极" in prompt
    assert "综合分析建议买入" in prompt
    assert "prediction_probability" in prompt
    assert "direction" in prompt
    assert "confidence_level" in prompt
    assert "reasoning" in prompt
    assert "当前股价: $155.0" in prompt

def test_structured_prediction_agent_technical_analysis_missing():
    """测试技术分析缺失时的处理"""
    import asyncio
    
    async def run_test():
        # 创建没有技术分析的状态
        mock_state = GraphState()
        mock_state.update({
            "ticker": "AAPL",
            "analysis_results": {
                # 缺少technical_analyst
                "fundamental_analyst": "基本面良好",
            }
        })
        
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
        mock_state = GraphState()
        mock_state.update({
            "ticker": "AAPL",
            "analysis_results": {
                "technical_analyst": "Error: 获取数据失败",
                "fundamental_analyst": "基本面良好",
            }
        })
        
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
    empty_state = GraphState()
    prompt = _build_structured_prediction_prompt(empty_state)
    assert "UNKNOWN" in prompt
    assert "无技术分析数据" in prompt
    assert "无基本面分析数据" in prompt
    
    # 测试部分数据缺失
    partial_state = GraphState()
    partial_state.update({
        "ticker": "TSLA",
        "analysis_results": {
            "technical_analyst": "技术分析结果"
            # 其他分析结果缺失
        }
    })
    
    prompt = _build_structured_prediction_prompt(partial_state)
    assert "TSLA" in prompt
    assert "技术分析结果" in prompt
    assert "无基本面分析数据" in prompt
    assert "无新闻情感分析数据" in prompt

def test_market_data_parsing():
    """测试市场数据解析"""
    # 测试正常市场数据
    normal_state = GraphState()
    normal_state.update({
        "ticker": "MSFT",
        "market_data": {
            "daily": {
                "close": [300.0, 305.0, 310.0],
                "volume": [800000, 900000, 1000000]
            }
        }
    })
    
    prompt = _build_structured_prediction_prompt(normal_state)
    assert "当前股价: $310.0" in prompt
    assert "成交量: 1000000" in prompt
    
    # 测试异常市场数据
    bad_state = GraphState()
    bad_state.update({
        "ticker": "MSFT",
        "market_data": {
            "daily": {
                "close": [],  # 空数组
                "volume": []
            }
        }
    })
    
    prompt = _build_structured_prediction_prompt(bad_state)
    assert "当前股价: $未知" in prompt
    assert "成交量: 未知" in prompt

if __name__ == "__main__":
    pytest.main([__file__, "-v"])