#!/usr/bin/env python3
"""
删除stock_prices_minute表的自动化脚本

本脚本安全删除stock_prices_minute表及其相关索引和约束。
分钟线数据现在只保存在Redis缓存中，不再需要PostgreSQL持久化。

使用方法:
    python drop_minute_table.py

要求:
    - PostgreSQL数据库连接
    - 具有DROP TABLE和DROP INDEX权限的数据库用户

回滚方案:
    如需恢复表结构，可执行以下SQL：
    
    CREATE TABLE stock_prices_minute (
        ticker VARCHAR(10) NOT NULL,
        minute_timestamp TIMESTAMP NOT NULL,
        open NUMERIC(10, 4) NOT NULL,
        high NUMERIC(10, 4) NOT NULL,
        low NUMERIC(10, 4) NOT NULL,
        close NUMERIC(10, 4) NOT NULL,
        volume BIGINT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (ticker, minute_timestamp)
    );
    
    CREATE INDEX idx_minute_ticker ON stock_prices_minute (ticker);
    CREATE INDEX idx_minute_timestamp ON stock_prices_minute (minute_timestamp);
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

# 统一导入日志配置
from stockaivo.logging_config import configure_logging as configure_app_logging

# 加载环境变量
load_dotenv()

configure_app_logging()
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
    database = os.getenv('DB_NAME', 'stock')
    username = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD', '')
    
    return f"postgresql://{username}:{password}@{host}:{port}/{database}"

def check_table_exists(engine):
    """检查stock_prices_minute表是否存在"""
    try:
        with engine.connect() as conn:
            check_table_sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'stock_prices_minute'
                )
            """
            result = conn.execute(text(check_table_sql)).fetchone()
            return result[0] if result else False
    except Exception as e:
        logger.error(f"检查表存在性时出错: {e}")
        return False

def drop_indexes_concurrently(engine):
    """使用CONCURRENTLY选项删除索引"""
    indexes_to_drop = [
        'idx_minute_ticker',
        'idx_minute_timestamp'
    ]
    
    # 使用raw_connection删除索引（CONCURRENTLY需要在autocommit模式下运行）
    raw_conn = engine.raw_connection()
    try:
        # 设置autocommit模式
        raw_conn.set_session(autocommit=True)
        cursor = raw_conn.cursor()
        
        for index_name in indexes_to_drop:
            try:
                # 检查索引是否存在
                check_index_sql = f"""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE tablename = 'stock_prices_minute' 
                        AND indexname = '{index_name}'
                    )
                """
                cursor.execute(check_index_sql)
                index_exists = cursor.fetchone()[0]
                
                if index_exists:
                    drop_index_sql = f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"
                    logger.info(f"正在删除索引: {index_name}")
                    cursor.execute(drop_index_sql)
                    logger.info(f"索引 {index_name} 删除成功")
                else:
                    logger.info(f"索引 {index_name} 不存在，跳过删除")
                    
            except Exception as e:
                logger.error(f"删除索引 {index_name} 时出错: {e}")
                raise
        
        cursor.close()
        
    finally:
        raw_conn.close()

def drop_minute_table():
    """删除stock_prices_minute表及其相关索引和约束"""
    
    try:
        # 获取数据库连接
        database_url = get_database_url()
        engine = create_engine(database_url)
        
        logger.info("开始删除stock_prices_minute表...")
        
        # 检查表是否存在
        if not check_table_exists(engine):
            logger.info("stock_prices_minute表不存在，无需删除")
            return True
        
        # 获取表的统计信息
        with engine.connect() as conn:
            stats_sql = """
                SELECT 
                    COUNT(*) as record_count,
                    pg_size_pretty(pg_total_relation_size('stock_prices_minute')) as table_size
                FROM stock_prices_minute
            """
            try:
                stats = conn.execute(text(stats_sql)).fetchone()
                if stats:
                    logger.info(f"表统计信息: 记录数={stats.record_count}, 大小={stats.table_size}")
            except Exception as e:
                logger.warning(f"获取表统计信息失败: {e}")
        
        # 1. 首先删除索引（使用CONCURRENTLY避免锁表）
        logger.info("步骤1: 删除索引...")
        drop_indexes_concurrently(engine)
        
        # 2. 删除表
        with engine.connect() as conn:
            # 开始事务
            trans = conn.begin()
            try:
                # 删除表
                logger.info("步骤2: 删除表...")
                drop_table_sql = "DROP TABLE IF EXISTS stock_prices_minute CASCADE"
                conn.execute(text(drop_table_sql))
                logger.info("表 stock_prices_minute 删除成功")
                
                # 提交事务
                trans.commit()
                
            except Exception as e:
                # 回滚事务
                trans.rollback()
                logger.error(f"删除表时出错: {e}")
                raise
        
        # 3. 验证删除结果
        logger.info("步骤3: 验证删除结果...")
        verify_deletion(engine)
        
        logger.info("stock_prices_minute表及相关结构删除完成！")
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"数据库操作失败: {e}")
        return False
    except Exception as e:
        logger.error(f"删除表时发生错误: {e}")
        return False

def verify_deletion(engine):
    """验证删除操作是否成功"""
    try:
        with engine.connect() as conn:
            # 检查表是否已删除
            table_exists = check_table_exists(engine)
            if table_exists:
                logger.error("验证失败: stock_prices_minute表仍然存在")
                return False
            else:
                logger.info("✓ 验证成功: stock_prices_minute表已删除")
            
            # 检查索引是否已删除
            check_indexes_sql = """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'stock_prices_minute'
            """
            remaining_indexes = conn.execute(text(check_indexes_sql)).fetchall()
            
            if remaining_indexes:
                logger.warning(f"发现残留索引: {[idx.indexname for idx in remaining_indexes]}")
                return False
            else:
                logger.info("✓ 验证成功: 所有相关索引已删除")
            
            return True
            
    except Exception as e:
        logger.error(f"验证删除结果时出错: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("stock_prices_minute表删除脚本")
    logger.info(f"执行时间: {datetime.now()}")
    logger.info("=" * 60)
    
    # 确认删除操作
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        logger.info("使用 --force 参数，跳过确认")
    else:
        confirm = input("确认要删除stock_prices_minute表及其所有数据吗？(输入 'yes' 确认): ")
        if confirm.lower() != 'yes':
            logger.info("操作已取消")
            sys.exit(0)
    
    # 执行删除
    success = drop_minute_table()
    
    if success:
        logger.info("表删除操作完成！")
    else:
        logger.error("表删除操作失败！")
        sys.exit(1)
    
    logger.info("=" * 60)
