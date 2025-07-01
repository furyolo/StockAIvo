import unittest
from unittest.mock import patch, MagicMock, call
import pandas as pd
from datetime import date
from sqlalchemy.orm import Session

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


class TestGetData(unittest.TestCase):

    def setUp(self):
        """Set up a dummy DataFrame for testing."""
        self.dummy_df = pd.DataFrame({
            'dates': pd.to_datetime(['2023-01-01', '2023-01-02']),
            'open': [100, 102],
            'close': [101, 103]
        })
        self.ticker: str = "TEST"
        self.period: PeriodType = "daily"
    
    @patch('stockaivo.data_service.cache_manager')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._get_required_dates')
    def test_cache_hit(self, mock_get_required_dates, mock_data_provider, mock_query_db, mock_cache_manager):
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
        result_df = get_stock_data(mock_db_session, self.ticker, self.period, start_date='2023-01-01', end_date='2023-01-02')

        # Assert
        mock_cache_manager.get_from_redis.assert_called_once_with(self.ticker, self.period, CacheType.GENERAL_CACHE)
        mock_query_db.assert_not_called()
        mock_data_provider.fetch_from_akshare.assert_not_called()
        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df, self.dummy_df)
        print("--- Test: Cache Hit PASSED ---")

class TestDataServiceDualCache(unittest.TestCase):

    def setUp(self):
        """为测试设置通用资源。"""
        self.ticker = "DUMMY"
        self.period: PeriodType = "daily"
        self.start_date = "2023-01-01"
        self.end_date = "2023-01-05"
        self.db_session = MagicMock(spec=Session)
        
        # 从数据库返回的数据
        self.db_data = pd.DataFrame({
            'dates': pd.to_datetime(['2023-01-01', '2023-01-02']),
            'price': [10, 11]
        })
        
        # 从API返回的数据
        self.api_data = pd.DataFrame({
            'dates': pd.to_datetime(['2023-01-03', '2023-01-04']),
            'price': [12, 13]
        })

    @patch('stockaivo.data_service._get_required_dates', MagicMock(return_value=[date(2023,1,1), date(2023,1,2)]))
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    def test_database_hit_saves_to_general_cache(self, mock_cache_manager, mock_query_database, mock_data_provider):
        """验证从数据库获取数据后，会将其存入 GENERAL_CACHE。"""
        # 安排
        mock_cache_manager.get_from_redis.return_value = None  # 模拟缓存未命中
        mock_query_database.return_value = self.db_data
        
        # 操作
        get_stock_data(self.db_session, self.ticker, self.period, self.start_date, self.end_date)
        
        # 断言
        mock_cache_manager.save_to_redis.assert_called_once_with(
            self.ticker, self.period, self.db_data, CacheType.GENERAL_CACHE
        )
        mock_data_provider.fetch_from_akshare.assert_not_called()

    @patch('stockaivo.data_service.database_writer.save_dataframe_to_db', MagicMock(return_value=True))
    @patch('stockaivo.data_service._get_required_dates', MagicMock(return_value=[date(2023,1,3), date(2023,1,4)]))
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    def test_api_hit_saves_to_both_caches(self, mock_cache_manager, mock_query_database, mock_data_provider):
        """验证从API获取数据后，会将其同时存入 PENDING_SAVE 和 GENERAL_CACHE。"""
        # 安排
        mock_cache_manager.get_from_redis.return_value = None  # 缓存未命中
        mock_query_database.return_value = None  # 数据库未命中
        mock_data_provider.fetch_from_akshare.return_value = self.api_data
        
        # 操作
        get_stock_data(self.db_session, self.ticker, self.period, self.start_date, self.end_date)
        
        # 断言
        expected_calls = [
            call(self.ticker, self.period, self.api_data, CacheType.PENDING_SAVE),
            call(self.ticker, self.period, self.api_data, CacheType.GENERAL_CACHE)
        ]
        mock_cache_manager.save_to_redis.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_cache_manager.save_to_redis.call_count, 2)

    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service.cache_manager')
    def test_partial_cache_triggers_fetch_and_merge(self, mock_cache_manager, mock_query_database, mock_data_provider, mock_get_required_dates):
        """验证当通用缓存不完整时，能正确获取缺失数据、合并并更新两种缓存。"""
        # 安排
        # 模拟 GENERAL_CACHE 中只有部分数据
        mock_cache_manager.get_from_redis.return_value = self.db_data
        
        # 模拟缺失的数据可以从 API 获取
        mock_query_database.return_value = None # 数据库中没有缺失的数据
        mock_data_provider.fetch_from_akshare.return_value = self.api_data
        
        # 模拟日期计算
        required_dates = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
        mock_get_required_dates.return_value = required_dates

        # 预期的合并后数据
        combined_data = pd.concat([self.db_data, self.api_data]).sort_values(by='dates').reset_index(drop=True)

        # 操作
        result_df = get_stock_data(self.db_session, self.ticker, self.period, "2023-01-01", "2023-01-04")

        # 断言
        # 1. 检查是否尝试从通用缓存获取
        mock_cache_manager.get_from_redis.assert_called_once_with(self.ticker, self.period, CacheType.GENERAL_CACHE)
        
        # 2. 检查是否为缺失范围调用了数据提供者
        mock_data_provider.fetch_from_akshare.assert_called_once()
        
        # 3. 检查缓存更新调用
        save_calls = mock_cache_manager.save_to_redis.call_args_list
        
        # 验证 PENDING_SAVE 只保存了新获取的数据和 GENERAL_CACHE 保存了合并后的数据
        found_pending_call = False
        found_general_call = False
        for c in save_calls:
            # c is a call object, e.g., call(ticker, period, df, cache_type)
            args, _ = c
            actual_df = args[2]
            cache_type = args[3]

            if cache_type == CacheType.PENDING_SAVE:
                # 比较前重置索引，以忽略索引差异
                pd.testing.assert_frame_equal(actual_df.reset_index(drop=True), self.api_data.reset_index(drop=True))
                found_pending_call = True
            elif cache_type == CacheType.GENERAL_CACHE:
                # 比较前重置索引
                pd.testing.assert_frame_equal(actual_df.reset_index(drop=True), combined_data.reset_index(drop=True))
                found_general_call = True

        self.assertTrue(found_pending_call, "save_to_redis call for PENDING_SAVE not found or its DataFrame did not match.")
        self.assertTrue(found_general_call, "save_to_redis call for GENERAL_CACHE not found or its DataFrame did not match.")

        # 4. 验证最终返回的数据是合并后的数据
        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df.reset_index(drop=True), combined_data.reset_index(drop=True))

    @patch('stockaivo.data_service.database_writer')
    @patch('stockaivo.data_service.data_provider')
    @patch('stockaivo.data_service._query_database')
    @patch('stockaivo.data_service._get_required_dates')
    @patch('stockaivo.data_service.cache_manager')
    def test_fills_gap_from_database_and_saves_missing_data(self, mock_cache_manager, mock_get_required_dates, mock_query_database, mock_data_provider, mock_db_writer):
        """
        验证当数据库数据存在缺口时，能够正确从 API 获取缺失数据，
        合并数据，返回完整结果，并将新数据异步写入数据库。
        """
        # 1. 设置场景
        # 模拟缓存未命中
        mock_cache_manager.get_from_redis.return_value = None

        # 准备一个有日期缺口的 DataFrame
        db_data_with_gap = pd.DataFrame({
            'dates': pd.to_datetime(['2025-05-15', '2025-05-16', '2025-05-17', '2025-05-18', '2025-05-22', '2025-05-23']),
            'price': [100, 101, 102, 103, 108, 109]
        })
        mock_query_database.return_value = db_data_with_gap

        # 模拟所需的完整日期范围
        required_dates = pd.to_datetime(pd.date_range(start='2025-05-15', end='2025-05-23')).date
        mock_get_required_dates.return_value = required_dates

        # 2. 模拟外部调用
        # 准备缺失日期的数据
        missing_data = pd.DataFrame({
            'dates': pd.to_datetime(['2025-05-19', '2025-05-20', '2025-05-21']),
            'price': [104, 105, 107]
        })
        mock_data_provider.fetch_from_akshare.return_value = missing_data
        
        # 3. 模拟后台任务
        mock_db_writer.save_dataframe_to_db = MagicMock()

        # 4. 执行
        result_df = get_stock_data(
            self.db_session,
            self.ticker,
            self.period,
            start_date='2025-05-15',
            end_date='2025-05-23'
        )

        # 5. 断言
        # 断言返回的 DataFrame 是完整的
        expected_data = pd.concat([db_data_with_gap, missing_data]).sort_values(by='dates').reset_index(drop=True)
        self.assertIsNotNone(result_df)
        if result_df is not None:
            pd.testing.assert_frame_equal(result_df.reset_index(drop=True), expected_data.reset_index(drop=True))

        # 断言 fetch_from_akshare 被以正确的缺失日期范围调用
        mock_data_provider.fetch_from_akshare.assert_called_once()
        call_args, call_kwargs = mock_data_provider.fetch_from_akshare.call_args
        # 验证位置参数
        # (db_session, ticker, period, start_date, end_date)
        self.assertEqual(call_args[3], '2025-05-19')
        self.assertEqual(call_args[4], '2025-05-21')

        # 断言 save_dataframe_to_db 被异步调用，并且只包含新获取的数据
        mock_db_writer.save_dataframe_to_db.assert_called_once()
        save_call_args = mock_db_writer.save_dataframe_to_db.call_args
        saved_df = save_call_args.kwargs['dataframe']
        pd.testing.assert_frame_equal(saved_df.reset_index(drop=True), missing_data.reset_index(drop=True))

class TestQueryDatabase(unittest.TestCase):

    @patch('stockaivo.data_service.pd.read_sql')
    @patch('stockaivo.data_service.inspect')
    @patch('stockaivo.data_service.select')
    def test_excludes_timestamp_columns(self, mock_select, mock_inspect, mock_read_sql):
        """
        验证 _query_database 是否正确地从查询中排除了 created_at 和 updated_at 列。
        """
        # 安排
        mock_db_session = MagicMock(spec=Session)
        mock_db_session.bind = "dummy_connection"
        ticker = "TEST"
        period = "daily"

        # 模拟 inspect(model).c 返回的列对象
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
        
        # 模拟 read_sql 返回一个不包含时间戳列的 DataFrame
        mock_read_sql.return_value = pd.DataFrame({
            'ticker': [ticker],
            'dates': [pd.to_datetime('2023-01-01')],
            'open': [100],
            'close': [101]
        })
        
        # 设置 select 的返回值，以便后续的 .where 和 .order_by 调用能够链式执行
        mock_query = MagicMock()
        mock_select.return_value.where.return_value.order_by.return_value = mock_query

        # 导入要测试的函数
        from stockaivo.data_service import _query_database
        
        # 操作
        result_df = _query_database(mock_db_session, ticker, period)

        # 断言
        # 1. 验证 inspect 被调用
        mock_inspect.assert_called_once()

        # 2. 验证 select 函数被以正确的列调用
        mock_select.assert_called_once()
        selected_columns = mock_select.call_args[0]
        
        # 提取列名进行断言
        selected_column_names = [c.name for c in selected_columns]

        self.assertIn('ticker', selected_column_names)
        self.assertIn('dates', selected_column_names)
        self.assertNotIn('created_at', selected_column_names)
        self.assertNotIn('updated_at', selected_column_names)

        # 3. 验证 read_sql 被调用
        mock_read_sql.assert_called_once_with(mock_select.return_value.where.return_value.order_by.return_value, "dummy_connection")

        # 4. 验证返回的 DataFrame 是预期的
        self.assertIsNotNone(result_df)
        if result_df is not None:
            self.assertNotIn('created_at', result_df.columns)
            self.assertNotIn('updated_at', result_df.columns)


if __name__ == '__main__':
    unittest.main()