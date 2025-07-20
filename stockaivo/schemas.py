"""
StockAIvo - Pydantic数据模型
定义API请求和响应的数据结构
"""

from datetime import datetime
from datetime import date as DateType
from decimal import Decimal
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class StockPriceBase(BaseModel):
    """股票价格数据基础模型"""
    open: Decimal = Field(..., description="开盘价", ge=0)
    high: Decimal = Field(..., description="最高价", ge=0)
    low: Decimal = Field(..., description="最低价", ge=0)
    close: Decimal = Field(..., description="收盘价", ge=0)
    volume: Optional[int] = Field(None, description="成交量", ge=0)

    # 新增交易指标字段
    turnover: Optional[int] = Field(None, description="交易额", ge=0)
    amplitude: Optional[Decimal] = Field(None, description="振幅(%)")
    price_change_percent: Optional[Decimal] = Field(None, description="涨跌幅(%)")
    price_change: Optional[Decimal] = Field(None, description="涨跌额")
    turnover_rate: Optional[Decimal] = Field(None, description="换手率(%)")

    class Config:
        from_attributes = True


class StockPriceDaily(StockPriceBase):
    """日线数据模型"""
    date: DateType = Field(..., description="日期")
    model_config = {"json_encoders": {DateType: lambda d: d.strftime('%Y-%m-%d')}}


class StockPriceWeekly(StockPriceBase):
    """周线数据模型"""
    date: DateType = Field(..., description="周开始日期")
    model_config = {"json_encoders": {DateType: lambda d: d.strftime('%Y-%m-%d')}}


class StockPriceHourly(StockPriceBase):
    """小时线数据模型"""
    timestamp: datetime = Field(..., description="时间戳")


class StockDataResponse(BaseModel):
    """股票数据响应模型"""
    ticker: str = Field(..., description="股票代码")
    period: str = Field(..., description="时间周期")
    data_count: int = Field(..., description="数据条数", ge=0)
    data: List[Union[StockPriceDaily, StockPriceWeekly, StockPriceHourly]] = Field(..., description="股票数据列表")
    timestamp: datetime = Field(..., description="响应时间戳")
    
    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """错误响应模型"""
    detail: str = Field(..., description="错误详情")
    timestamp: datetime = Field(..., description="错误发生时间")


class SearchResult(BaseModel):
    """搜索结果单项模型"""
    symbol: str = Field(..., description="股票代码", min_length=1, max_length=10)
    name: str = Field(..., description="英文公司名称", min_length=1, max_length=200)
    cname: Optional[str] = Field(None, description="中文公司名称", max_length=200)
    relevance_score: float = Field(..., description="相关性评分", ge=0.0, le=1.0)

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """搜索响应模型"""
    query: str = Field(..., description="搜索查询词", min_length=1, max_length=100)
    total_count: int = Field(..., description="总结果数量", ge=0)
    results: List[SearchResult] = Field(..., description="搜索结果列表")
    has_more: bool = Field(..., description="是否还有更多结果")
    timestamp: datetime = Field(..., description="响应时间戳")

    class Config:
        from_attributes = True


class StockNewsItem(BaseModel):
    """股票新闻单项模型"""
    ticker: str = Field(..., description="股票代码")
    title: str = Field(..., description="新闻标题")
    publish_time: datetime = Field(..., description="发布时间")
    content: Optional[str] = Field(None, description="新闻内容摘要")

    class Config:
        from_attributes = True


class StockNewsResponse(BaseModel):
    """股票新闻响应模型"""
    ticker: str = Field(..., description="股票代码")
    data_type: str = Field(default="news", description="数据类型")
    data_count: int = Field(..., description="新闻条数", ge=0)
    data: List[StockNewsItem] = Field(..., description="新闻数据列表")
    timestamp: datetime = Field(..., description="响应时间戳")
    message: Optional[str] = Field(None, description="响应消息")

    class Config:
        from_attributes = True