"""
统一日志时区配置模块

解决uvicorn日志和应用日志时区不一致的问题，
强制所有日志记录器使用UTC时区显示。
"""

import logging
from datetime import datetime, timezone


class UTCFormatter(logging.Formatter):
    """
    UTC时区格式化器
    
    强制所有日志时间戳使用UTC时区，确保与uvicorn日志时区一致。
    """
    
    def formatTime(self, record, datefmt=None):
        """
        将日志记录时间转换为UTC时区格式
        
        Args:
            record: 日志记录对象
            datefmt: 时间格式字符串
            
        Returns:
            str: UTC时区格式化的时间字符串
        """
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime('%H:%M:%S')


def configure_utc_logging():
    """
    配置所有日志记录器使用UTC时区
    
    应用UTC格式化器到所有现有的日志处理器，
    确保日志时间显示的一致性。
    """
    # 创建UTC格式化器
    utc_formatter = UTCFormatter(
        fmt='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 应用到根日志记录器的所有处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(utc_formatter)
    
    # 应用到应用特定的日志记录器
    app_loggers = [
        'stockaivo',
        'stockaivo.database', 
        'stockaivo.data_service',
        'stockaivo.ai.orchestrator',
        'stockaivo.middleware',
        'stockaivo.dependencies',
        'uvicorn.access',  # uvicorn访问日志
        'uvicorn.error'    # uvicorn错误日志
    ]
    
    for logger_name in app_loggers:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            handler.setFormatter(utc_formatter)


def get_uvicorn_log_config():
    """
    获取uvicorn的UTC日志配置
    
    Returns:
        dict: uvicorn日志配置字典
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "stockaivo.logging_config.UTCFormatter",
                "fmt": "[%(asctime)s] %(levelname)s - %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "access": {
                "()": "stockaivo.logging_config.UTCFormatter", 
                "fmt": '[%(asctime)s] %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler", 
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


__all__ = ['UTCFormatter', 'configure_utc_logging', 'get_uvicorn_log_config']