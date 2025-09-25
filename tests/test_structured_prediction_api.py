#!/usr/bin/env python3
"""
测试结构化预测API端点
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date

def test_structured_prediction_request_model():
    """测试结构化预测请求模型"""
    from stockaivo.routers.ai import StructuredPredictionRequest
    
    # 测试基本请求
    request = StructuredPredictionRequest(ticker="AAPL")
    assert request.ticker == "AAPL"
    assert request.end_date is None
    assert request.save_to_db is True
    
    # 测试带日期的请求
    test_date = date(2024, 12, 31)
    request_with_date = StructuredPredictionRequest(
        ticker="TSLA", 
        end_date=test_date, 
        save_to_db=False
    )
    assert request_with_date.ticker == "TSLA"
    assert request_with_date.end_date == test_date
    assert request_with_date.save_to_db is False

def test_structured_prediction_response_model():
    """测试结构化预测响应模型"""
    from stockaivo.routers.ai import StructuredPredictionResponse
    from datetime import datetime
    
    # 测试成功响应
    success_response = StructuredPredictionResponse(
        success=True,
        prediction_probability=0.75,
        direction="UP",
        confidence_level="HIGH",
        reasoning="基于技术分析，股票呈现上涨趋势",
        ticker="AAPL",
        timestamp=datetime.now().isoformat(),
        market_aware_date="2024-12-31"
    )
    
    assert success_response.success is True
    assert success_response.prediction_probability == 0.75
    assert success_response.direction == "UP"
    assert success_response.confidence_level == "HIGH"
    assert success_response.ticker == "AAPL"
    assert success_response.error is None
    
    # 测试失败响应
    error_response = StructuredPredictionResponse(
        success=False,
        ticker="NVDA",
        timestamp=datetime.now().isoformat(),
        error="技术分析失败"
    )
    
    assert error_response.success is False
    assert error_response.ticker == "NVDA"
    assert error_response.error == "技术分析失败"
    assert error_response.prediction_probability is None

def test_nested_structured_prediction_request():
    """测试嵌套结构化预测请求模型"""
    from stockaivo.routers.ai import NestedStructuredPredictionRequest, StructuredPredictionRequest
    
    inner_request = StructuredPredictionRequest(ticker="GOOGL")
    nested_request = NestedStructuredPredictionRequest(
        summary="预测GOOGL股价",
        value=inner_request
    )
    
    assert nested_request.summary == "预测GOOGL股价"
    assert nested_request.value.ticker == "GOOGL"
    assert nested_request.value.save_to_db is True

def test_api_endpoint_import():
    """测试API端点函数导入"""
    from stockaivo.routers.ai import analyze_stock_structured_prediction
    assert callable(analyze_stock_structured_prediction)

def test_api_models_validation():
    """测试API模型的字段验证"""
    from stockaivo.routers.ai import StructuredPredictionRequest
    import pytest
    
    # 测试必需字段验证
    with pytest.raises(ValueError):
        StructuredPredictionRequest()  # 缺少ticker
    
    # 测试ticker字段
    request = StructuredPredictionRequest(ticker="")
    assert request.ticker == ""  # 空字符串也是有效的，业务逻辑会处理
    
    # 测试日期字段
    from datetime import date
    request = StructuredPredictionRequest(ticker="AAPL", end_date=date(2024, 1, 1))
    assert request.end_date == date(2024, 1, 1)

def test_response_model_optional_fields():
    """测试响应模型可选字段"""
    from stockaivo.routers.ai import StructuredPredictionResponse
    from datetime import datetime
    
    # 最小响应（只有必需字段）
    minimal_response = StructuredPredictionResponse(
        success=False,
        ticker="AAPL",
        timestamp=datetime.now().isoformat()
    )
    
    assert minimal_response.success is False
    assert minimal_response.ticker == "AAPL"
    assert minimal_response.prediction_probability is None
    assert minimal_response.direction is None
    assert minimal_response.confidence_level is None
    assert minimal_response.reasoning is None
    assert minimal_response.market_aware_date is None
    assert minimal_response.error is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])