"""
技术指标功能测试
测试TechnicalIndicator类的功能和与agents的集成
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch
from stockaivo.ai.technical_indicator import TechnicalIndicator
from stockaivo.ai.agents import _process_technical_analysis_data
from stockaivo.ai.state import GraphState


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
        ticker, daily_str, weekly_str = _process_technical_analysis_data(self.mock_state)
        
        # 验证基本返回值
        assert ticker == 'AAPL'
        assert isinstance(daily_str, str)
        assert isinstance(weekly_str, str)
        
        # 验证技术指标在输出中
        technical_indicators = ['MA5', 'MA20', 'RSI', 'MACD', 'BB_Upper', 'ATR']
        for indicator in technical_indicators:
            assert indicator in daily_str, f"日线数据中缺少技术指标: {indicator}"
            assert indicator in weekly_str, f"周线数据中缺少技术指标: {indicator}"
    
    def test_process_technical_analysis_data_no_data(self):
        """测试无数据的情况"""
        empty_state = {'ticker': 'TEST', 'raw_data': {}}
        ticker, daily_str, weekly_str = _process_technical_analysis_data(empty_state)
        
        assert ticker == 'TEST'
        assert daily_str == "无日线数据"
        assert weekly_str == "无周线数据"
    
    @patch('stockaivo.ai.agents.TechnicalIndicator')
    def test_process_technical_analysis_data_exception_handling(self, mock_indicator_class):
        """测试技术指标计算异常处理"""
        # 模拟技术指标计算抛出异常
        mock_indicator = Mock()
        mock_indicator.calculate_indicators.side_effect = Exception("计算错误")
        mock_indicator_class.return_value = mock_indicator
        
        # 应该能够处理异常并继续执行
        ticker, daily_str, weekly_str = _process_technical_analysis_data(self.mock_state)
        
        assert ticker == 'AAPL'
        assert isinstance(daily_str, str)
        assert isinstance(weekly_str, str)


if __name__ == "__main__":
    pytest.main([__file__])
