"""
bulk_predict_from_db CLI 脚本测试
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pytest

from stockaivo.routers.ai import (
    StructuredPredictionBatchItem,
    StructuredPredictionBatchResponse,
    StructuredPredictionBatchSummary,
)
from stockaivo.scripts import bulk_predict_from_db as cli


def _build_config(
    *,
    batch_size: int = 2,
    dry_run: bool = False,
    output_path: Optional[Path] = None,
) -> cli.BulkPredictConfig:
    """快捷构建配置对象"""
    return cli.BulkPredictConfig(
        batch_size=batch_size,
        max_concurrency=5,
        max_retries=1,
        retry_delay=5.0,
        save_to_db=True,
        end_date=None,
        output_path=output_path,
        dry_run=dry_run,
        limit=None,
        api_base_url=None,
        api_key=None,
        request_timeout=300.0,
    )


@pytest.mark.asyncio
async def test_run_bulk_prediction_dry_run():
    """dry-run 模式仅统计批次数"""
    config = _build_config(batch_size=3, dry_run=True, output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        assert limit is None
        return ["AAPL", "MSFT", "TSLA", "NVDA"]

    stats = await cli.run_bulk_prediction(config, symbol_provider=fake_provider)

    assert stats.total_tickers == 4
    assert stats.batch_count == 2  # 4 个股票，批大小 3 -> 2 批
    assert stats.success == 0
    assert stats.failed == 0
    assert stats.failed_details == []


@pytest.mark.asyncio
async def test_run_bulk_prediction_batches_and_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """验证批次拆分、失败记录与输出文件"""
    output = tmp_path / "failures.json"
    config = _build_config(batch_size=3, output_path=output)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAA", "BBB", "CCC", "DDD"]

    calls = []

    async def fake_dispatch(request, config_obj, limiter):
        calls.append(request)
        failed = []
        items = []
        for ticker in request.tickers:
            if ticker == "DDD":
                failed.append(ticker)
                items.append(
                    StructuredPredictionBatchItem(
                        ticker=ticker,
                        success=False,
                        latency_seconds=0.12,
                        retries=1,
                        response=None,
                        error="LLM 服务不可用",
                    )
                )
            else:
                items.append(
                    StructuredPredictionBatchItem(
                        ticker=ticker,
                        success=True,
                        latency_seconds=0.08,
                        retries=0,
                        response=None,
                        error=None,
                    )
                )
        summary = StructuredPredictionBatchSummary(
            total=len(items),
            success=len(items) - len(failed),
            failed=len(failed),
            duration_seconds=0.2,
        )
        return StructuredPredictionBatchResponse(
            results=items,
            summary=summary,
            failed_tickers=failed,
        )

    monkeypatch.setattr(cli, "dispatch_batch_request", fake_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    stats = await cli.run_bulk_prediction(config, symbol_provider=fake_provider)

    assert len(calls) == 2  # 4 个股票，批大小 3 -> 2 批
    assert stats.total_tickers == 4
    assert stats.success == 3
    assert stats.failed == 1
    assert len(stats.failed_details) == 1
    assert stats.failed_details[0]["ticker"] == "DDD"
    assert stats.failed_details[0]["batch_index"] == 2

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["total"] == 4
    assert payload["failed"] == 1
    assert payload["failures"][0]["ticker"] == "DDD"


@pytest.mark.asyncio
async def test_run_bulk_prediction_handles_dispatch_error(monkeypatch: pytest.MonkeyPatch):
    """dispatch 抛出异常时应被标记为失败"""
    config = _build_config(batch_size=2, output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAPL", "MSFT"]

    async def failing_dispatch(request, config_obj, limiter):
        raise RuntimeError("网络异常")

    monkeypatch.setattr(cli, "dispatch_batch_request", failing_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    stats = await cli.run_bulk_prediction(config, symbol_provider=fake_provider)

    assert stats.failed == 2
    assert len(stats.failed_details) == 2
    assert {item["ticker"] for item in stats.failed_details} == {"AAPL", "MSFT"}
    assert all("网络异常" in (item["error"] or "") for item in stats.failed_details)
