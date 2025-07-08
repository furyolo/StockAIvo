"""
现代化依赖注入模块

本模块提供基于FastAPI最佳实践的现代化依赖注入模式，包括：
- 改进的数据库会话管理（完整的异常处理）
- 使用Annotated类型注解的依赖声明
- 可重用的依赖组合和类型别名
- 与现有database.py模块的兼容性
"""

import logging
from typing import Annotated, Generator
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal, engine

# 配置日志
logger = logging.getLogger(__name__)


def get_db_with_error_handling() -> Generator[Session, None, None]:
    """
    改进的数据库会话依赖，包含完整的异常处理。
    
    基于Context7最佳实践，使用try/except/finally模式：
    - try: 提供数据库会话
    - except: 处理异常，回滚事务并重新抛出
    - finally: 确保会话总是被关闭
    
    Yields:
        Session: SQLAlchemy数据库会话
        
    Raises:
        HTTPException: 当数据库连接失败或发生其他数据库错误时
    """
    if SessionLocal is None:
        logger.error("数据库会话未初始化，无法提供数据库连接。")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库服务不可用"
        )
        
    db: Session = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"数据库操作发生错误: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库操作失败"
        )
    except Exception as e:
        logger.error(f"数据库会话中发生未预期的错误: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器内部错误"
        )
    finally:
        db.close()


def get_db_health_check() -> bool:
    """
    数据库健康检查依赖。
    
    Returns:
        bool: 数据库连接是否正常
    """
    if engine is None:
        return False
    try:
        with engine.connect() as connection:
            return True
    except SQLAlchemyError as e:
        logger.error(f"数据库健康检查失败: {e}")
        return False


# 现代化类型别名，使用Annotated进行依赖注入
DatabaseDep = Annotated[Session, Depends(get_db_with_error_handling)]
DatabaseHealthDep = Annotated[bool, Depends(get_db_health_check)]

# 向后兼容性：保持原有的get_db函数可用
from .database import get_db

__all__ = [
    "get_db_with_error_handling",
    "get_db_health_check", 
    "DatabaseDep",
    "DatabaseHealthDep",
    "get_db"  # 向后兼容
]
