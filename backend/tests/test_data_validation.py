"""
数据验证和修复功能的单元测试

测试智能数据验证与修复系统的各种场景，包括：
- 正常数据验证
- 边界异常修复
- 分层验证策略
- 配置参数影响
- 边界情况处理
"""

import unittest
import pandas as pd
from datetime import datetime
from stockaivo.data_provider import DataValidator, ValidationResult, DataProviderConfig


class TestDataValidation(unittest.TestCase):
    """数据验证功能测试类"""
    
    def setUp(self):
        """测试前的设置"""
        # 创建正常的测试数据
        self.normal_data = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'minute_timestamp': pd.to_datetime([
                '2024-01-01 09:30:00', 
                '2024-01-01 09:31:00', 
                '2024-01-01 09:32:00'
            ])
        })
        
        # 创建边界异常数据（异常比例在容忍范围内）
        # 创建20条记录，只有1条异常，异常比例为5%
        timestamps = pd.date_range('2024-01-01 09:30:00', periods=20, freq='1min')
        opens = [100.0] * 20
        highs = [105.0] * 20
        lows = [99.0] * 20
        closes = [104.0] * 20

        # 只在第一条记录设置异常（首时刻）
        opens[0] = 110.0  # 开盘价超出范围

        self.boundary_anomaly_data = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'minute_timestamp': timestamps
        })
        
        # 创建严重异常数据（超过容忍度的异常比例）
        # 创建20条记录，有3条异常，异常比例为15%，超过5%的容忍度
        timestamps = pd.date_range('2024-01-01 09:30:00', periods=20, freq='1min')
        opens = [100.0] * 20
        highs = [105.0] * 20
        lows = [99.0] * 20
        closes = [104.0] * 20

        # 设置3条异常记录
        opens[0] = 110.0   # 第1条异常
        opens[1] = 110.0   # 第2条异常
        closes[2] = 90.0   # 第3条异常

        self.severe_anomaly_data = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'minute_timestamp': timestamps
        })
        
        # 创建缺少列的数据
        self.missing_columns_data = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            # 缺少 'low' 和 'close' 列
        })
    
    def test_normal_data_validation(self):
        """测试正常数据的验证"""
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            self.normal_data, 'minute'
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(result.repaired_count, 0)
        self.assertEqual(result.error_count, 0)
        self.assertEqual(len(result.warnings), 0)
        self.assertEqual(result.quality_score, 1.0)
        self.assertEqual(result.anomaly_ratio, 0.0)
    
    def test_boundary_anomaly_repair(self):
        """测试边界异常的修复"""
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            self.boundary_anomaly_data, 'minute'
        )
        
        # 应该通过验证（修复后）
        self.assertTrue(is_valid)
        self.assertGreater(result.repaired_count, 0)
        
        # 验证修复后的价格在合理范围内
        self.assertTrue((repaired_df['open'] >= repaired_df['low']).all())
        self.assertTrue((repaired_df['open'] <= repaired_df['high']).all())
        self.assertTrue((repaired_df['close'] >= repaired_df['low']).all())
        self.assertTrue((repaired_df['close'] <= repaired_df['high']).all())
        
        # 验证修复统计
        self.assertIn('open_repaired', result.repair_stats)
        self.assertIn('close_repaired', result.repair_stats)
    
    def test_severe_anomaly_handling(self):
        """测试严重异常的处理"""
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            self.severe_anomaly_data, 'minute'
        )

        # 异常比例超过容忍度时应该验证失败
        self.assertFalse(is_valid)
        self.assertGreater(result.repaired_count, 0)

        # 验证异常比例计算
        self.assertGreater(result.anomaly_ratio, 0)
        self.assertGreater(result.anomaly_ratio, DataProviderConfig.MAX_ANOMALY_RATIO)
    
    def test_missing_columns(self):
        """测试缺少必要列的情况"""
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            self.missing_columns_data, 'minute'
        )
        
        self.assertFalse(is_valid)
        self.assertEqual(result.error_count, 1)
        self.assertGreater(len(result.warnings), 0)
        self.assertIn('缺少必要列', result.warnings[0])
    
    def test_empty_dataframe(self):
        """测试空DataFrame的处理"""
        empty_df = pd.DataFrame()
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            empty_df, 'minute'
        )
        
        self.assertFalse(is_valid)
        self.assertEqual(result.error_count, 1)
        self.assertIn('数据为空', result.warnings)
    
    def test_none_dataframe(self):
        """测试None DataFrame的处理"""
        is_valid, repaired_df, result = DataValidator.validate_price_data_with_repair(
            None, 'minute'
        )
        
        self.assertFalse(is_valid)
        self.assertEqual(result.error_count, 1)
        self.assertIn('数据为空', result.warnings)


class TestValidationStrategy(unittest.TestCase):
    """验证策略测试类"""
    
    def setUp(self):
        """测试前的设置"""
        # 创建足够多的分钟线数据
        timestamps = pd.date_range(
            '2024-01-01 09:30:00', 
            periods=20, 
            freq='1min'
        )
        self.minute_data = pd.DataFrame({
            'open': [100.0] * 20,
            'high': [105.0] * 20,
            'low': [99.0] * 20,
            'close': [104.0] * 20,
            'minute_timestamp': timestamps
        })
        
        # 创建非分钟线数据
        self.daily_data = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'date': pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03'])
        })
    
    def test_minute_data_strategy(self):
        """测试分钟线数据的验证策略"""
        strategy = DataValidator._get_validation_strategy(self.minute_data, 'minute')
        
        # 验证策略Series的长度
        self.assertEqual(len(strategy), len(self.minute_data))
        
        # 验证边界记录使用宽松策略
        boundary_count = DataProviderConfig.BOUNDARY_MINUTES
        self.assertEqual(strategy.iloc[0], 'lenient')  # 第一条
        self.assertEqual(strategy.iloc[-1], 'lenient')  # 最后一条
        
        # 验证中间记录使用严格策略
        if len(self.minute_data) > boundary_count * 2:
            self.assertEqual(strategy.iloc[boundary_count], 'strict')
    
    def test_non_minute_data_strategy(self):
        """测试非分钟线数据的验证策略"""
        strategy = DataValidator._get_validation_strategy(self.daily_data, 'daily')
        
        # 所有记录都应该使用严格策略
        self.assertTrue((strategy == 'strict').all())
    
    def test_insufficient_data_strategy(self):
        """测试数据量不足时的验证策略"""
        small_data = self.minute_data.head(3)  # 只有3条记录
        strategy = DataValidator._get_validation_strategy(small_data, 'minute')
        
        # 数据量不足时，所有记录都使用严格策略
        self.assertTrue((strategy == 'strict').all())


class TestPriceBoundaryRepair(unittest.TestCase):
    """价格边界修复测试类"""
    
    def setUp(self):
        """测试前的设置"""
        self.test_data = pd.DataFrame({
            'open': [110.0, 101.0, 90.0],   # 第一条超出上界，第三条超出下界
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 95.0, 108.0], # 第二条超出下界，第三条超出上界
        })
    
    def test_repair_statistics(self):
        """测试修复统计的准确性"""
        repair_stats = DataValidator._repair_price_boundaries(self.test_data.copy())
        
        # 验证修复统计
        self.assertIn('open_repaired', repair_stats)
        self.assertIn('close_repaired', repair_stats)
        self.assertEqual(repair_stats['open_repaired'], 2)  # 两条开盘价需要修复
        self.assertEqual(repair_stats['close_repaired'], 2)  # 两条收盘价需要修复
    
    def test_repair_correctness(self):
        """测试修复结果的正确性"""
        df_copy = self.test_data.copy()
        DataValidator._repair_price_boundaries(df_copy)
        
        # 验证修复后的价格在合理范围内
        self.assertTrue((df_copy['open'] >= df_copy['low']).all())
        self.assertTrue((df_copy['open'] <= df_copy['high']).all())
        self.assertTrue((df_copy['close'] >= df_copy['low']).all())
        self.assertTrue((df_copy['close'] <= df_copy['high']).all())


if __name__ == "__main__":
    unittest.main()
