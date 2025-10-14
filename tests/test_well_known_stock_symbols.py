"""
针对 well_known_stock_symbols 导入脚本的单元测试。

覆盖数据清洗、UPSERT 构造以及主流程干跑/实际写入路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, cast

import pandas as pd
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ClauseElement

from stockaivo.scripts import import_well_known_symbols as script


class DummySession:
    """简易的 SQLAlchemy Session 替身，用于捕获执行的 SQL 语句。"""

    def __init__(self) -> None:
        self.statements: List[ClauseElement] = []
        self.committed = False

    def execute(self, stmt):
        self.statements.append(stmt)

        class Result:
            rowcount = 2

        return Result()

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> "DummySession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class DummySessionFactory:
    """模拟 sessionmaker，使其支持 SessionLocal() 调用。"""

    def __call__(self) -> DummySession:
        return DummySession()


def test_normalize_dataframe_handles_duplicates_and_empty():
    """确保清洗逻辑能够去重并过滤空 symbol。"""
    df = pd.DataFrame(
        [
            {"symbol": " aapl ", "name": "Apple Inc."},
            {"symbol": "AAPL", "name": "Should Skip"},
            {"symbol": "msft", "name": None},
            {"symbol": "", "name": "Empty"},
            {"symbol": None, "name": "Also Empty"},
        ]
    )

    normalized = script.normalize_dataframe(df)

    assert list(normalized["symbol"]) == ["AAPL", "MSFT"]
    assert normalized.loc[0, "name"] == "Apple Inc."
    assert normalized.loc[1, "name"] is None


def test_upsert_records_generates_on_conflict_clause():
    """验证 UPSERT 语句包含 ON CONFLICT 且会调用 commit。"""
    session = DummySession()
    records = [{"symbol": "AAPL", "name": "Apple"}, {"symbol": "MSFT", "name": None}]

    affected, ignored = script.upsert_records(cast(script.Session, session), records)

    assert affected == 2
    assert ignored == 0
    assert session.committed is True
    assert session.statements, "应至少执行一条语句"

    compiled_sql = str(
        session.statements[0].compile(dialect=postgresql.dialect())
    )
    assert "ON CONFLICT" in compiled_sql
    assert "DO UPDATE" in compiled_sql


def test_import_symbols_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """干跑模式下只读取数据，不触发数据库写入。"""
    fake_excel = tmp_path / "fake.xlsx"
    fake_excel.write_bytes(b"")  # 仅用于通过 exists 校验

    sample_df = pd.DataFrame(
        [
            {"symbol": "tsla", "name": "Tesla"},
            {"symbol": "brk.b", "name": "Berkshire Hathaway"},
        ]
    )

    monkeypatch.setattr(script.pd, "read_excel", lambda path: sample_df)

    # 干跑不应访问数据库，因此暂时设置 SessionLocal 为 None
    monkeypatch.setattr(script, "SessionLocal", None)

    script.import_symbols(fake_excel, dry_run=True)


def test_import_symbols_persists_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """实际导入路径应调用 upsert 并写入数据库。"""
    fake_excel = tmp_path / "fake.xlsx"
    fake_excel.write_bytes(b"")

    sample_df = pd.DataFrame(
        [
            {"symbol": "nvda", "name": "NVIDIA"},
            {"symbol": "goog", "name": "Alphabet"},
        ]
    )

    monkeypatch.setattr(script.pd, "read_excel", lambda path: sample_df)
    monkeypatch.setattr(script, "SessionLocal", DummySessionFactory())

    captured_records = []

    def fake_upsert(session, records):
        captured_records.extend(records)
        return len(records), 0

    monkeypatch.setattr(script, "upsert_records", fake_upsert)

    script.import_symbols(fake_excel, dry_run=False)

    assert len(captured_records) == 2
    assert captured_records[0]["symbol"] == "NVDA"
    assert captured_records[1]["name"] == "Alphabet"
