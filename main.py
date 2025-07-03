"""
StockAIvo - FastAPI主应用
智能美股数据与分析平台的API服务器
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
 
# 导入项目模块
from stockaivo import database, models
from stockaivo.database import get_db
from stockaivo.database_writer import persist_pending_data
from stockaivo.cache_manager import get_pending_data_keys, health_check as redis_health_check, get_cache_stats
from stockaivo.data_service import get_stock_data, check_data_service_health, PeriodType
from stockaivo.routers import stocks_router
from stockaivo.routers.ai import router as ai_router
from stockaivo.routers.search import router as search_router
from stockaivo.background_scheduler import start_scheduler, stop_scheduler
# from stockaivo.ai.orchestrator import cleanup_orchestrator # Removed after refactor
# from stockaivo.ai.llm_service import cleanup_llm_service # Removed after refactor

# 配置日志
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    - 启动时: 初始化数据库连接和表
    - 关闭时: 执行清理操作
    """
    logger.info("StockAIvo API 服务启动中...")
    
    # 测试数据库连接
    if database.check_db_connection():
        logger.info("数据库连接正常")
    else:
        logger.error("数据库连接失败，请检查DATABASE_URL环境变量和数据库服务状态。")

    # 可选：创建数据库表（生产环境建议使用Alembic）
    try:
        if database.engine:
            models.Base.metadata.create_all(bind=database.engine)
            logger.info("数据库表初始化完成（如果表不存在则创建）。")
        else:
            logger.error("数据库引擎未初始化，跳过表创建。")
    except Exception as e:
        logger.error(f"数据库表初始化失败: {e}")
    
    logger.info("StockAIvo API 服务启动完成")
    
    # 启动后台调度器
    logger.info("启动后台持久化调度器...")
    start_scheduler()

    yield
    
    # Shutdown logic
    logger.info("停止后台持久化调度器...")
    stop_scheduler()
    logger.info("StockAIvo API 服务正在关闭...")
    # 清理AI服务 (Refactored, no-op for now)
    # try:
    #     await cleanup_orchestrator()
    #     await cleanup_llm_service()
    #     logger.info("AI服务清理完成")
    # except Exception as e:
    #     logger.error(f"AI服务清理失败: {e}")


# 创建FastAPI应用实例
app = FastAPI(
    title="StockAIvo API",
    description="智能美股数据与分析平台后端API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3223",  # 前端开发服务器
        "http://127.0.0.1:3223",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由器
app.include_router(stocks_router)
app.include_router(ai_router)
app.include_router(search_router)


@app.get("/", tags=["基础"])
async def root():
    """
    根路径，返回API基本信息
    """
    return {
        "message": "欢迎使用 StockAIvo API",
        "version": "1.0.0",
        "description": "智能美股数据与分析平台",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["健康检查"])
async def health_check():
    """
    系统健康检查端点
    检查数据库、Redis等核心组件状态
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # 检查数据库连接
    try:
        db_healthy = database.check_db_connection()
        health_status["components"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "details": "PostgreSQL连接正常" if db_healthy else "PostgreSQL连接失败"
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "details": f"数据库检查失败: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # 检查Redis连接
    try:
        redis_healthy = redis_health_check()
        health_status["components"]["redis"] = {
            "status": "healthy" if redis_healthy else "unhealthy",
            "details": "Redis连接正常" if redis_healthy else "Redis连接失败"
        }
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "details": f"Redis检查失败: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # 检查数据服务
    try:
        data_service_status = check_data_service_health()
        health_status["components"]["data_service"] = {
            "status": "healthy" if data_service_status.get("healthy", False) else "unhealthy",
            "details": data_service_status
        }
    except Exception as e:
        health_status["components"]["data_service"] = {
            "status": "unhealthy",
            "details": f"数据服务检查失败: {str(e)}"
        }
        health_status["status"] = "unhealthy"
    
    # 根据整体状态返回适当的HTTP状态码
    status_code = status.HTTP_200_OK if health_status["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        content=health_status,
        status_code=status_code
    )


@app.get("/check-pending-data", tags=["数据持久化"], response_model=Dict[str, Any])
async def check_pending_data():
    """
    检查Redis中是否存在待处理数据。
    """
    try:
        pending_keys = get_pending_data_keys()
        pending_count = len(pending_keys)
        
        return {
            "pending": pending_count > 0,
            "count": pending_count,
            "keys": pending_keys,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查待处理数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"检查待处理数据失败: {str(e)}"
        )


@app.post("/persist-data", tags=["数据持久化"], status_code=status.HTTP_202_ACCEPTED)
async def persist_data_endpoint(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    异步执行数据持久化操作。
    将Redis中的待处理数据批量写入PostgreSQL数据库。
    """
    try:
        logger.info("接收到数据持久化请求，将在后台执行...")
        background_tasks.add_task(persist_pending_data, db)
        return {"message": "数据持久化任务已在后台启动。", "timestamp": datetime.now().isoformat()}
            
    except Exception as e:
        logger.error(f"数据持久化端点发生异常: {e}")
        error_response = {
            "success": False,
            "message": f"数据持久化操作失败: {str(e)}",
            "processed_count": 0,
            "failed_count": 0,
            "errors": [{"general_error": str(e)}],
            "timestamp": datetime.now().isoformat()
        }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response
        )


@app.get("/stock-data/{ticker}", tags=["数据查询"])
async def get_stock_data_endpoint(
    ticker: str,
    period: PeriodType = "daily",
    db: Session = Depends(get_db)
):
    """
    获取股票数据端点
    
    Args:
        ticker: 股票代码 (例如: AAPL)
        period: 时间周期 (daily, weekly, hourly)
        db: 数据库会话依赖项
        
    Returns:
        Dict: 股票数据
    """
    try:
        # 验证ticker参数
        ticker = ticker.upper().strip()
        if not ticker or len(ticker) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的股票代码"
            )
        
        logger.info(f"获取股票数据请求: {ticker}_{period}")
        
        # 调用数据服务获取数据
        data = await get_stock_data(db, ticker, period)
        
        if data is None or data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到股票 {ticker} 的 {period} 数据"
            )
        
        # 转换DataFrame为字典格式返回
        response = {
            "ticker": ticker,
            "period": period,
            "data_count": len(data),
            "data": data.to_dict('records'),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"成功返回股票数据: {ticker}_{period}, 记录数: {len(data)}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取股票数据失败 {ticker}_{period}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取股票数据失败: {str(e)}"
        )


@app.get("/cache-stats", tags=["缓存管理"])
async def get_cache_statistics():
    """
    获取Redis缓存统计信息

    Returns:
        Dict: 缓存统计信息
    """
    try:
        # 获取缓存统计信息
        stats = get_cache_stats()

        if "error" in stats:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"获取缓存统计失败: {stats['error']}"
            )

        # 添加时间戳和格式化信息
        response = {
            **stats,
            "timestamp": datetime.now().isoformat(),
            "memory_usage_mb": round(int(stats.get("memory_usage", 0)) / 1024 / 1024, 2) if stats.get("memory_usage") else 0
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取缓存统计失败: {str(e)}"
        )


# 异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "服务器内部错误",
            "timestamp": datetime.now().isoformat()
        }
    )


# 应用入口点
if __name__ == "__main__":
    import uvicorn
    
    # 开发环境运行配置
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )