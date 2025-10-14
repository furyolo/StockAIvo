#!/usr/bin/env python3
"""
从 well-known US stocks.xlsx 导入常用美股符号到数据库。

脚本读取 Excel 中的 symbol/name 两列，将数据幂等写入 well_known_stock_symbols 表。
支持通过命令行参数指定 Excel 路径与干跑模式（仅预览，不写入数据库）。

用法示例:
    uv run python -m stockaivo.scripts.import_well_known_symbols
    uv run python -m stockaivo.scripts.import_well_known_symbols --excel-path path/to/file.xlsx
    uv run python -m stockaivo.scripts.import_well_known_symbols --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import WellKnownStockSymbol

# 加载环境变量，确保 DATABASE_URL 等配置可用
load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 默认 Excel 路径：项目根目录的 well-known US stocks.xlsx
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEL_PATH = PROJECT_ROOT / "well-known US stocks.xlsx"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="导入 well-known US stocks.xlsx 中的 symbol/name 数据到 well_known_stock_symbols 表"
    )
    parser.add_argument(
        "--excel-path",
        type=Path,
        default=DEFAULT_EXCEL_PATH,
        help=f"Excel 文件路径，默认 {DEFAULT_EXCEL_PATH}"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览导入数据，不写入数据库"
    )
    return parser.parse_args()


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    清洗并标准化 DataFrame：
    - 统一列名为小写
    - 保留 symbol/name 列
    - 丢弃 symbol 为空的行
    - 去除重复 symbol，仅保留首次出现
    - symbol 统一去空格并大写
    """
    normalized = df.copy()
    normalized.columns = [str(col).strip().lower() for col in normalized.columns]

    required_columns = {"symbol", "name"}
    missing = required_columns - set(normalized.columns)
    if missing:
        raise ValueError(f"Excel 中缺少必要列: {', '.join(sorted(missing))}")

    normalized = normalized[["symbol", "name"]]

    # 清洗 symbol
    normalized["symbol"] = normalized["symbol"].where(normalized["symbol"].notna(), None)
    normalized["symbol"] = normalized["symbol"].apply(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    normalized["symbol"] = normalized["symbol"].replace({"": None, "nan": None, "NaN": None, "None": None})
    normalized = normalized[normalized["symbol"].notna()]
    normalized["symbol"] = normalized["symbol"].apply(
        lambda value: value.upper() if isinstance(value, str) else value
    )

    # name 允许为空，统一处理成字符串或 None
    normalized["name"] = normalized["name"].apply(
        lambda value: value.strip() if isinstance(value, str) and value.strip() else None
    )

    # 去重，保留首次出现
    normalized = normalized.drop_duplicates(subset=["symbol"], keep="first")
    normalized = normalized.reset_index(drop=True)

    return normalized


def to_records(df: pd.DataFrame) -> List[dict]:
    """将 DataFrame 转换为可插入数据库的记录字典列表。"""
    records: List[dict] = []
    for row in df.to_dict(orient="records"):
        records.append(
            {
                "symbol": row["symbol"],
                "name": row["name"],
            }
        )
    return records


def upsert_records(session: Session, records: Iterable[dict]) -> Tuple[int, int]:
    """
    批量 upsert 记录。

    Returns:
        Tuple[int, int]: (插入或更新的记录数, 忽略的记录数)
    """
    records_list = list(records)
    if not records_list:
        return 0, 0

    insert_stmt = insert(WellKnownStockSymbol).values(records_list)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[WellKnownStockSymbol.symbol],
        set_={
            "name": func.coalesce(insert_stmt.excluded.name, WellKnownStockSymbol.name),
            "updated_at": func.now(),
        },
    )

    result = session.execute(upsert_stmt)
    session.commit()

    # result.rowcount 对于 upsert 场景表示影响行数
    affected = result.rowcount or 0
    return affected, 0


def import_symbols(excel_path: Path, dry_run: bool = False) -> None:
    """主流程：读取 Excel 并导入数据库。"""
    if not excel_path.exists():
        raise FileNotFoundError(f"未找到 Excel 文件: {excel_path}")

    logger.info("开始读取 Excel: %s", excel_path)
    raw_df = pd.read_excel(excel_path)
    cleaned_df = normalize_dataframe(raw_df)

    cleaned_count = len(cleaned_df.index)
    unique_symbols = cleaned_df["symbol"].nunique()

    logger.info(
        "Excel 解析完成：原始行数=%d，清洗后数据行数=%d，有效 symbol 数=%d",
        len(raw_df.index),
        cleaned_count,
        unique_symbols,
    )

    if dry_run:
        logger.info("干跑模式 --dry-run 已启用，不写入数据库。")
        logger.info("预览前 10 条记录:\n%s", cleaned_df.head(10))
        return

    if SessionLocal is None:
        raise RuntimeError("数据库会话未初始化，无法写入数据。")

    records = to_records(cleaned_df)
    with SessionLocal() as session:
        affected, _ = upsert_records(session, records)

    logger.info("导入完成，成功插入/更新 %d 条记录。", affected)


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    import_symbols(args.excel_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
