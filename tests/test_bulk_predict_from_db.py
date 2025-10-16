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


def _build_success_response(tickers: List[str]) -> StructuredPredictionBatchResponse:
    """构造全部成功的批量响应"""
    items = [
        StructuredPredictionBatchItem(
            ticker=ticker,
            success=True,
            latency_seconds=0.05,
            retries=0,
            response=None,
            error=None,
        )
        for ticker in tickers
    ]
    summary = StructuredPredictionBatchSummary(
        total=len(items),
        success=len(items),
        failed=0,
        duration_seconds=0.1,
    )
    return StructuredPredictionBatchResponse(
        results=items,
        summary=summary,
        failed_tickers=[],
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


@pytest.mark.asyncio
async def test_run_bulk_prediction_exclude_symbols(monkeypatch: pytest.MonkeyPatch):
    """排除清单应在执行前过滤"""
    config = _build_config(batch_size=2, output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAA", "BBB", "CCC"]

    calls: List[List[str]] = []

    async def success_dispatch(request, config_obj, limiter):
        calls.append(list(request.tickers))
        return _build_success_response(request.tickers)

    monkeypatch.setattr(cli, "dispatch_batch_request", success_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    stats = await cli.run_bulk_prediction(
        config,
        symbol_provider=fake_provider,
        exclude_symbols=["BBB"],
    )

    # 只有 AAA 与 CCC 被提交
    assert stats.total_tickers == 2
    assert stats.success == 2
    assert stats.failed == 0
    assert calls == [["AAA", "CCC"]]


@pytest.mark.asyncio
async def test_run_bulk_prediction_progress_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """进度文件结合 resume 参数应正确跳过已完成股票"""
    config = _build_config(batch_size=2, output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAPL", "MSFT", "TSLA"]

    progress_path = tmp_path / "progress.json"
    tracker = cli.ProgressTracker(progress_path)
    tracker.record_success(["AAPL"])

    async def success_dispatch(request, config_obj, limiter):
        return _build_success_response(request.tickers)

    monkeypatch.setattr(cli, "dispatch_batch_request", success_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    # 第一次运行应仅处理 MSFT、TSLA
    stats_first = await cli.run_bulk_prediction(
        config,
        symbol_provider=fake_provider,
        progress_tracker=tracker,
        resume=True,
    )
    assert stats_first.total_tickers == 2
    assert stats_first.success == 2
    data = json.loads(progress_path.read_text(encoding="utf-8"))
    assert data["processed_count"] == 3
    assert set(data["processed_tickers"]) == {"AAPL", "MSFT", "TSLA"}

    # 第二次运行 resume=True，应直接跳过所有股票
    stats_second = await cli.run_bulk_prediction(
        config,
        symbol_provider=fake_provider,
        progress_tracker=tracker,
        resume=True,
    )
    assert stats_second.total_tickers == 0
    assert stats_second.batch_count == 0

    # resume=False 时，应重新执行全部股票
    stats_third = await cli.run_bulk_prediction(
        config,
        symbol_provider=fake_provider,
        progress_tracker=tracker,
        resume=False,
    )
    assert stats_third.total_tickers == 3
    assert stats_third.success == 3
