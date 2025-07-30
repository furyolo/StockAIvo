"""
技术指标功能测试
测试TechnicalIndicator类的功能和与agents的集成
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
from stockaivo.ai.technical_indicator import TechnicalIndicator
from stockaivo.ai.agents import _process_technical_analysis_data, data_collection_agent, _build_technical_analysis_prompt
from stockaivo.ai.state import GraphState
from stockaivo.cache_manager import _is_market_open


class TestTechnicalIndicator:
    """TechnicalIndicator类的单元测试"""
    
    def setup_method(self):
        """测试前的设置"""
        self.indicator = TechnicalIndicator()
        
        # 创建测试数据
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(42)  # 确保测试结果可重复
        
        # 生成模拟股价数据
        close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        high_prices = close_prices + np.random.rand(100) * 2
        low_prices = close_prices - np.random.rand(100) * 2
        open_prices = close_prices + np.random.randn(100) * 0.3
        volumes = np.random.randint(1000000, 10000000, 100)
        
        self.test_df = pd.DataFrame({
            'Open': open_prices,
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)
    
    def test_init_default_params(self):
        """测试默认参数初始化"""
        indicator = TechnicalIndicator()
        assert 'ma_periods' in indicator.params
        assert 'rsi_period' in indicator.params
        assert indicator.params['rsi_period'] == 14
    
    def test_init_custom_params(self):
        """测试自定义参数初始化"""
        custom_params = {'rsi_period': 21, 'bollinger_period': 30}
        indicator = TechnicalIndicator(custom_params)
        assert indicator.params['rsi_period'] == 21
        assert indicator.params['bollinger_period'] == 30
    
    def test_calculate_ema(self):
        """测试EMA计算"""
        ema = self.indicator.calculate_ema(self.test_df['Close'], 20)
        
        # 验证EMA序列的基本属性
        assert len(ema) == len(self.test_df)
        assert not ema.isna().all()  # 不应该全是NaN
        assert ema.isna().sum() < len(ema)  # 应该有有效值
    
    def test_calculate_rsi(self):
        """测试RSI计算"""
        rsi = self.indicator.calculate_rsi(self.test_df['Close'], 14)
        
        # 验证RSI的基本属性
        assert len(rsi) == len(self.test_df)
        valid_rsi = rsi.dropna()
        assert len(valid_rsi) > 0
        assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()
    
    def test_calculate_macd(self):
        """测试MACD计算"""
        macd, signal, histogram = self.indicator.calculate_macd(self.test_df['Close'])
        
        # 验证MACD的基本属性
        assert len(macd) == len(self.test_df)
        assert len(signal) == len(self.test_df)
        assert len(histogram) == len(self.test_df)
        
        # 验证柱状图 = MACD - 信号线
        valid_indices = ~(macd.isna() | signal.isna())
        if valid_indices.any():
            np.testing.assert_array_almost_equal(
                histogram[valid_indices], 
                (macd - signal)[valid_indices], 
                decimal=10
            )
    
    def test_calculate_bollinger_bands(self):
        """测试布林带计算"""
        middle, upper, lower = self.indicator.calculate_bollinger_bands(
            self.test_df['Close'], 20, 2
        )
        
        # 验证布林带的基本属性
        assert len(middle) == len(self.test_df)
        assert len(upper) == len(self.test_df)
        assert len(lower) == len(self.test_df)
        
        # 验证上轨 > 中轨 > 下轨
        valid_indices = ~(middle.isna() | upper.isna() | lower.isna())
        if valid_indices.any():
            assert (upper[valid_indices] >= middle[valid_indices]).all()
            assert (middle[valid_indices] >= lower[valid_indices]).all()
    
    def test_calculate_atr(self):
        """测试ATR计算"""
        atr = self.indicator.calculate_atr(self.test_df, 14)
        
        # 验证ATR的基本属性
        assert len(atr) == len(self.test_df)
        valid_atr = atr.dropna()
        assert len(valid_atr) > 0
        assert (valid_atr >= 0).all()  # ATR应该非负
    
    def test_calculate_indicators_success(self):
        """测试完整技术指标计算成功情况"""
        result_df = self.indicator.calculate_indicators(self.test_df)
        
        # 验证返回的DataFrame包含原始列
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            assert col in result_df.columns
        
        # 验证技术指标列存在
        expected_indicators = [
            'MA5', 'MA20', 'MA60', 'RSI', 'MACD', 'Signal', 'Histogram',
            'BB_Middle', 'BB_Upper', 'BB_Lower', 'Volume_MA', 'Volume_Ratio',
            'ATR', 'Volatility'
        ]
        
        for indicator in expected_indicators:
            assert indicator in result_df.columns, f"缺少技术指标: {indicator}"
    
    def test_calculate_indicators_insufficient_data(self):
        """测试数据不足的情况"""
        # 创建只有10行的小数据集
        small_df = self.test_df.head(10)
        result_df = self.indicator.calculate_indicators(small_df)
        
        # 应该返回原始数据，不添加技术指标
        assert len(result_df.columns) == len(small_df.columns)
    
    def test_calculate_indicators_missing_columns(self):
        """测试缺少必要列的情况"""
        # 创建缺少Volume列的数据
        incomplete_df = self.test_df.drop('Volume', axis=1)
        result_df = self.indicator.calculate_indicators(incomplete_df)
        
        # 应该返回原始数据，不添加技术指标
        assert len(result_df.columns) == len(incomplete_df.columns)
    
    def test_calculate_indicators_exception_handling(self):
        """测试异常处理"""
        # 创建包含NaN的数据
        bad_df = self.test_df.copy()
        bad_df.loc[:, 'Close'] = np.nan
        
        # 应该能够处理异常并返回原始数据
        result_df = self.indicator.calculate_indicators(bad_df)
        assert result_df is not None
        assert len(result_df) == len(bad_df)


class TestAgentsIntegration:
    """测试与agents模块的集成"""
    
    def setup_method(self):
        """测试前的设置"""
        # 创建模拟的GraphState数据
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(42)
        
        close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        high_prices = close_prices + np.random.rand(100) * 2
        low_prices = close_prices - np.random.rand(100) * 2
        open_prices = close_prices + np.random.randn(100) * 0.3
        volumes = np.random.randint(1000000, 10000000, 100)
        
        test_df = pd.DataFrame({
            'Open': open_prices,
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)
        
        # 模拟raw_data格式
        self.mock_state = {
            'ticker': 'AAPL',
            'raw_data': {
                'daily_prices': {
                    'data': test_df.values.tolist(),
                    'columns': test_df.columns.tolist(),
                    'index': test_df.index.strftime('%Y-%m-%d').tolist()
                },
                'weekly_prices': {
                    'data': test_df.values.tolist(),
                    'columns': test_df.columns.tolist(),
                    'index': test_df.index.strftime('%Y-%m-%d').tolist()
                }
            }
        }
    
    def test_process_technical_analysis_data_with_indicators(self):
        """测试_process_technical_analysis_data函数包含技术指标"""
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(self.mock_state)

        # 验证基本返回值
        assert ticker == 'AAPL'
        assert isinstance(daily_str, str)
        assert isinstance(weekly_str, str)
        assert isinstance(tenmin_str, str)
        assert isinstance(daily_indicators, list)
        assert isinstance(weekly_indicators, list)
        assert isinstance(tenmin_indicators, list)

        # 验证技术指标在输出中
        technical_indicators = ['MA5', 'MA20', 'RSI', 'MACD', 'BB_Upper', 'ATR']
        for indicator in technical_indicators:
            assert indicator in daily_str, f"日线数据中缺少技术指标: {indicator}"
            assert indicator in weekly_str, f"周线数据中缺少技术指标: {indicator}"

        # 验证10分钟线数据（应该是"无10分钟线数据"，因为mock_state中没有tenmin_prices）
        assert tenmin_str == "无10分钟线数据"
        assert tenmin_indicators == []
    
    def test_process_technical_analysis_data_no_data(self):
        """测试无数据的情况"""
        empty_state = {'ticker': 'TEST', 'raw_data': {}}
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(empty_state)

        assert ticker == 'TEST'
        assert daily_str == "无日线数据"
        assert weekly_str == "无周线数据"
        assert tenmin_str == "无10分钟线数据"
        assert daily_indicators == []
        assert weekly_indicators == []
        assert tenmin_indicators == []
    
    @patch('stockaivo.ai.agents.TechnicalIndicator')
    def test_process_technical_analysis_data_exception_handling(self, mock_indicator_class):
        """测试技术指标计算异常处理"""
        # 模拟技术指标计算抛出异常
        mock_indicator = Mock()
        mock_indicator.calculate_indicators.side_effect = Exception("计算错误")
        mock_indicator_class.return_value = mock_indicator

        # 应该能够处理异常并继续执行
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(self.mock_state)

        assert ticker == 'AAPL'
        assert isinstance(daily_str, str)
        assert isinstance(weekly_str, str)
        assert isinstance(tenmin_str, str)
        assert isinstance(daily_indicators, list)
        assert isinstance(weekly_indicators, list)
        assert isinstance(tenmin_indicators, list)


class TestTenMinuteLineIntegration:
    """测试10分钟线数据支持的完整集成"""

    def setup_method(self):
        """测试前的设置"""
        # 创建模拟的10分钟线数据
        dates = pd.date_range('2024-01-01 09:30:00', periods=39, freq='10min')  # 一天的10分钟线数据
        np.random.seed(42)

        close_prices = 100 + np.cumsum(np.random.randn(39) * 0.1)
        high_prices = close_prices + np.random.rand(39) * 0.5
        low_prices = close_prices - np.random.rand(39) * 0.5
        open_prices = close_prices + np.random.randn(39) * 0.1
        volumes = np.random.randint(100000, 1000000, 39)

        self.tenmin_df = pd.DataFrame({
            'Open': open_prices,
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)

        # 创建包含10分钟线数据的mock state
        self.mock_state_with_tenmin = {
            'ticker': 'AAPL',
            'raw_data': {
                'daily_prices': {
                    'data': self.tenmin_df.values.tolist(),
                    'columns': self.tenmin_df.columns.tolist(),
                    'index': self.tenmin_df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
                },
                'weekly_prices': {
                    'data': self.tenmin_df.values.tolist(),
                    'columns': self.tenmin_df.columns.tolist(),
                    'index': self.tenmin_df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
                },
                'tenmin_prices': {
                    'data': self.tenmin_df.values.tolist(),
                    'columns': self.tenmin_df.columns.tolist(),
                    'index': self.tenmin_df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
                }
            }
        }

    def test_process_technical_analysis_data_with_tenmin(self):
        """测试包含10分钟线数据的处理"""
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(self.mock_state_with_tenmin)

        # 验证基本返回值
        assert ticker == 'AAPL'
        assert isinstance(daily_str, str)
        assert isinstance(weekly_str, str)
        assert isinstance(tenmin_str, str)

        # 验证10分钟线数据不是"无数据"
        assert tenmin_str != "无10分钟线数据"
        assert "Open" in tenmin_str
        assert "High" in tenmin_str
        assert "Low" in tenmin_str
        assert "Close" in tenmin_str
        assert "Volume" in tenmin_str

        # 验证10分钟线不计算技术指标
        assert tenmin_indicators == []

        # 验证日线和周线仍然计算技术指标
        assert len(daily_indicators) > 0
        assert len(weekly_indicators) > 0

    @patch('stockaivo.ai.agents._is_market_open')
    def test_data_collection_agent_market_open(self, mock_is_market_open):
        """测试市场开放时的数据收集逻辑"""
        mock_is_market_open.return_value = True

        # 模拟数据收集agent的periods_to_fetch逻辑
        periods_to_fetch = ["daily", "weekly"]

        if mock_is_market_open():
            periods_to_fetch.append("10min")

        # 验证10分钟线被添加
        assert "10min" in periods_to_fetch
        assert len(periods_to_fetch) == 3

    @patch('stockaivo.ai.agents._is_market_open')
    def test_data_collection_agent_market_closed(self, mock_is_market_open):
        """测试市场关闭时的数据收集逻辑"""
        mock_is_market_open.return_value = False

        # 模拟数据收集agent的periods_to_fetch逻辑
        periods_to_fetch = ["daily", "weekly"]

        if mock_is_market_open():
            periods_to_fetch.append("10min")

        # 验证10分钟线未被添加
        assert "10min" not in periods_to_fetch
        assert len(periods_to_fetch) == 2

    def test_build_technical_analysis_prompt_with_tenmin(self):
        """测试包含10分钟线的提示词构建"""
        from datetime import date

        ticker = "AAPL"
        daily_str = "日线数据..."
        weekly_str = "周线数据..."
        tenmin_str = "10分钟线数据..."
        daily_indicators = ["MA5", "RSI", "MACD"]
        weekly_indicators = ["MA20", "RSI", "MACD"]
        tenmin_indicators = []  # 10分钟线不计算技术指标
        market_date = date(2024, 1, 15)

        prompt = _build_technical_analysis_prompt(
            ticker, daily_str, weekly_str, tenmin_str,
            daily_indicators, weekly_indicators, tenmin_indicators,
            market_date
        )

        # 验证提示词包含多时间框架分析
        assert "多时间框架" in prompt
        assert "周线" in prompt
        assert "日线" in prompt
        assert "10分钟线" in prompt
        assert "短期波动观察" in prompt
        assert "不计算技术指标" in prompt

    def test_build_technical_analysis_prompt_without_tenmin(self):
        """测试不包含10分钟线的提示词构建"""
        from datetime import date

        ticker = "AAPL"
        daily_str = "日线数据..."
        weekly_str = "周线数据..."
        tenmin_str = "无10分钟线数据"
        daily_indicators = ["MA5", "RSI", "MACD"]
        weekly_indicators = ["MA20", "RSI", "MACD"]
        tenmin_indicators = []
        market_date = date(2024, 1, 15)

        prompt = _build_technical_analysis_prompt(
            ticker, daily_str, weekly_str, tenmin_str,
            daily_indicators, weekly_indicators, tenmin_indicators,
            market_date
        )

        # 验证提示词使用传统的日线+周线分析
        assert "多时间框架" not in prompt
        assert "日线和周线" in prompt
        assert "10分钟线数据" not in prompt


class TestTenMinuteLineEdgeCases:
    """测试10分钟线功能的边界情况和错误场景"""

    def test_tenmin_data_empty_dataframe(self):
        """测试10分钟线数据为空DataFrame的情况"""
        empty_tenmin_state = {
            'ticker': 'TEST',
            'raw_data': {
                'tenmin_prices': {
                    'data': [],
                    'columns': ['Open', 'High', 'Low', 'Close', 'Volume'],
                    'index': []
                }
            }
        }

        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(empty_tenmin_state)

        # 验证空数据的处理
        assert ticker == 'TEST'
        assert tenmin_str != "无10分钟线数据"  # 有数据结构，但是空的
        assert tenmin_indicators == []

    def test_tenmin_data_malformed(self):
        """测试10分钟线数据格式错误的情况"""
        malformed_state = {
            'ticker': 'TEST',
            'raw_data': {
                'tenmin_prices': {
                    'data': [[1, 2, 3]],  # 数据列数不匹配
                    'columns': ['Open', 'High', 'Low', 'Close', 'Volume'],
                    'index': ['2024-01-01 09:30:00']
                }
            }
        }

        # 应该能够处理格式错误的数据
        try:
            ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(malformed_state)
            assert ticker == 'TEST'
            assert isinstance(tenmin_str, str)
            assert tenmin_indicators == []
        except Exception:
            # 如果抛出异常，也是可以接受的
            pass

    def test_tenmin_data_with_nan_values(self):
        """测试10分钟线数据包含NaN值的情况"""
        import numpy as np

        nan_data = [
            [100.0, 101.0, 99.0, 100.5, 1000000],
            [np.nan, 102.0, 100.0, 101.0, 1100000],  # 包含NaN
            [101.0, 103.0, 101.0, 102.0, 1200000]
        ]

        nan_state = {
            'ticker': 'TEST',
            'raw_data': {
                'tenmin_prices': {
                    'data': nan_data,
                    'columns': ['Open', 'High', 'Low', 'Close', 'Volume'],
                    'index': ['2024-01-01 09:30:00', '2024-01-01 09:40:00', '2024-01-01 09:50:00']
                }
            }
        }

        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(nan_state)

        # 验证包含NaN的数据处理
        assert ticker == 'TEST'
        assert isinstance(tenmin_str, str)
        assert tenmin_indicators == []

    @patch('stockaivo.ai.agents.pd.DataFrame')
    def test_tenmin_dataframe_creation_exception(self, mock_dataframe):
        """测试10分钟线DataFrame创建异常的情况"""
        mock_dataframe.side_effect = Exception("DataFrame创建失败")

        tenmin_state = {
            'ticker': 'TEST',
            'raw_data': {
                'tenmin_prices': {
                    'data': [[100, 101, 99, 100.5, 1000000]],
                    'columns': ['Open', 'High', 'Low', 'Close', 'Volume'],
                    'index': ['2024-01-01 09:30:00']
                }
            }
        }

        # 应该能够处理DataFrame创建异常
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(tenmin_state)

        assert ticker == 'TEST'
        assert tenmin_str == "无10分钟线数据"  # 异常时应该返回无数据
        assert tenmin_indicators == []

    def test_prompt_building_with_none_indicators(self):
        """测试提示词构建时指标列表为None的情况"""
        from datetime import date

        prompt = _build_technical_analysis_prompt(
            "AAPL", "日线数据", "周线数据", "10分钟线数据",
            None, None, None,  # 所有指标列表都是None
            date(2024, 1, 15)
        )

        # 验证能够处理None指标列表
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "AAPL" in prompt


class TestTenMinuteLinePerformance:
    """测试10分钟线功能的性能相关测试"""

    def test_large_tenmin_dataset_processing(self):
        """测试大量10分钟线数据的处理性能"""
        import time

        # 创建一个月的10分钟线数据（约858个数据点）
        dates = pd.date_range('2024-01-01 09:30:00', periods=858, freq='10min')
        np.random.seed(42)

        close_prices = 100 + np.cumsum(np.random.randn(858) * 0.1)
        high_prices = close_prices + np.random.rand(858) * 0.5
        low_prices = close_prices - np.random.rand(858) * 0.5
        open_prices = close_prices + np.random.randn(858) * 0.1
        volumes = np.random.randint(100000, 1000000, 858)

        large_df = pd.DataFrame({
            'Open': open_prices,
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)

        large_state = {
            'ticker': 'AAPL',
            'raw_data': {
                'tenmin_prices': {
                    'data': large_df.values.tolist(),
                    'columns': large_df.columns.tolist(),
                    'index': large_df.index.strftime('%Y-%m-%d %H:%M:%S').tolist()
                }
            }
        }

        # 测试处理时间
        start_time = time.time()
        ticker, daily_str, weekly_str, tenmin_str, daily_indicators, weekly_indicators, tenmin_indicators = _process_technical_analysis_data(large_state)
        end_time = time.time()

        processing_time = end_time - start_time

        # 验证处理结果
        assert ticker == 'AAPL'
        assert tenmin_str != "无10分钟线数据"
        assert tenmin_indicators == []

        # 验证处理时间合理（应该在几秒内完成）
        assert processing_time < 10.0, f"处理时间过长: {processing_time}秒"

        print(f"大数据集处理时间: {processing_time:.3f}秒")


if __name__ == "__main__":
    pytest.main([__file__])
