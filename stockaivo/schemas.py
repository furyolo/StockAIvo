"""
StockAIvo - Pydantic数据模型
定义API请求和响应的数据结构
"""

from datetime import datetime
from datetime import date as DateType
from decimal import Decimal
from typing import List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


class StockPriceDaily(StockPriceBase):
    """日线数据模型"""
    date: DateType = Field(..., description="日期")


class StockPriceWeekly(StockPriceBase):
    """周线数据模型"""
    date: DateType = Field(..., description="周开始日期")


class StockPrice10Min(StockPriceBase):
    """10分钟线数据模型"""
    timestamp_10min: datetime = Field(..., description="10分钟时间戳")


class StockPriceMinute(StockPriceBase):
    """分钟线数据模型"""
    minute_timestamp: datetime = Field(..., description="分钟时间戳")
    latest_price: Optional[Decimal] = Field(None, description="最新价格", ge=0)


class StockDataResponse(BaseModel):
    """股票数据响应模型"""
    ticker: str = Field(..., description="股票代码")
    period: str = Field(..., description="时间周期")
    data_count: int = Field(..., description="数据条数", ge=0)
    data: List[Union[StockPriceDaily, StockPriceWeekly, StockPrice10Min, StockPriceMinute]] = Field(..., description="股票数据列表")
    timestamp: datetime = Field(..., description="响应时间戳")

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """搜索响应模型"""
    query: str = Field(..., description="搜索查询词", min_length=1, max_length=100)
    total_count: int = Field(..., description="总结果数量", ge=0)
    results: List[SearchResult] = Field(..., description="搜索结果列表")
    has_more: bool = Field(..., description="是否还有更多结果")
    timestamp: datetime = Field(..., description="响应时间戳")

    model_config = ConfigDict(from_attributes=True)


class StockNewsItem(BaseModel):
    """股票新闻单项模型"""
    keyword: str = Field(..., description="搜索关键词")
    title: str = Field(..., description="新闻标题")
    publish_time: datetime = Field(..., description="发布时间（美国东部时间）")
    content: Optional[str] = Field(None, description="新闻内容摘要")

    model_config = ConfigDict(from_attributes=True)


class StockNewsResponse(BaseModel):
    """股票新闻响应模型"""
    keyword: str = Field(..., description="搜索关键词")
    data_type: str = Field(default="news", description="数据类型")
    data_count: int = Field(..., description="新闻条数", ge=0)
    data: List[StockNewsItem] = Field(..., description="新闻数据列表")
    timestamp: datetime = Field(..., description="响应时间戳")
    message: Optional[str] = Field(None, description="响应消息")

    model_config = ConfigDict(from_attributes=True)


class StructuredPredictionBatchRequest(BaseModel):
    """批量结构化预测请求模型"""
    tickers: List[str] = Field(
        ...,
        min_length=1,
        description="待预测的股票代码列表，至少包含1个元素",
    )
    end_date: Optional[DateType] = Field(
        None,
        description="可选的统一结束日期 (YYYY-MM-DD)，为空时按系统日期自动推算",
    )
    save_to_db: bool = Field(True, description="是否将每只股票的预测结果保存到数据库")
    max_concurrency: int = Field(
        3,
        ge=1,
        le=10,
        description="处理并发度上限，建议范围 1-5，用于控制 AI/数据源请求并发",
    )
    max_retries: int = Field(
        0,
        ge=0,
        le=5,
        description="单只股票失败后的最大重试次数（不含首次尝试）",
    )
    retry_delay_seconds: float = Field(
        5.0,
        ge=0.0,
        le=120.0,
        description="重试前的等待时间（秒），用于指数退避基础值",
    )


class StructuredPredictionRequest(BaseModel):
    """结构化预测请求模型"""
    ticker: str = Field(..., description="股票代码，例如 'AAPL'")
    end_date: Optional[DateType] = Field(
        None,
        description="自定义结束日期 (YYYY-MM-DD)，开始日期由系统自动推算",
    )
    save_to_db: bool = Field(True, description="是否将预测结果保存到数据库")


class StructuredPredictionResponse(BaseModel):
    """结构化预测响应模型"""
    success: bool = Field(..., description="预测是否成功")
    prediction_probability: Optional[float] = Field(
        None,
        description="预测概率值，范围 0.0-1.0",
        ge=0.0,
        le=1.0,
    )
    direction: Optional[str] = Field(None, description="预测方向：UP 或 DOWN")
    confidence_level: Optional[str] = Field(
        None,
        description="预测置信度：HIGH、MEDIUM 或 LOW",
    )
    reasoning: Optional[str] = Field(None, description="预测推理说明")
    ticker: str = Field(..., description="股票代码")
    timestamp: str = Field(..., description="预测生成时间（ISO8601）")
    market_aware_date: Optional[str] = Field(
        None,
        description="市场感知日期（ISO8601）",
    )
    error: Optional[str] = Field(None, description="错误信息（若失败）")


class NestedStructuredPredictionRequest(BaseModel):
    """嵌套结构化预测请求模型（兼容表单/前端配置）"""
    summary: str = Field(..., description="请求摘要说明")
    value: StructuredPredictionRequest = Field(
        ...,
        description="结构化预测请求明细",
    )


class StructuredPredictionBatchItem(BaseModel):
    """批量结构化预测结果单项"""
    ticker: str = Field(..., description="股票代码")
    success: bool = Field(..., description="该股票预测是否成功")
    latency_seconds: float = Field(
        ...,
        ge=0.0,
        description="完成预测耗时（秒，包括重试等待）",
    )
    retries: int = Field(..., ge=0, description="实际重试次数")
    response: Optional[StructuredPredictionResponse] = Field(
        None,
        description="成功时的结构化预测结果载荷",
    )
    error: Optional[str] = Field(
        None,
        description="失败原因说明，成功时为空",
    )


class StructuredPredictionBatchSummary(BaseModel):
    """批量结构化预测汇总信息"""
    total: int = Field(..., ge=0, description="请求处理的股票总数")
    success: int = Field(..., ge=0, description="成功的股票数量")
    failed: int = Field(..., ge=0, description="失败的股票数量")
    duration_seconds: float = Field(
        ...,
        ge=0.0,
        description="批量处理总耗时（秒）",
    )


class StructuredPredictionBatchResponse(BaseModel):
    """批量结构化预测响应模型"""
    results: List[StructuredPredictionBatchItem] = Field(
        ...,
        description="每只股票的结构化预测结果明细",
    )
    summary: StructuredPredictionBatchSummary = Field(
        ...,
        description="批量任务的整体汇总信息",
    )
    failed_tickers: List[str] = Field(
        ...,
        description="预测失败的股票代码列表（无失败时为空）",
    )
