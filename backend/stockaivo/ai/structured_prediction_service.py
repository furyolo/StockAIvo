"""
结构化预测核心服务

该模块承载 `/ai/predict-structured` 单票预测流程的业务逻辑，用于在路由层之外复用。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple, cast

from sqlalchemy.orm import Session

from stockaivo.ai.agents import (
    data_collection_agent,
    fundamental_analysis_agent,
    news_sentiment_analysis_agent,
    structured_prediction_agent,
    technical_analysis_agent,
    _is_llm_error_result,
)
from stockaivo.ai.state import GraphState
from stockaivo.cache_manager import StructuredPredictionPendingEntry, save_structured_prediction_pending_cache
from stockaivo.data_service import get_market_aware_current_date
from stockaivo.exceptions import AIServiceException
from stockaivo.models import StockPrediction
from stockaivo.schemas import (
    StructuredPredictionExecutionMode,
    StructuredPredictionRequest,
    StructuredPredictionResponse,
)

logger = logging.getLogger(__name__)


async def run_structured_prediction(
    request: StructuredPredictionRequest,
    db: Optional[Session] = None,
) -> StructuredPredictionResponse:
    """运行结构化预测主流程"""
    execution_mode: StructuredPredictionExecutionMode = request.execution_mode
    logger.info(
        "开始处理结构化预测请求: %s | 模式: %s",
        request.ticker,
        execution_mode,
    )

    analysis_state = _initialize_graph_state(request)

    await _prepare_analysis_state(analysis_state, execution_mode)

    if execution_mode == "data_collection_only":
        data_summary = _summarize_data_collection(analysis_state)
        timestamp = datetime.now().isoformat()
        reasoning = _format_data_collection_reasoning(request.ticker, data_summary)
        required_datasets = ("daily_prices", "weekly_prices")
        missing_datasets = [
            dataset for dataset in required_datasets if data_summary.get(dataset, 0) <= 0
        ]
        success_flag = len(missing_datasets) == 0
        error_message: Optional[str] = None
        if not success_flag:
            joined_missing = ", ".join(missing_datasets)
            error_message = f"缺少关键数据集: {joined_missing}"
            logger.error("数据采集模式缺失关键数据: %s -> %s", request.ticker, joined_missing)
            reasoning = f"{reasoning}\n⚠️ 注意：{error_message}"

        prediction_payload = {
            "success": success_flag,
            "timestamp": timestamp,
            "reasoning": reasoning,
        }
        if error_message:
            prediction_payload["error"] = error_message
        response = _build_response(
            request,
            analysis_state,
            prediction_payload,
            execution_mode=execution_mode,
            data_summary=data_summary,
        )
        if request.save_to_db:
            logger.debug(
                "数据采集模式不会将结构化预测结果写入 Redis 待持久化队列或数据库，已忽略 save_to_db 标志: %s",
                request.ticker,
            )
        logger.info("数据采集模式完成: %s, 摘要=%s", request.ticker, data_summary)
        return response

    prediction_payload = await structured_prediction_agent(analysis_state)
    prediction_data = prediction_payload.get("structured_prediction", {})

    success = bool(prediction_data.get("success"))
    response = _build_response(
        request,
        analysis_state,
        prediction_data,
        execution_mode=execution_mode,
    )

    if success and request.save_to_db and execution_mode == "full":
        _persist_prediction_if_needed(db, request, analysis_state, prediction_data)

    return response


def _initialize_graph_state(request: StructuredPredictionRequest) -> GraphState:
    """根据请求初始化 LangGraph State"""
    state: GraphState = GraphState(
        ticker=request.ticker,
        custom_date_range=None,
        raw_data={},
        analysis_results={},
        final_report="",
        market_analysis=None,
    )

    if request.end_date:
        state["custom_date_range"] = {"end_date": request.end_date.isoformat()}

    return state


async def _prepare_analysis_state(
    state: GraphState,
    execution_mode: StructuredPredictionExecutionMode,
) -> None:
    """执行数据收集与多 Agent 分析，准备结构化预测所需状态"""
    try:
        data_result = await data_collection_agent(
            state,
            include_news=execution_mode == "full",
            include_intraday=execution_mode == "full",
        )
    except Exception as exc:  # pragma: no cover - 兜底日志
        logger.error("数据收集阶段失败: %s", exc)
        raise AIServiceException(f"数据收集阶段失败: {exc}") from exc

    _merge_state(state, data_result)

    if execution_mode == "full":
        await _run_parallel_analysis(state)


async def _run_parallel_analysis(state: GraphState) -> None:
    """并行执行技术、基本面、新闻情感分析"""
    try:
        analysis_tasks = [
            technical_analysis_agent(state),
            fundamental_analysis_agent(state),
            news_sentiment_analysis_agent(state),
        ]

        results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
    except Exception as exc:  # pragma: no cover - asyncio gather 内部异常
        logger.error("分析阶段调度失败: %s", exc)
        raise AIServiceException(f"分析阶段调度失败: {exc}") from exc

    _handle_technical_analysis(state, results[0])
    _handle_optional_analysis(
        state=state,
        agent_result=results[1],
        agent_label="基本面分析",
        analyst_key="fundamental_analyst",
    )
    _handle_optional_analysis(
        state=state,
        agent_result=results[2],
        agent_label="新闻情感分析",
        analyst_key="news_sentiment_analyst",
    )

    logger.info("多智能体分析完成: %s", state.get("ticker"))


def _handle_technical_analysis(state: GraphState, result: Any) -> None:
    """处理技术分析结果（必须成功）"""
    if isinstance(result, Exception):
        logger.error("技术分析失败: %s", result)
        raise AIServiceException(f"技术分析失败，无法生成结构化预测: {result}")

    if isinstance(result, dict):
        _merge_state(state, result)

    analysis_results = cast(Dict[str, Any], state.get("analysis_results", {}))
    technical_analysis = analysis_results.get("technical_analyst")

    if not technical_analysis or _is_llm_error_result(technical_analysis):
        error_msg = (
            f"技术分析失败，无法生成结构化预测: {technical_analysis}"
            if technical_analysis
            else "技术分析未返回有效结果，无法生成结构化预测"
        )
        logger.error(error_msg)
        raise AIServiceException(error_msg)

    logger.info("技术分析完成: %s", state.get("ticker"))


def _handle_optional_analysis(
    state: GraphState,
    agent_result: Any,
    agent_label: str,
    analyst_key: str,
) -> None:
    """处理可选分析的结果并记录日志"""
    if isinstance(agent_result, Exception):
        logger.warning("%s失败，继续执行: %s", agent_label, agent_result)
        return

    if not isinstance(agent_result, dict):
        logger.info("%s无可合并结果，跳过", agent_label)
        return

    _merge_state(state, agent_result)

    analysis_results = cast(Dict[str, Any], state.get("analysis_results", {}))
    analyst_result = analysis_results.get(analyst_key)

    if analyst_result is None:
        logger.info("%s未返回有效结果，跳过", agent_label)
        return

    if _is_llm_error_result(analyst_result):
        logger.warning("%s LLM 调用失败: %s", agent_label, analyst_result)
        return

    logger.info("%s完成", agent_label)


def _merge_state(state: GraphState, updates: Dict[str, Any]) -> None:
    """将 Agent 返回结果合并回 GraphState"""
    state_dict = cast(Dict[str, Any], state)

    for key, value in updates.items():
        if key in {"analysis_results", "raw_data"} and isinstance(value, dict):
            current = cast(Dict[str, Any], state_dict.get(key) or {})
            current.update(value)
            state_dict[key] = current
        else:
            state_dict[key] = value


def _summarize_data_collection(state: GraphState) -> Dict[str, int]:
    """生成数据采集模式下的记录数摘要"""
    raw_data = cast(Dict[str, Any], state.get("raw_data") or {})
    summary: Dict[str, int] = {}

    for key, value in raw_data.items():
        if isinstance(value, dict):
            data_records = value.get("data")
            if isinstance(data_records, list):
                summary[key] = len(data_records)
            else:
                summary[key] = len(value)
        elif isinstance(value, list):
            summary[key] = len(value)
        else:
            summary[key] = 0

    return summary


def _format_data_collection_reasoning(
    ticker: str,
    summary: Dict[str, int],
) -> str:
    """构造数据采集模式下的推理说明"""
    if not summary:
        return f"数据采集模式已执行，但未获取到 {ticker} 的有效数据。"

    parts = [f"{dataset}: {count} 条" for dataset, count in summary.items()]
    joined = "，".join(parts)
    return f"数据采集模式已完成，采集 {ticker} 的数据摘要：{joined}。"


def _build_response(
    request: StructuredPredictionRequest,
    state: GraphState,
    prediction_data: Dict[str, Any],
    *,
    execution_mode: StructuredPredictionExecutionMode,
    data_summary: Optional[Dict[str, int]] = None,
) -> StructuredPredictionResponse:
    """根据预测结果构建响应模型"""
    timestamp = prediction_data.get("timestamp") or datetime.now().isoformat()
    market_context = _resolve_market_context(state, request)

    response_kwargs: Dict[str, Any] = {
        "success": bool(prediction_data.get("success")),
        "prediction_probability": prediction_data.get("prediction_probability"),
        "direction": prediction_data.get("direction"),
        "confidence_level": prediction_data.get("confidence_level"),
        "reasoning": prediction_data.get("reasoning"),
        "ticker": request.ticker,
        "timestamp": timestamp,
        "market_aware_date": market_context[0],
        "error": prediction_data.get("error"),
    }
    response_kwargs["execution_mode"] = execution_mode
    response_kwargs["data_collection_summary"] = data_summary

    # market_context[0] 可能为日期，也可能为空
    market_date = market_context[0]
    if isinstance(market_date, date):
        response_kwargs["market_aware_date"] = market_date.isoformat()
    elif market_date is None:
        response_kwargs["market_aware_date"] = None
    else:
        response_kwargs["market_aware_date"] = str(market_date)

    if execution_mode == "data_collection_only":
        # 数据采集模式不返回预测结果相关字段
        response_kwargs["prediction_probability"] = None
        response_kwargs["direction"] = None
        response_kwargs["confidence_level"] = None
        response_kwargs["error"] = None if response_kwargs["success"] else response_kwargs["error"]
        logger.debug(
            "数据采集模式响应构建完成: %s, 摘要=%s",
            request.ticker,
            data_summary,
        )
        return StructuredPredictionResponse(**response_kwargs)

    if not response_kwargs["success"]:
        return StructuredPredictionResponse(**response_kwargs)

    # 成功时清理错误字段
    response_kwargs["error"] = None

    probability = response_kwargs.get("prediction_probability")
    if probability is not None:
        logger.info(
            "结构化预测成功: %s, 方向=%s, 概率=%.2f",
            request.ticker,
            response_kwargs.get("direction"),
            probability,
        )
    else:
        logger.info(
            "结构化预测成功: %s, 方向=%s",
            request.ticker,
            response_kwargs.get("direction"),
        )

    return StructuredPredictionResponse(**response_kwargs)


def _persist_prediction_if_needed(
    db: Optional[Session],
    request: StructuredPredictionRequest,
    state: GraphState,
    prediction_data: Dict[str, Any],
) -> None:
    """根据需要将预测结果持久化"""
    market_date, target_date, trading_days = _resolve_market_context(state, request)

    if not isinstance(market_date, date):
        logger.warning("无法解析市场日期，跳过持久化: %s", market_date)
        return
    direction_normalized = str(prediction_data.get("direction") or "UNKNOWN").upper()
    confidence_normalized = str(prediction_data.get("confidence_level") or "UNKNOWN").upper()

    payload: StructuredPredictionPendingEntry = StructuredPredictionPendingEntry(
        ticker=request.ticker,
        market_aware_date=market_date.isoformat(),
        target_date=target_date.isoformat(),
        trading_days_count=trading_days,
        prediction_probability=prediction_data.get("prediction_probability"),
        direction=direction_normalized,
        confidence_level=confidence_normalized,
        reasoning=prediction_data.get("reasoning"),
        prediction_timestamp=str(prediction_data.get("timestamp") or datetime.now(timezone.utc).isoformat()),
    )

    cache_key = save_structured_prediction_pending_cache(payload)
    if cache_key:
        logger.info(
            "结构化预测结果已写入待持久化缓存: %s -> %s",
            request.ticker,
            cache_key,
        )
        return

    if db is None:
        logger.warning(
            "结构化预测写入缓存失败且未提供数据库会话，结果将不会自动持久化: %s",
            request.ticker,
        )
        return

    try:
        fallback_record = StockPrediction(
            ticker=request.ticker,
            market_aware_date=market_date,
            target_date=target_date,
            trading_days_count=trading_days,
            prediction_probability=prediction_data.get("prediction_probability"),
            direction=direction_normalized,
            confidence_level=confidence_normalized,
            reasoning=prediction_data.get("reasoning", ""),
        )

        db.merge(fallback_record)
        db.commit()
        logger.info(
            "结构化预测已直接写入数据库(缓存失败): %s, 市场日期=%s, 目标日期=%s",
            request.ticker,
            market_date,
            target_date,
        )
    except Exception as exc:  # pragma: no cover - SQLAlchemy 抛错
        logger.error("结构化预测缓存失败后写入数据库也失败: %s", exc)
        db.rollback()


def _resolve_market_context(
    state: GraphState,
    request: StructuredPredictionRequest,
) -> Tuple[Optional[date], date, int]:
    """提取市场上下文信息"""
    market_analysis = state.get("market_analysis")

    if market_analysis is not None:
        market_aware_date = getattr(market_analysis, "market_aware_date", None)
        target_date = getattr(
            market_analysis,
            "target_friday_date",
            request.end_date or date.today(),
        )
        trading_days = getattr(market_analysis, "trading_days_count", 5)
        return market_aware_date, target_date, trading_days

    market_aware_date = get_market_aware_current_date()
    target_date = request.end_date or date.today()
    trading_days = 5
    return market_aware_date, target_date, trading_days


__all__ = ["run_structured_prediction"]
