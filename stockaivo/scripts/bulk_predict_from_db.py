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
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, Iterable, List, Optional, Sequence, cast

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
class BatchRunStats:
    """批量执行统计"""

    total_tickers: int
    batch_count: int
    success: int
    failed: int
    failed_details: List[dict]


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
        default=Path("bulk_predict_failures.json"),
        help="失败列表输出路径（默认 bulk_predict_failures.json），传入 '-' 可跳过写文件",
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
) -> BatchRunStats:
    """批量执行主流程"""
    provider = symbol_provider or fetch_well_known_symbols
    tickers = provider(config.limit)
    total = len(tickers)

    if not tickers:
        logger.warning("未从数据库读取到任何股票代码，流程结束。")
        return BatchRunStats(0, 0, 0, 0, [])

    logger.info("读取到 %d 个股票代码，将按每批 %d 个处理。", total, config.batch_size)

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

    for batch_index, batch in enumerate(chunked(tickers, config.batch_size), start=1):
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

        for item in response.results:
            if not item.success:
                failure_details.append(
                    {
                        "ticker": item.ticker,
                        "error": item.error,
                        "retries": item.retries,
                        "latency_seconds": item.latency_seconds,
                        "batch_index": batch_index,
                    }
                )

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
        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "generated_at": datetime.now().isoformat(),
            "total": total,
            "success": success,
            "failed": failed,
            "failures": failures,
        }

        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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

    try:
        stats = asyncio.run(run_bulk_prediction(config))
    except KeyboardInterrupt:
        logger.warning("用户中断执行。")
        raise SystemExit(1)

    if stats.failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
