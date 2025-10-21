#!/usr/bin/env python3
"""
创建 well_known_stock_symbols 表的自动化脚本

该表用于存储来源于 well-known US stocks.xlsx 的常用美股代码及其名称。
symbol 作为主键且必填，name 可为空；表主要用于一次性静态导入，后续更新频率极低。

使用方法:
    python create_well_known_stock_symbols.py

要求:
    - PostgreSQL 数据库连接可用
    - 执行用户具备创建表和索引的权限
"""

import logging
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# 将项目根目录加入 sys.path，方便脚本在独立执行时导入项目模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 统一导入日志配置
from stockaivo.logging_config import configure_logging as configure_app_logging

# 加载环境变量
load_dotenv()

configure_app_logging()
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """从环境变量中获取数据库连接 URL。"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_NAME", "stock")
    username = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    return f"postgresql://{username}:{password}@{host}:{port}/{database}"


def table_exists(engine) -> bool:
    """检查 well_known_stock_symbols 表是否已经存在。"""
    check_sql = text(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'well_known_stock_symbols'
        )
        """
    )
    with engine.connect() as conn:
        result = conn.execute(check_sql).scalar_one()
        return bool(result)


def create_table(engine) -> None:
    """创建 well_known_stock_symbols 表及相关约束与注释。"""
    create_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS public.well_known_stock_symbols (
            symbol VARCHAR NOT NULL,
            name VARCHAR NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('UTC', now()),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('UTC', now()),
            CONSTRAINT pk_well_known_stock_symbols PRIMARY KEY (symbol)
        );

        COMMENT ON TABLE public.well_known_stock_symbols IS
            '常用美股符号字典表，源自 well-known US stocks.xlsx，一次性静态导入';

        COMMENT ON COLUMN public.well_known_stock_symbols.symbol IS
            '股票代码（主键，统一转大写）';

        COMMENT ON COLUMN public.well_known_stock_symbols.name IS
            '股票名称，可为空以兼容缺失数据';

        COMMENT ON COLUMN public.well_known_stock_symbols.created_at IS
            '记录创建时间';

        COMMENT ON COLUMN public.well_known_stock_symbols.updated_at IS
            '记录更新时间';
        """
    )

    with engine.connect() as conn:
        conn.execute(create_table_sql)
        conn.commit()

    logger.info("表 well_known_stock_symbols 创建完成（若不存在则创建）。")


def ensure_updated_at_trigger(engine) -> None:
    """
    为 updated_at 字段创建触发器，使其在更新时自动写入当前时间。

    虽然 ORM 层会通过 onupdate=get_current_time 设置更新时间，
    但为避免直接 SQL 操作遗漏，这里补充数据库层触发器。
    """
    create_function_sql = text(
        """
        CREATE OR REPLACE FUNCTION public.set_timestamp_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = timezone('UTC', now());
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    create_trigger_sql = text(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_well_known_stock_symbols_updated_at'
            ) THEN
                CREATE TRIGGER trg_well_known_stock_symbols_updated_at
                BEFORE UPDATE ON public.well_known_stock_symbols
                FOR EACH ROW
                EXECUTE FUNCTION public.set_timestamp_updated_at();
            END IF;
        END;
        $$;
        """
    )

    with engine.connect() as conn:
        conn.execute(create_function_sql)
        conn.execute(create_trigger_sql)
        conn.commit()

    logger.info("updated_at 自动更新时间触发器已确保存在。")


def create_well_known_stock_symbols_table() -> bool:
    """主流程：创建表并配置触发器。"""
    try:
        database_url = get_database_url()
        engine = create_engine(database_url, pool_pre_ping=True)

        if table_exists(engine):
            logger.info("表 well_known_stock_symbols 已存在，跳过创建。")
            ensure_updated_at_trigger(engine)
            return True

        logger.info("开始创建表 well_known_stock_symbols...")
        create_table(engine)
        ensure_updated_at_trigger(engine)
        logger.info("表结构创建完成。")
        return True

    except SQLAlchemyError as exc:
        logger.error("执行数据库操作时发生错误: %s", exc)
        return False
    except Exception as exc:
        logger.error("创建表结构时发生未知错误: %s", exc)
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("well_known_stock_symbols 表创建脚本")
    logger.info("执行时间: %s", datetime.now(UTC))
    logger.info("=" * 60)

    success = create_well_known_stock_symbols_table()
    if success:
        logger.info("表结构已准备就绪。")
        sys.exit(0)

    logger.error("表结构创建失败，请检查日志。")
    sys.exit(1)
