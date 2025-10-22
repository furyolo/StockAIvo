"""现代化依赖注入模块"""

import logging
import os
from functools import lru_cache
from typing import Annotated, Any, Generator, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .utils.rate_limiter import RateLimiter, RateLimitConfig, RateLimiterSettings

# 配置日志
logger = logging.getLogger(__name__)


def get_db_with_error_handling() -> Generator[Session, None, None]:
    """改进的数据库会话依赖，包含完整的异常处理。"""
    if SessionLocal is None:
        logger.error("数据库会话未初始化，无法提供数据库连接。")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库服务不可用",
        )

    db: Session = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as exc:
        logger.error("数据库操作发生错误: %s", exc)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败",
        )
    except Exception as exc:
        logger.error("数据库会话中发生未预期的错误: %s", exc)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器内部错误",
        )
    finally:
        db.close()


def get_db_health_check() -> bool:
    """数据库健康检查依赖。"""
    if engine is None:
        return False
    try:
        with engine.connect():
            return True
    except SQLAlchemyError as exc:
        logger.error("数据库健康检查失败: %s", exc)
        return False


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("环境变量 %s 格式错误，使用默认值 %d", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("环境变量 %s 格式错误，使用默认值 %.2f", name, default)
        return default


@lru_cache(maxsize=1)
def _build_batch_prediction_rate_limiter() -> Optional[RateLimiter]:
    """懒加载批量预测限流器，避免重复构造。"""

    disabled = os.getenv("BATCH_RATE_LIMITER_DISABLED", "false").lower()
    if disabled in {"1", "true", "yes"}:
        logger.info("批量结构化预测限流器已通过环境变量禁用")
        return None

    limits = {
        "ai_predict": RateLimitConfig(
            requests=_env_int("AI_PREDICT_REQUESTS_PER_WINDOW", 5),
            window=_env_float("AI_PREDICT_WINDOW_SECONDS", 60.0),
            jitter=_env_float("AI_PREDICT_JITTER_SECONDS", 0.5),
        ),
        "tickertick": RateLimitConfig(
            requests=_env_int("TICKERTICK_REQUESTS_PER_WINDOW", 10),
            window=_env_float("TICKERTICK_WINDOW_SECONDS", 60.0),
            jitter=_env_float("TICKERTICK_JITTER_SECONDS", 1.0),
        ),
        "akshare": RateLimitConfig(
            requests=_env_int("AKSHARE_REQUESTS_PER_WINDOW", 20),
            window=_env_float("AKSHARE_WINDOW_SECONDS", 60.0),
            jitter=_env_float("AKSHARE_JITTER_SECONDS", 0.5),
        ),
    }

    settings = RateLimiterSettings(
        default_jitter=_env_float("BATCH_RATE_LIMITER_DEFAULT_JITTER", 0.5),
        error_base_delay=_env_float("BATCH_RATE_LIMITER_ERROR_BASE", 2.0),
        error_max_delay=_env_float("BATCH_RATE_LIMITER_ERROR_MAX", 45.0),
        error_jitter=_env_float("BATCH_RATE_LIMITER_ERROR_JITTER", 1.0),
        max_retries=_env_int("BATCH_RATE_LIMITER_MAX_RETRIES", 3),
        global_concurrency=_env_int("BATCH_RATE_LIMITER_GLOBAL_CONCURRENCY", 6),
    )

    try:
        return RateLimiter(limits, settings)
    except ValueError as exc:
        logger.error("初始化批量结构化预测限流器失败: %s", exc)
        return None


def get_batch_prediction_rate_limiter() -> Optional[Any]:
    """批量结构化预测限流器依赖。"""
    limiter = _build_batch_prediction_rate_limiter()
    if limiter is None:
        logger.debug("批量结构化预测限流器未启用")
    return limiter


# 现代化类型别名，使用Annotated进行依赖注入
DatabaseDep = Annotated[Session, Depends(get_db_with_error_handling)]
DatabaseHealthDep = Annotated[bool, Depends(get_db_health_check)]

__all__ = [
    "get_db_with_error_handling",
    "get_db_health_check",
    "get_batch_prediction_rate_limiter",
    "DatabaseDep",
    "DatabaseHealthDep",
    "get_db",
]
