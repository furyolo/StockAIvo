"""
统一日志配置模块

提供UTC时间统一格式化、dictConfig集中初始化以及uvicorn专用配置。
"""

import logging
import logging.config
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Optional


class UTCFormatter(logging.Formatter):
    """
    UTC时区格式化器

    强制所有日志时间戳使用UTC时区，确保与uvicorn日志时区一致。
    """

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:  # type: ignore[override]
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
        return dt.strftime("%H:%M:%S")


def _resolve_log_level(default_level: str = "INFO", explicit_level: Optional[str] = None) -> str:
    """
    解析日志级别，优先使用显式参数，其次读取环境变量 LOG_LEVEL。
    """
    if explicit_level:
        return explicit_level.upper()
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        return env_level.upper()
    return default_level.upper()


def build_logging_config(log_level: Optional[str] = None) -> dict:
    """
    构建统一的 logging.dictConfig 配置。

    Args:
        log_level: 根日志级别，默认使用 LOG_LEVEL 环境变量或 INFO。

    Returns:
        dict: 可直接传入 dictConfig 的配置字典。
    """
    resolved_level = _resolve_log_level("INFO", log_level)
    default_log_root = os.path.join("logs", "backend")
    log_dir = os.getenv("LOG_FILE_DIR", default_log_root)
    os.makedirs(log_dir, exist_ok=True)
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file_path = os.path.join(log_dir, f"{current_date}.log")

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
            "file": {
                "formatter": "default",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file_path,
                "maxBytes": int(os.getenv("LOG_FILE_MAX_BYTES", "10485760")),
                "backupCount": int(os.getenv("LOG_FILE_BACKUP_COUNT", "5")),
                "encoding": "utf-8",
            },
        },
        "root": {
            "handlers": ["default", "file"],
            "level": resolved_level,
        },
        "loggers": {
            "uvicorn": {"handlers": ["default", "file"], "level": resolved_level, "propagate": False},
            "uvicorn.error": {"handlers": ["default", "file"], "level": resolved_level, "propagate": False},
            "uvicorn.access": {"handlers": ["default", "file"], "level": resolved_level, "propagate": False},
        },
    }


def configure_logging(log_level: Optional[str] = None) -> None:
    """
    使用统一配置初始化日志系统。
    """
    logging.config.dictConfig(build_logging_config(log_level))


def configure_utc_logging(log_level: Optional[str] = None) -> None:
    """
    向后兼容接口，保持原函数名。
    """
    configure_logging(log_level)


def get_uvicorn_log_config(log_level: Optional[str] = None) -> dict:
    """
    获取uvicorn的UTC日志配置。
    """
    return build_logging_config(log_level)


__all__ = [
    "UTCFormatter",
    "configure_logging",
    "configure_utc_logging",
    "get_uvicorn_log_config",
    "build_logging_config",
]
