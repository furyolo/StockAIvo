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
from ..data_service import get_stock_data, get_stock_news
from ..schemas import StockDataResponse, ErrorResponse, StockNewsResponse
from ..data_provider import fetch_realtime_quotes, fetch_us_stock_names
from ..database_writer import save_realtime_quotes_to_db, save_us_stock_names_to_db

# 导入现代化依赖注入和异常处理模块
from ..dependencies import DatabaseDep
from ..exceptions import DataServiceException, ValidationException

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
    db: DatabaseDep,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)")
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
        data = await get_stock_data(db, ticker, "daily", end_date, background_tasks)

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
    except ValueError as e:
        logger.error(f"股票代码验证失败 {ticker}: {e}")
        raise ValidationException(f"股票代码验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"获取日线数据失败 {ticker}: {e}")
        raise DataServiceException(f"获取日线数据失败: {str(e)}")


@router.get("/{ticker}/weekly", response_model=StockDataResponse)
async def get_weekly_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)")
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
        data = await get_stock_data(db, ticker, "weekly", end_date, background_tasks)
        
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
    except ValueError as e:
        logger.error(f"股票代码验证失败 {ticker}: {e}")
        raise ValidationException(f"股票代码验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"获取周线数据失败 {ticker}: {e}")
        raise DataServiceException(f"获取周线数据失败: {str(e)}")


@router.get("/{ticker}/10min", response_model=StockDataResponse)
async def get_10min_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)")
):
    """
    获取股票10分钟线数据

    Args:
        ticker: 股票代码 (例如: AAPL)
        start_date: 可选的开始日期，格式：YYYY-MM-DD
        end_date: 可选的结束日期，格式：YYYY-MM-DD
        db: 数据库会话依赖项

    Returns:
        StockDataResponse: 包含10分钟线数据的响应
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)

        logger.info(f"获取10分钟线数据请求: {ticker}, 日期范围: {start_date} - {end_date}")

        # 调用数据服务获取10分钟线数据
        data = await get_stock_data(db, ticker, "10min", end_date, background_tasks)

        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"在指定日期范围内未找到股票 {ticker} 的数据"
            )

        # 构建响应
        response = StockDataResponse(
            ticker=ticker,
            period="10min",
            data_count=len(data),
            data=data.to_dict('records'),  # type: ignore
            timestamp=datetime.now()
        )

        logger.info(f"成功返回10分钟线数据: {ticker}, 记录数: {len(data)}")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"股票代码验证失败 {ticker}: {e}")
        raise ValidationException(f"股票代码验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"获取10分钟线数据失败 {ticker}: {e}")
        raise DataServiceException(f"获取10分钟线数据失败: {str(e)}")


@router.get("/{ticker}/minute", response_model=StockDataResponse)
async def get_minute_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)")
):
    """
    获取股票分钟线数据

    Args:
        ticker: 股票代码 (例如: AAPL)
        start_date: 可选的开始日期，格式：YYYY-MM-DD
        end_date: 可选的结束日期，格式：YYYY-MM-DD
        db: 数据库会话依赖项
        background_tasks: 后台任务管理器

    Returns:
        StockDataResponse: 包含分钟线数据的响应
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)

        logger.info(f"获取分钟线数据请求: {ticker}, 日期范围: {start_date} - {end_date}")

        # 调用数据服务获取分钟线数据
        data = await get_stock_data(db, ticker, "minute", end_date, background_tasks)

        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"在指定日期范围内未找到股票 {ticker} 的数据"
            )

        # 构建响应
        response = StockDataResponse(
            ticker=ticker,
            period="minute",
            data_count=len(data),
            data=data.to_dict('records'),  # type: ignore
            timestamp=datetime.now()
        )

        logger.info(f"成功返回分钟线数据: {ticker}, 记录数: {len(data)}")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"股票代码验证失败 {ticker}: {e}")
        raise ValidationException(f"股票代码验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"获取分钟线数据失败 {ticker}: {e}")
        raise DataServiceException(f"获取分钟线数据失败: {str(e)}")


@router.get("/{ticker}/news")
async def get_stock_news_data(
    ticker: str,
    background_tasks: BackgroundTasks,
    end_date: Optional[str] = Query(None, description="新闻截止日期 (YYYY-MM-DD)，如果不提供则获取所有可用新闻"),
):
    """
    获取指定股票的新闻数据

    Args:
        ticker: 股票代码 (如: AAPL, TSLA)
        background_tasks: 后台任务管理器
        end_date: 新闻截止日期 (YYYY-MM-DD)，如果不提供则获取所有可用新闻

    Returns:
        包含新闻数据的响应对象

    Raises:
        HTTPException: 当股票代码无效或数据获取失败时
    """
    try:
        # 验证股票代码
        ticker = validate_ticker(ticker)

        logger.info(f"获取新闻数据请求: {ticker}, 截止日期: {end_date}")

        # 调用数据服务获取新闻数据
        news_data = await get_stock_news(ticker, background_tasks, end_date)

        if news_data is None or news_data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到股票 {ticker} 的新闻数据"
            )

        # 构建响应（使用第一条记录的keyword，如果没有数据则使用ticker作为fallback）
        keyword = news_data.iloc[0]['keyword'] if not news_data.empty and 'keyword' in news_data.columns else ticker
        response = StockNewsResponse(
            keyword=keyword,
            data_type="news",
            data_count=len(news_data),
            data=news_data.to_dict('records'),  # type: ignore
            timestamp=datetime.now(),
            message=f"成功获取 {len(news_data)} 条新闻数据"
        )

        logger.info(f"成功返回新闻数据: {ticker}, 记录数: {len(news_data)}")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"股票代码验证失败 {ticker}: {e}")
        raise ValidationException(f"股票代码验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"获取新闻数据失败 {ticker}: {e}")
        raise DataServiceException(f"获取新闻数据失败: {str(e)}")


@router.post("/realtime-quotes/update")
async def update_realtime_quotes():
    """
    手动触发实时行情数据更新

    用于管理员或定时任务触发数据库更新，获取最新的美股实时行情数据
    并直接保存到stock_symbols表中。

    Returns:
        Dict: 更新结果，包含成功状态、更新记录数和时间戳
    """
    try:
        logger.info("手动触发实时行情数据更新")

        # 获取实时行情数据
        data = await fetch_realtime_quotes()

        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未能获取到实时行情数据"
            )

        # 直接更新数据库
        success = save_realtime_quotes_to_db(data)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新实时行情数据到数据库失败"
            )

        result = {
            "success": True,
            "message": "实时行情数据更新成功",
            "updated_count": len(data),
            "timestamp": datetime.now()
        }

        logger.info(f"手动更新实时行情数据成功，更新记录数: {len(data)}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动更新实时行情数据失败: {e}")
        raise DataServiceException(f"更新实时行情数据失败: {str(e)}")


@router.post("/us-stock-names/update")
async def update_us_stock_names():
    """
    手动触发美股名称数据更新

    用于管理员或定时任务触发数据库更新，获取最新的美股名称数据
    并直接保存到us_stocks_name表中。

    Returns:
        Dict: 更新结果，包含成功状态、更新记录数和时间戳
    """
    try:
        logger.info("手动触发美股名称数据更新")

        # 获取美股名称数据
        data = await fetch_us_stock_names()

        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未能获取到美股名称数据"
            )

        # 直接更新数据库
        success = save_us_stock_names_to_db(data)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新美股名称数据到数据库失败"
            )

        result = {
            "success": True,
            "message": "美股名称数据更新成功",
            "updated_count": len(data),
            "timestamp": datetime.now()
        }

        logger.info(f"手动更新美股名称数据成功，更新记录数: {len(data)}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动更新美股名称数据失败: {e}")
        raise DataServiceException(f"更新美股名称数据失败: {str(e)}")