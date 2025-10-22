"""
结构化预测核心服务测试
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, Generator, List, Optional, cast

from sqlalchemy.orm import Session

import pytest

from stockaivo.exceptions import AIServiceException
from stockaivo.schemas import StructuredPredictionRequest
from stockaivo.ai import structured_prediction_service as service
from stockaivo.cache_manager import StructuredPredictionPendingEntry


class DummySession:
    """用于捕获数据库交互的简单假对象"""

    def __init__(self) -> None:
        self.merged = None
        self.committed = False
        self.rolled_back = False

    def merge(self, obj: object) -> None:
        self.merged = obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
async def test_run_structured_prediction_success(monkeypatch):
    """验证正常流程会返回成功结果并写入数据库"""

    fake_market = SimpleNamespace(
        market_aware_date=date(2024, 1, 5),
        target_friday_date=date(2024, 1, 12),
        trading_days_count=5,
    )

    captured_kwargs: Dict[str, Any] = {}

    async def fake_data_agent(state: Any, **kwargs: Any) -> Dict[str, Any]:
        captured_kwargs.update(kwargs)
        return {
            "analysis_results": {"data_collector": "ok"},
            "market_analysis": fake_market,
        }

    async def fake_tech_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {"technical_analyst": "技术分析通过"}}

    async def fake_fund_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {"fundamental_analyst": "基本面通过"}}

    async def fake_news_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {"news_sentiment_analyst": "新闻情绪正面"}}

    async def fake_structured_agent(state: Any) -> Dict[str, Any]:
        return {
            "structured_prediction": {
                "success": True,
                "prediction_probability": 0.72,
                "direction": "UP",
                "confidence_level": "HIGH",
                "reasoning": "多方信号一致",
                "timestamp": "2024-01-05T12:00:00",
            }
        }

    monkeypatch.setattr(service, "data_collection_agent", fake_data_agent)
    monkeypatch.setattr(service, "technical_analysis_agent", fake_tech_agent)
    monkeypatch.setattr(service, "fundamental_analysis_agent", fake_fund_agent)
    monkeypatch.setattr(service, "news_sentiment_analysis_agent", fake_news_agent)
    monkeypatch.setattr(service, "structured_prediction_agent", fake_structured_agent)

    saved_payloads: List[StructuredPredictionPendingEntry] = []

    def fake_save_prediction(payload: StructuredPredictionPendingEntry) -> str:
        ticker = payload.get("ticker", "UNKNOWN")
        saved_payloads.append(payload)
        return f"prediction:pending:{ticker}:20240105:20240112"

    monkeypatch.setattr(service, "save_structured_prediction_pending_cache", fake_save_prediction)

    request = StructuredPredictionRequest(
        ticker="AAPL",
        end_date=None,
        save_to_db=True,
        execution_mode="full",
    )
    session = DummySession()

    response = await service.run_structured_prediction(request, cast(Session, session))

    assert response.success is True
    assert response.direction == "UP"
    assert response.market_aware_date == "2024-01-05"
    assert response.execution_mode == "full"
    assert response.data_collection_summary is None
    assert session.committed is False
    assert session.merged is None
    assert len(saved_payloads) == 1
    saved_payload = saved_payloads[0]
    assert saved_payload.get("ticker") == "AAPL"
    assert saved_payload.get("market_aware_date") == "2024-01-05"
    assert saved_payload.get("target_date") == "2024-01-12"
    assert captured_kwargs == {"include_news": True, "include_intraday": True}


@pytest.mark.asyncio
async def test_run_structured_prediction_technical_failure(monkeypatch):
    """技术分析失败时应抛出 AIServiceException"""

    async def fake_data_agent(state: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"analysis_results": {}, "market_analysis": None}

    async def fake_tech_agent(state: Any) -> Dict[str, Any]:
        raise RuntimeError("tech fail")

    async def fake_fund_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {}}

    async def fake_news_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {}}

    async def fake_structured_agent(state: Any) -> Dict[str, Any]:
        return {"structured_prediction": {"success": False}}

    monkeypatch.setattr(service, "data_collection_agent", fake_data_agent)
    monkeypatch.setattr(service, "technical_analysis_agent", fake_tech_agent)
    monkeypatch.setattr(service, "fundamental_analysis_agent", fake_fund_agent)
    monkeypatch.setattr(service, "news_sentiment_analysis_agent", fake_news_agent)
    monkeypatch.setattr(service, "structured_prediction_agent", fake_structured_agent)

    request = StructuredPredictionRequest(
        ticker="TSLA",
        end_date=None,
        save_to_db=False,
        execution_mode="full",
    )

    with pytest.raises(AIServiceException):
        await service.run_structured_prediction(request, None)


@pytest.mark.asyncio
async def test_run_structured_prediction_failure_response(monkeypatch):
    """预测失败时应返回错误信息且不写库"""

    fake_market = SimpleNamespace(
        market_aware_date=date(2024, 2, 2),
        target_friday_date=date(2024, 2, 9),
        trading_days_count=5,
    )

    async def fake_data_agent(state: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "analysis_results": {"data_collector": "ok"},
            "market_analysis": fake_market,
        }

    async def fake_tech_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {"technical_analyst": "技术分析通过"}}

    async def fake_structured_agent(state: Any) -> Dict[str, Any]:
        return {
            "structured_prediction": {
                "success": False,
                "error": "LLM 调用失败",
                "timestamp": "2024-02-02T09:30:00",
            }
        }

    monkeypatch.setattr(service, "data_collection_agent", fake_data_agent)
    monkeypatch.setattr(service, "technical_analysis_agent", fake_tech_agent)
    async def fake_fund_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {}}

    async def fake_news_agent(state: Any) -> Dict[str, Any]:
        return {"analysis_results": {}}

    monkeypatch.setattr(service, "fundamental_analysis_agent", fake_fund_agent)
    monkeypatch.setattr(service, "news_sentiment_analysis_agent", fake_news_agent)
    monkeypatch.setattr(service, "structured_prediction_agent", fake_structured_agent)

    session = DummySession()
    request = StructuredPredictionRequest(
        ticker="NVDA",
        end_date=None,
        save_to_db=True,
        execution_mode="full",
    )

    saved_payloads: List[StructuredPredictionPendingEntry] = []

    def fake_save_prediction(payload: StructuredPredictionPendingEntry) -> str:
        saved_payloads.append(payload)
        return "prediction:pending:dummy"

    monkeypatch.setattr(service, "save_structured_prediction_pending_cache", fake_save_prediction)

    response = await service.run_structured_prediction(request, cast(Session, session))

    assert response.success is False
    assert response.error == "LLM 调用失败"
    assert response.execution_mode == "full"
    assert response.data_collection_summary is None
    assert session.committed is False
    assert session.merged is None
    assert saved_payloads == []


@pytest.mark.asyncio
async def test_run_structured_prediction_data_collection_only(monkeypatch):
    """数据采集模式应跳过分析与持久化，仅返回数据摘要"""

    fake_market = SimpleNamespace(
        market_aware_date=date(2024, 3, 1),
        target_friday_date=date(2024, 3, 8),
        trading_days_count=5,
    )

    captured_kwargs: Dict[str, Any] = {}

    async def fake_data_agent(state: Any, **kwargs: Any) -> Dict[str, Any]:
        captured_kwargs.update(kwargs)
        return {
            "analysis_results": {"data_collector": "ok"},
            "market_analysis": fake_market,
            "raw_data": {
                "daily_prices": {"data": [[1], [2]]},
                "weekly_prices": {"data": [[3]]},
            },
        }

    async def fail_agent(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("analysis agent should not execute in data_collection_only mode")

    async def fail_structured(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("structured_prediction_agent should not be called in data_collection_only mode")

    monkeypatch.setattr(service, "data_collection_agent", fake_data_agent)
    monkeypatch.setattr(service, "technical_analysis_agent", fail_agent)
    monkeypatch.setattr(service, "fundamental_analysis_agent", fail_agent)
    monkeypatch.setattr(service, "news_sentiment_analysis_agent", fail_agent)
    monkeypatch.setattr(service, "structured_prediction_agent", fail_structured)

    persist_calls: List[StructuredPredictionPendingEntry] = []

    def fake_save_prediction(payload: StructuredPredictionPendingEntry) -> str:
        persist_calls.append(payload)
        return "ignored"

    monkeypatch.setattr(service, "save_structured_prediction_pending_cache", fake_save_prediction)

    request = StructuredPredictionRequest(
        ticker="BABA",
        end_date=None,
        save_to_db=True,
        execution_mode="data_collection_only",
    )
    session = DummySession()

    response = await service.run_structured_prediction(request, cast(Session, session))

    assert response.success is True
    assert response.execution_mode == "data_collection_only"
    assert response.data_collection_summary == {"daily_prices": 2, "weekly_prices": 1}
    assert response.direction is None
    assert response.prediction_probability is None
    assert response.error is None
    assert "数据采集模式已完成" in (response.reasoning or "")
    assert response.market_aware_date == "2024-03-01"
    assert session.committed is False
    assert session.merged is None
    assert persist_calls == []
    assert captured_kwargs == {"include_news": False, "include_intraday": False}


class DummyDBSession(Session):
    """用于测试数据库写入逻辑的简单会话"""

    def __init__(self) -> None:
        super().__init__()
        self.merged_records: List[object] = []
        self.commit_called = False
        self.rollback_called = False

    def begin(self) -> "_DummyTransaction":
        return _DummyTransaction(self)

    def merge(self, record: object) -> None:
        self.merged_records.append(record)

    def commit(self) -> None:
        self.commit_called = True

    def rollback(self) -> None:
        self.rollback_called = True


class _DummyTransaction:
    """模拟 SQLAlchemy 的上下文事务"""

    def __init__(self, session: DummyDBSession) -> None:
        self._session = session

    def __enter__(self) -> DummyDBSession:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self._session.rollback_called = True
        return False


def test_persist_pending_data_handles_structured_predictions(monkeypatch):
    """验证数据库写入器能够消费结构化预测待持久化数据"""
    from stockaivo import database_writer as writer_module

    dummy_db = DummyDBSession()

    payload: StructuredPredictionPendingEntry = StructuredPredictionPendingEntry(
        ticker="AAPL",
        market_aware_date="2024-01-05",
        target_date="2024-01-12",
        trading_days_count=5,
        prediction_probability=0.72,
        direction="UP",
        confidence_level="HIGH",
        reasoning="多指标一致看涨",
        prediction_timestamp="2024-01-05T12:00:00Z",
    )

    monkeypatch.setattr(writer_module, "get_pending_data_from_redis", lambda: [])
    prediction_entries: list[tuple[str, StructuredPredictionPendingEntry]] = [
        ("prediction:pending:AAPL:20240105:20240112", payload)
    ]
    monkeypatch.setattr(writer_module, "get_structured_prediction_pending_cache", lambda: prediction_entries)
    monkeypatch.setattr(writer_module, "clear_saved_data", lambda *_args, **_kwargs: True)

    cleared_keys: List[str] = []

    def fake_delete_prediction(key: str) -> bool:
        cleared_keys.append(key)
        return True

    monkeypatch.setattr(writer_module, "delete_structured_prediction_pending_cache", fake_delete_prediction)

    result = writer_module.database_writer.persist_pending_data(dummy_db)

    assert result["pending_prediction_count"] == 1
    assert result["prediction_processed_count"] == 1
    assert result["processed_count"] == 0
    assert result["failed_count"] == 0
    assert dummy_db.commit_called is True
    assert dummy_db.rollback_called is False
    assert len(dummy_db.merged_records) == 1
    record = dummy_db.merged_records[0]
    assert getattr(record, "ticker", None) == "AAPL"
    assert cleared_keys == ["prediction:pending:AAPL:20240105:20240112"]
