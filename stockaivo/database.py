"""
数据库连接与会话管理模块

本模块负责处理与PostgreSQL数据库的连接、会话创建和依赖注入。
"""

import os
import logging
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

from .models import StockSymbols

# 加载环境变量
load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)

# 从环境变量获取数据库连接URL，并提供默认值
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/stockaivo_db")

try:
    # 创建SQLAlchemy引擎
    # connect_args用于设置网络相关的参数，例如超时
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
        echo=os.getenv("SQL_ECHO", "False").lower() == "true" # 仅在需要时开启SQL日志
    )
    
    # 创建SessionLocal类，用于创建数据库会话
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("数据库引擎和会话创建成功。")

except SQLAlchemyError as e:
    logger.error(f"创建数据库引擎时发生错误: {e}")
    # 如果引擎创建失败，将SessionLocal设置为None，以便后续检查
    SessionLocal = None
    engine = None


def get_db():
    """
    FastAPI依赖项函数，用于获取数据库会话。
    
    为每个请求创建一个新的Session，并在请求完成后关闭它。
    这种模式确保了会话的独立性和线程安全。
    """
    if SessionLocal is None:
        logger.error("数据库会话未初始化，无法提供数据库连接。")
        raise RuntimeError("Database session not initialized.")
        
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_connection():
    """
    检查数据库连接是否正常。
    
    尝试从引擎获取一个连接并立即关闭它。
    
    Returns:
        bool: 如果连接成功则返回 True，否则返回 False。
    """
    if engine is None:
        return False
    try:
        with engine.connect() as connection:
            return True
    except SQLAlchemyError as e:
        logger.error(f"数据库连接检查失败: {e}")
        return False


def get_fullsymbol_from_db(db: Session, symbol: str) -> str | None:
    """
    根据 symbol 从 stock_symbols 表中查询并返回其对应的 full_symbol。

    Args:
        db (Session): 数据库会话。
        symbol (str): 股票代码, 例如 "AAPL"。

    Returns:
        str | None: 如果找到，则返回 full_symbol；否则返回 None。
    """
    try:
        stmt = select(StockSymbols.full_symbol).where(StockSymbols.symbol == symbol)
        full_symbol = db.execute(stmt).scalar_one_or_none()
        
        if full_symbol:
            logger.info(f"成功为 symbol '{symbol}' 从数据库 stock_symbols 表中找到 full_symbol: '{full_symbol}'")
            return full_symbol
        else:
            logger.warning(f"无法在 stock_symbols 表中为 symbol '{symbol}' 找到匹配的记录。")
            return None
    except SQLAlchemyError as e:
        logger.error(f"查询 symbol '{symbol}' 的 full_symbol 时发生数据库错误: {e}")
        return None