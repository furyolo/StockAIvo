#!/usr/bin/env python3
"""
从 bulk_predict_failures.json 读取失败股票列表并重新触发批量预测。

典型使用流程：
    1. 先运行 bulk_predict_from_db.py 批量预测并生成失败列表；
    2. 使用本脚本读取失败 JSON，再次调用批量预测接口进行补跑；
    3. 结果仍会写入新的失败文件，便于多轮重试或审计。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, cast

from dotenv import load_dotenv

from stockaivo.scripts.bulk_predict_from_db import (
    BulkPredictConfig,
    ProgressTracker,
    run_bulk_prediction,
)
from stockaivo.schemas import StructuredPredictionExecutionMode


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="根据失败 JSON 列表补跑结构化预测"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("logs/batch_failures/bulk_predict_failures.json"),
        help="待读取的失败列表 JSON 文件路径（默认 logs/batch_failures/bulk_predict_failures.json）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/batch_failures/bulk_predict_failures_retry.json"),
        help="补跑后失败列表输出路径（默认 logs/batch_failures/bulk_predict_failures_retry.json）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="每批提交的股票数量（默认 10）",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="批量接口最大并发数（默认 3）",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="单票最大重试次数（默认 2）",
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
        help="可选统一 end_date (YYYY-MM-DD)，默认由服务端自动推算",
    )
    parser.add_argument(
        "--api-base-url",
        type=str,
        default=None,
        help="FastAPI 服务地址，设置后优先通过 HTTP 调用（例如 http://127.0.0.1:8000）",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="HTTP 调用时附加的 Authorization 头部，可选",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=300.0,
        help="HTTP 调用超时时间（秒），默认 300 秒",
    )
    parser.add_argument(
        "--execution-mode",
        type=str,
        default=None,
        choices=["full", "data_collection_only"],
        help="执行模式：默认根据失败列表推断，必要时可手动指定 full 或 data_collection_only",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅补跑失败列表前 N 支股票，默认补跑全部",
    )
    parser.add_argument(
        "--run-context",
        type=str,
        default=None,
        help="当失败文件包含多个运行记录时，指定 context 标识以选择对应批次（默认选择最新记录）",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path("logs/batch_progress/bulk_progress.json"),
        help="进度文件路径（默认 logs/batch_progress/bulk_progress.json），用于同步成功股票记录",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否根据进度文件跳过已成功股票（默认开启，可通过 --no-resume 关闭）",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="运行前清空进度文件并重新记录",
    )
    return parser


def _parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 字符串"""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse 将输出错误信息
        raise argparse.ArgumentTypeError(f"无法解析日期 {value}: {exc}") from exc


def _load_failure_entries(path: Path, run_context: Optional[str] = None) -> tuple[List[Dict[str, object]], Optional[str], Optional[str]]:
    """读取失败 JSON 并返回带元数据的去重股票失败记录"""
    if not path.exists():
        raise FileNotFoundError(f"未找到失败列表文件：{path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    selected_block: Dict[str, object]
    selected_context: Optional[str] = None
    failures: List[Dict[str, object]]
    execution_mode: Optional[object]

    runs = data.get("runs")
    if isinstance(runs, list) and runs:
        selected_run: Optional[Dict[str, object]] = None
        if run_context:
            for run in runs:
                if isinstance(run, dict) and run.get("context") == run_context:
                    selected_run = run
                    selected_context = str(run.get("context") or "")
                    break
            if selected_run is None:
                raise ValueError(f"失败文件中未找到 context={run_context} 的记录。")
        else:
            # 默认选择最新一条记录
            for run in reversed(runs):
                if isinstance(run, dict):
                    selected_context = str(run.get("context") or "")
                    selected_run = run
                    break
        if selected_run is None:
            raise ValueError("失败文件的 runs 列表中没有有效的记录。")
        selected_block = selected_run
    else:
        selected_block = data

    raw_failures = selected_block.get("failures") or []
    execution_mode = selected_block.get("execution_mode")
    mode_value: Optional[str] = execution_mode if isinstance(execution_mode, str) else None
    ordered: "OrderedDict[str, Dict[str, object]]" = OrderedDict()

    if isinstance(raw_failures, list):
        for item in raw_failures:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker", "")).strip()
            if not ticker or ticker in ordered:
                continue
            normalized = dict(item)
            normalized["ticker"] = ticker
            ordered[ticker] = normalized

    if not ordered:
        legacy = data.get("failed_tickers") or []
        for ticker in legacy:
            ticker_str = str(ticker).strip()
            if not ticker_str or ticker_str in ordered:
                continue
            ordered[ticker_str] = {"ticker": ticker_str}

    return list(ordered.values()), mode_value, selected_context


def _load_failed_tickers(path: Path, run_context: Optional[str] = None) -> List[str]:
    """保持向后兼容，返回失败股票代码列表"""
    entries, _, _ = _load_failure_entries(path, run_context=run_context)
    return [str(entry["ticker"]) for entry in entries]


def configure_logging(level: str) -> None:
    """初始化日志配置"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def main() -> None:
    """脚本入口"""
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)

    try:
        failure_entries, file_mode, selected_context = _load_failure_entries(
            args.input, run_context=args.run_context
        )
    except Exception as exc:
        logger.error("读取失败列表文件出错：%s", exc)
        raise SystemExit(1) from exc

    if selected_context:
        logger.info("已选择失败记录 context=%s", selected_context)
    elif args.run_context:
        logger.info("按照 context=%s 过滤失败记录，但源文件未提供 context 字段。", args.run_context)

    if not failure_entries:
        logger.info("失败列表为空，无需补跑。")
        return

    mode_candidates: Set[str] = set()
    if file_mode:
        mode_candidates.add(file_mode)
    for entry in failure_entries:
        entry_mode = entry.get("execution_mode")
        if isinstance(entry_mode, str) and entry_mode:
            mode_candidates.add(entry_mode)

    if args.execution_mode:
        resolved_mode = cast(StructuredPredictionExecutionMode, args.execution_mode)
        if mode_candidates and resolved_mode not in mode_candidates:
            logger.warning(
                "失败列表记录的执行模式为 %s，但将按参数 execution_mode=%s 补跑。",
                sorted(mode_candidates),
                resolved_mode,
            )
    elif len(mode_candidates) == 1:
        resolved_mode = cast(
            StructuredPredictionExecutionMode, next(iter(mode_candidates))
        )
    else:
        if len(mode_candidates) > 1:
            logger.warning(
                "失败列表包含多个执行模式 %s，将默认使用 full，可通过 --execution-mode 指定。",
                sorted(mode_candidates),
            )
        resolved_mode = cast(StructuredPredictionExecutionMode, "full")

    logger.info("补跑执行模式：%s", resolved_mode)

    limit = args.limit if args.limit and args.limit > 0 else None
    if limit is not None:
        to_process_entries = failure_entries[:limit]
        remaining_entries = failure_entries[limit:]
    else:
        to_process_entries = failure_entries
        remaining_entries = []

    if not to_process_entries:
        logger.info("limit=%s 导致本次无股票需要补跑。", args.limit)
        return

    tickers = [entry["ticker"] for entry in to_process_entries]

    logger.info(
        "将补跑 %d 支股票（失败总数 %d），来源文件 %s",
        len(tickers),
        len(failure_entries),
        args.input,
    )
    if remaining_entries:
        logger.info("因 limit 参数剩余 %d 支股票待后续补跑。", len(remaining_entries))
        logger.info(
            "若需继续分批补跑，可将 --input 指向本次输出文件 %s 并重复执行。",
            args.output,
        )

    config = BulkPredictConfig(
        batch_size=args.batch_size,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        save_to_db=args.save_to_db,
        end_date=args.end_date,
        output_path=None,
        dry_run=False,
        limit=len(tickers),
        api_base_url=args.api_base_url,
        api_key=args.api_key,
        request_timeout=args.request_timeout,
        execution_mode=resolved_mode,
    )

    if config.execution_mode == "data_collection_only" and config.save_to_db:
        logger.info("数据采集模式不会写入数据库，save_to_db 参数将被忽略。")

    def provide_tickers(limit_override: Optional[int]) -> List[str]:
        """返回补跑股票列表"""
        resolved_limit = limit_override or len(tickers)
        return [str(ticker) for ticker in tickers[:resolved_limit]]

    progress_tracker: Optional[ProgressTracker] = None
    progress_path = args.progress_file
    if progress_path and progress_path != Path("-"):
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
                symbol_provider=provide_tickers,
                progress_tracker=progress_tracker,
                resume=args.resume,
            )
        )
    except KeyboardInterrupt:
        logger.warning("用户中断补跑执行。")
        raise SystemExit(1) from None

    failed_details_map: "OrderedDict[str, Dict[str, object]]" = OrderedDict()
    for detail in stats.failed_details:
        ticker = str(detail.get("ticker", "")).strip()
        if not ticker or ticker in failed_details_map:
            continue
        normalized = dict(detail)
        normalized["ticker"] = ticker
        if not normalized.get("execution_mode"):
            normalized["execution_mode"] = resolved_mode
        failed_details_map[ticker] = normalized

    successful_tickers = [ticker for ticker in tickers if ticker not in failed_details_map]
    if successful_tickers:
        logger.info("成功补跑 %d 支股票，将从失败列表中移除。", len(successful_tickers))
    else:
        logger.info("本次补跑未移除任何股票，全部保留在失败列表。")

    updated_failures = list(remaining_entries)
    updated_failures.extend(failed_details_map.values())
    for entry in updated_failures:
        if isinstance(entry, dict) and not entry.get("execution_mode"):
            entry["execution_mode"] = resolved_mode

    if args.output and args.output != Path("-"):
        try:
            if not args.output.parent.exists():
                args.output.parent.mkdir(parents=True, exist_ok=True)
            payload: Dict[str, object] = {
                "generated_at": datetime.now().isoformat(),
                "total": len(tickers),
                "success": len(successful_tickers),
                "failed": len(failed_details_map),
                "outstanding": len(updated_failures),
                "execution_mode": resolved_mode,
                "failures": updated_failures,
                "source_context": selected_context or args.run_context,
            }
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if updated_failures:
                logger.warning("仍有 %d 支股票待补跑，已写入 %s。", len(updated_failures), args.output)
            else:
                logger.info("所有失败股票已补跑成功，输出文件 %s 为空列表。", args.output)
        except Exception as exc:  # pragma: no cover - 记录即可
            logger.error("写入补跑结果文件失败：%s", exc)

    if stats.failed > 0:
        logger.warning(
            "补跑仍有 %d 支股票失败，请检查输出文件 %s",
            stats.failed,
            args.output,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
