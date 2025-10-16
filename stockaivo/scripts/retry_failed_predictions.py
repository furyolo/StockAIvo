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
from typing import Dict, List, Optional

from dotenv import load_dotenv

from stockaivo.scripts.bulk_predict_from_db import (
    BulkPredictConfig,
    run_bulk_prediction,
)


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
    return parser


def _parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 字符串"""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse 将输出错误信息
        raise argparse.ArgumentTypeError(f"无法解析日期 {value}: {exc}") from exc


def _load_failure_entries(path: Path) -> List[Dict[str, object]]:
    """读取失败 JSON 并返回带元数据的去重股票失败记录"""
    if not path.exists():
        raise FileNotFoundError(f"未找到失败列表文件：{path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    failures = data.get("failures") or []
    ordered: "OrderedDict[str, Dict[str, object]]" = OrderedDict()

    if isinstance(failures, list):
        for item in failures:
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

    return list(ordered.values())


def _load_failed_tickers(path: Path) -> List[str]:
    """保持向后兼容，返回失败股票代码列表"""
    entries = _load_failure_entries(path)
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
        failure_entries = _load_failure_entries(args.input)
    except Exception as exc:
        logger.error("读取失败列表文件出错：%s", exc)
        raise SystemExit(1) from exc

    if not failure_entries:
        logger.info("失败列表为空，无需补跑。")
        return

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
    )

    def provide_tickers(limit_override: Optional[int]) -> List[str]:
        """返回补跑股票列表"""
        resolved_limit = limit_override or len(tickers)
        return [str(ticker) for ticker in tickers[:resolved_limit]]

    try:
        stats = asyncio.run(
            run_bulk_prediction(
                config,
                symbol_provider=provide_tickers,
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
        failed_details_map[ticker] = normalized

    successful_tickers = [ticker for ticker in tickers if ticker not in failed_details_map]
    if successful_tickers:
        logger.info("成功补跑 %d 支股票，将从失败列表中移除。", len(successful_tickers))
    else:
        logger.info("本次补跑未移除任何股票，全部保留在失败列表。")

    updated_failures = list(remaining_entries)
    updated_failures.extend(failed_details_map.values())

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
                "failures": updated_failures,
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
