"""限流器功能测试"""

from __future__ import annotations

import asyncio
import time
from importlib import reload

import pytest

from stockaivo.utils.rate_limiter import RateLimitConfig, RateLimiter, RateLimiterSettings


@pytest.mark.asyncio
async def test_acquire_respects_window():
    """验证令牌桶会在超限时等待窗口恢复"""
    limiter = RateLimiter(
        {"bucket": RateLimitConfig(requests=2, window=0.1, jitter=0.0)},
        RateLimiterSettings(
            default_jitter=0.0,
            error_base_delay=0.01,
            error_max_delay=0.02,
            error_jitter=0.0,
            max_retries=2,
        ),
    )

    await limiter.acquire("bucket")
    await limiter.acquire("bucket")
    before = time.perf_counter()
    await limiter.acquire("bucket")
    elapsed = time.perf_counter() - before

    # 允许少量调度误差
    assert elapsed >= 0.08


@pytest.mark.asyncio
async def test_guard_respects_global_concurrency():
    """验证 guard 会遵守全局并发限制"""
    limiter = RateLimiter(
        {"ai_predict": RateLimitConfig(requests=5, window=1.0, jitter=0.0)},
        RateLimiterSettings(
            default_jitter=0.0,
            error_base_delay=0.05,
            error_max_delay=0.05,
            error_jitter=0.0,
            max_retries=1,
            global_concurrency=1,
        ),
    )

    events: dict[str, float] = {}

    async def worker(name: str):
        async with limiter.guard("ai_predict"):
            events[f"{name}_enter"] = time.perf_counter()
            await asyncio.sleep(0.05)
            events[f"{name}_exit"] = time.perf_counter()

    await asyncio.gather(worker("A"), worker("B"))

    assert events["B_enter"] >= events["A_exit"]


def test_compute_backoff_respects_cap(monkeypatch):
    """验证退避时间遵循指数并在上限处截断"""
    limiter = RateLimiter(
        {"bucket": RateLimitConfig(requests=1, window=1.0, jitter=0.0)},
        RateLimiterSettings(
            default_jitter=0.0,
            error_base_delay=1.0,
            error_max_delay=3.0,
            error_jitter=0.0,
            max_retries=3,
        ),
    )

    assert limiter.compute_backoff(1) == pytest.approx(1.0, rel=0.05)
    assert limiter.compute_backoff(2) == pytest.approx(2.0, rel=0.05)
    assert limiter.compute_backoff(5) == pytest.approx(3.0, rel=0.05)


def test_get_batch_prediction_rate_limiter_cached(monkeypatch):
    """确保依赖注入返回的限流器实例被缓存"""
    from stockaivo import dependencies

    reload(dependencies)
    dependencies._build_batch_prediction_rate_limiter.cache_clear()

    limiter_1 = dependencies.get_batch_prediction_rate_limiter()
    limiter_2 = dependencies.get_batch_prediction_rate_limiter()

    assert limiter_1 is limiter_2
