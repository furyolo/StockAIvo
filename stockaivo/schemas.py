"""
StockAIvo - Pydantic数据模型
定义API请求和响应的数据结构
"""

from datetime import datetime
from datetime import date as Date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class StockPriceBase(BaseModel):
    """股票价格数据基础模型"""
    open: Decimal = Field(..., description="开盘价", ge=0)
    high: Decimal = Field(..., description="最高价", ge=0)
    low: Decimal = Field(..., description="最低价", ge=0)
    close: Decimal = Field(..., description="收盘价", ge=0)
    volume: Optional[int] = Field(None, description="成交量", ge=0)
    
    class Config:
        from_attributes = True


class StockPriceDaily(StockPriceBase):
    """日线数据模型"""
    date: Date = Field(..., description="日期")


class StockPriceWeekly(StockPriceBase):
    """周线数据模型"""
    date: Date = Field(..., description="周开始日期")


class StockPriceHourly(StockPriceBase):
    """小时线数据模型"""
    timestamp: datetime = Field(..., description="时间戳")


class StockDataResponse(BaseModel):
    """股票数据响应模型"""
    ticker: str = Field(..., description="股票代码")
    period: str = Field(..., description="时间周期")
    data_count: int = Field(..., description="数据条数", ge=0)
    data: List[dict] = Field(..., description="股票数据列表")
    timestamp: datetime = Field(..., description="响应时间戳")
    
    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """错误响应模型"""
    detail: str = Field(..., description="错误详情")
    timestamp: datetime = Field(..., description="错误发生时间")