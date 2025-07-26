#!/usr/bin/env python3
"""
创建股票新闻数据表的迁移脚本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stockaivo.database import engine
from sqlalchemy import text
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """执行股票新闻表创建迁移"""
    
    # 读取SQL文件
    sql_file_path = Path(__file__).parent / "create_stock_news_table.sql"
    
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        logger.info("开始执行股票新闻表创建迁移...")
        
        # 执行SQL
        with engine.connect() as conn:
            # 分割SQL语句并逐个执行
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements, 1):
                if statement:
                    logger.info(f"执行SQL语句 {i}/{len(statements)}")
                    conn.execute(text(statement))
            
            conn.commit()
        
        logger.info("股票新闻表创建迁移执行成功！")
        
    except FileNotFoundError:
        logger.error(f"SQL文件未找到: {sql_file_path}")
        return False
    except Exception as e:
        logger.error(f"迁移执行失败: {e}")
        return False
    
    return True


def verify_migration():
    """验证迁移是否成功"""
    try:
        with engine.connect() as conn:
            # 检查表是否存在
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'stock_news'
                );
            """))
            
            table_exists = result.scalar()
            
            if table_exists:
                logger.info("✓ stock_news 表创建成功")
                
                # 检查索引是否存在
                result = conn.execute(text("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'stock_news';
                """))

                indexes = [row[0] for row in result.fetchall()]
                expected_indexes = ['idx_stock_news_keyword_time', 'idx_stock_news_publish_time', 'idx_stock_news_keyword']

                for index in expected_indexes:
                    if index in indexes:
                        logger.info(f"✓ 索引 {index} 创建成功")
                    else:
                        logger.warning(f"⚠ 索引 {index} 未找到")

                # 检查主键约束
                result = conn.execute(text("""
                    SELECT constraint_name FROM information_schema.table_constraints
                    WHERE table_name = 'stock_news'
                    AND constraint_type = 'PRIMARY KEY';
                """))

                constraints = [row[0] for row in result.fetchall()]
                if constraints:
                    logger.info(f"✓ 主键约束 {constraints[0]} 创建成功")
                else:
                    logger.warning("⚠ 主键约束未找到")

                # 检查keyword列是否存在
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'stock_news'
                    AND column_name = 'keyword';
                """))

                if result.fetchone():
                    logger.info("✓ keyword 列创建成功")
                else:
                    logger.warning("⚠ keyword 列未找到")
                
                return True
            else:
                logger.error("✗ stock_news 表创建失败")
                return False
                
    except Exception as e:
        logger.error(f"验证迁移失败: {e}")
        return False


if __name__ == "__main__":
    logger.info("开始股票新闻表迁移...")
    
    # 执行迁移
    if run_migration():
        # 验证迁移
        if verify_migration():
            logger.info("股票新闻表迁移完成并验证成功！")
            sys.exit(0)
        else:
            logger.error("迁移验证失败")
            sys.exit(1)
    else:
        logger.error("迁移执行失败")
        sys.exit(1)
