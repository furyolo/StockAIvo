#!/usr/bin/env python3
"""
删除股票新闻数据表的迁移脚本

根据用户需求，新闻数据将仅使用Redis缓存，不再持久化到数据库。
此脚本将删除stock_news表及其相关索引。
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from stockaivo.database import engine
from sqlalchemy import text

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_stock_news_table():
    """删除股票新闻表及相关索引"""
    
    if engine is None:
        logger.error("数据库引擎未初始化")
        return False
    
    try:
        with engine.connect() as connection:
            # 开始事务
            with connection.begin():
                logger.info("开始删除股票新闻表...")
                
                # 删除相关索引
                logger.info("删除相关索引...")
                connection.execute(text("DROP INDEX IF EXISTS idx_stock_news_keyword_time"))
                connection.execute(text("DROP INDEX IF EXISTS idx_stock_news_publish_time"))
                connection.execute(text("DROP INDEX IF EXISTS idx_stock_news_keyword"))
                
                # 删除表
                logger.info("删除stock_news表...")
                connection.execute(text("DROP TABLE IF EXISTS stock_news"))
                
                logger.info("股票新闻表及相关索引删除成功")
                
        return True
        
    except Exception as e:
        logger.error(f"删除股票新闻表时发生错误: {e}")
        return False

if __name__ == "__main__":
    logger.info("开始执行股票新闻表删除迁移...")
    
    success = drop_stock_news_table()
    
    if success:
        logger.info("迁移完成：股票新闻表已成功删除")
        sys.exit(0)
    else:
        logger.error("迁移失败：无法删除股票新闻表")
        sys.exit(1)
