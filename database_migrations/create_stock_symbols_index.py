#!/usr/bin/env python3
"""
为stock_symbols表创建索引的自动化脚本

本脚本为stock_symbols表的symbol字段创建索引，以优化查询性能。
特别针对get_fullsymbol_from_db函数中频繁的symbol查询进行优化。

使用方法:
    python create_stock_symbols_index.py

要求:
    - PostgreSQL数据库连接
    - 具有CREATE INDEX权限的数据库用户
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_database_url():
    """从环境变量获取数据库连接URL"""
    # 尝试从环境变量获取数据库URL
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return database_url
    
    # 如果没有DATABASE_URL，尝试从单独的环境变量构建
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    database = os.getenv('DB_NAME', 'stockaivo')
    username = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD', '')
    
    return f"postgresql://{username}:{password}@{host}:{port}/{database}"

def create_stock_symbols_index():
    """创建stock_symbols表的symbol字段索引"""
    
    try:
        # 获取数据库连接
        database_url = get_database_url()
        engine = create_engine(database_url)
        
        logger.info("开始为stock_symbols表创建索引...")
        
        # 检查索引是否已存在
        with engine.connect() as conn:
            check_index_sql = """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'stock_symbols'
                AND indexname = 'idx_stock_symbols_symbol'
            """

            result = conn.execute(text(check_index_sql)).fetchone()

            if result:
                logger.info("索引 idx_stock_symbols_symbol 已存在，跳过创建")
                return True

        # 使用raw_connection创建索引（CONCURRENTLY需要在autocommit模式下运行）
        raw_conn = engine.raw_connection()
        try:
            # 设置autocommit模式
            raw_conn.set_session(autocommit=True)
            cursor = raw_conn.cursor()

            create_index_sql = """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_symbols_symbol
                ON stock_symbols (symbol)
            """

            logger.info("正在创建索引 idx_stock_symbols_symbol...")
            cursor.execute(create_index_sql.strip())
            cursor.close()

            logger.info("索引创建成功！")

        finally:
            raw_conn.close()

        # 分析表以更新统计信息
        with engine.connect() as conn:
            logger.info("正在分析表统计信息...")
            conn.execute(text("ANALYZE stock_symbols"))
            conn.commit()

            # 验证索引创建
            verify_sql = """
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE tablename = 'stock_symbols'
                ORDER BY indexname
            """

            indexes = conn.execute(text(verify_sql)).fetchall()

            logger.info("当前stock_symbols表的索引:")
            for index in indexes:
                logger.info(f"  - {index.indexname}: {index.indexdef}")

            return True
            
    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {e}")
        return False
    except Exception as e:
        logger.error(f"创建索引时发生错误: {e}")
        return False

def test_query_performance():
    """测试查询性能"""
    try:
        database_url = get_database_url()
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # 测试查询
            test_sql = """
                EXPLAIN ANALYZE 
                SELECT fullsymbol 
                FROM stock_symbols 
                WHERE symbol = 'AAPL'
            """
            
            logger.info("测试查询性能:")
            result = conn.execute(text(test_sql)).fetchall()
            for row in result:
                logger.info(f"  {row[0]}")
                
    except Exception as e:
        logger.error(f"性能测试失败: {e}")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("stock_symbols表索引创建脚本")
    logger.info(f"执行时间: {datetime.now()}")
    logger.info("=" * 60)
    
    # 创建索引
    success = create_stock_symbols_index()
    
    if success:
        logger.info("索引创建完成！")
        
        # 可选：测试查询性能
        if len(sys.argv) > 1 and sys.argv[1] == "--test":
            test_query_performance()
    else:
        logger.error("索引创建失败！")
        sys.exit(1)
    
    logger.info("=" * 60)
