"""
中间件管理模块

本模块提供基于FastAPI最佳实践的中间件统一管理，包括：
- 请求日志中间件（记录请求详情和响应时间）
- 性能监控中间件（追踪API性能指标）
- 安全头中间件（添加安全相关HTTP头）
- 可配置的中间件启用/禁用机制
- 与现有CORS中间件的兼容性
"""

import os
import time
import logging
from typing import Callable, Optional
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    
    记录每个HTTP请求的详细信息，包括：
    - 请求方法和路径
    - 客户端IP地址
    - 响应状态码
    - 处理时间
    - 请求和响应大小
    """
    
    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        # 获取客户端信息
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # 记录请求开始
        logger.info(f"请求开始: {request.method} {request.url} - 客户端: {client_ip}")
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 记录请求完成
            logger.info(
                f"请求完成: {request.method} {request.url} - "
                f"状态码: {response.status_code} - "
                f"处理时间: {process_time:.3f}s - "
                f"客户端: {client_ip}"
            )
            
            # 添加响应头
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"请求异常: {request.method} {request.url} - "
                f"错误: {str(e)} - "
                f"处理时间: {process_time:.3f}s - "
                f"客户端: {client_ip}"
            )
            raise


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    性能监控中间件
    
    监控API性能指标，包括：
    - 响应时间统计
    - 慢请求警告
    - 性能指标记录
    """
    
    def __init__(self, app: ASGIApp, enabled: bool = True, slow_request_threshold: float = 1.0):
        super().__init__(app)
        self.enabled = enabled
        self.slow_request_threshold = slow_request_threshold
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 检查慢请求
            if process_time > self.slow_request_threshold:
                logger.warning(
                    f"慢请求检测: {request.method} {request.url} - "
                    f"处理时间: {process_time:.3f}s (阈值: {self.slow_request_threshold}s)"
                )
            
            # 添加性能相关响应头
            response.headers["X-Response-Time"] = f"{process_time:.3f}"
            response.headers["X-Timestamp"] = datetime.now().isoformat()
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"性能监控异常: {request.method} {request.url} - 时间: {process_time:.3f}s")
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全头中间件
    
    添加安全相关的HTTP响应头，包括：
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Content-Security-Policy (可选)
    """
    
    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        if not self.enabled:
            return response
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 为API添加适当的CSP
        if request.url.path.startswith("/docs") or request.url.path.startswith("/redoc"):
            # 为API文档页面设置宽松的CSP，允许CDN资源
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self';"
            )
        else:
            # 为API端点设置严格的CSP
            response.headers["Content-Security-Policy"] = "default-src 'none'"
        
        return response


def get_middleware_config() -> dict:
    """
    从环境变量获取中间件配置
    
    Returns:
        dict: 中间件配置字典
    """
    return {
        "request_logging_enabled": os.getenv("MIDDLEWARE_REQUEST_LOGGING", "true").lower() == "true",
        "performance_monitoring_enabled": os.getenv("MIDDLEWARE_PERFORMANCE_MONITORING", "true").lower() == "true",
        "security_headers_enabled": os.getenv("MIDDLEWARE_SECURITY_HEADERS", "true").lower() == "true",
        "slow_request_threshold": float(os.getenv("SLOW_REQUEST_THRESHOLD", "1.0")),
    }


def register_middleware(app: FastAPI) -> None:
    """
    注册所有中间件到FastAPI应用
    
    按照正确的顺序注册中间件：
    1. 安全头中间件（最外层）
    2. 请求日志中间件
    3. 性能监控中间件（最内层）
    
    Args:
        app: FastAPI应用实例
    """
    config = get_middleware_config()
    
    # 注意：FastAPI中间件是按照注册的相反顺序执行的
    # 所以最后注册的中间件最先执行
    
    # 性能监控中间件（最内层，最后执行）
    if config["performance_monitoring_enabled"]:
        app.add_middleware(
            PerformanceMonitoringMiddleware,
            enabled=True,
            slow_request_threshold=config["slow_request_threshold"]
        )
        logger.info("性能监控中间件已启用")
    
    # 请求日志中间件（中间层）
    if config["request_logging_enabled"]:
        app.add_middleware(
            RequestLoggingMiddleware,
            enabled=True
        )
        logger.info("请求日志中间件已启用")
    
    # 安全头中间件（最外层，最先执行）
    if config["security_headers_enabled"]:
        app.add_middleware(
            SecurityHeadersMiddleware,
            enabled=True
        )
        logger.info("安全头中间件已启用")
    
    logger.info("所有中间件注册完成")


__all__ = [
    "RequestLoggingMiddleware",
    "PerformanceMonitoringMiddleware", 
    "SecurityHeadersMiddleware",
    "get_middleware_config",
    "register_middleware"
]
