import unittest
from unittest.mock import patch, MagicMock, call
import pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
import asyncio
import pytz

# The function to be tested
from stockaivo.data_service import get_stock_data, PeriodType, _find_missing_date_ranges
from stockaivo.cache_manager import CacheType

class TestFindMissingDateRanges(unittest.TestCase):

    def test_no_missing_dates(self):
        """当所有必需日期都已缓存时，应返回空列表。"""
        from stockaivo.data_service import _find_missing_date_ranges
        required = [date(2023, 1, 1), date(2023, 1, 2)]
        cached = [date(2023, 1, 1), date(2023, 1, 2)]
        market_aware_date = date(2023, 1, 2)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), [])

    def test_all_dates_missing(self):
        """当所有必需日期都缺失时，应返回一个包含整个范围的列表。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = []
        expected = [(date(2023, 1, 1), date(2023, 1, 3))]
        market_aware_date = date(2023, 1, 3)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_single_gap_in_the_middle(self):
        """当缓存数据中间有一个缺口时，应正确识别该缺失范围。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
        cached = [date(2023, 1, 1), date(2023, 1, 4)]
        expected = [(date(2023, 1, 2), date(2023, 1, 3))]
        market_aware_date = date(2023, 1, 4)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_multiple_gaps(self):
        """当存在多个不连续的缺失范围时，应全部识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5), date(2023, 1, 6)]
        cached = [date(2023, 1, 2), date(2023, 1, 5)]
        expected = [(date(2023, 1, 1), date(2023, 1, 1)), (date(2023, 1, 3), date(2023, 1, 4)), (date(2023, 1, 6), date(2023, 1, 6))]
        market_aware_date = date(2023, 1, 6)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_missing_at_the_beginning(self):
        """当缺失范围在开始部分时，应正确识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = [date(2023, 1, 3)]
        expected = [(date(2023, 1, 1), date(2023, 1, 2))]
        market_aware_date = date(2023, 1, 3)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_missing_at_the_end(self):
        """当缺失范围在结尾部分时，应正确识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = [date(2023, 1, 1)]
        expected = [(date(2023, 1, 2), date(2023, 1, 3))]
        market_aware_date = date(2023, 1, 3)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_empty_required_dates(self):
        """当必需日期列表为空时，应返回空列表。"""
        required = []
        cached = [date(2023, 1, 1)]
        market_aware_date = date(2023, 1, 1)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), [])

    def test_empty_cached_dates(self):
        """当缓存日期列表为空时，应返回整个必需范围。"""
        required = [date(2023, 1, 1), date(2023, 1, 2)]
        cached = []
        expected = [(date(2023, 1, 1), date(2023, 1, 2))]
        market_aware_date = date(2023, 1, 2)
        self.assertEqual(_find_missing_date_ranges(required, cached, market_aware_date), expected)

    def test_unsorted_inputs(self):
        """即使输入是未排序的，也应该能正确处理（尽管函数内部目前依赖排序的required_dates）。"""
        required = [date(2023, 1, 4), date(2023, 1, 1), date(2023, 1, 3), date(2023, 1, 2)]
        cached = [date(2023, 1, 3), date(2023, 1, 1)]
        # The new implementation doesn't rely on sorted required_dates
        expected = [(date(2023, 1, 4), date(2023, 1, 4)), (date(2023, 1, 2), date(2023, 1, 2))]
        # The result might be in a different order depending on the iteration order of the unsorted list
        market_aware_date = date(2023, 1, 4)
        result = _find_missing_date_ranges(required, cached, market_aware_date)
        self.assertCountEqual(result, expected)


class TestGetData(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up a dummy DataFrame for testing."""
        self.dummy_df = pd.DataFrame({
            'date': pd.to_datetime(['2023-01-01', '2023-01-02']),
            'open': [100, 102],
            'close': [101, 103]
        })
        self.ticker: str = "TEST"
        self.period: PeriodType = "daily"
    
    @patch('stockaivo.data_service.cache_manager')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._get_required_dates')
    async def test_cache_hit(self, mock_get_required_dates, mock_data_provider, mock_query_db, mock_cache_manager):
        """
        Scenario 1: Test cache hit.
        - `get_from_redis` should be called and return a DataFrame.
        - The database and API should not be called.
        """
        print("\n--- Running Test: Cache Hit ---")
        # Arrange
        mock_cache_manager.get_from_redis.return_value = self.dummy_df
        mock_get_required_dates.return_value = [date(2023, 1, 1), date(2023, 1, 2)]
        mock_db_session = MagicMock(spec=Session)

        # Act
        result_df = await get_stock_data(mock_db_session, self.ticker, self.period, end_date='2023-01-02')

        # Assert
        mock_cache_manager.get_from_redis.assert_called_once_with(self.ticker, self.period, CacheType.GENERAL_CACHE)
        mock_query_db.assert_not_called()
        mock_data_provider.fetch_from_akshare.assert_not_called()
        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df, self.dummy_df)
        print("--- Test: Cache Hit PASSED ---")

    @patch('stockaivo.data_service._get_required_dates', return_value=[])
    @patch('stockaivo.data_service.cache_manager')
    async def test_default_date_range_daily(self, mock_cache_manager, mock_get_required_dates):
        """测试当 period='daily' 且未提供日期时，是否应用30天的默认范围。"""
        print("\n--- Running Test: Default Date Range Daily ---")
        # 安排
        mock_cache_manager.get_from_redis.return_value = None
        mock_db_session = MagicMock(spec=Session)
        from datetime import datetime
        today = datetime.strptime("2025-07-03", "%Y-%m-%d").date()
        start_date_expected = (today - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        end_date_expected = (today - pd.Timedelta(days=1)).strftime('%Y-%m-%d')

        with patch('stockaivo.data_service.date') as mock_date:
            mock_date.today.return_value = today
            await get_stock_data(mock_db_session, self.ticker, "daily")

        mock_get_required_dates.assert_called_once_with(
            "daily",
            start_date_expected,
            end_date_expected
        )
        print("--- Test: Default Date Range Daily PASSED ---")

    @patch('stockaivo.data_service._get_required_dates', return_value=[])
    @patch('stockaivo.data_service.cache_manager')
    async def test_default_date_range_weekly(self, mock_cache_manager, mock_get_required_dates):
        """测试当 period='weekly' 且未提供日期时，是否应用180天的默认范围。"""
        print("\n--- Running Test: Default Date Range Weekly ---")
        mock_cache_manager.get_from_redis.return_value = None
        mock_db_session = MagicMock(spec=Session)
        from datetime import datetime
        today = datetime.strptime("2025-07-03", "%Y-%m-%d").date()
        start_date_expected = (today - pd.Timedelta(days=180)).strftime('%Y-%m-%d')
        end_date_expected = (today - pd.Timedelta(days=1)).strftime('%Y-%m-%d')

        with patch('stockaivo.data_service.date') as mock_date:
            mock_date.today.return_value = today
            await get_stock_data(mock_db_session, self.ticker, "weekly")

        mock_get_required_dates.assert_called_once_with(
            "weekly",
            start_date_expected,
            end_date_expected
        )
        print("--- Test: Default Date Range Weekly PASSED ---")

    @patch('stockaivo.data_service._get_required_dates', return_value=[])
    @patch('stockaivo.data_service.cache_manager')
    async def test_no_default_date_range_when_provided(self, mock_cache_manager, mock_get_required_dates):
        """测试当提供了 start_date 和 end_date 时，不使用默认日期范围。"""
        print("\n--- Running Test: No Default on Provided Dates ---")
        mock_cache_manager.get_from_redis.return_value = None
        mock_db_session = MagicMock(spec=Session)
        provided_start_date = "2022-01-01"
        provided_end_date = "2022-01-31"

        await get_stock_data(mock_db_session, self.ticker, "daily", end_date=provided_end_date)

        mock_get_required_dates.assert_called_once_with(
            "daily",
            provided_start_date,
            provided_end_date
        )
        print("--- Test: No Default on Provided Dates PASSED ---")

    @patch('stockaivo.data_provider.fetch_from_akshare')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service._get_required_dates')
    async def test_weekly_data_fetch_does_not_exceed_today(self, mock_get_required_dates, mock_query_database, mock_fetch_from_akshare):
        """
        验证当周线数据缺失并延伸到未来时，
        对 `fetch_from_akshare` 的调用被截断到今天。
        """
        print("\n--- Running Test: Weekly Data Fetch Does Not Exceed Today ---")
        today = date(2025, 7, 3)
        start_date_req = date(2025, 6, 23)
        end_date_req = date(2025, 7, 11)

        required_dates = [d.date() for d in pd.bdate_range(start_date_req, end_date_req)]
        mock_get_required_dates.return_value = required_dates

        db_data = pd.DataFrame({
            'date': [d.date() for d in pd.bdate_range(start_date_req, date(2025, 6, 27))],
            'price': range(5)
        })
        # The first call to _query_database is for the whole range
        # The logic will find missing dates and call remote fetch
        mock_query_database.return_value = db_data
        
        # Set the return value for the async mock directly.
        # The test runner will handle the awaitable.
        mock_fetch_from_akshare.return_value = pd.DataFrame()

        mock_db_session = MagicMock(spec=Session)

        with patch('stockaivo.data_service.date') as mock_date:
            mock_date.today.return_value = today
            await get_stock_data(
                mock_db_session,
                self.ticker,
                "weekly",
                end_date=end_date_req.strftime('%Y-%m-%d')
            )
        
        # The logic inside get_stock_data will call _find_missing_date_ranges,
        # which now truncates the end date to today.
        # This will result in a call to fetch_from_akshare with the correct, truncated date range.
        self.assertGreater(mock_fetch_from_akshare.call_count, 0, "fetch_from_akshare should be called")

        # We check the arguments of the first call.
        call_args, _ = mock_fetch_from_akshare.call_args

        # The call from data_service is: `data_provider.fetch_from_akshare(db, ticker, period, ms_str, me_str)`
        # The mock captures all positional arguments.
        # call_args[0] is db_session, [1] is ticker, [2] is period, [3] is start_date, [4] is end_date.
        self.assertEqual(call_args[3], '2025-06-30')
        self.assertEqual(call_args[4], '2025-07-03')
        print("--- Test: Weekly Data Fetch Does Not Exceed Today PASSED ---")


class TestDataServiceDualCache(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """为测试设置通用资源。"""
        self.ticker = "DUMMY"
        self.period: PeriodType = "daily"
        self.start_date = "2023-01-01"
        self.end_date = "2023-01-05"
        self.db_session = MagicMock(spec=Session)
        
        self.db_data = pd.DataFrame({
            'date': pd.to_datetime(['2023-01-01', '2023-01-02']),
            'price': [10, 11]
        })
        
        self.api_data = pd.DataFrame({
            'date': pd.to_datetime(['2023-01-03', '2023-01-04']),
            'price': [12, 13]
        })

    @patch('stockaivo.data_service._get_required_dates', MagicMock(return_value=[date(2023,1,1), date(2023,1,2)]))
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    async def test_database_hit_saves_to_general_cache(self, mock_cache_manager, mock_query_database, mock_data_provider):
        """验证从数据库获取数据后，会将其存入 GENERAL_CACHE。"""
        mock_cache_manager.get_from_redis.return_value = None
        mock_query_database.return_value = self.db_data
        
        await get_stock_data(self.db_session, self.ticker, self.period, end_date=self.end_date)
        
        mock_cache_manager.save_to_redis.assert_called_once_with(
            self.ticker, self.period, self.db_data, CacheType.GENERAL_CACHE
        )
        mock_data_provider.fetch_from_akshare.assert_not_called()

    @patch('stockaivo.data_service._get_required_dates', MagicMock(return_value=[date(2023,1,3), date(2023,1,4)]))
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    async def test_api_hit_saves_to_both_caches(self, mock_cache_manager, mock_query_database, mock_data_provider):
        """验证从API获取数据后，会将其同时存入 PENDING_SAVE 和 GENERAL_CACHE。"""
        mock_cache_manager.get_from_redis.return_value = None
        mock_query_database.return_value = None
        
        future = asyncio.Future()
        future.set_result(self.api_data)
        mock_data_provider.fetch_from_akshare.return_value = future
        
        await get_stock_data(self.db_session, self.ticker, self.period, end_date=self.end_date)
        
        expected_calls = [
            call(self.ticker, self.period, self.api_data, CacheType.PENDING_SAVE),
            call(self.ticker, self.period, self.api_data, CacheType.GENERAL_CACHE)
        ]
        mock_cache_manager.save_to_redis.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_cache_manager.save_to_redis.call_count, 2)

    @patch('stockaivo.data_service._append_to_pending_save')
    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    async def test_partial_cache_triggers_fetch_and_merge(self, mock_cache_manager, mock_query_database, mock_data_provider, mock_get_required_dates, mock_append_to_pending_save):
        """验证当通用缓存不完整时，能正确获取缺失数据、合并并更新两种缓存。"""
        mock_cache_manager.get_from_redis.return_value = self.db_data
        
        mock_query_database.return_value = None
        future = asyncio.Future()
        future.set_result(self.api_data)
        mock_data_provider.fetch_from_akshare.return_value = future
        
        required_dates = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
        mock_get_required_dates.return_value = required_dates

        combined_data = pd.concat([self.db_data, self.api_data]).sort_values(by='date').reset_index(drop=True)

        result_df = await get_stock_data(self.db_session, self.ticker, self.period, end_date="2023-01-04")

        mock_cache_manager.get_from_redis.assert_called_once_with(self.ticker, self.period, CacheType.GENERAL_CACHE)
        
        mock_data_provider.fetch_from_akshare.assert_called_once()
        
        mock_append_to_pending_save.assert_called_once()
        call_args, _ = mock_append_to_pending_save.call_args
        pd.testing.assert_frame_equal(call_args[2].reset_index(drop=True), self.api_data.reset_index(drop=True))

        mock_cache_manager.save_to_redis.assert_called_once()
        args, kwargs = mock_cache_manager.save_to_redis.call_args
        pd.testing.assert_frame_equal(args[2].reset_index(drop=True), combined_data.reset_index(drop=True))
        self.assertEqual(args[3], CacheType.GENERAL_CACHE)

        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df.reset_index(drop=True), combined_data.reset_index(drop=True))

    @patch('stockaivo.data_service._append_to_pending_save')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service.cache_manager')
    async def test_fills_gap_from_database_and_saves_missing_data(self, mock_cache_manager, mock_get_required_dates, mock_query_database, mock_data_provider, mock_append_to_pending_save):
        """
        验证当数据库数据存在缺口时，能够正确从 API 获取缺失数据，
        合并数据，返回完整结果，并将新数据异步写入数据库。
        """
        mock_cache_manager.get_from_redis.return_value = None

        db_data_with_gap = pd.DataFrame({
            'date': pd.to_datetime(['2025-05-15', '2025-05-16', '2025-05-17', '2025-05-18', '2025-05-22', '2025-05-23']),
            'price': [100, 101, 102, 103, 108, 109]
        })
        mock_query_database.return_value = db_data_with_gap

        required_dates = pd.to_datetime(pd.date_range(start='2025-05-15', end='2025-05-23')).date
        mock_get_required_dates.return_value = required_dates

        missing_data = pd.DataFrame({
            'date': pd.to_datetime(['2025-05-19', '2025-05-20', '2025-05-21']),
            'price': [104, 105, 107]
        })
        future = asyncio.Future()
        future.set_result(missing_data)
        mock_data_provider.fetch_from_akshare.return_value = future
        
        result_df = await get_stock_data(
            self.db_session,
            self.ticker,
            self.period,
            end_date='2025-05-23'
        )

        expected_data = pd.concat([db_data_with_gap, missing_data]).sort_values(by='date').reset_index(drop=True)
        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df.reset_index(drop=True), expected_data.reset_index(drop=True))

        mock_data_provider.fetch_from_akshare.assert_called_once()
        call_args, call_kwargs = mock_data_provider.fetch_from_akshare.call_args
        self.assertEqual(call_args[3], '2025-05-19')
        self.assertEqual(call_args[4], '2025-05-21')

        mock_append_to_pending_save.assert_called_once()
        call_args, _ = mock_append_to_pending_save.call_args
        saved_df = call_args[2]
        pd.testing.assert_frame_equal(saved_df.reset_index(drop=True), missing_data.reset_index(drop=True))

class TestQueryDatabase(unittest.TestCase):

    @patch('stockaivo.data_service.pd.read_sql')
    @patch('stockaivo.data_service.inspect')
    @patch('stockaivo.data_service.select')
    def test_excludes_timestamp_columns(self, mock_select, mock_inspect, mock_read_sql):
        """
        验证 _query_database 是否正确地从查询中排除了 created_at 和 updated_at 列。
        """
        mock_db_session = MagicMock(spec=Session)
        mock_db_session.bind = "dummy_connection"
        ticker = "TEST"
        period = "daily"

        mock_columns = [
            MagicMock(name='ticker'),
            MagicMock(name='dates'),
            MagicMock(name='open'),
            MagicMock(name='close'),
            MagicMock(name='created_at'),
            MagicMock(name='updated_at')
        ]
        for col in mock_columns:
            col.name = col._extract_mock_name()

        mock_inspect.return_value.c = mock_columns
        
        mock_read_sql.return_value = pd.DataFrame({
            'ticker': [ticker],
            'dates': [pd.to_datetime('2023-01-01')],
            'open': [100],
            'close': [101]
        })
        
        mock_query = MagicMock()
        mock_select.return_value.where.return_value.order_by.return_value = mock_query

        from stockaivo.data_service import _query_database
        
        result_df = _query_database(mock_db_session, ticker, period)

        mock_inspect.assert_called_once()

        mock_select.assert_called_once()
        selected_columns = mock_select.call_args[0]
        
        selected_column_names = [c.name for c in selected_columns]

        self.assertIn('ticker', selected_column_names)
        self.assertIn('dates', selected_column_names)
        self.assertNotIn('created_at', selected_column_names)
        self.assertNotIn('updated_at', selected_column_names)

        mock_read_sql.assert_called_once_with(mock_select.return_value.where.return_value.order_by.return_value, "dummy_connection")

        self.assertIsNotNone(result_df)
        if result_df is not None:
            self.assertNotIn('created_at', result_df.columns)
            self.assertNotIn('updated_at', result_df.columns)

class TestHolidayDataFetching(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """为节假日获取逻辑测试设置通用资源。"""
        self.ticker = "HOLIDAY_TEST"
        self.period: PeriodType = "daily"
        self.db_session = MagicMock(spec=Session)

    @patch('stockaivo.data_service.data_provider.fetch_from_akshare')
    @patch('stockaivo.data_service._find_missing_date_ranges')
    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    async def test_skips_fetching_for_holiday_only_range(self, mock_cache_manager, mock_query_database, mock_get_required_dates, mock_find_missing_ranges, mock_fetch_from_akshare):
        """
        验证当缺失范围仅包含节假日时，系统会跳过远程数据获取。
        """
        print("\n--- Running Test: Skips Fetching for Holiday-Only Range ---")
        # 安排
        # 1. 模拟缓存未命中，以便逻辑继续进行到数据库查询
        mock_cache_manager.get_from_redis.return_value = None

        # 2. 模拟数据库返回一个非空但无相关日期的DataFrame，以进入“数据不完整”逻辑路径
        mock_query_database.return_value = pd.DataFrame({'date': [date(2025, 1, 1)]})

        # 3. 模拟 `_get_required_dates` 返回一个包含节假日的日期列表
        good_friday_2025 = date(2025, 4, 18)
        required_dates = [good_friday_2025]
        mock_get_required_dates.return_value = required_dates

        # 4. 模拟 `_find_missing_date_ranges` 返回仅包含节假日的范围
        missing_range = [(good_friday_2025, good_friday_2025)]
        mock_find_missing_ranges.return_value = missing_range

        # 5. 模拟远程API调用
        mock_fetch_from_akshare.return_value = asyncio.Future()
        mock_fetch_from_akshare.return_value.set_result(pd.DataFrame())

        # 行动
        await get_stock_data(
            self.db_session,
            self.ticker,
            self.period,
            end_date='2025-04-18'
        )

        # 断言
        # 关键断言：`fetch_from_akshare` 不应该被调用，因为该日期范围是节假日
        mock_fetch_from_akshare.assert_not_called()
        print("--- Test: Skips Fetching for Holiday-Only Range PASSED ---")


class TestWeeklyEndDateLogic(unittest.TestCase):
    """测试周线数据结束日期计算逻辑"""

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_get_latest_complete_weekly_end_date_monday(self, mock_market_manager, mock_mcal):
        """测试周一时应该使用上一个完整周的最后交易日作为结束日期"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import date, datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')  # 使用真实的时区对象
        mock_mcal.get_calendar.return_value = mock_calendar

        # 模拟MarketStateManager
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 6, 23),  # 更早的日期
            date(2025, 6, 24),
            date(2025, 6, 25),
            date(2025, 6, 26),
            date(2025, 6, 27),  # 上周五
            date(2025, 6, 30),  # 上周一
            date(2025, 7, 1),   # 上周二
            date(2025, 7, 2),   # 上周三
            date(2025, 7, 3),   # 上周四
            # 2025-07-04 (周五) 是假期，不在交易日列表中
            date(2025, 7, 7),   # 本周一
            date(2025, 7, 8),   # 本周二
            date(2025, 7, 9),   # 本周三
            date(2025, 7, 10),  # 本周四
            date(2025, 7, 11),  # 本周五
            date(2025, 7, 14),  # 下周一
        }

        # 模拟MarketStateManager.get_trading_days_set
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 测试周一（2025-07-07）
        test_date = date(2025, 7, 7)  # 周一
        result = _get_latest_complete_weekly_end_date(test_date)

        # 应该返回上一个完整周的最后交易日（2025-07-03，上周四，因为上周五是假期）
        expected = date(2025, 7, 3)
        self.assertEqual(result, expected)


class TestWeeklyEndDateLogicEnhanced(unittest.TestCase):
    """测试增强的周线结束日期逻辑（修复后的逻辑）"""

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_historical_weekday_returns_previous_week(self, mock_market_manager, mock_mcal):
        """测试历史工作日（周一到周四）应该返回上一个完整周的最后交易日"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 7, 28),  # 上周一
            date(2025, 7, 29),  # 上周二
            date(2025, 7, 30),  # 上周三
            date(2025, 7, 31),  # 上周四
            date(2025, 8, 1),   # 上周五
            date(2025, 8, 4),   # 本周一
            date(2025, 8, 5),   # 本周二
            date(2025, 8, 6),   # 本周三
            date(2025, 8, 7),   # 本周四
            date(2025, 8, 8),   # 本周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day的行为
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 8, 6):  # 本周三
                return date(2025, 8, 8)  # 本周五
            elif target_date == date(2025, 7, 27):  # 上周日
                return date(2025, 8, 1)  # 上周五
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试历史周三
            test_date = date(2025, 8, 6)  # 周三
            result = _get_latest_complete_weekly_end_date(test_date)

            # 周三所在周未完整，应该返回上一个完整周的最后交易日
            expected = date(2025, 8, 1)  # 上周五
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_historical_weekend_returns_current_week(self, mock_market_manager, mock_mcal):
        """测试历史周末应该返回该周的最后交易日"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day返回该周的最后交易日
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 8, 9):  # 周六
                return date(2025, 8, 8)  # 该周五
            elif target_date == date(2025, 8, 10):  # 周日
                return date(2025, 8, 8)  # 该周五
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试历史周六
            test_date = date(2025, 8, 9)  # 周六
            result = _get_latest_complete_weekly_end_date(test_date)

            # 周六时该周已完整，应该返回该周的最后交易日
            expected = date(2025, 8, 8)  # 该周五
            self.assertEqual(result, expected)

            # 测试历史周日
            test_date = date(2025, 8, 10)  # 周日
            result = _get_latest_complete_weekly_end_date(test_date)

            # 周日时该周已完整，应该返回该周的最后交易日
            expected = date(2025, 8, 8)  # 该周五
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_holiday_friday_logic(self, mock_market_manager, mock_mcal):
        """测试假期周五的特殊逻辑"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（周五是假期）
        trading_days_set = {
            date(2025, 7, 1),   # 周二
            date(2025, 7, 2),   # 周三
            date(2025, 7, 3),   # 周四
            # 2025-07-04 (周五) 是假期，不在交易日列表中
            date(2025, 7, 7),   # 下周一
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day返回该周的最后交易日（周四）
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 7, 4):  # 假期周五
                return date(2025, 7, 3)  # 该周四（该周最后交易日）
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试假期周五
            test_date = date(2025, 7, 4)  # 假期周五
            result = _get_latest_complete_weekly_end_date(test_date)

            # 假期周五时，该周的最后交易日是周四，该周应该被认为完整
            expected = date(2025, 7, 3)  # 该周四
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_regular_friday_as_last_trading_day(self, mock_market_manager, mock_mcal):
        """测试正常周五作为最后交易日的逻辑"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（正常的一周）
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day返回该周的最后交易日（周五）
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 8, 8):  # 周五
                return date(2025, 8, 8)  # 该周五（该周最后交易日）
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试正常周五
            test_date = date(2025, 8, 8)  # 周五
            result = _get_latest_complete_weekly_end_date(test_date)

            # 正常周五且是该周最后交易日，该周应该被认为完整
            expected = date(2025, 8, 8)  # 该周五
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_core_logic_fix_verification(self, mock_market_manager, mock_mcal):
        """验证核心逻辑修复：历史周三不应该返回自身"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 7, 28),  # 上周一
            date(2025, 7, 29),  # 上周二
            date(2025, 7, 30),  # 上周三
            date(2025, 7, 31),  # 上周四
            date(2025, 8, 1),   # 上周五
            date(2025, 8, 4),   # 本周一
            date(2025, 8, 5),   # 本周二
            date(2025, 8, 6),   # 本周三
            date(2025, 8, 7),   # 本周四
            date(2025, 8, 8),   # 本周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day的行为
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 8, 6):  # 本周三
                return date(2025, 8, 8)  # 本周五（该周最后交易日）
            elif target_date == date(2025, 7, 27):  # 上周日
                return date(2025, 8, 1)  # 上周五
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试原始问题：2025-08-06（周三）
            test_date = date(2025, 8, 6)  # 周三
            result = _get_latest_complete_weekly_end_date(test_date)

            # 核心验证：绝对不能返回target_date本身
            self.assertNotEqual(result, test_date,
                f"错误：历史周三 {test_date} 不应该返回自身，应该返回上一个完整周的结束日期")

            # 应该返回上一个完整周的最后交易日
            expected = date(2025, 8, 1)  # 上周五
            self.assertEqual(result, expected,
                f"应该返回上一个完整周的最后交易日 {expected}，实际返回 {result}")

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_week_completion_logic_comprehensive(self, mock_market_manager, mock_mcal):
        """全面测试周完整性判断逻辑"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（包含上一周的数据）
        trading_days_set = {
            # 上一周
            date(2025, 7, 28),  # 上周一
            date(2025, 7, 29),  # 上周二
            date(2025, 7, 30),  # 上周三
            date(2025, 7, 31),  # 上周四
            date(2025, 8, 1),   # 上周五
            # 本周
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day的行为
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date >= date(2025, 8, 4) and target_date <= date(2025, 8, 10):
                # 本周的最后交易日是周五
                return date(2025, 8, 8)
            elif target_date >= date(2025, 7, 28) and target_date <= date(2025, 8, 3):
                # 上周的最后交易日是上周五
                return date(2025, 8, 1)
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为未来，使测试日期成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试用例：(日期, 预期行为)
            test_cases = [
                (date(2025, 8, 4), "周一：该周未完整"),  # 周一
                (date(2025, 8, 5), "周二：该周未完整"),  # 周二
                (date(2025, 8, 6), "周三：该周未完整"),  # 周三
                (date(2025, 8, 7), "周四：该周未完整"),  # 周四
                (date(2025, 8, 8), "周五：该周完整（是最后交易日）"),  # 周五
                (date(2025, 8, 9), "周六：该周完整"),  # 周六
                (date(2025, 8, 10), "周日：该周完整"),  # 周日
            ]

            for test_date, description in test_cases:
                with self.subTest(date=test_date, description=description):
                    result = _get_latest_complete_weekly_end_date(test_date)

                    if test_date.weekday() < 4:  # 周一到周四
                        # 该周未完整，不应该返回该周的任何日期
                        week_start = test_date - timedelta(days=test_date.weekday())
                        week_end = week_start + timedelta(days=6)
                        self.assertFalse(week_start <= result <= week_end,
                            f"{description}：不应该返回该周内的日期 {result}")
                    elif test_date.weekday() == 4:  # 周五
                        # 如果是最后交易日，该周完整，应该返回该周五
                        self.assertEqual(result, test_date,
                            f"{description}：应该返回该周五 {test_date}")
                    else:  # 周末
                        # 该周完整，应该返回该周的最后交易日
                        expected_friday = date(2025, 8, 8)
                        self.assertEqual(result, expected_friday,
                            f"{description}：应该返回该周的最后交易日 {expected_friday}")

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_get_latest_complete_weekly_end_date_friday(self, mock_market_manager, mock_mcal):
        """测试周五交易日时应该跳过当前周，使用上一个完整周的最后交易日"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import date, datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')  # 使用真实的时区对象
        mock_mcal.get_calendar.return_value = mock_calendar

        # 模拟MarketStateManager
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 模拟find_week_last_trading_day的不同调用
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 7, 11):  # 当前周
                return date(2025, 7, 11)
            elif target_date == date(2025, 7, 6):  # 上周日
                return date(2025, 7, 3)  # 上周四
            else:
                # 其他情况，找该周的最后交易日
                week_start = target_date - timedelta(days=target_date.weekday())
                week_end = week_start + timedelta(days=6)
                for d in sorted(trading_days_set, reverse=True):
                    if week_start <= d <= week_end:
                        return d
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 创建交易日集合
        trading_days_set = {
            date(2025, 6, 30),  # 上周一
            date(2025, 7, 1),   # 上周二
            date(2025, 7, 2),   # 上周三
            date(2025, 7, 3),   # 上周四
            date(2025, 7, 7),   # 本周一
            date(2025, 7, 8),   # 本周二
            date(2025, 7, 9),   # 本周三
            date(2025, 7, 10),  # 本周四
            date(2025, 7, 11),  # 本周五
            date(2025, 7, 14),  # 下周一
            date(2025, 7, 15),  # 下周二
            date(2025, 7, 16),  # 下周三
            date(2025, 7, 17),  # 下周四
            date(2025, 7, 18),  # 下周五
        }

        # 模拟MarketStateManager.get_trading_days_set
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前日期为2025-07-11，使其成为当前日期而不是历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            # 设置当前时间为2025-07-11的某个时间（市场交易中）
            mock_now = datetime(2025, 7, 11, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟交易时间表，显示市场16:00收盘
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_close': datetime(2025, 7, 11, 16, 0, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            # 测试周五（2025-07-11）
            test_date = date(2025, 7, 11)  # 周五
            result = _get_latest_complete_weekly_end_date(test_date)

        # 应该返回上一个完整周的最后交易日（2025-07-03，上周四）
        # 因为当前周五是交易日，当前周还在进行中，数据不完整
        expected = date(2025, 7, 3)
        self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_get_latest_complete_weekly_end_date_weekend(self, mock_market_manager, mock_mcal):
        """测试周末时应该使用本周的最后交易日作为结束日期"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import date, datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')  # 使用真实的时区对象
        mock_mcal.get_calendar.return_value = mock_calendar

        # 模拟MarketStateManager
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 7, 7),   # 本周一
            date(2025, 7, 8),   # 本周二
            date(2025, 7, 9),   # 本周三
            date(2025, 7, 10),  # 本周四
            date(2025, 7, 11),  # 本周五
            date(2025, 7, 14),  # 下周一
            date(2025, 7, 15),  # 下周二
            date(2025, 7, 16),  # 下周三
            date(2025, 7, 17),  # 下周四
            date(2025, 7, 18),  # 下周五
        }

        # 模拟MarketStateManager.get_trading_days_set
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 测试周六和周日
        test_cases = [
            (date(2025, 7, 19), "周六"),  # 周六
            (date(2025, 7, 20), "周日"),  # 周日
        ]

        for test_date, day_name in test_cases:
            with self.subTest(date=test_date, day=day_name):
                result = _get_latest_complete_weekly_end_date(test_date)

                # 应该返回本周五（2025-07-18），而不是上周五（2025-07-11）
                # 这修复了用户报告的错误：周末时错误地使用上周五作为结束日期
                expected = date(2025, 7, 18)
                self.assertEqual(result, expected,
                    f"{day_name}时应该返回本周五 {expected}，而不是 {result}")

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_get_latest_complete_weekly_end_date_holiday_friday(self, mock_market_manager, mock_mcal):
        """测试周五是假期时应该使用上一个完整周的最后交易日作为结束日期"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import date, datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')  # 使用真实的时区对象
        mock_mcal.get_calendar.return_value = mock_calendar

        # 模拟MarketStateManager
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（7月4日独立日假期）
        trading_days_set = {
            date(2025, 6, 23),  # 更早的日期
            date(2025, 6, 24),
            date(2025, 6, 25),
            date(2025, 6, 26),
            date(2025, 6, 27),  # 上周五
            date(2025, 6, 30),  # 上周一
            date(2025, 7, 1),   # 上周二
            date(2025, 7, 2),   # 上周三
            date(2025, 7, 3),   # 上周四
            # 2025-07-04 (周五) 是假期，不在交易日列表中
            date(2025, 7, 7),   # 下周一
            date(2025, 7, 8),   # 下周二
            date(2025, 7, 9),   # 下周三
            date(2025, 7, 10),  # 下周四
            date(2025, 7, 11),  # 下周五
        }

        # 模拟MarketStateManager.get_trading_days_set
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 测试假期周五（2025-07-04）
        test_date = date(2025, 7, 4)  # 周五，但是假期
        result = _get_latest_complete_weekly_end_date(test_date)

        # 应该返回上一个完整周的最后交易日（2025-07-03，上周四）
        expected = date(2025, 7, 3)
        self.assertEqual(result, expected)


class TestDailyMarketAwareDateLogic(unittest.TestCase):
    """测试日线数据的市场感知日期逻辑"""

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_before_open(self, mock_market_manager, mock_mcal):
        """测试开盘前时间应该返回前一交易日"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三早上7:00（开盘前）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 7, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟今天是交易日
            current_date = date(2025, 8, 6)

            result = get_market_aware_current_date()

            # 开盘前应该返回前一交易日
            expected = date(2025, 8, 5)  # 周二
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_during_trading(self, mock_market_manager, mock_mcal):
        """测试交易时间内应该返回前一交易日"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三上午10:30（交易中）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 10, 30, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场开放状态检查返回True（市场开放中）
            mock_market_manager.check_market_open_status.return_value = True

            result = get_market_aware_current_date()

            # 交易时间内应该返回前一交易日
            expected = date(2025, 8, 5)  # 周二
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_after_close_within_buffer(self, mock_market_manager, mock_mcal):
        """测试收盘后1小时内应该返回前一交易日"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三下午4:30（收盘后30分钟）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 16, 30, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场已收盘
            mock_market_manager.check_market_open_status.return_value = False

            # 模拟交易时间表
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_close': datetime(2025, 8, 6, 16, 0, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            result = get_market_aware_current_date()

            # 收盘后1小时内应该返回前一交易日
            expected = date(2025, 8, 5)  # 周二
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_after_close_beyond_buffer(self, mock_market_manager, mock_mcal):
        """测试收盘后超过1小时应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三下午6:00（收盘后2小时）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 18, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场已收盘
            mock_market_manager.check_market_open_status.return_value = False

            # 模拟交易时间表
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_close': datetime(2025, 8, 6, 16, 0, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            result = get_market_aware_current_date()

            # 收盘后超过1小时应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_weekend(self, mock_market_manager, mock_mcal):
        """测试周末应该返回最近的交易日"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（周末不包含）
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
            # 周六周日不是交易日
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周六上午10:00
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 9, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟_get_latest_trading_day返回周五
            with patch('stockaivo.data_service._get_latest_trading_day') as mock_get_latest:
                mock_get_latest.return_value = date(2025, 8, 8)  # 周五

                result = get_market_aware_current_date()

                # 周末应该返回最近的交易日（周五）
                expected = date(2025, 8, 8)  # 周五
                self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_holiday(self, mock_market_manager, mock_mcal):
        """测试假期应该返回最近的交易日"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（7月4日独立日假期）
        trading_days_set = {
            date(2025, 7, 1),   # 周二
            date(2025, 7, 2),   # 周三
            date(2025, 7, 3),   # 周四
            # 2025-07-04 (周五) 是假期，不在交易日列表中
            date(2025, 7, 7),   # 下周一
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为7月4日（假期）上午10:00
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 7, 4, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟_get_latest_trading_day返回周四
            with patch('stockaivo.data_service._get_latest_trading_day') as mock_get_latest:
                mock_get_latest.return_value = date(2025, 7, 3)  # 周四

                result = get_market_aware_current_date()

                # 假期应该返回最近的交易日（周四）
                expected = date(2025, 7, 3)  # 周四
                self.assertEqual(result, expected)


class TestMinuteMarketAwareDateLogic(unittest.TestCase):
    """测试分钟线数据的市场感知日期逻辑"""

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_pre_market(self, mock_market_manager, mock_mcal):
        """测试盘前时间（9:25）应该返回前一交易日"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三早上9:25（盘前）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 9, 25, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场未开放
            mock_market_manager.check_market_open_status.return_value = False

            # 模拟交易时间表
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_open': datetime(2025, 8, 6, 9, 30, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            # 模拟_get_latest_trading_day返回前一交易日
            with patch('stockaivo.data_service._get_latest_trading_day') as mock_get_latest:
                mock_get_latest.return_value = date(2025, 8, 5)  # 周二

                result = get_market_aware_minute_date()

                # 盘前应该返回前一交易日
                expected = date(2025, 8, 5)  # 周二
                self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_market_open(self, mock_market_manager, mock_mcal):
        """测试开盘时刻（9:30）应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三早上9:30（开盘时刻）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 9, 30, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场开放
            mock_market_manager.check_market_open_status.return_value = True

            result = get_market_aware_minute_date()

            # 开盘时刻应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_during_trading_hours(self, mock_market_manager, mock_mcal):
        """测试交易时间内（10:30）应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三上午10:30（交易中）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 10, 30, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场开放
            mock_market_manager.check_market_open_status.return_value = True

            result = get_market_aware_minute_date()

            # 交易时间内应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_before_close(self, mock_market_manager, mock_mcal):
        """测试收盘前5分钟（15:55）应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三下午3:55（收盘前5分钟）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 15, 55, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场仍在开放
            mock_market_manager.check_market_open_status.return_value = True

            result = get_market_aware_minute_date()

            # 收盘前应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_market_close(self, mock_market_manager, mock_mcal):
        """测试收盘时刻（16:00）应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三下午4:00（收盘时刻）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 16, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场刚收盘
            mock_market_manager.check_market_open_status.return_value = False

            result = get_market_aware_minute_date()

            # 收盘时刻应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_after_hours(self, mock_market_manager, mock_mcal):
        """测试盘后时间（16:05）应该返回当前日期"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周三下午4:05（盘后）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 6, 16, 5, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场已收盘
            mock_market_manager.check_market_open_status.return_value = False

            result = get_market_aware_minute_date()

            # 盘后应该返回当前日期
            expected = date(2025, 8, 6)  # 周三
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_minute_aware_date_weekend(self, mock_market_manager, mock_mcal):
        """测试周末应该返回最近的交易日"""
        from stockaivo.data_service import get_market_aware_minute_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（周末不包含）
        trading_days_set = {
            date(2025, 8, 4),   # 周一
            date(2025, 8, 5),   # 周二
            date(2025, 8, 6),   # 周三
            date(2025, 8, 7),   # 周四
            date(2025, 8, 8),   # 周五
            # 周六周日不是交易日
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为周六上午10:00
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 8, 9, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟_get_latest_trading_day返回周五
            with patch('stockaivo.data_service._get_latest_trading_day') as mock_get_latest:
                mock_get_latest.return_value = date(2025, 8, 8)  # 周五

                result = get_market_aware_minute_date()

                # 周末应该返回最近的交易日（周五）
                expected = date(2025, 8, 8)  # 周五
                self.assertEqual(result, expected)


class TestEdgeCasesAndSpecialScenarios(unittest.TestCase):
    """测试边界情况和特殊场景"""

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_early_close_day(self, mock_market_manager, mock_mcal):
        """测试提前收盘日（如感恩节前一天）的逻辑"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 11, 26),  # 感恩节前一天（提前收盘）
            date(2025, 11, 28),  # 感恩节后第一个交易日
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为感恩节前一天下午2:00（提前收盘后）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 11, 26, 14, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场已收盘（提前收盘）
            mock_market_manager.check_market_open_status.return_value = False

            # 模拟交易时间表（提前收盘时间13:00）
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_close': datetime(2025, 11, 26, 13, 0, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            result = get_market_aware_current_date()

            # 提前收盘超过1小时后应该返回当前日期
            expected = date(2025, 11, 26)
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_daylight_saving_transition(self, mock_market_manager, mock_mcal):
        """测试夏令时转换日的逻辑"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 3, 7),   # 夏令时转换前一天
            date(2025, 3, 10),  # 夏令时转换后第一个交易日
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为夏令时转换日（周日）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 3, 9, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟_get_latest_trading_day返回周五
            with patch('stockaivo.data_service._get_latest_trading_day') as mock_get_latest:
                mock_get_latest.return_value = date(2025, 3, 7)  # 周五

                result = get_market_aware_current_date()

                # 夏令时转换日应该返回最近的交易日
                expected = date(2025, 3, 7)  # 周五
                self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_market_aware_date_new_years_eve(self, mock_market_manager, mock_mcal):
        """测试新年前夜（提前收盘）的逻辑"""
        from stockaivo.data_service import get_market_aware_current_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合
        trading_days_set = {
            date(2025, 12, 30),  # 新年前夜前一天
            date(2025, 12, 31),  # 新年前夜（提前收盘）
            # 2026-01-01 新年假期
            date(2026, 1, 2),    # 新年后第一个交易日
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟当前时间为新年前夜下午2:30（提前收盘后30分钟）
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 31, 14, 30, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 模拟市场已收盘（提前收盘）
            mock_market_manager.check_market_open_status.return_value = False

            # 模拟交易时间表（提前收盘时间14:00）
            mock_schedule = MagicMock()
            mock_schedule.empty = False
            mock_schedule.iloc = [{'market_close': datetime(2025, 12, 31, 14, 0, 0, tzinfo=pytz.timezone('America/New_York'))}]
            mock_calendar.schedule.return_value = mock_schedule

            result = get_market_aware_current_date()

            # 提前收盘后30分钟，仍在缓冲期内，应该返回前一交易日
            expected = date(2025, 12, 30)
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_weekly_end_date_three_day_weekend(self, mock_market_manager, mock_mcal):
        """测试三天长周末的周线结束日期逻辑"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（劳动节长周末：周五正常，周一假期）
        trading_days_set = {
            date(2025, 8, 28),  # 上周四
            date(2025, 8, 29),  # 上周五
            date(2025, 9, 1),   # 本周一（劳动节假期，不是交易日）
            date(2025, 9, 2),   # 本周二
            date(2025, 9, 3),   # 本周三
            date(2025, 9, 4),   # 本周四
            date(2025, 9, 5),   # 本周五
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day的行为
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 9, 2):  # 周二
                return date(2025, 9, 5)  # 本周五
            elif target_date == date(2025, 8, 31):  # 上周日
                return date(2025, 8, 29)  # 上周五
            else:
                return target_date

        mock_market_manager.get_trading_days_set.return_value = trading_days_set
        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为2025-12-01，使2025-09-02成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 1, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试劳动节假期周二（历史日期）
            test_date = date(2025, 9, 2)  # 周二
            result = _get_latest_complete_weekly_end_date(test_date)

            # 周二是该周未完整，应该返回上一个完整周的最后交易日
            expected = date(2025, 8, 29)  # 上周五
            self.assertEqual(result, expected)

    @patch('stockaivo.data_service.mcal')
    @patch('stockaivo.data_service.MarketStateManager')
    def test_weekly_end_date_short_trading_week(self, mock_market_manager, mock_mcal):
        """测试短交易周（只有3天）的周线结束日期逻辑"""
        from stockaivo.data_service import _get_latest_complete_weekly_end_date
        from datetime import datetime
        import pytz

        # 模拟NYSE日历
        mock_calendar = MagicMock()
        mock_calendar.tz = pytz.timezone('America/New_York')
        mock_mcal.get_calendar.return_value = mock_calendar
        mock_market_manager.get_nyse_calendar.return_value = mock_calendar

        # 创建交易日集合（感恩节周：周一到周三，周四周五假期）
        trading_days_set = {
            date(2025, 11, 24),  # 周一
            date(2025, 11, 25),  # 周二
            date(2025, 11, 26),  # 周三（提前收盘）
            # 2025-11-27 感恩节假期
            # 2025-11-28 黑色星期五假期
            date(2025, 12, 1),   # 下周一
        }
        mock_market_manager.get_trading_days_set.return_value = trading_days_set

        # 模拟find_week_last_trading_day的行为
        def mock_find_week_last_trading_day(target_date, trading_days_set):
            if target_date == date(2025, 11, 29):  # 周六
                return date(2025, 11, 26)  # 本周三
            else:
                return target_date

        mock_market_manager.find_week_last_trading_day.side_effect = mock_find_week_last_trading_day

        # 模拟当前日期为2025-12-15，使2025-11-29成为历史日期
        with patch('stockaivo.data_service.datetime') as mock_datetime:
            mock_now = datetime(2025, 12, 15, 10, 0, 0, tzinfo=pytz.timezone('America/New_York'))
            mock_datetime.now.return_value = mock_now

            # 测试感恩节后的周六（历史日期）
            test_date = date(2025, 11, 29)  # 周六
            result = _get_latest_complete_weekly_end_date(test_date)

            # 周六时该周已完整，应该返回本周最后交易日（周三）
            expected = date(2025, 11, 26)  # 周三
            self.assertEqual(result, expected)


class TestMarketStateManagerPerformance(unittest.TestCase):
    """测试MarketStateManager的性能和缓存功能"""

    def test_market_state_manager_cache_stats(self):
        """测试MarketStateManager的缓存统计功能"""
        from stockaivo.data_service import MarketStateManager

        # 清空缓存
        MarketStateManager.clear_cache()

        # 获取初始统计
        initial_stats = MarketStateManager.get_cache_stats()
        self.assertEqual(initial_stats['cache_size'], 0)
        self.assertEqual(initial_stats['total_requests'], 0)

    def test_market_state_manager_performance_test(self):
        """测试MarketStateManager的性能测试功能"""
        from stockaivo.data_service import MarketStateManager

        # 运行性能测试
        test_results = MarketStateManager.test_performance()

        # 验证测试结果结构
        self.assertIn('test_date', test_results)
        self.assertIn('tests', test_results)
        self.assertIn('cache_stats', test_results)

        # 验证测试项目
        test_names = [test['name'] for test in test_results['tests']]
        expected_tests = [
            'NYSE日历获取',
            '交易日集合获取（首次）',
            '交易日集合获取（缓存命中）',
            '市场开放状态检查',
            '周线交易日查找'
        ]

        for expected_test in expected_tests:
            self.assertIn(expected_test, test_names)


if __name__ == '__main__':
    unittest.main()