import unittest
from unittest.mock import patch, MagicMock, call
import pandas as pd
from datetime import date
from sqlalchemy.orm import Session
import asyncio

# The function to be tested
from stockaivo.data_service import get_stock_data, PeriodType, _find_missing_date_ranges
from stockaivo.cache_manager import CacheType

class TestFindMissingDateRanges(unittest.TestCase):

    def test_no_missing_dates(self):
        """当所有必需日期都已缓存时，应返回空列表。"""
        required = [date(2023, 1, 1), date(2023, 1, 2)]
        cached = [date(2023, 1, 1), date(2023, 1, 2)]
        self.assertEqual(_find_missing_date_ranges(required, cached), [])

    def test_all_dates_missing(self):
        """当所有必需日期都缺失时，应返回一个包含整个范围的列表。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = []
        expected = [(date(2023, 1, 1), date(2023, 1, 3))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_single_gap_in_the_middle(self):
        """当缓存数据中间有一个缺口时，应正确识别该缺失范围。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
        cached = [date(2023, 1, 1), date(2023, 1, 4)]
        expected = [(date(2023, 1, 2), date(2023, 1, 3))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_multiple_gaps(self):
        """当存在多个不连续的缺失范围时，应全部识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5), date(2023, 1, 6)]
        cached = [date(2023, 1, 2), date(2023, 1, 5)]
        expected = [(date(2023, 1, 1), date(2023, 1, 1)), (date(2023, 1, 3), date(2023, 1, 4)), (date(2023, 1, 6), date(2023, 1, 6))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_missing_at_the_beginning(self):
        """当缺失范围在开始部分时，应正确识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = [date(2023, 1, 3)]
        expected = [(date(2023, 1, 1), date(2023, 1, 2))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_missing_at_the_end(self):
        """当缺失范围在结尾部分时，应正确识别。"""
        required = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
        cached = [date(2023, 1, 1)]
        expected = [(date(2023, 1, 2), date(2023, 1, 3))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_empty_required_dates(self):
        """当必需日期列表为空时，应返回空列表。"""
        required = []
        cached = [date(2023, 1, 1)]
        self.assertEqual(_find_missing_date_ranges(required, cached), [])

    def test_empty_cached_dates(self):
        """当缓存日期列表为空时，应返回整个必需范围。"""
        required = [date(2023, 1, 1), date(2023, 1, 2)]
        cached = []
        expected = [(date(2023, 1, 1), date(2023, 1, 2))]
        self.assertEqual(_find_missing_date_ranges(required, cached), expected)

    def test_unsorted_inputs(self):
        """即使输入是未排序的，也应该能正确处理（尽管函数内部目前依赖排序的required_dates）。"""
        required = [date(2023, 1, 4), date(2023, 1, 1), date(2023, 1, 3), date(2023, 1, 2)]
        cached = [date(2023, 1, 3), date(2023, 1, 1)]
        # The new implementation doesn't rely on sorted required_dates
        expected = [(date(2023, 1, 4), date(2023, 1, 4)), (date(2023, 1, 2), date(2023, 1, 2))]
        # The result might be in a different order depending on the iteration order of the unsorted list
        result = _find_missing_date_ranges(required, cached)
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
        result_df = await get_stock_data(mock_db_session, self.ticker, self.period, start_date='2023-01-01', end_date='2023-01-02')

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

        await get_stock_data(mock_db_session, self.ticker, "daily", start_date=provided_start_date, end_date=provided_end_date)

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
                start_date=start_date_req.strftime('%Y-%m-%d'),
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
        
        await get_stock_data(self.db_session, self.ticker, self.period, self.start_date, self.end_date)
        
        mock_cache_manager.save_to_redis.assert_called_once_with(
            self.ticker, self.period, self.db_data, CacheType.GENERAL_CACHE
        )
        mock_data_provider.fetch_from_akshare.assert_not_called()

    @patch('stockaivo.data_service.database_writer.save_dataframe_to_db', MagicMock(return_value=True))
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
        
        await get_stock_data(self.db_session, self.ticker, self.period, self.start_date, self.end_date)
        
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

        result_df = await get_stock_data(self.db_session, self.ticker, self.period, "2023-01-01", "2023-01-04")

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
    @patch('stockaivo.data_service.database_writer')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service.cache_manager')
    async def test_fills_gap_from_database_and_saves_missing_data(self, mock_cache_manager, mock_get_required_dates, mock_query_database, mock_data_provider, mock_db_writer, mock_append_to_pending_save):
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
            start_date='2025-05-15',
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
            start_date='2025-04-18',
            end_date='2025-04-18'
        )

        # 断言
        # 关键断言：`fetch_from_akshare` 不应该被调用，因为该日期范围是节假日
        mock_fetch_from_akshare.assert_not_called()
        print("--- Test: Skips Fetching for Holiday-Only Range PASSED ---")


if __name__ == '__main__':
    unittest.main()