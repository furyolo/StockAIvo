#!/usr/bin/env python3
"""
批量读取 well_known_stock_symbols 表并调用结构化预测批量接口的 CLI。

默认行为：
    - 从数据库读取全部常用股票代码；
    - 按批次调用 `/ai/predict-structured/batch`；
    - 默认不指定 end_date，保持服务端自动推算；
    - 默认并发为 5，最大重试 1 次；
    - 将失败列表写入 JSON 文件，便于后续重试。

可通过 `--api-base-url` 指定已有 FastAPI 服务地址走 HTTP 调用；
若未配置，则直接复用内部路由函数与限流器。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, Iterable, List, Optional, Sequence, Set, cast

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from stockaivo.database import SessionLocal
from stockaivo.dependencies import get_batch_prediction_rate_limiter
from stockaivo.models import WellKnownStockSymbol
from stockaivo.routers.ai import (
    StructuredPredictionBatchItem,
    StructuredPredictionBatchRequest,
    StructuredPredictionBatchResponse,
    StructuredPredictionBatchSummary,
    analyze_stock_structured_prediction_batch,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BulkPredictConfig:
    """CLI 参数配置"""

    batch_size: int
    max_concurrency: int
    max_retries: int
    retry_delay: float
    save_to_db: bool
    end_date: Optional[date]
    output_path: Optional[Path]
    dry_run: bool
    limit: Optional[int]
    api_base_url: Optional[str]
    api_key: Optional[str]
    request_timeout: float


@dataclass(slots=True)
class ManifestGenerationConfig:
    """批次清单生成参数"""

    output_dir: Path
    batch_size: int
    shuffle: bool
    suggested_concurrency: int
    prefix: str
    seed: Optional[int]
    limit: Optional[int]


@dataclass(slots=True)
class BatchRunStats:
    """批量执行统计"""

    total_tickers: int
    batch_count: int
    success: int
    failed: int
    failed_details: List[dict]


class ProgressTracker:
    """处理批量执行进度的工具"""

    def __init__(self, path: Path):
        self.path = path
        self._processed_list: List[str] = []
        self._processed_set: Set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"读取进度文件失败：{self.path}: {exc}") from exc

        raw_entries = data.get("processed_tickers") or data.get("tickers") or []
        if not isinstance(raw_entries, list):
            raise RuntimeError(f"进度文件格式不正确：{self.path}")

        for symbol in raw_entries:
            normalized = _normalize_symbol(symbol)
            if normalized and normalized not in self._processed_set:
                self._processed_set.add(normalized)
                self._processed_list.append(normalized)

    def reset(self) -> None:
        """清空进度文件"""
        if self.path.exists():
            try:
                self.path.unlink()
            except Exception as exc:
                raise RuntimeError(f"删除进度文件失败：{self.path}: {exc}") from exc
        self._processed_list.clear()
        self._processed_set.clear()

    def processed_count(self) -> int:
        return len(self._processed_list)

    def filter_pending(self, tickers: Sequence[str], *, resume: bool) -> List[str]:
        if not resume:
            return list(tickers)
        return [ticker for ticker in tickers if ticker not in self._processed_set]

    def record_success(self, tickers: Iterable[str]) -> None:
        updated = False
        for ticker in tickers:
            normalized = _normalize_symbol(ticker)
            if not normalized or normalized in self._processed_set:
                continue
            self._processed_set.add(normalized)
            self._processed_list.append(normalized)
            updated = True
        if updated:
            self._save()

    def _save(self) -> None:
        payload = {
            "updated_at": datetime.now().isoformat(),
            "processed_count": len(self._processed_list),
            "processed_tickers": self._processed_list,
        }
        _write_json_atomic(self.path, payload)


def _normalize_symbol(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _normalize_and_deduplicate(symbols: Iterable[object]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for symbol in symbols:
        normalized = _normalize_symbol(symbol)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _load_symbols_from_file(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"未找到清单文件：{path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        entries: List[str] = []
        for line in text.replace(",", "\n").splitlines():
            candidate = line.strip()
            if candidate:
                entries.append(candidate)
        return _normalize_and_deduplicate(entries)

    if isinstance(data, list):
        return _normalize_and_deduplicate(data)

    if isinstance(data, dict):
        for key in ("tickers", "symbols", "items"):
            maybe = data.get(key)
            if isinstance(maybe, list):
                return _normalize_and_deduplicate(maybe)
        raise ValueError(f"JSON 清单文件缺少 tickers/symbols/items 列表：{path}")

    raise ValueError(f"不支持的清单文件结构：{path}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="从 well_known_stock_symbols 表批量运行结构化预测"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="每批提交的股票数量（默认 20）",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
        help="批量接口的并发上限（默认 5）",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="批量接口单票最大重试次数（默认 1）",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="指数退避基础等待秒数（默认 5.0 秒）",
    )
    parser.add_argument(
        "--save-to-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在服务端写入数据库（默认启用，可通过 --no-save-to-db 关闭）",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        default=None,
        help="可选的统一 end_date (YYYY-MM-DD)，默认由服务端自动推算",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/batch_failures/bulk_predict_failures.json"),
        help="失败列表输出路径（默认 logs/batch_failures/bulk_predict_failures.json），传入 '-' 可跳过写文件",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 个股票代码，默认处理全部",
    )
    parser.add_argument(
        "--api-base-url",
        type=str,
        default=None,
        help="可选的 FastAPI 服务地址（例如 http://127.0.0.1:8000），设置后优先走 HTTP 调用",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="HTTP 调用时附加 Authorization 头部，可选",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=300.0,
        help="HTTP 调用超时时间（秒），默认 300 秒",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要处理的批次数量，不实际调用批量接口",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--generate-manifests",
        action="store_true",
        help="启用批次清单生成模式，仅生成 manifest 文件并退出",
    )
    parser.add_argument(
        "--manifest-output-dir",
        type=Path,
        default=Path("data/batch_manifests"),
        help="批次清单输出目录（默认 data/batch_manifests）",
    )
    parser.add_argument(
        "--manifest-batch-size",
        type=int,
        default=30,
        help="清单中每批次的股票数量（默认 30）",
    )
    parser.add_argument(
        "--manifest-concurrency",
        type=int,
        default=3,
        help="清单推荐的最大并发配置（默认 3）",
    )
    parser.add_argument(
        "--manifest-prefix",
        type=str,
        default="batch_",
        help="清单文件名前缀（默认 batch_）",
    )
    parser.add_argument(
        "--manifest-shuffle",
        action="store_true",
        help="生成清单前随机打散股票顺序",
    )
    parser.add_argument(
        "--manifest-seed",
        type=int,
        default=None,
        help="清单随机乱序的随机种子（默认无种子，使用系统随机）",
    )
    parser.add_argument(
        "--include-symbols-file",
        type=Path,
        default=None,
        help="从指定 JSON/CSV/文本清单中读取需处理的股票列表，设置后优先使用该清单",
    )
    parser.add_argument(
        "--exclude-symbols-file",
        type=Path,
        default=None,
        help="从指定 JSON/CSV/文本清单中排除股票，常用于跳过问题票",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path("logs/batch_progress/bulk_progress.json"),
        help="进度文件路径（默认 logs/batch_progress/bulk_progress.json），记录已成功处理的股票",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否根据进度文件跳过已完成股票（默认开启，可通过 --no-resume 关闭）",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="运行前清空进度文件并重新记录",
    )
    return parser


def configure_logging(level: str) -> None:
    """初始化日志配置"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def fetch_well_known_symbols(limit: Optional[int] = None) -> List[str]:
    """从数据库读取 well_known_stock_symbols.symbol 列"""
    if SessionLocal is None:
        raise RuntimeError("数据库 SessionLocal 未初始化，无法读取股票列表。")

    session: Session = SessionLocal()
    try:
        stmt = select(WellKnownStockSymbol.symbol).order_by(WellKnownStockSymbol.symbol)
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)
        result = session.execute(stmt)
        symbols = [row[0] for row in result if row[0]]
        return symbols
    finally:
        session.close()


def chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    """简单的批次切片"""
    total = len(items)
    if size <= 0:
        raise ValueError("batch size 必须大于 0")
    for idx in range(0, total, size):
        yield list(items[idx : idx + size])


def _write_json_atomic(path: Path, payload: dict) -> None:
    """原子写入 JSON 文件"""
    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:  # pragma: no cover - 记录即可
        logger.error("写入 JSON 文件 %s 时发生异常: %s", path, exc)
        raise


def generate_manifests(config: ManifestGenerationConfig) -> None:
    """生成批次清单 manifest 文件"""
    tickers = fetch_well_known_symbols(config.limit)
    if not tickers:
        logger.warning("未读取到任何股票代码，停止生成批次清单。")
        return

    normalized = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    unique_tickers = list(dict.fromkeys(normalized))
    if config.shuffle and len(unique_tickers) > 1:
        rng = random.Random(config.seed)
        rng.shuffle(unique_tickers)

    if config.batch_size <= 0:
        raise ValueError("manifest-batch-size 必须大于 0")

    batches = list(chunked(unique_tickers, config.batch_size))
    if not batches:
        logger.warning("没有需要输出的批次，终止生成。")
        return

    timestamp = datetime.now().isoformat()
    manifest_entries = []

    for index, batch in enumerate(batches, start=1):
        batch_id = f"{config.prefix}{index:03d}"
        payload = {
            "batch_id": batch_id,
            "generated_at": timestamp,
            "ticker_count": len(batch),
            "tickers": batch,
            "suggested_max_concurrency": config.suggested_concurrency,
        }
        file_path = config.output_dir / f"{batch_id}.json"
        _write_json_atomic(file_path, payload)
        manifest_entries.append(
            {
                "batch_id": batch_id,
                "file": str(file_path.name),
                "ticker_count": len(batch),
            }
        )

    index_payload = {
        "generated_at": timestamp,
        "total_tickers": len(unique_tickers),
        "batch_size": config.batch_size,
        "total_batches": len(manifest_entries),
        "suggested_max_concurrency": config.suggested_concurrency,
        "manifest_files": manifest_entries,
    }
    index_path = config.output_dir / "manifest_index.json"
    _write_json_atomic(index_path, index_payload)

    logger.info(
        "批次清单生成完成：总股票=%d，批次数=%d，输出目录=%s",
        len(unique_tickers),
        len(manifest_entries),
        config.output_dir,
    )


async def dispatch_batch_request(
    request: StructuredPredictionBatchRequest,
    config: BulkPredictConfig,
    limiter,
) -> StructuredPredictionBatchResponse:
    """
    分发批量预测请求。
    优先尝试 HTTP，失败后回退到内部调用。
    """
    if config.api_base_url:
        try:
            response = await _dispatch_via_http(request, config)
            logger.debug("HTTP 调用成功，已使用外部接口。")
            return response
        except Exception as exc:  # pragma: no cover - 记录即可
            logger.error("HTTP 调用批量预测失败，将回退到内部调用: %s", exc)
            logger.debug("HTTP 调用异常详情", exc_info=True)

    return await _dispatch_internal(request, limiter)


async def _dispatch_via_http(
    request: StructuredPredictionBatchRequest,
    config: BulkPredictConfig,
) -> StructuredPredictionBatchResponse:
    """通过 HTTP POST 调用现有批量接口"""
    base_url = cast(str, config.api_base_url)
    base_url = base_url.rstrip("/")
    url = f"{base_url}/ai/predict-structured/batch"
    payload = request.model_dump(mode="json", exclude_none=True)
    headers = {}
    if config.api_key:
        headers["Authorization"] = config.api_key

    timeout = httpx.Timeout(config.request_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return StructuredPredictionBatchResponse.model_validate(data)


async def _dispatch_internal(
    request: StructuredPredictionBatchRequest,
    limiter,
) -> StructuredPredictionBatchResponse:
    """直接复用 FastAPI 路由函数"""
    if SessionLocal is None:
        raise RuntimeError("数据库 SessionLocal 未初始化，无法执行内部批量预测。")

    session: Session = SessionLocal()
    try:
        return await analyze_stock_structured_prediction_batch(request, session, limiter)
    finally:
        session.close()


def _build_failure_response(
    tickers: Sequence[str],
    error_message: str,
) -> StructuredPredictionBatchResponse:
    """将批次整体失败转换为结构化响应"""
    items = [
        StructuredPredictionBatchItem(
            ticker=ticker,
            success=False,
            latency_seconds=0.0,
            retries=0,
            response=None,
            error=error_message,
        )
        for ticker in tickers
    ]
    summary = StructuredPredictionBatchSummary(
        total=len(items),
        success=0,
        failed=len(items),
        duration_seconds=0.0,
    )
    return StructuredPredictionBatchResponse(
        results=items,
        summary=summary,
        failed_tickers=[item.ticker for item in items],
    )


async def run_bulk_prediction(
    config: BulkPredictConfig,
    *,
    symbol_provider: Optional[Callable[[Optional[int]], List[str]]] = None,
    dispatcher: Optional[
        Callable[[StructuredPredictionBatchRequest], Awaitable[StructuredPredictionBatchResponse]]
    ] = None,
    exclude_symbols: Optional[Sequence[str]] = None,
    progress_tracker: Optional[ProgressTracker] = None,
    resume: bool = True,
) -> BatchRunStats:
    """批量执行主流程"""
    provider = symbol_provider or fetch_well_known_symbols
    tickers = provider(config.limit)
    normalized_tickers = _normalize_and_deduplicate(tickers)

    if not normalized_tickers:
        logger.warning("未获取到任何股票代码，流程结束。")
        return BatchRunStats(0, 0, 0, 0, [])

    logger.info(
        "读取到 %d 个股票代码，初始批大小=%d。",
        len(normalized_tickers),
        config.batch_size,
    )

    exclude_set: Set[str] = set()
    if exclude_symbols:
        exclude_set = {
            symbol for symbol in (_normalize_symbol(item) for item in exclude_symbols) if symbol
        }

    filtered_tickers = (
        [ticker for ticker in normalized_tickers if ticker not in exclude_set]
        if exclude_set
        else normalized_tickers
    )

    skipped_by_exclude = len(normalized_tickers) - len(filtered_tickers)
    if skipped_by_exclude:
        logger.info("根据排除清单跳过 %d 支股票。", skipped_by_exclude)

    pending_tickers = filtered_tickers
    if progress_tracker:
        pending_tickers = progress_tracker.filter_pending(filtered_tickers, resume=resume)
        skipped_by_progress = len(filtered_tickers) - len(pending_tickers)
        if resume and skipped_by_progress:
            logger.info("根据进度文件跳过 %d 支已完成股票。", skipped_by_progress)
        elif not resume and progress_tracker.processed_count():
            logger.info(
                "进度文件记录已有 %d 支股票，本次仍将重新执行。",
                progress_tracker.processed_count(),
            )

    total = len(pending_tickers)
    if total == 0:
        logger.warning("待处理股票数量为 0，流程结束。")
        return BatchRunStats(0, 0, 0, 0, [])

    logger.info("本次准备处理 %d 支股票，将按每批 %d 支执行。", total, config.batch_size)

    if config.dry_run:
        batch_count = (total + config.batch_size - 1) // config.batch_size
        logger.info("干跑模式已开启，将需要 %d 个批次。", batch_count)
        return BatchRunStats(total, batch_count, 0, 0, [])

    limiter = None
    if dispatcher is None:
        limiter = get_batch_prediction_rate_limiter()

    async def default_dispatch(
        request: StructuredPredictionBatchRequest,
    ) -> StructuredPredictionBatchResponse:
        try:
            return await dispatch_batch_request(request, config, limiter)
        except Exception as exc:
            logger.error("批次调用失败，所有股票标记失败: %s", exc)
            return _build_failure_response(request.tickers, str(exc))

    dispatch = dispatcher or default_dispatch

    total_success = 0
    total_failed = 0
    batch_counter = 0
    failure_details: List[dict] = []
    wall_clock_start = perf_counter()

    for batch_index, batch in enumerate(chunked(pending_tickers, config.batch_size), start=1):
        request = StructuredPredictionBatchRequest(
            tickers=batch,
            end_date=config.end_date,
            save_to_db=config.save_to_db,
            max_concurrency=config.max_concurrency,
            max_retries=config.max_retries,
            retry_delay_seconds=config.retry_delay,
        )

        batch_start = perf_counter()
        response = await dispatch(request)
        batch_duration = perf_counter() - batch_start

        batch_counter += 1
        total_success += response.summary.success
        total_failed += response.summary.failed

        logger.info(
            "批次 %d 完成：总计=%d，成功=%d，失败=%d，耗时=%.2f 秒",
            batch_index,
            response.summary.total,
            response.summary.success,
            response.summary.failed,
            batch_duration,
        )

        batch_success_tickers: List[str] = []
        for item in response.results:
            if item.success:
                batch_success_tickers.append(item.ticker)
                continue
            failure_details.append(
                {
                    "ticker": item.ticker,
                    "error": item.error,
                    "retries": item.retries,
                    "latency_seconds": item.latency_seconds,
                    "batch_index": batch_index,
                }
            )
        if progress_tracker and batch_success_tickers:
            progress_tracker.record_success(batch_success_tickers)

    if progress_tracker:
        logger.info("进度文件已更新，累计成功股票数=%d。", progress_tracker.processed_count())

    total_duration = perf_counter() - wall_clock_start
    logger.info(
        "批量执行完毕：股票总数=%d，批次数=%d，成功=%d，失败=%d，总耗时=%.2f 秒",
        total,
        batch_counter,
        total_success,
        total_failed,
        total_duration,
    )

    if config.output_path and config.output_path != Path("-"):
        _write_failures(config.output_path, total, total_success, total_failed, failure_details)

    return BatchRunStats(total, batch_counter, total_success, total_failed, failure_details)


def _write_failures(
    output_path: Path,
    total: int,
    success: int,
    failed: int,
    failures: List[dict],
) -> None:
    """将失败列表写入 JSON 文件"""
    try:
        payload = {
            "generated_at": datetime.now().isoformat(),
            "total": total,
            "success": success,
            "failed": failed,
            "failures": failures,
        }
        _write_json_atomic(output_path, payload)
        if failed > 0:
            logger.warning("失败列表已写入 %s，共 %d 条。", output_path, failed)
        else:
            logger.info("无失败记录，仍写入空文件 %s 以供审计。", output_path)
    except Exception as exc:  # pragma: no cover - 记录即可
        logger.error("写入失败列表文件时发生异常: %s", exc)


def _parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 字符串"""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse 会处理异常展示
        raise argparse.ArgumentTypeError(f"无法解析日期 {value}: {exc}") from exc


def main() -> None:
    """CLI 入口"""
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)

    config = BulkPredictConfig(
        batch_size=args.batch_size,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        save_to_db=args.save_to_db,
        end_date=args.end_date,
        output_path=None if args.output == Path("-") else args.output,
        dry_run=args.dry_run,
        limit=args.limit,
        api_base_url=args.api_base_url,
        api_key=args.api_key,
        request_timeout=args.request_timeout,
    )

    if args.generate_manifests:
        manifest_config = ManifestGenerationConfig(
            output_dir=args.manifest_output_dir,
            batch_size=args.manifest_batch_size,
            shuffle=args.manifest_shuffle,
            suggested_concurrency=args.manifest_concurrency,
            prefix=args.manifest_prefix,
            seed=args.manifest_seed,
            limit=args.limit if args.limit and args.limit > 0 else None,
        )
        try:
            generate_manifests(manifest_config)
        except Exception as exc:
            logger.error("生成批次清单时发生异常：%s", exc)
            raise SystemExit(1) from exc
        return

    include_symbols: Optional[List[str]] = None
    symbol_provider_override: Optional[Callable[[Optional[int]], List[str]]] = None
    if args.include_symbols_file:
        try:
            include_symbols = _load_symbols_from_file(args.include_symbols_file)
        except Exception as exc:
            logger.error("读取清单文件 %s 失败：%s", args.include_symbols_file, exc)
            raise SystemExit(1) from exc

        if not include_symbols:
            logger.warning("清单文件 %s 未包含有效股票，流程结束。", args.include_symbols_file)
            return

        logger.info(
            "从清单文件 %s 读取到 %d 支股票，将作为本次处理列表。",
            args.include_symbols_file,
            len(include_symbols),
        )

        def provide_from_manifest(limit_override: Optional[int]) -> List[str]:
            if limit_override and limit_override > 0:
                return include_symbols[:limit_override]
            return list(include_symbols)

        symbol_provider_override = provide_from_manifest

    exclude_symbols: Optional[List[str]] = None
    if args.exclude_symbols_file:
        try:
            exclude_symbols = _load_symbols_from_file(args.exclude_symbols_file)
        except Exception as exc:
            logger.error("读取排除清单 %s 失败：%s", args.exclude_symbols_file, exc)
            raise SystemExit(1) from exc
        if exclude_symbols:
            logger.info(
                "排除清单 %s 包含 %d 支股票，将跳过这些股票。",
                args.exclude_symbols_file,
                len(exclude_symbols),
            )

    progress_tracker: Optional[ProgressTracker] = None
    progress_path = args.progress_file
    if progress_path is not None and progress_path != Path("-"):
        try:
            progress_tracker = ProgressTracker(progress_path)
        except Exception as exc:
            logger.error("读取进度文件 %s 失败：%s", progress_path, exc)
            raise SystemExit(1) from exc
        if args.reset_progress:
            try:
                progress_tracker.reset()
                logger.info("已重置进度文件 %s。", progress_path)
            except Exception as exc:
                logger.error("重置进度文件 %s 失败：%s", progress_path, exc)
                raise SystemExit(1) from exc
        elif progress_tracker.processed_count():
            logger.info(
                "进度文件 %s 已记录 %d 支成功股票。",
                progress_path,
                progress_tracker.processed_count(),
            )
    elif args.reset_progress:
        logger.warning("指定了 --reset-progress 但未启用进度文件，将忽略该参数。")

    try:
        stats = asyncio.run(
            run_bulk_prediction(
                config,
                symbol_provider=symbol_provider_override,
                exclude_symbols=exclude_symbols,
                progress_tracker=progress_tracker,
                resume=args.resume,
            )
        )
    except KeyboardInterrupt:
        logger.warning("用户中断执行。")
        raise SystemExit(1)

    if stats.failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
