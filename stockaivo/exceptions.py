"""
统一异常处理模块

本模块提供基于FastAPI最佳实践的异常处理机制，包括：
- 自定义异常类定义
- 统一错误响应格式
- 改进的全局异常处理器（重用FastAPI默认处理器）
- 与现有错误处理逻辑的兼容性
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# 配置日志
logger = logging.getLogger(__name__)


class StockAIvoException(Exception):
    """
    StockAIvo自定义异常基类
    
    提供统一的异常处理接口，包含错误消息、状态码和额外的上下文信息。
    """
    
    def __init__(
        self, 
        message: str, 
        status_code: int = 500, 
        detail: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(self.message)


class DatabaseException(StockAIvoException):
    """数据库相关异常"""
    
    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


class DataServiceException(StockAIvoException):
    """数据服务相关异常"""
    
    def __init__(self, message: str, status_code: int = 500, detail: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status_code,
            detail=detail
        )


class ValidationException(StockAIvoException):
    """数据验证异常"""
    
    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class AIServiceException(StockAIvoException):
    """AI服务相关异常"""
    
    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )


def create_error_response(
    message: str,
    status_code: int = 500,
    detail: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    创建统一的错误响应格式
    
    Args:
        message: 错误消息
        status_code: HTTP状态码
        detail: 额外的错误详情
        timestamp: 错误发生时间，默认为当前时间
        
    Returns:
        Dict: 标准化的错误响应
    """
    response = {
        "detail": message,
        "timestamp": (timestamp or datetime.now()).isoformat()
    }
    
    if detail:
        response.update(detail)
        
    return response


# 改进的异常处理器，遵循Context7最佳实践
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    自定义HTTP异常处理器
    
    基于Context7最佳实践，重用FastAPI默认异常处理器而非完全覆盖。
    在调用默认处理器前添加自定义日志记录。
    """
    logger.error(f"HTTP异常: {exc.status_code} - {exc.detail} - 路径: {request.url}")
    
    # 重用FastAPI默认异常处理器
    return await http_exception_handler(request, exc)


async def custom_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    自定义请求验证异常处理器
    
    处理请求参数验证错误，提供更友好的错误信息。
    """
    logger.error(f"请求验证错误: {exc.errors()} - 路径: {request.url}")
    
    # 重用FastAPI默认验证异常处理器
    return await request_validation_exception_handler(request, exc)


async def custom_stockaivo_exception_handler(request: Request, exc: StockAIvoException) -> JSONResponse:
    """
    StockAIvo自定义异常处理器
    
    处理项目特定的异常类型，提供统一的错误响应格式。
    """
    logger.error(f"StockAIvo异常: {exc.message} - 状态码: {exc.status_code} - 路径: {request.url}")
    
    error_response = create_error_response(
        message=exc.message,
        status_code=exc.status_code,
        detail=exc.detail
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    全局异常处理器
    
    处理所有未被其他处理器捕获的异常，确保系统稳定性。
    记录详细的错误信息用于调试，但向客户端返回通用错误消息。
    """
    logger.error(f"未处理的异常: {type(exc).__name__}: {exc} - 路径: {request.url}", exc_info=True)
    
    error_response = create_error_response(
        message="服务器内部错误",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


def register_exception_handlers(app):
    """
    注册所有异常处理器到FastAPI应用
    
    Args:
        app: FastAPI应用实例
    """
    # 注册自定义异常处理器
    app.add_exception_handler(StockAIvoException, custom_stockaivo_exception_handler)
    
    # 注册改进的HTTP异常处理器
    app.add_exception_handler(StarletteHTTPException, custom_http_exception_handler)
    
    # 注册请求验证异常处理器
    app.add_exception_handler(RequestValidationError, custom_validation_exception_handler)
    
    # 注册全局异常处理器
    app.add_exception_handler(Exception, global_exception_handler)
    
    logger.info("所有异常处理器已注册")


__all__ = [
    "StockAIvoException",
    "DatabaseException", 
    "DataServiceException",
    "ValidationException",
    "AIServiceException",
    "create_error_response",
    "custom_http_exception_handler",
    "custom_validation_exception_handler", 
    "custom_stockaivo_exception_handler",
    "global_exception_handler",
    "register_exception_handlers"
]
