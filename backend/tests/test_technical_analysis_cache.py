import unittest
from datetime import datetime, date, time, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pandas as pd
import pytz

from stockaivo.cache_manager import _calculate_market_aware_ttl
from stockaivo.ai.state import GraphState
from stockaivo.ai.agents import technical_analysis_agent, MarketAnalysisResult
from stockaivo.cache_manager import RedisConnectionError


class FakeCalendar:
    """用于模拟NYSE日历的简易对象"""

    def __init__(self, schedule_map: dict[date, tuple[datetime, datetime]]):
        self.schedule_map = schedule_map
        self.tz = pytz.timezone("US/Eastern")

    def schedule(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows = []
        index = []
        current = start_date
        while current <= end_date:
            if current in self.schedule_map:
                market_open, market_close = self.schedule_map[current]
                rows.append({
                    "market_open": market_open,
                    "market_close": market_close,
                })
                index.append(pd.Timestamp(current, tz=self.tz))
            current += timedelta(days=1)
        if not rows:
            return pd.DataFrame(columns=["market_open", "market_close"])
        return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


class TestMarketAwareTTL(unittest.TestCase):
    """验证技术分析缓存TTL计算逻辑"""

    def setUp(self) -> None:
        self.tz = pytz.timezone("US/Eastern")
        self.today = date(2025, 2, 3)
        self.tomorrow = self.today + timedelta(days=1)
        self.schedule_map = {
            self.today: (
                self.tz.localize(datetime.combine(self.today, time(9, 30))),
                self.tz.localize(datetime.combine(self.today, time(16, 0)))
            ),
            self.tomorrow: (
                self.tz.localize(datetime.combine(self.tomorrow, time(9, 30))),
                self.tz.localize(datetime.combine(self.tomorrow, time(16, 0)))
            )
        }
        self.fake_calendar = FakeCalendar(self.schedule_map)

    def test_ttl_during_trading_hours(self):
        """交易时段内TTL固定为180秒"""
        current_time = self.tz.localize(datetime.combine(self.today, time(10, 0)))
        with patch('stockaivo.cache_manager._get_nyse_calendar', return_value=self.fake_calendar):
            ttl = _calculate_market_aware_ttl(current_time)
        self.assertEqual(ttl, 180)

    def test_ttl_after_market_close(self):
        """收盘后TTL为距下一次开盘的秒数"""
        current_time = self.tz.localize(datetime.combine(self.today, time(20, 0)))
        with patch('stockaivo.cache_manager._get_nyse_calendar', return_value=self.fake_calendar):
            ttl = _calculate_market_aware_ttl(current_time)
        expected_seconds = int((self.schedule_map[self.tomorrow][0] - current_time).total_seconds())
        self.assertEqual(ttl, expected_seconds)


class TestTechnicalAnalysisAgentCaching(unittest.IsolatedAsyncioTestCase):
    """验证 Agent 在缓存不可用时的降级策略"""

    async def test_agent_fallback_when_cache_unavailable(self):
        """Redis不可用时应继续调用LLM并返回结果"""
        market_analysis = MarketAnalysisResult(
            market_aware_date=date(2025, 2, 3),
            target_friday="2025-02-07",
            target_friday_date=date(2025, 2, 7),
            trading_days_count=5,
            calendar_days=4
        )
        state: GraphState = {
            "ticker": "TEST",
            "custom_date_range": None,
            "raw_data": {"daily_prices": {"data": [1]}},
            "analysis_results": {},
            "final_report": "",
            "market_analysis": market_analysis
        }

        with patch('stockaivo.ai.agents.get_technical_analysis_cache', side_effect=RedisConnectionError("down")), \
             patch('stockaivo.ai.agents.save_technical_analysis_cache', return_value=None) as mock_save_cache, \
             patch('stockaivo.ai.agents.llm_tool') as mock_llm_tool, \
             patch('stockaivo.ai.agents._process_technical_analysis_data', return_value=("TEST", "daily", "weekly", "tenmin", ["MA5"], ["MA20"], [])), \
             patch('stockaivo.ai.agents._build_technical_analysis_prompt', return_value="prompt"), \
             patch('stockaivo.ai.agents.get_llm_service') as mock_get_service:

            mock_llm_tool.ainvoke = AsyncMock(return_value="技术分析结果")
            mock_get_service.return_value.get_model_name_for_agent.return_value = "mock-model"

            result = await technical_analysis_agent(state)

        self.assertEqual(result["analysis_results"]["technical_analyst"], "技术分析结果")
        metadata = result["analysis_results"].get("technical_analyst_metadata")
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.get("cache_status"), "miss")
        mock_llm_tool.ainvoke.assert_awaited_once()
        mock_save_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
