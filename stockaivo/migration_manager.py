#!/usr/bin/env python3
"""
数据库迁移管理器

自动执行数据库性能优化迁移，确保Docker环境和开发环境的数据库性能优化。
"""

import logging
import os
from pathlib import Path
from typing import Optional, Union, Any
import subprocess
import sys

from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from stockaivo import database
from stockaivo.database import DATABASE_URL

logger = logging.getLogger(__name__)

class DatabaseMigrationManager:
    """数据库迁移管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.migrations_dir = self.project_root / "database_migrations"
        self.migrations_table = "schema_migrations"
        
        # 迁移脚本列表（只包含性能优化迁移，不包含废弃表清理）
        self.migrations = [
            {
                "name": "create_search_indexes",
                "file": "create_search_indexes.py",
                "description": "为us_stocks_name表创建搜索优化索引"
            },
            {
                "name": "create_stock_symbols_index", 
                "file": "create_stock_symbols_index.py",
                "description": "为stock_symbols表创建symbol字段索引"
            }
        ]
    
    def should_run_migrations(self) -> bool:
        """检查是否应该运行迁移"""
        # 环境变量控制，默认在生产环境中运行
        run_migrations = os.getenv("RUN_DATABASE_MIGRATIONS", "true").lower()
        return run_migrations == "true"
    
    def ensure_migrations_table(self, session: Session) -> None:
        """确保迁移记录表存在"""
        try:
            session.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                    name TEXT PRIMARY KEY,
                    executed_at TIMESTAMP DEFAULT NOW()
                )
            """))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"创建迁移记录表失败: {e}")
    
    def record_migration_execution(self, session: Session, migration_name: str) -> None:
        """记录迁移执行情况"""
        try:
            session.execute(
                text(f"""
                    INSERT INTO {self.migrations_table} (name, executed_at)
                    VALUES (:name, NOW())
                    ON CONFLICT (name) DO UPDATE SET executed_at = EXCLUDED.executed_at
                """),
                {"name": migration_name}
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"记录迁移执行状态失败 {migration_name}: {e}")
    
    def check_database_connection(self) -> bool:
        """检查数据库连接"""
        try:
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"数据库连接检查失败: {e}")
            return False
    
    def migration_already_executed(self, session: Session, migration_name: str) -> bool:
        """检查迁移是否已执行"""
        record_exists = False
        artifact_exists = False

        # 先检查迁移记录
        try:
            result = session.execute(
                text(f"SELECT 1 FROM {self.migrations_table} WHERE name = :name"),
                {"name": migration_name}
            ).first()
            record_exists = bool(result)
        except Exception as e:
            logger.warning(f"检查迁移记录失败 {migration_name}: {e}")

        try:
            # 检查特定的索引是否存在来判断迁移产物
            if migration_name == "create_search_indexes":
                # 检查us_stocks_name表的搜索索引
                result = session.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes 
                        WHERE tablename = 'us_stocks_name' 
                        AND indexname LIKE '%_gin'
                    )
                """))
                row = result.fetchone()
                artifact_exists = bool(row[0]) if row else False
            
            elif migration_name == "create_stock_symbols_index":
                # 检查stock_symbols表的symbol索引
                result = session.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes 
                        WHERE tablename = 'stock_symbols' 
                        AND indexname = 'idx_stock_symbols_symbol'
                    )
                """))
                row = result.fetchone()
                artifact_exists = bool(row[0]) if row else False
            
        except Exception as e:
            logger.warning(f"检查迁移状态时出错 {migration_name}: {e}")
            artifact_exists = False

        if record_exists and artifact_exists:
            return True

        if record_exists and not artifact_exists:
            logger.warning(f"迁移记录存在但未检测到产物，准备重新执行: {migration_name}")
            return False

        if not record_exists and artifact_exists:
            logger.info(f"检测到迁移产物但缺少记录，将执行迁移脚本确保状态一致: {migration_name}")
            return False

        return False
    
    def run_migration_script(self, migration_file: str) -> bool:
        """运行迁移脚本"""
        try:
            script_path = self.migrations_dir / migration_file
            
            if not script_path.exists():
                logger.error(f"迁移脚本不存在: {script_path}")
                return False
            
            # 使用uv运行迁移脚本
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                env=env
            )
            
            if result.returncode == 0:
                logger.info(f"迁移脚本执行成功: {migration_file}")
                if result.stdout:
                    logger.debug(f"迁移输出: {result.stdout}")
                return True
            else:
                logger.error(f"迁移脚本执行失败: {migration_file}")
                logger.error(f"错误输出: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"运行迁移脚本时出错 {migration_file}: {e}")
            return False
    
    def run_migrations(self) -> bool:
        """运行所有待执行的迁移"""
        if not self.should_run_migrations():
            logger.info("数据库迁移已禁用 (RUN_DATABASE_MIGRATIONS=false)")
            return True
        
        if not self.check_database_connection():
            logger.error("数据库连接失败，跳过迁移执行")
            return False
        
        logger.info("开始执行数据库迁移...")
        
        # 获取数据库会话
        engine = create_engine(DATABASE_URL)
        
        try:
            if database.SessionLocal is None:
                logger.error("数据库会话未初始化，无法执行迁移")
                return False
                
            with database.SessionLocal() as session:
                success_count = 0
                
                # 确保迁移记录表存在
                self.ensure_migrations_table(session)
                
                for migration in self.migrations:
                    migration_name = migration["name"]
                    migration_file = migration["file"]
                    description = migration["description"]
                    
                    logger.info(f"检查迁移: {migration_name} - {description}")
                    
                    # 检查迁移是否已执行
                    if self.migration_already_executed(session, migration_name):
                        logger.info(f"迁移已执行，跳过: {migration_name}")
                        continue
                    
                    # 执行迁移
                    logger.info(f"执行迁移: {migration_name}")
                    if self.run_migration_script(migration_file):
                        success_count += 1
                        logger.info(f"迁移执行成功: {migration_name}")
                        self.record_migration_execution(session, migration_name)
                    else:
                        logger.error(f"迁移执行失败: {migration_name}")
                        return False
                
                logger.info(f"数据库迁移完成，成功执行 {success_count} 个迁移")
                return True
                
        except Exception as e:
            logger.error(f"执行迁移时出错: {e}")
            return False
    
    def get_migration_status(self) -> dict:
        """获取迁移状态"""
        status = {
            "enabled": self.should_run_migrations(),
            "database_connected": self.check_database_connection(),
            "migrations": []
        }
        
        if status["database_connected"]:
            try:
                engine = create_engine(DATABASE_URL)
                if database.SessionLocal is None:
                    logger.warning("数据库会话未初始化，无法检查迁移状态")
                    return status
                    
                with database.SessionLocal() as session:
                    for migration in self.migrations:
                        migration_name = migration["name"]
                        description = migration["description"]
                        
                        executed = self.migration_already_executed(session, migration_name)
                        
                        migrations_list = status["migrations"]
                        if isinstance(migrations_list, list):
                            migrations_list.append({
                                "name": migration_name,
                                "description": description,
                                "executed": executed
                            })
            except Exception as e:
                logger.error(f"获取迁移状态时出错: {e}")
                status["database_connected"] = False
        
        return status


# 全局迁移管理器实例
migration_manager = DatabaseMigrationManager()

def run_database_migrations() -> bool:
    """运行数据库迁移的便捷函数"""
    return migration_manager.run_migrations()

def get_migration_status() -> dict:
    """获取迁移状态的便捷函数"""
    return migration_manager.get_migration_status()

if __name__ == "__main__":
    # 命令行执行迁移
    logging.basicConfig(level=logging.INFO)
    
    print("StockAIvo 数据库迁移管理器")
    print("=" * 40)
    
    # 显示当前状态
    status = get_migration_status()
    print(f"迁移启用: {status['enabled']}")
    print(f"数据库连接: {status['database_connected']}")
    
    if status["database_connected"]:
        print("\n迁移状态:")
        for migration in status["migrations"]:
            status_text = "✅ 已执行" if migration["executed"] else "❌ 未执行"
            print(f"  {migration['name']}: {status_text} - {migration['description']}")
    
    if status["enabled"] and status["database_connected"]:
        print("\n开始执行迁移...")
        if run_database_migrations():
            print("✅ 迁移执行完成")
        else:
            print("❌ 迁移执行失败")
            sys.exit(1)
    else:
        print("\n跳过迁移执行")