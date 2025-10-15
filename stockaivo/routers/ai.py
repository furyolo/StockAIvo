"""
AI分析路由器 - 提供AI投资决策分析的API端点
"""

import asyncio
import logging
from datetime import date
from time import perf_counter
from types import TracebackType
from typing import Any, AsyncContextManager, List, Optional, Protocol, Set

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from stockaivo import schemas
from stockaivo.ai.orchestrator import (
    run_ai_analysis,
    run_ai_analysis_parallel_stream,
    run_ai_analysis_stream,
)
from stockaivo.ai.structured_prediction_service import run_structured_prediction
from stockaivo.database import SessionLocal
from stockaivo.dependencies import DatabaseDep, get_batch_prediction_rate_limiter
from stockaivo.exceptions import AIServiceException, ValidationException, create_error_response

logger = logging.getLogger(__name__)

# 创建路由器
StructuredPredictionBatchRequest = schemas.StructuredPredictionBatchRequest
StructuredPredictionBatchResponse = schemas.StructuredPredictionBatchResponse
StructuredPredictionResponse = schemas.StructuredPredictionResponse
StructuredPredictionBatchItem = schemas.StructuredPredictionBatchItem
StructuredPredictionBatchSummary = schemas.StructuredPredictionBatchSummary
StructuredPredictionRequest = schemas.StructuredPredictionRequest
NestedStructuredPredictionRequest = schemas.NestedStructuredPredictionRequest


router = APIRouter(prefix="/ai", tags=["AI分析"])

# 移除全局状态管理，改为直接流式响应


class BatchPredictionRateLimiter(Protocol):
    """批量预测限流器协议占位，用于后续 Task D 接入"""

    async def acquire(self, bucket: str) -> None:  # pragma: no cover - 协议定义
        ...

    def guard(self, bucket: str) -> AsyncContextManager[None]:  # pragma: no cover - 协议定义
        ...

    def compute_backoff(self, attempt: int) -> float:  # pragma: no cover - 协议定义
        ...

    @property
    def max_retry_attempts(self) -> int:  # pragma: no cover - 协议定义
        ...


class _NullAsyncContext:
    """空实现的异步上下文管理器，用于无限流场景"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        return False


class _AcquireReleaseContext:
    """包装具有 acquire/release 方法的限流器"""

    def __init__(self, limiter: Any, bucket: str) -> None:
        self._limiter = limiter
        self._bucket = bucket

    async def __aenter__(self) -> None:
        await self._limiter.acquire(self._bucket)  # type: ignore[attr-defined]
        return None

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        release = getattr(self._limiter, "release", None)
        if callable(release):
            await release(self._bucket, exc_type, exc, tb)  # type: ignore[arg-type]
        return False


def _rate_limit_guard(
    limiter: Optional[BatchPredictionRateLimiter],
    bucket: str,
) -> AsyncContextManager[None]:
    """根据限流器实现动态生成上下文管理器"""
    if limiter is None:
        return _NullAsyncContext()

    guard_callable = getattr(limiter, "guard", None)
    if callable(guard_callable):
        try:
            context = guard_callable(bucket)
            if context is not None:
                return context
        except Exception as exc:  # pragma: no cover - 记录日志并降级
            logger.warning("创建限流 guard 时发生异常，将回退到 acquire 模式: %s", exc)

    if hasattr(limiter, "acquire"):
        return _AcquireReleaseContext(limiter, bucket)  # type: ignore[arg-type]

    logger.debug("限流器缺少 guard/acquire 接口，回退到无操作模式")
    return _NullAsyncContext()


__all__ = [
    "StructuredPredictionBatchRequest",
    "StructuredPredictionBatchResponse",
    "StructuredPredictionRequest",
    "StructuredPredictionResponse",
    "StructuredPredictionBatchItem",
    "StructuredPredictionBatchSummary",
    "NestedStructuredPredictionRequest",
]


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    ticker: str = Field(..., description="股票代码，例如 'AAPL'")
    end_date: Optional[date] = Field(None, description="自定义结束日期 (YYYY-MM-DD)，开始日期由系统根据数据周期自动计算")


@router.post("/analyze-sequential")
async def analyze_stock_sequential(request: AnalysisRequest) -> StreamingResponse:
    """
    启动AI投资分析并顺序流式返回结果。

    分析代理将按顺序执行，提供逐步的分析过程展示。
    这是一个简化的单一端点，直接返回流式分析结果。
    """
    try:
        logger.info(f"收到AI顺序分析请求: {request.ticker}, 结束日期: {request.end_date}")

        custom_date_range = None
        if request.end_date:
            custom_date_range = {
                "end_date": request.end_date.isoformat()
            }

        # 直接创建并返回流式响应
        analysis_generator = run_ai_analysis_stream(
            ticker=request.ticker,
            custom_date_range=custom_date_range
        )

        async def stream_wrapper():
            """包装生成器以处理错误和清理"""
            try:
                async for event in analysis_generator:
                    yield event
            except asyncio.CancelledError:
                logger.warning("客户端断开了连接，AI顺序分析流已取消。")
                # 客户端断开连接时不需要发送错误事件
            except Exception as e:
                logger.error(f"AI顺序分析过程中发生错误: {e}")
                # 使用统一的错误响应格式
                error_response = create_error_response(
                    message=f"AI顺序分析过程中发生错误: {str(e)}",
                    status_code=500
                )
                error_event = f"data: {error_response}\n\n"
                yield error_event
            finally:
                logger.info("AI顺序分析流结束。")

        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

    except ValueError as e:
        logger.error(f"AI顺序分析请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"启动AI顺序分析失败: {e}")
        raise AIServiceException(f"启动AI顺序分析失败: {str(e)}")


@router.post("/analyze-parallel")
async def analyze_stock_parallel_stream(request: AnalysisRequest) -> StreamingResponse:
    """
    启动AI投资分析并行流式返回结果。

    三个分析代理（技术分析、基本面分析、新闻情感分析）将并行执行，
    提供更快的分析速度和更好的用户体验。
    """
    try:
        logger.info(f"收到AI并行分析请求: {request.ticker}, 结束日期: {request.end_date}")

        custom_date_range = None
        if request.end_date:
            custom_date_range = {
                "end_date": request.end_date.isoformat()
            }

        # 创建并行流式响应
        analysis_generator = run_ai_analysis_parallel_stream(
            ticker=request.ticker,
            custom_date_range=custom_date_range
        )

        async def parallel_stream_wrapper():
            """包装并行生成器以处理错误和清理"""
            try:
                async for event in analysis_generator:
                    yield event
            except asyncio.CancelledError:
                logger.warning("客户端断开了连接，AI并行分析流已取消。")
                # 客户端断开连接时不需要发送错误事件
            except Exception as e:
                logger.error(f"AI并行分析过程中发生错误: {e}")
                # 使用统一的错误响应格式
                error_response = create_error_response(
                    message=f"AI并行分析过程中发生错误: {str(e)}",
                    status_code=500
                )
                error_event = f"data: {error_response}\n\n"
                yield error_event
            finally:
                logger.info("AI并行分析流结束。")

        return StreamingResponse(parallel_stream_wrapper(), media_type="text/event-stream")

    except ValueError as e:
        logger.error(f"AI并行分析请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"启动AI并行分析失败: {e}")
        raise AIServiceException(f"启动AI并行分析失败: {str(e)}")


@router.post("/predict-structured", response_model=StructuredPredictionResponse)
async def analyze_stock_structured_prediction(
    request: StructuredPredictionRequest,
    db: DatabaseDep,
    rate_limiter: Optional[BatchPredictionRateLimiter] = Depends(get_batch_prediction_rate_limiter),
) -> schemas.StructuredPredictionResponse:
    """
    生成股票结构化预测。
    
    基于综合AI分析生成概率化的股价预测，包括：
    - 预测概率值（0.0-1.0）
    - 预测方向（UP/DOWN）
    - 置信度（HIGH/MEDIUM/LOW） 
    - 详细推理说明
    
    注意：需要技术分析成功执行才能生成预测结果。
    """
    
    try:
        logger.info("收到结构化预测请求: %s, 结束日期: %s", request.ticker, request.end_date)

        if rate_limiter is not None:
            await rate_limiter.acquire("tickertick")
            await rate_limiter.acquire("akshare")

        async with _rate_limit_guard(rate_limiter, "ai_predict"):
            return await run_structured_prediction(request, db)

    except ValueError as e:
        logger.error(f"结构化预测请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except AIServiceException as e:
        # 重新抛出AI服务异常
        raise e
    except Exception as e:
        logger.error(f"结构化预测失败: {e}")
        raise AIServiceException(f"结构化预测失败: {str(e)}")


@router.post(
    "/predict-structured/batch",
    response_model=StructuredPredictionBatchResponse,
    summary="批量生成结构化预测结果",
)
async def analyze_stock_structured_prediction_batch(
    request: StructuredPredictionBatchRequest,
    db: DatabaseDep,
    rate_limiter: Optional[BatchPredictionRateLimiter] = Depends(get_batch_prediction_rate_limiter),
) -> schemas.StructuredPredictionBatchResponse:
    """
    批量生成多只股票的结构化预测。

    - 使用 `max_concurrency` 控制并发度，避免击穿外部数据源与LLM限流。
    - 对失败任务可按 `max_retries` 与退避间隔进行自动重试。
    - 汇总输出每只股票的执行结果、耗时与失败原因，便于外部系统重试。
    """

    # 1. 预处理与参数校验
    normalized_tickers: List[str] = []
    seen: Set[str] = set()
    for ticker in request.tickers:
        normalized = ticker.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tickers.append(normalized)

    if not normalized_tickers:
        raise ValidationException("tickers 列表不能为空。")

    if request.max_concurrency < 1:
        raise ValidationException("max_concurrency 必须至少为 1。")

    if request.save_to_db and SessionLocal is None and request.max_concurrency > 1:
        logger.warning(
            "SessionLocal 未初始化，批量结构化预测降级为串行执行以避免共享会话冲突。"
        )

    effective_concurrency = min(
        request.max_concurrency if SessionLocal or not request.save_to_db else 1,
        len(normalized_tickers),
    )
    semaphore = asyncio.Semaphore(effective_concurrency)

    batch_start = perf_counter()

    async def process_ticker(ticker: str) -> StructuredPredictionBatchItem:
        single_request = StructuredPredictionRequest(
            ticker=ticker,
            end_date=request.end_date,
            save_to_db=request.save_to_db,
        )
        limiter_retry_cap = (
            rate_limiter.max_retry_attempts if rate_limiter is not None else request.max_retries
        )
        attempts_allowed = min(request.max_retries, limiter_retry_cap) + 1
        attempt_start = perf_counter()
        last_error: Optional[str] = None
        latest_response: Optional[StructuredPredictionResponse] = None

        for attempt in range(1, attempts_allowed + 1):
            session_to_use = None
            try:
                async with semaphore:
                    if request.save_to_db:
                        if SessionLocal is not None:
                            session_to_use = SessionLocal()
                        else:
                            session_to_use = db
                    if rate_limiter is not None:
                        await rate_limiter.acquire("tickertick")
                        await rate_limiter.acquire("akshare")

                    async with _rate_limit_guard(rate_limiter, "ai_predict"):
                        latest_response = await run_structured_prediction(
                            single_request,
                            session_to_use,
                        )

                if latest_response.success:
                    latency = perf_counter() - attempt_start
                    return StructuredPredictionBatchItem(
                        ticker=ticker,
                        success=True,
                        latency_seconds=latency,
                        retries=attempt - 1,
                        response=latest_response,
                        error=None,
                    )

                last_error = latest_response.error or "结构化预测失败"
                logger.warning(
                    "结构化预测失败（待重试）: ticker=%s, attempt=%d/%d, error=%s",
                    ticker,
                    attempt,
                    attempts_allowed,
                    last_error,
                )
            except Exception as exc:  # 捕获服务层抛出的异常
                last_error = str(exc)
                logger.error(
                    "结构化预测执行异常: ticker=%s, attempt=%d/%d, error=%s",
                    ticker,
                    attempt,
                    attempts_allowed,
                    last_error,
                )
            finally:
                if session_to_use is not None and session_to_use is not db:
                    try:
                        session_to_use.close()
                    except Exception:  # pragma: no cover - 记录即可
                        logger.debug("关闭临时数据库会话时发生异常", exc_info=True)

            if attempt < attempts_allowed:
                base_backoff = request.retry_delay_seconds * (2 ** (attempt - 1))
                limiter_backoff = (
                    rate_limiter.compute_backoff(attempt)
                    if rate_limiter is not None
                    else 0.0
                )
                backoff_seconds = max(base_backoff, limiter_backoff)
                if backoff_seconds > 0:
                    logger.info(
                        "批量结构化预测退避等待 %.2f 秒: ticker=%s, attempt=%d/%d",
                        backoff_seconds,
                        ticker,
                        attempt,
                        attempts_allowed,
                    )
                    await asyncio.sleep(backoff_seconds)

        latency = perf_counter() - attempt_start
        return StructuredPredictionBatchItem(
            ticker=ticker,
            success=False,
            latency_seconds=latency,
            retries=attempts_allowed - 1,
            response=None,
            error=last_error,
        )

    # 2. 并发执行批量任务
    tasks = [asyncio.create_task(process_ticker(ticker)) for ticker in normalized_tickers]
    results = await asyncio.gather(*tasks)

    # 3. 汇总统计与日志
    total_duration = perf_counter() - batch_start
    success_count = sum(1 for item in results if item.success)
    failed_items = [item for item in results if not item.success]

    logger.info(
        "批量结构化预测完成: 总数=%d, 成功=%d, 失败=%d, 总耗时=%.2fs",
        len(results),
        success_count,
        len(failed_items),
        total_duration,
    )

    if failed_items:
        logger.warning(
            "批量结构化预测失败列表: %s",
            ", ".join(item.ticker for item in failed_items),
        )

    response_summary = StructuredPredictionBatchSummary(
        total=len(results),
        success=success_count,
        failed=len(failed_items),
        duration_seconds=total_duration,
    )

    return StructuredPredictionBatchResponse(
        results=results,
        summary=response_summary,
        failed_tickers=[item.ticker for item in failed_items],
    )
