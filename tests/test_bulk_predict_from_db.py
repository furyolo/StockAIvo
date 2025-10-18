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
from stockaivo.schemas import StructuredPredictionExecutionMode
from stockaivo.scripts import bulk_predict_from_db as cli


def _build_config(
    *,
    batch_size: int = 2,
    dry_run: bool = False,
    output_path: Optional[Path] = None,
    execution_mode: StructuredPredictionExecutionMode = "full",
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
        execution_mode=execution_mode,  
    )


def _build_success_response(
    tickers: List[str],
    *,
    execution_mode: StructuredPredictionExecutionMode = "full",
) -> StructuredPredictionBatchResponse:
    """构造全部成功的批量响应"""
    items = [
        StructuredPredictionBatchItem(
            ticker=ticker,
            success=True,
            latency_seconds=0.05,
            retries=0,
            response=None,
            error=None,
            execution_mode=execution_mode,  
        )
        for ticker in tickers
    ]
    summary = StructuredPredictionBatchSummary(
        total=len(items),
        success=len(items),
        failed=0,
        duration_seconds=0.1,
        execution_mode_counts={execution_mode: len(items)},  # type: ignore[arg-type]
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
                        execution_mode="full",
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
                        execution_mode="full",
                    )
                )
        summary = StructuredPredictionBatchSummary(
            total=len(items),
            success=len(items) - len(failed),
            failed=len(failed),
            duration_seconds=0.2,
            execution_mode_counts={"full": len(items)},
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
    assert stats.failed_details[0]["execution_mode"] == "full"

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["aggregate_total"] == 4
    assert payload["aggregate_failed"] == 1
    runs = payload["runs"]
    assert len(runs) == 1
    last_run = runs[-1]
    assert last_run["total"] == 4
    assert last_run["failed"] == 1
    assert last_run["execution_mode"] == "full"
    assert last_run["failures"][0]["ticker"] == "DDD"
    assert last_run["failures"][0]["execution_mode"] == "full"
    stats_by_mode = payload["execution_mode_stats"]["full"]
    assert stats_by_mode["runs"] == 1
    assert stats_by_mode["failed"] == 1


def test_write_failures_skips_when_no_failures(tmp_path: Path):
    """没有失败时不应创建新的失败文件"""
    output = tmp_path / "failures.json"
    cli._write_failures(
        output_path=output,
        total=5,
        success=5,
        failed=0,
        failures=[],
        execution_mode="full",
    )
    assert not output.exists()


def test_write_failures_preserves_existing_on_success(tmp_path: Path):
    """历史失败文件存在时，全成功应保持原文件不变"""
    output = tmp_path / "failures.json"
    original_payload = {
        "updated_at": "2025-10-18T00:00:00",
        "aggregate_total": 3,
        "aggregate_success": 2,
        "aggregate_failed": 1,
        "runs": [
            {
                "generated_at": "2025-10-18T00:00:00",
                "total": 3,
                "success": 2,
                "failed": 1,
                "execution_mode": "full",
                "context": "batch_001",
                "failures": [
                    {
                        "ticker": "AAA",
                        "error": "mock",
                        "retries": 1,
                        "batch_index": 1,
                        "execution_mode": "full",
                    }
                ],
            }
        ],
        "execution_mode_stats": {
            "full": {"runs": 1, "total": 3, "success": 2, "failed": 1}
        },
    }
    output.write_text(json.dumps(original_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    before = output.read_text(encoding="utf-8")
    cli._write_failures(
        output_path=output,
        total=2,
        success=2,
        failed=0,
        failures=[],
        execution_mode="full",
        context_label="batch_001",
    )
    after = output.read_text(encoding="utf-8")
    assert after == before


def test_write_failures_same_context_different_mode(tmp_path: Path):
    """同一 context 不同执行模式应共存"""
    output = tmp_path / "failures.json"
    cli._write_failures(
        output_path=output,
        total=5,
        success=4,
        failed=1,
        failures=[{"ticker": "AAA"}],
        execution_mode="full",
        context_label="batch_001",
    )

    cli._write_failures(
        output_path=output,
        total=5,
        success=4,
        failed=1,
        failures=[{"ticker": "BBB"}],
        execution_mode="data_collection_only",
        context_label="batch_001",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    runs = payload["runs"]
    assert len(runs) == 2
    contexts = [run for run in runs if run.get("context") == "batch_001"]
    assert {run["execution_mode"] for run in contexts} == {"full", "data_collection_only"}


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
    assert all(item["execution_mode"] == "full" for item in stats.failed_details)


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


def test_progress_tracker_last_processed_count_increment(tmp_path: Path):
    """last_processed_count 应反映最近一次写入新增的股票数量"""
    progress_path = tmp_path / "progress.json"
    tracker = cli.ProgressTracker(progress_path)

    tracker.record_success(["AAA", "BBB"], execution_mode="full")
    payload_initial = json.loads(progress_path.read_text(encoding="utf-8"))
    assert payload_initial["summary"]["last_processed_count"] == 2

    tracker.record_success(["CCC"], execution_mode="full")
    payload_after = json.loads(progress_path.read_text(encoding="utf-8"))
    assert payload_after["summary"]["last_processed_count"] == 1
    assert payload_after["execution_modes"]["full"]["processed_count"] == 3

    # 再次写入重复股票，应记录为 0
    tracker.record_success(["CCC"], execution_mode="full")
    payload_dup = json.loads(progress_path.read_text(encoding="utf-8"))
    assert payload_dup["summary"]["last_processed_count"] == 0


@pytest.mark.asyncio
async def test_run_bulk_prediction_progress_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """进度文件结合 resume 参数应正确跳过已完成股票"""
    config = _build_config(batch_size=2, output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAPL", "MSFT", "TSLA"]

    progress_path = tmp_path / "progress.json"
    tracker = cli.ProgressTracker(progress_path)
    tracker.record_success(["AAPL"], execution_mode="full")

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
    assert data["schema_version"] == 2
    assert "processed_tickers" not in data
    assert "processed_count" not in data
    assert "execution_mode" not in data
    modes_block = data["execution_modes"]
    assert modes_block["full"]["processed_count"] == 3
    assert set(modes_block["full"]["processed_tickers"]) == {"AAPL", "MSFT", "TSLA"}
    summary = data["summary"]
    assert summary["total_execution_modes"] == 1
    assert summary["total_processed_count"] == 3
    assert summary["total_unique_tickers"] == 3
    assert summary["last_execution_mode"] == "full"
    assert summary["last_processed_count"] == 2
    assert "last_processed_sample" not in summary

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


@pytest.mark.asyncio
async def test_progress_tracker_supports_multiple_execution_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """同一进度文件应记录多个执行模式的数据"""
    progress_path = tmp_path / "progress.json"
    tracker = cli.ProgressTracker(progress_path)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAA", "BBB"]

    calls: List[List[str]] = []

    async def success_dispatch(request, config_obj, limiter):
        calls.append(list(request.tickers))
        return _build_success_response(
            request.tickers,
            execution_mode=request.execution_mode,
        )

    monkeypatch.setattr(cli, "dispatch_batch_request", success_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    config_full = _build_config(batch_size=2, output_path=None, execution_mode="full")
    await cli.run_bulk_prediction(
        config_full,
        symbol_provider=fake_provider,
        progress_tracker=tracker,
        resume=True,
    )

    config_data_collection = _build_config(
        batch_size=2,
        output_path=None,
        execution_mode="data_collection_only",
    )
    await cli.run_bulk_prediction(
        config_data_collection,
        symbol_provider=fake_provider,
        progress_tracker=tracker,
        resume=True,
    )

    assert calls == [["AAA", "BBB"], ["AAA", "BBB"]]

    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert "processed_tickers" not in payload
    assert "execution_mode" not in payload

    modes = payload["execution_modes"]
    assert set(modes.keys()) == {"full", "data_collection_only"}
    assert modes["full"]["processed_count"] == 2
    assert set(modes["full"]["processed_tickers"]) == {"AAA", "BBB"}
    assert modes["data_collection_only"]["processed_count"] == 2
    assert set(modes["data_collection_only"]["processed_tickers"]) == {"AAA", "BBB"}

    summary = payload["summary"]
    assert summary["total_execution_modes"] == 2
    assert summary["total_processed_count"] == 4
    assert summary["total_unique_tickers"] == 2
    assert summary["last_execution_mode"] == "data_collection_only"
    assert summary["last_processed_count"] == 2
    assert "last_processed_sample" not in summary


def test_progress_tracker_can_load_legacy_format(tmp_path: Path):
    """进度跟踪器应兼容旧版顶层字段格式并写回新结构"""
    progress_path = tmp_path / "legacy.json"
    legacy_payload = {
        "updated_at": "2025-10-18T00:00:00",
        "processed_count": 1,
        "processed_tickers": ["AAPL"],
        "execution_mode": "full",
    }
    progress_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

    tracker = cli.ProgressTracker(progress_path)
    pending = tracker.filter_pending(["AAPL", "MSFT"], resume=True, execution_mode="full")
    assert pending == ["MSFT"]

    tracker.record_success(["MSFT"], execution_mode="full")

    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert "processed_tickers" not in payload
    modes = payload["execution_modes"]
    assert set(modes["full"]["processed_tickers"]) == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_run_bulk_prediction_data_collection_mode(monkeypatch: pytest.MonkeyPatch):
    """data_collection_only 模式应透传到批量请求与汇总"""
    config = _build_config(batch_size=2, execution_mode="data_collection_only", output_path=None)

    def fake_provider(limit: Optional[int]) -> List[str]:
        return ["AAA", "BBB"]

    recorded_modes: List[str] = []

    async def success_dispatch(request, config_obj, limiter):
        recorded_modes.append(request.execution_mode)
        return _build_success_response(
            request.tickers,
            execution_mode=request.execution_mode,
        )

    monkeypatch.setattr(cli, "dispatch_batch_request", success_dispatch)
    monkeypatch.setattr(cli, "get_batch_prediction_rate_limiter", lambda: None)

    stats = await cli.run_bulk_prediction(config, symbol_provider=fake_provider)

    assert recorded_modes == ["data_collection_only"]
    assert stats.total_tickers == 2
    assert stats.success == 2
    assert stats.failed == 0
    assert stats.failed_details == []
