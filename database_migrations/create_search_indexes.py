#!/usr/bin/env python3
"""
数据库索引创建脚本

为us_stocks_name表创建搜索优化索引，提升模糊搜索性能。
使用CONCURRENTLY选项避免锁表，适合生产环境使用。
"""

import os
import sys
import logging
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
    """获取数据库连接URL"""
    return os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/stockaivo_db")


def check_pg_trgm_extension(engine):
    """检查并创建pg_trgm扩展"""
    try:
        with engine.connect() as conn:
            # 检查pg_trgm扩展是否存在
            result = conn.execute(text("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'
                );
            """))
            
            extension_exists = result.scalar()
            
            if not extension_exists:
                logger.info("创建pg_trgm扩展...")
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
                conn.commit()
                logger.info("pg_trgm扩展创建成功")
            else:
                logger.info("pg_trgm扩展已存在")
                
    except SQLAlchemyError as e:
        logger.error(f"检查/创建pg_trgm扩展失败: {e}")
        raise


def check_table_exists(engine):
    """检查us_stocks_name表是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'us_stocks_name'
                );
            """))
            
            table_exists = result.scalar()
            
            if not table_exists:
                logger.error("us_stocks_name表不存在，请先创建表")
                return False
            
            logger.info("us_stocks_name表存在，可以创建索引")
            return True
            
    except SQLAlchemyError as e:
        logger.error(f"检查表存在性失败: {e}")
        return False


def create_indexes(engine):
    """创建搜索索引"""

    # 索引创建SQL语句列表
    index_statements = [
        {
            "name": "idx_us_stocks_name_name_gin",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_name_gin
                ON us_stocks_name USING gin (name gin_trgm_ops)
            """,
            "description": "name字段GIN索引（trigram）"
        },
        {
            "name": "idx_us_stocks_name_cname_gin",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_cname_gin
                ON us_stocks_name USING gin (cname gin_trgm_ops)
            """,
            "description": "cname字段GIN索引（trigram）"
        },
        {
            "name": "idx_us_stocks_name_name_btree",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_name_btree
                ON us_stocks_name (name)
            """,
            "description": "name字段B-tree索引"
        },
        {
            "name": "idx_us_stocks_name_cname_btree",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_cname_btree
                ON us_stocks_name (cname)
            """,
            "description": "cname字段B-tree索引"
        },
        {
            "name": "idx_us_stocks_name_composite",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_composite
                ON us_stocks_name (symbol, name, cname)
            """,
            "description": "复合索引（symbol, name, cname）"
        }
    ]

    created_indexes = []
    failed_indexes = []

    for index_info in index_statements:
        try:
            logger.info(f"创建索引: {index_info['name']} - {index_info['description']}")

            # 检查索引是否已存在
            with engine.connect() as conn:
                check_result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes
                        WHERE indexname = :index_name
                    )
                """), {"index_name": index_info['name']})

                if check_result.scalar():
                    logger.info(f"索引 {index_info['name']} 已存在，跳过创建")
                    created_indexes.append(index_info['name'])
                    continue

            # 注意：CONCURRENTLY不能在事务中使用，需要使用autocommit模式
            # 使用原始连接来执行CONCURRENTLY操作
            raw_conn = engine.raw_connection()
            try:
                # 设置autocommit模式
                raw_conn.set_session(autocommit=True)
                cursor = raw_conn.cursor()
                cursor.execute(index_info['sql'].strip())
                cursor.close()

                logger.info(f"索引 {index_info['name']} 创建成功")
                created_indexes.append(index_info['name'])

            finally:
                raw_conn.close()

        except Exception as e:
            logger.error(f"创建索引 {index_info['name']} 失败: {e}")
            failed_indexes.append(index_info['name'])

    return created_indexes, failed_indexes


def analyze_table(engine):
    """分析表统计信息"""
    try:
        with engine.connect() as conn:
            logger.info("分析us_stocks_name表统计信息...")
            conn.execute(text("ANALYZE us_stocks_name;"))
            conn.commit()
            logger.info("表统计信息分析完成")
    except SQLAlchemyError as e:
        logger.error(f"分析表统计信息失败: {e}")


def verify_indexes(engine):
    """验证索引创建结果"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    indexname,
                    indexdef
                FROM pg_indexes 
                WHERE tablename = 'us_stocks_name'
                ORDER BY indexname;
            """))
            
            indexes = result.fetchall()
            
            logger.info("us_stocks_name表的索引列表:")
            for index in indexes:
                logger.info(f"  - {index[0]}: {index[1]}")
            
            return len(indexes)
            
    except SQLAlchemyError as e:
        logger.error(f"验证索引失败: {e}")
        return 0


def main():
    """主函数"""
    logger.info("开始创建搜索索引...")
    
    try:
        # 创建数据库引擎
        database_url = get_database_url()
        engine = create_engine(database_url, echo=False)
        
        logger.info(f"连接数据库: {database_url.split('@')[1] if '@' in database_url else 'localhost'}")
        
        # 检查表是否存在
        if not check_table_exists(engine):
            return False
        
        # 检查并创建pg_trgm扩展
        check_pg_trgm_extension(engine)
        
        # 创建索引
        created_indexes, failed_indexes = create_indexes(engine)
        
        # 分析表统计信息
        analyze_table(engine)
        
        # 验证索引
        total_indexes = verify_indexes(engine)
        
        # 输出结果
        logger.info(f"索引创建完成！")
        logger.info(f"成功创建: {len(created_indexes)} 个索引")
        if created_indexes:
            logger.info(f"成功的索引: {', '.join(created_indexes)}")
        
        if failed_indexes:
            logger.warning(f"失败的索引: {', '.join(failed_indexes)}")
        
        logger.info(f"表总索引数: {total_indexes}")
        
        return len(failed_indexes) == 0
        
    except Exception as e:
        logger.error(f"创建索引过程中发生错误: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
