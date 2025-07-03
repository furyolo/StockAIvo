"""
StockAIvo - 股票数据API路由
提供股票数据查询的RESTful接口
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session

from ..database import get_db
from ..data_service import get_stock_data
from ..schemas import StockDataResponse, ErrorResponse

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/stocks",
    tags=["股票数据"],
    responses={
        404: {"model": ErrorResponse, "description": "股票数据未找到"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    }
)


def validate_ticker(ticker: str) -> str:
    """验证和标准化股票代码"""
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的股票代码：代码不能为空且长度不能超过10个字符"
        )
    return ticker


@router.get("/{ticker}/daily", response_model=StockDataResponse)
async def get_daily_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    获取股票日线数据
    
    Args:
        ticker: 股票代码 (例如: AAPL)
        start_date: 可选的开始日期，格式：YYYY-MM-DD
        end_date: 可选的结束日期，格式：YYYY-MM-DD
        db: 数据库会话依赖项
        
    Returns:
        StockDataResponse: 包含日线数据的响应
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)
        
        logger.info(f"获取日线数据请求: {ticker}, 日期范围: {start_date} - {end_date}")
        
        # 调用数据服务获取日线数据
        data = await get_stock_data(db, ticker, "daily", start_date, end_date, background_tasks)
        
        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"在指定日期范围内未找到股票 {ticker} 的数据"
            )
        
        # 构建响应
        response = StockDataResponse(
            ticker=ticker,
            period="daily",
            data_count=len(data),
            data=data.to_dict('records'),  # type: ignore
            timestamp=datetime.now()
        )
        
        logger.info(f"成功返回日线数据: {ticker}, 记录数: {len(data)}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取日线数据失败 {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日线数据失败: {str(e)}"
        )


@router.get("/{ticker}/weekly", response_model=StockDataResponse)
async def get_weekly_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    获取股票周线数据
    
    Args:
        ticker: 股票代码 (例如: AAPL)
        start_date: 可选的开始日期，格式：YYYY-MM-DD
        end_date: 可选的结束日期，格式：YYYY-MM-DD
        db: 数据库会话依赖项
        
    Returns:
        StockDataResponse: 包含周线数据的响应
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)
        
        logger.info(f"获取周线数据请求: {ticker}, 日期范围: {start_date} - {end_date}")
        
        # 调用数据服务获取周线数据
        data = await get_stock_data(db, ticker, "weekly", start_date, end_date, background_tasks)
        
        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"在指定日期范围内未找到股票 {ticker} 的数据"
            )
        
        # 构建响应
        response = StockDataResponse(
            ticker=ticker,
            period="weekly",
            data_count=len(data),
            data=data.to_dict('records'),  # type: ignore
            timestamp=datetime.now()
        )
        
        logger.info(f"成功返回周线数据: {ticker}, 记录数: {len(data)}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取周线数据失败 {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取周线数据失败: {str(e)}"
        )


@router.get("/{ticker}/hourly", response_model=StockDataResponse)
async def get_hourly_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    获取股票小时线数据
    
    Args:
        ticker: 股票代码 (例如: AAPL)
        start_date: 可选的开始日期，格式：YYYY-MM-DD
        end_date: 可选的结束日期，格式：YYYY-MM-DD
        db: 数据库会话依赖项
        
    Returns:
        StockDataResponse: 包含小时线数据的响应
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)
        
        logger.info(f"获取小时线数据请求: {ticker}, 日期范围: {start_date} - {end_date}")
        
        # 调用数据服务获取小时线数据
        data = await get_stock_data(db, ticker, "hourly", start_date, end_date, background_tasks)
        
        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"在指定日期范围内未找到股票 {ticker} 的数据"
            )
        
        # 构建响应
        response = StockDataResponse(
            ticker=ticker,
            period="hourly",
            data_count=len(data),
            data=data.to_dict('records'),  # type: ignore
            timestamp=datetime.now()
        )
        
        logger.info(f"成功返回小时线数据: {ticker}, 记录数: {len(data)}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取小时线数据失败 {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取小时线数据失败: {str(e)}"
        )