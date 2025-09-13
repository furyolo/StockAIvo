#!/usr/bin/env python3
"""
测试LLM结构化输出功能
"""

import pytest
import json
from typing import Literal
from pydantic import BaseModel, Field

class MockStockPredictionResult(BaseModel):
    """测试用的预测结果模型"""
    prediction_probability: float = Field(
        ..., ge=0.0, le=1.0,
        description="预测概率值，范围0.0-1.0"
    )
    direction: Literal["UP", "DOWN"] = Field(
        ..., description="预测方向"
    )
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        ..., description="置信度"
    )
    reasoning: str = Field(
        ..., max_length=1000,
        description="预测推理说明"
    )

def test_schema_converter_import():
    """测试schema转换工具导入"""
    from stockaivo.ai.schema_converter import pydantic_to_openai_schema
    
    # 测试转换功能
    openai_schema = pydantic_to_openai_schema(MockStockPredictionResult)
    
    assert "json_schema" in openai_schema
    assert "schema" in openai_schema["json_schema"]
    assert openai_schema["json_schema"]["name"] == "MockStockPredictionResult"
    assert openai_schema["json_schema"]["strict"] is True

def test_llm_service_structured_methods():
    """测试LLM服务结构化输出方法存在性"""
    # 直接导入类定义而不初始化实例
    from stockaivo.ai.llm_service import LLMService
    
    # 检查结构化输出方法是否存在
    assert hasattr(LLMService, 'invoke_structured'), "invoke_structured方法不存在"
    assert hasattr(LLMService, '_invoke_openai_structured'), "_invoke_openai_structured方法不存在"
    assert hasattr(LLMService, '_invoke_gemini_structured'), "_invoke_gemini_structured方法不存在"

def test_structured_response_parsing():
    """测试结构化响应解析"""
    # 模拟一个结构化响应
    mock_response_json = {
        "prediction_probability": 0.75,
        "direction": "UP",
        "confidence_level": "HIGH",
        "reasoning": "基于技术指标分析，股票呈现上涨趋势。"
    }
    
    # 测试解析
    parsed_response = MockStockPredictionResult(**mock_response_json)
    
    assert parsed_response.prediction_probability == 0.75
    assert parsed_response.direction == "UP"
    assert parsed_response.confidence_level == "HIGH"
    assert "技术指标" in parsed_response.reasoning

def test_structured_response_validation():
    """测试结构化响应验证"""
    # 测试无效概率值
    with pytest.raises(ValueError):
        MockStockPredictionResult(
            prediction_probability=1.5,  # 超出范围
            direction="UP",
            confidence_level="HIGH",
            reasoning="测试推理"
        )
    
    # 测试无效方向
    with pytest.raises(ValueError):
        MockStockPredictionResult(
            prediction_probability=0.5,
            direction="SIDEWAYS",  # 不在枚举中
            confidence_level="HIGH",
            reasoning="测试推理"
        )
    
    # 测试无效置信度
    with pytest.raises(ValueError):
        MockStockPredictionResult(
            prediction_probability=0.5,
            direction="UP",
            confidence_level="VERY_HIGH",  # 不在枚举中
            reasoning="测试推理"
        )

def test_schema_conversion_completeness():
    """测试schema转换的完整性"""
    from stockaivo.ai.schema_converter import pydantic_to_openai_schema
    
    openai_schema = pydantic_to_openai_schema(MockStockPredictionResult)
    schema = openai_schema["json_schema"]["schema"]
    
    # 检查所有必需字段都存在
    required_fields = {"prediction_probability", "direction", "confidence_level", "reasoning"}
    assert set(schema["required"]) == required_fields
    
    # 检查字段类型和约束
    properties = schema["properties"]
    
    # 概率字段
    prob_field = properties["prediction_probability"]
    assert prob_field["type"] == "number"
    assert prob_field["minimum"] == 0.0
    assert prob_field["maximum"] == 1.0
    
    # 方向字段（枚举）
    direction_field = properties["direction"]
    assert direction_field["type"] == "string"
    assert set(direction_field["enum"]) == {"UP", "DOWN"}
    
    # 置信度字段（枚举）
    confidence_field = properties["confidence_level"]
    assert confidence_field["type"] == "string"
    assert set(confidence_field["enum"]) == {"HIGH", "MEDIUM", "LOW"}
    
    # 推理字段
    reasoning_field = properties["reasoning"]
    assert reasoning_field["type"] == "string"
    assert reasoning_field["maxLength"] == 1000

if __name__ == "__main__":
    pytest.main([__file__, "-v"])