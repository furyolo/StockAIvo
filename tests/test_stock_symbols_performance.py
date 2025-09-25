#!/usr/bin/env python3
"""
stock_symbols表查询性能测试

本脚本用于测试symbol字段索引对查询性能的影响。
比较创建索引前后的查询性能差异。

使用方法:
    python test_stock_symbols_performance.py
"""

import time
import logging
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv()

from stockaivo.database import get_fullsymbol_from_db, get_db
from stockaivo.models import StockSymbols

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_engine():
    """获取数据库引擎"""
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:123456@localhost:5432/stock")
    return create_engine(database_url)

def test_query_performance():
    """测试查询性能"""

    # 测试用的股票代码列表
    test_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA',
        'META', 'NVDA', 'NFLX', 'ADBE', 'CRM',
        'ORCL', 'INTC', 'AMD', 'QCOM', 'AVGO'
    ]

    print("=" * 60)
    print("stock_symbols表查询性能测试")
    print("=" * 60)

    try:
        # 获取数据库引擎和会话
        engine = get_database_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        with SessionLocal() as db:
            print(f"测试查询 {len(test_symbols)} 个股票代码...")
            print()

            # 记录开始时间
            start_time = time.time()

            found_count = 0
            not_found_count = 0

            for symbol in test_symbols:
                symbol_start_time = time.time()
                full_symbol = get_fullsymbol_from_db(db, symbol)
                symbol_end_time = time.time()
                symbol_time = (symbol_end_time - symbol_start_time) * 1000  # 转换为毫秒

                if full_symbol:
                    print(f"  ✅ {symbol} -> {full_symbol} ({symbol_time:.3f}ms)")
                    found_count += 1
                else:
                    print(f"  ❌ {symbol} -> 未找到 ({symbol_time:.3f}ms)")
                    not_found_count += 1

            # 记录结束时间
            end_time = time.time()
            total_time = end_time - start_time

            print()
            print("=" * 60)
            print("查询完成！")
            print(f"总耗时: {total_time:.4f} 秒")
            print(f"平均每次查询: {(total_time/len(test_symbols)*1000):.3f} 毫秒")
            print(f"找到记录: {found_count} 个")
            print(f"未找到记录: {not_found_count} 个")
            print("=" * 60)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print("请确保：")
        print("1. 数据库连接配置正确")
        print("2. stock_symbols表中有测试数据")
        print("3. 已创建symbol字段的索引")

def explain_query_plan():
    """显示查询执行计划"""

    print("\n" + "=" * 60)
    print("查询执行计划分析")
    print("=" * 60)

    try:
        engine = get_database_engine()

        with engine.connect() as conn:
            # 执行EXPLAIN ANALYZE查询
            explain_sql = """
                EXPLAIN ANALYZE
                SELECT fullsymbol
                FROM stock_symbols
                WHERE symbol = 'AAPL'
            """

            print("执行查询计划分析...")
            result = conn.execute(text(explain_sql)).fetchall()

            print("\n查询执行计划：")
            for row in result:
                print(f"  {row[0]}")

            print("\n分析说明：")
            plan_text = '\n'.join([row[0] for row in result])

            if "Index Scan" in plan_text:
                print("  ✅ 使用了索引扫描 (Index Scan)")
                print("  ✅ 查询性能优化成功")
            elif "Seq Scan" in plan_text:
                print("  ⚠️  使用了全表扫描 (Seq Scan)")
                print("  ⚠️  建议检查索引是否正确创建")

            # 提取执行时间
            for row in result:
                if "Execution Time" in row[0]:
                    print(f"  📊 {row[0]}")

    except Exception as e:
        print(f"❌ 查询计划分析失败: {e}")
        print("\n手动执行以下SQL来查看查询计划：")
        print("EXPLAIN ANALYZE SELECT fullsymbol FROM stock_symbols WHERE symbol = 'AAPL';")

def check_index_usage():
    """检查索引使用情况"""

    print("\n" + "=" * 60)
    print("索引使用情况检查")
    print("=" * 60)

    try:
        engine = get_database_engine()

        with engine.connect() as conn:
            # 查询索引使用统计
            index_usage_sql = """
                SELECT
                    schemaname,
                    relname as tablename,
                    indexrelname as indexname,
                    idx_scan as index_scans,
                    idx_tup_read as tuples_read,
                    idx_tup_fetch as tuples_fetched
                FROM pg_stat_user_indexes
                WHERE relname = 'stock_symbols'
                ORDER BY idx_scan DESC
            """

            result = conn.execute(text(index_usage_sql)).fetchall()

            if result:
                print("索引使用统计：")
                print(f"{'索引名称':<30} {'扫描次数':<10} {'读取元组':<10} {'获取元组':<10}")
                print("-" * 60)

                for row in result:
                    print(f"{row.indexname:<30} {row.index_scans:<10} {row.tuples_read:<10} {row.tuples_fetched:<10}")

                print("\n说明：")
                print("  - 扫描次数: 索引被使用的次数")
                print("  - 读取元组: 从索引读取的记录数")
                print("  - 获取元组: 通过索引实际获取的有效记录数")
            else:
                print("❌ 未找到索引使用统计信息")

    except Exception as e:
        print(f"❌ 索引使用情况检查失败: {e}")
        print("\n手动执行以下SQL来检查索引使用情况：")
        print("SELECT * FROM pg_stat_user_indexes WHERE tablename = 'stock_symbols';")

if __name__ == "__main__":
    test_query_performance()
    explain_query_plan()
    check_index_usage()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
