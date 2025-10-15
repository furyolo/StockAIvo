#!/usr/bin/env python3
"""
测试结构化预测API端点
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generator, Iterable, Optional, TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stockaivo.schemas import (
    StructuredPredictionBatchItem,
    StructuredPredictionBatchRequest,
    StructuredPredictionBatchResponse,
    StructuredPredictionBatchSummary,
)

if TYPE_CHECKING:
    from stockaivo.routers.ai import (
        NestedStructuredPredictionRequest as NestedStructuredPredictionRequestType,
        StructuredPredictionRequest as StructuredPredictionRequestType,
        StructuredPredictionResponse as StructuredPredictionResponseType,
    )


def build_structured_prediction_request(
    ticker: str,
    *,
    end_date: Optional[date] = None,
    save_to_db: bool = True,
) -> "StructuredPredictionRequestType":
    from stockaivo.routers.ai import StructuredPredictionRequest

    return StructuredPredictionRequest(
        ticker=ticker,
        end_date=end_date,
        save_to_db=save_to_db,
    )


def build_structured_prediction_response(
    *,
    success: bool,
    ticker: str,
    timestamp: str,
    prediction_probability: Optional[float] = None,
    direction: Optional[str] = None,
    confidence_level: Optional[str] = None,
    reasoning: Optional[str] = None,
    market_aware_date: Optional[str] = None,
    error: Optional[str] = None,
) -> "StructuredPredictionResponseType":
    from stockaivo.routers.ai import StructuredPredictionResponse

    return StructuredPredictionResponse(
        success=success,
        prediction_probability=prediction_probability,
        direction=direction,
        confidence_level=confidence_level,
        reasoning=reasoning,
        ticker=ticker,
        timestamp=timestamp,
        market_aware_date=market_aware_date,
        error=error,
    )


def build_batch_request(
    tickers: Iterable[str],
    *,
    end_date: Optional[date] = None,
    save_to_db: bool = True,
    max_concurrency: int = 3,
    max_retries: int = 0,
    retry_delay_seconds: float = 5.0,
) -> StructuredPredictionBatchRequest:
    return StructuredPredictionBatchRequest(
        tickers=list(tickers),
        end_date=end_date,
        save_to_db=save_to_db,
        max_concurrency=max_concurrency,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
    )


def test_structured_prediction_request_model() -> None:
    """测试结构化预测请求模型"""
    request = build_structured_prediction_request("AAPL")
    assert request.ticker == "AAPL"
    assert request.end_date is None
    assert request.save_to_db is True

    test_date = date(2024, 12, 31)
    request_with_date = build_structured_prediction_request(
        "TSLA",
        end_date=test_date,
        save_to_db=False,
    )
    assert request_with_date.ticker == "TSLA"
    assert request_with_date.end_date == test_date
    assert request_with_date.save_to_db is False


def test_structured_prediction_response_model() -> None:
    """测试结构化预测响应模型"""
    success_response = build_structured_prediction_response(
        success=True,
        prediction_probability=0.75,
        direction="UP",
        confidence_level="HIGH",
        reasoning="基于技术分析，股票呈现上涨趋势",
        ticker="AAPL",
        timestamp=datetime.now().isoformat(),
        market_aware_date="2024-12-31",
    )

    assert success_response.success is True
    assert success_response.prediction_probability == 0.75
    assert success_response.direction == "UP"
    assert success_response.confidence_level == "HIGH"
    assert success_response.ticker == "AAPL"
    assert success_response.error is None

    error_response = build_structured_prediction_response(
        success=False,
        ticker="NVDA",
        timestamp=datetime.now().isoformat(),
        error="技术分析失败",
    )

    assert error_response.success is False
    assert error_response.ticker == "NVDA"
    assert error_response.error == "技术分析失败"
    assert error_response.prediction_probability is None


def test_nested_structured_prediction_request() -> None:
    """测试嵌套结构化预测请求模型"""
    from stockaivo.routers.ai import NestedStructuredPredictionRequest

    inner_request = build_structured_prediction_request("GOOGL")
    nested_request: "NestedStructuredPredictionRequestType" = NestedStructuredPredictionRequest(
        summary="预测GOOGL股价",
        value=inner_request,
    )

    assert nested_request.summary == "预测GOOGL股价"
    assert nested_request.value.ticker == "GOOGL"
    assert nested_request.value.save_to_db is True


def test_api_endpoint_import() -> None:
    """测试API端点函数导入"""
    from stockaivo.routers.ai import analyze_stock_structured_prediction

    assert callable(analyze_stock_structured_prediction)


def test_api_models_validation() -> None:
    """测试API模型的字段验证"""
    from stockaivo.routers.ai import StructuredPredictionRequest

    with pytest.raises(ValidationError):
        StructuredPredictionRequest.model_validate({})

    request = build_structured_prediction_request(ticker="")
    assert request.ticker == ""

    explicit_date_request = build_structured_prediction_request(
        ticker="AAPL",
        end_date=date(2024, 1, 1),
    )
    assert explicit_date_request.end_date == date(2024, 1, 1)


def test_response_model_optional_fields() -> None:
    """测试响应模型可选字段"""
    minimal_response = build_structured_prediction_response(
        success=False,
        ticker="AAPL",
        timestamp=datetime.now().isoformat(),
        prediction_probability=None,
        direction=None,
        confidence_level=None,
        reasoning=None,
        market_aware_date=None,
        error=None,
    )

    assert minimal_response.success is False
    assert minimal_response.ticker == "AAPL"
    assert minimal_response.prediction_probability is None
    assert minimal_response.direction is None
    assert minimal_response.confidence_level is None
    assert minimal_response.reasoning is None
    assert minimal_response.market_aware_date is None
    assert minimal_response.error is None


def test_structured_prediction_batch_request_model_defaults() -> None:
    """测试批量预测请求模型默认值"""
    request = build_batch_request(["AAPL", "MSFT"])
    assert request.tickers == ["AAPL", "MSFT"]
    assert request.save_to_db is True
    assert request.max_concurrency == 3
    assert request.max_retries == 0
    assert request.retry_delay_seconds == pytest.approx(5.0)


def test_structured_prediction_batch_response_model() -> None:
    """测试批量预测响应模型结构"""
    single_response = build_structured_prediction_response(
        success=True,
        prediction_probability=0.65,
        direction="UP",
        confidence_level="MEDIUM",
        reasoning="多维分析看涨",
        ticker="AAPL",
        timestamp=datetime.now().isoformat(),
        market_aware_date="2024-01-05",
    )

    batch_item = StructuredPredictionBatchItem(
        ticker="AAPL",
        success=True,
        latency_seconds=1.2,
        retries=0,
        response=single_response,
        error=None,
    )

    batch_response = StructuredPredictionBatchResponse(
        results=[batch_item],
        summary=StructuredPredictionBatchSummary(
            total=1,
            success=1,
            failed=0,
            duration_seconds=1.2,
        ),
        failed_tickers=[],
    )

    assert batch_response.summary.success == 1
    assert batch_response.results[0].response is not None
    assert batch_response.results[0].response.direction == "UP"


@pytest.fixture
def batch_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """提供带有依赖覆盖的测试客户端"""
    from main import app
    from stockaivo.dependencies import get_db_with_error_handling

    class DummySession:
        def merge(self, *_: Any, **__: Any) -> None:
            return None

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    def override_db() -> Generator[DummySession, None, None]:
        yield DummySession()

    app.dependency_overrides[get_db_with_error_handling] = override_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db_with_error_handling, None)


def test_batch_prediction_endpoint_success(
    monkeypatch: pytest.MonkeyPatch,
    batch_client: TestClient,
) -> None:
    """测试批量结构化预测端点的成功响应"""
    from stockaivo.routers import ai as ai_router
    from stockaivo.routers.ai import StructuredPredictionRequest

    async def fake_run(
        request: StructuredPredictionRequest,
        _db: Any,
    ) -> "StructuredPredictionResponseType":
        return build_structured_prediction_response(
            success=True,
            prediction_probability=0.7,
            direction="UP",
            confidence_level="HIGH",
            reasoning=f"{request.ticker} 看涨",
            ticker=request.ticker,
            timestamp="2024-01-05T10:00:00",
            market_aware_date="2024-01-05",
            error=None,
        )

    monkeypatch.setattr(ai_router, "run_structured_prediction", fake_run)

    response = batch_client.post(
        "/ai/predict-structured/batch",
        json={
            "tickers": ["AAPL", "MSFT"],
            "save_to_db": False,
            "max_concurrency": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] == 2
    assert data["summary"]["success"] == 2
    assert data["failed_tickers"] == []
    assert all(item["success"] for item in data["results"])


def test_batch_prediction_endpoint_with_failures(
    monkeypatch: pytest.MonkeyPatch,
    batch_client: TestClient,
) -> None:
    """测试批量结构化预测端点的失败与重试逻辑"""
    from stockaivo.routers import ai as ai_router
    from stockaivo.routers.ai import StructuredPredictionRequest
    from stockaivo.exceptions import AIServiceException

    attempt_counter = {"MSFT": 0}

    async def fake_run(
        request: StructuredPredictionRequest,
        _db: Any,
    ) -> "StructuredPredictionResponseType":
        ticker = request.ticker
        if ticker == "AAPL":
            return build_structured_prediction_response(
                success=True,
                prediction_probability=0.6,
                direction="UP",
                confidence_level="MEDIUM",
                reasoning="AAPL 正常",
                ticker=ticker,
                timestamp="2024-01-05T10:05:00",
                market_aware_date="2024-01-05",
                error=None,
            )
        if ticker == "MSFT":
            attempt_counter["MSFT"] += 1
            if attempt_counter["MSFT"] == 1:
                return build_structured_prediction_response(
                    success=False,
                    prediction_probability=None,
                    direction=None,
                    confidence_level=None,
                    reasoning=None,
                    ticker=ticker,
                    timestamp="2024-01-05T10:05:00",
                    market_aware_date=None,
                    error="临时数据缺失",
                )
            return build_structured_prediction_response(
                success=True,
                prediction_probability=0.55,
                direction="UP",
                confidence_level="LOW",
                reasoning="第二次尝试成功",
                ticker=ticker,
                timestamp="2024-01-05T10:05:02",
                market_aware_date="2024-01-05",
                error=None,
            )
        raise AIServiceException("LLM 服务不可用")

    monkeypatch.setattr(ai_router, "run_structured_prediction", fake_run)

    response = batch_client.post(
        "/ai/predict-structured/batch",
        json={
            "tickers": ["AAPL", "MSFT", "TSLA"],
            "save_to_db": False,
            "max_concurrency": 2,
            "max_retries": 1,
            "retry_delay_seconds": 0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] == 3
    assert data["summary"]["success"] == 2
    assert data["summary"]["failed"] == 1
    assert data["failed_tickers"] == ["TSLA"]

    msft_entry = next(item for item in data["results"] if item["ticker"] == "MSFT")
    assert msft_entry["success"] is True
    assert msft_entry["retries"] == 1
    tsla_entry = next(item for item in data["results"] if item["ticker"] == "TSLA")
    assert tsla_entry["success"] is False
    assert tsla_entry["error"] == "LLM 服务不可用"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
