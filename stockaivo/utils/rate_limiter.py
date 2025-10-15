"""批量结构化预测限流与退避组件"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import AsyncContextManager, Callable, Deque, Dict, Mapping, Optional


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RateLimitConfig:
    """单个令牌桶配置"""

    requests: int
    window: float
    jitter: float = 0.0

    def __post_init__(self) -> None:
        if self.requests < 1:
            raise ValueError("requests 必须 >= 1")
        if self.window <= 0:
            raise ValueError("window 必须 > 0")
        if self.jitter < 0:
            raise ValueError("jitter 不能为负数")


@dataclass(slots=True)
class RateLimiterSettings:
    """全局限流器设置"""

    default_jitter: float = 0.5
    error_base_delay: float = 1.5
    error_max_delay: float = 30.0
    error_jitter: float = 0.5
    max_retries: int = 3
    global_concurrency: Optional[int] = None
    clock: Callable[[], float] = time.perf_counter

    def __post_init__(self) -> None:
        if self.default_jitter < 0:
            raise ValueError("default_jitter 不能为负数")
        if self.error_base_delay < 0:
            raise ValueError("error_base_delay 不能为负数")
        if self.error_max_delay < self.error_base_delay:
            raise ValueError("error_max_delay 需要 >= error_base_delay")
        if self.error_jitter < 0:
            raise ValueError("error_jitter 不能为负数")
        if self.max_retries < 0:
            raise ValueError("max_retries 不能为负数")


class _BucketState:
    """维护单个令牌桶的运行时状态"""

    __slots__ = ("config", "timestamps", "lock")

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self.timestamps: Deque[float] = deque()
        self.lock = asyncio.Lock()

    def trim(self, now: float) -> None:
        """移除窗口之外的时间戳"""
        window = self.config.window
        timestamps = self.timestamps
        while timestamps and now - timestamps[0] >= window:
            timestamps.popleft()


class _LimiterGuard(AsyncContextManager[None]):
    """封装 guard 使用场景的上下文对象"""

    __slots__ = ("_limiter", "_bucket", "_global_acquired")

    def __init__(self, limiter: "RateLimiter", bucket: str) -> None:
        self._limiter = limiter
        self._bucket = bucket
        self._global_acquired = False

    async def __aenter__(self) -> None:
        self._global_acquired = await self._limiter._acquire_global()
        try:
            await self._limiter._acquire_bucket(self._bucket)
        except Exception:
            if self._global_acquired:
                self._limiter._release_global()
            raise
        return None

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._global_acquired:
            self._limiter._release_global()
        return False


class RateLimiter:
    """多源限流与退避控制器"""

    def __init__(
        self,
        limits: Mapping[str, RateLimitConfig],
        settings: Optional[RateLimiterSettings] = None,
        *,
        rng: Optional[random.Random] = None,
    ) -> None:
        if not limits:
            raise ValueError("limits 不能为空")

        self._settings = settings or RateLimiterSettings()
        self._limits: Dict[str, _BucketState] = {
            bucket: _BucketState(config) for bucket, config in limits.items()
        }
        self._rng = rng or random.Random()
        self._global_semaphore: Optional[asyncio.Semaphore] = None
        if self._settings.global_concurrency:
            self._global_semaphore = asyncio.Semaphore(self._settings.global_concurrency)

    @property
    def max_retry_attempts(self) -> int:
        """返回建议的最大重试次数"""

        return self._settings.max_retries

    def guard(self, bucket: str) -> AsyncContextManager[None]:
        """返回异步上下文，用于包裹耗时操作"""

        if bucket not in self._limits:
            logger.debug("未配置的限流桶: %s，直接返回空 guard", bucket)
            return _NullAsyncContext()
        return _LimiterGuard(self, bucket)

    async def acquire(self, bucket: str) -> None:
        """单次获取令牌（不占用全局并发）"""

        if bucket not in self._limits:
            logger.debug("未配置的限流桶: %s，跳过令牌获取", bucket)
            return
        await self._acquire_bucket(bucket)

    def compute_backoff(self, attempt: int) -> float:
        """根据全局配置计算退避时间"""

        attempt_idx = max(1, attempt)
        settings = self._settings
        delay = min(
            settings.error_base_delay * (2 ** (attempt_idx - 1)),
            settings.error_max_delay,
        )
        jitter_source = settings.error_jitter
        if jitter_source > 0:
            delay += self._rng.uniform(0, jitter_source)
        return delay

    async def _acquire_bucket(self, bucket: str) -> None:
        state = self._limits[bucket]
        config = state.config
        jitter = config.jitter or self._settings.default_jitter

        while True:
            async with state.lock:
                now = self._settings.clock()
                state.trim(now)
                if len(state.timestamps) < config.requests:
                    state.timestamps.append(now)
                    return

                wait_time = config.window - (now - state.timestamps[0])
                wait_time = max(wait_time, 0.0)

            if wait_time <= 0:
                await asyncio.sleep(0)
                continue

            if jitter > 0:
                wait_time += self._rng.uniform(0, jitter)

            logger.info("限流命中: bucket=%s, 等待 %.2f 秒", bucket, wait_time)
            await asyncio.sleep(wait_time)

    async def _acquire_global(self) -> bool:
        if self._global_semaphore is None:
            return False

        await self._global_semaphore.acquire()
        logger.debug("全局并发令牌占用，剩余=%d", self._global_semaphore._value)  # type: ignore[attr-defined]
        return True

    def _release_global(self) -> None:
        if self._global_semaphore is None:
            return
        self._global_semaphore.release()
        logger.debug("全局并发令牌释放，剩余=%d", self._global_semaphore._value)  # type: ignore[attr-defined]


class _NullAsyncContext(AsyncContextManager[None]):
    """无操作上下文实现，用于未配置限流时的兼容场景"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


__all__ = ["RateLimiter", "RateLimitConfig", "RateLimiterSettings"]
