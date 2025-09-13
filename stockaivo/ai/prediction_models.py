"""
股票预测结构化输出模型
定义用于AI分析结构化预测的Pydantic模型，兼容Google GenAI SDK和OpenAI API
"""

from typing import Literal
from pydantic import BaseModel, Field
from datetime import date


class StockPredictionResult(BaseModel):
    """
    股票预测结果的结构化输出模型
    
    用于AI生成结构化的股票涨跌概率预测，确保输出格式的一致性和准确性。
    
    概率值含义：
    - 上涨概率：P(high >= close * 1.03) 在指定交易日内
    - 下跌概率：P(low <= close * 0.97) 在指定交易日内
    """
    
    prediction_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="预测概率值，范围0.0-1.0。若direction为UP，表示股价上涨超过3%的概率；若direction为DOWN，表示股价下跌超过3%的概率"
    )
    
    direction: Literal["UP", "DOWN"] = Field(
        ...,
        description="预测方向。UP表示预测上涨，DOWN表示预测下跌。基于技术分析和市场综合判断确定"
    )
    
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        ...,
        description="预测置信度。HIGH表示高置信度(>80%)，MEDIUM表示中等置信度(50%-80%)，LOW表示低置信度(<50%)"
    )
    
    reasoning: str = Field(
        ...,
        max_length=1000,
        description="预测推理说明，简要解释预测的主要依据，包括技术指标、市场趋势、基本面因素等关键分析要点"
    )

    class Config:
        """Pydantic配置"""
        # 生成JSON Schema时包含字段描述
        json_schema_extra = {
            "example": {
                "prediction_probability": 0.7500,
                "direction": "UP",
                "confidence_level": "HIGH",
                "reasoning": "基于RSI超卖信号、MACD金叉形态和成交量放大，预测短期内股价有较大概率上涨超过3%"
            }
        }


class StockPredictionContext(BaseModel):
    """
    股票预测上下文信息模型
    
    包含预测过程中的时间和股票上下文信息，用于Agent内部处理
    """
    
    ticker: str = Field(..., description="股票代码")
    market_aware_date: date = Field(..., description="市场感知日期（分析基准日期）")
    target_date: date = Field(..., description="预测目标日期")
    trading_days_count: int = Field(..., description="预测时间范围内的交易日数量")
    current_close_price: float = Field(..., description="分析基准日的收盘价")
    
    class Config:
        """Pydantic配置"""
        json_schema_extra = {
            "example": {
                "ticker": "AAPL",
                "market_aware_date": "2024-12-15",
                "target_date": "2024-12-20",
                "trading_days_count": 5,
                "current_close_price": 150.25
            }
        }