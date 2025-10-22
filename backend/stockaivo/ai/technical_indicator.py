"""
技术指标计算服务
负责计算常见的股票技术指标
"""

import logging
import pandas as pd
from typing import Optional, Dict, Any, Tuple

# 配置日志
logger = logging.getLogger(__name__)


class TechnicalIndicator:
    """
    技术指标计算服务
    负责计算常见的股票技术指标
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化技术指标计算服务
        
        Args:
            params: 技术指标参数配置
        """
        # 默认参数设置
        self.params = params or {
            'ma_periods': {'short': 5, 'medium': 20, 'long': 60},
            'rsi_period': 14,
            'bollinger_period': 20,
            'bollinger_std': 2,
            'volume_ma_period': 20,
            'atr_period': 14
        }
        
        logger.debug(f"初始化TechnicalIndicator技术指标计算服务，参数: {self.params}")
    
    def calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """
        计算指数移动平均线
        
        Args:
            series: 价格序列
            period: 周期
            
        Returns:
            EMA序列
        """
        return series.ewm(span=period, adjust=False).mean()
    
    def calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """
        计算相对强弱指标(RSI)，优化了计算逻辑。

        RSI的计算基于价格序列的涨跌变化。它使用指数移动平均线(EMA)
        来平滑涨幅和跌幅，从而反映市场的超买或超卖状态。

        Args:
            series: 价格序列 (通常是收盘价)。
            period: RSI计算周期，通常为14。

        Returns:
            与输入序列具有相同索引的RSI序列。
        """
        # 1. 计算价格变化
        delta = series.diff(1)

        # 2. 分离涨幅和跌幅
        # gain: 将负值（下跌）裁剪为0
        gain = delta.clip(lower=0)
        # loss: 将正值（上涨）裁剪为0，然后取绝对值
        loss = -delta.clip(upper=0)

        # 3. 计算涨幅和跌幅的EMA
        # Wilder's smoothing (used in standard RSI) is equivalent to an EMA with alpha = 1/period
        # which corresponds to com = period - 1
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        # 4. 计算相对强度 (RS)
        # 当avg_loss为0时，为避免除零错误，RS趋于无穷大，RSI趋于100
        # 使用 where 方法安全处理除零情况
        rs = avg_gain / avg_loss.where(avg_loss != 0, 1e-10)  # 避免除零，使用极小值

        # 5. 计算RSI
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # 处理边界情况：当avg_loss为0时，RSI应该为100
        rsi = rsi.where(avg_loss != 0, 100.0)

        # Reindex to match the original series' index
        return rsi.reindex(series.index)
    
    def calculate_macd(self, series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算MACD指标
        
        Args:
            series: 价格序列
            
        Returns:
            (MACD线, 信号线, 柱状图)的元组
        """
        ema12 = self.calculate_ema(series, 12)
        ema26 = self.calculate_ema(series, 26)
        
        macd = ema12 - ema26
        signal = self.calculate_ema(macd, 9)
        histogram = macd - signal
        
        return macd, signal, histogram
    
    def calculate_bollinger_bands(self, series: pd.Series, period: int, std_dev: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算布林带
        
        Args:
            series: 价格序列
            period: 周期
            std_dev: 标准差倍数
            
        Returns:
            (中轨, 上轨, 下轨)的元组
        """
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return middle, upper, lower
    
    def calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """
        计算平均真实波幅(ATR)

        Args:
            df: 包含high, low, close列的DataFrame
            period: 周期

        Returns:
            ATR序列
        """
        try:
            high = df['high']
            low = df['low']
            close = df['close']

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()

            return atr
        except KeyError as e:
            logger.error(f"ATR计算失败，缺少必要的列: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标

        Args:
            df: 原始价格数据，包含open, high, low, close, volume列

        Returns:
            添加了技术指标的DataFrame
        """
        try:
            # 复制数据框
            result_df = df.copy()

            # 简单验证必要的列是否存在
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in result_df.columns]

            if missing_columns:
                logger.warning(f"缺少必要的列: {missing_columns}，跳过技术指标计算")
                return result_df
            
            data_length = len(result_df)
            logger.info(f"开始计算技术指标，数据行数: {data_length}")

            # 根据数据量选择性计算技术指标
            calculated_indicators = []

            # 移动平均线 - 根据数据量选择合适的周期
            for period in self.params['ma_periods'].values():
                if data_length >= period:
                    result_df[f'MA{period}'] = result_df['close'].rolling(window=period).mean()
                    calculated_indicators.append(f'MA{period}')
                else:
                    logger.debug(f"数据量不足，跳过MA{period}计算（需要{period}行，实际{data_length}行）")

            # RSI - 需要至少rsi_period + 1行数据
            if data_length >= self.params['rsi_period'] + 1:
                result_df['RSI'] = self.calculate_rsi(result_df['close'], self.params['rsi_period'])
                calculated_indicators.append('RSI')
            else:
                logger.debug(f"数据量不足，跳过RSI计算（需要{self.params['rsi_period'] + 1}行，实际{data_length}行）")

            # MACD - 需要至少26行数据（EMA26）
            if data_length >= 26:
                macd, signal, histogram = self.calculate_macd(result_df['close'])
                result_df['MACD'] = macd
                result_df['Signal'] = signal
                result_df['Histogram'] = histogram
                calculated_indicators.extend(['MACD', 'Signal', 'Histogram'])
            else:
                logger.debug(f"数据量不足，跳过MACD计算（需要26行，实际{data_length}行）")

            # 布林带 - 需要至少bollinger_period行数据
            if data_length >= self.params['bollinger_period']:
                middle, upper, lower = self.calculate_bollinger_bands(
                    result_df['close'],
                    self.params['bollinger_period'],
                    self.params['bollinger_std']
                )
                result_df['BB_Middle'] = middle
                result_df['BB_Upper'] = upper
                result_df['BB_Lower'] = lower
                calculated_indicators.extend(['BB_Middle', 'BB_Upper', 'BB_Lower'])
            else:
                logger.debug(f"数据量不足，跳过布林带计算（需要{self.params['bollinger_period']}行，实际{data_length}行）")

            # 成交量移动平均 - 需要至少volume_ma_period行数据
            if data_length >= self.params['volume_ma_period']:
                result_df['Volume_MA'] = result_df['volume'].rolling(window=self.params['volume_ma_period']).mean()
                calculated_indicators.append('Volume_MA')

                # 成交量比率 - 依赖于Volume_MA
                volume_ma = result_df['Volume_MA']
                result_df['Volume_Ratio'] = result_df['volume'] / volume_ma.where(volume_ma != 0, 1)
                calculated_indicators.append('Volume_Ratio')
            else:
                logger.debug(f"数据量不足，跳过成交量指标计算（需要{self.params['volume_ma_period']}行，实际{data_length}行）")

            # ATR - 需要至少atr_period行数据
            if data_length >= self.params['atr_period']:
                result_df['ATR'] = self.calculate_atr(result_df, self.params['atr_period'])
                calculated_indicators.append('ATR')
            else:
                logger.debug(f"数据量不足，跳过ATR计算（需要{self.params['atr_period']}行，实际{data_length}行）")

            # 波动率 - 需要至少20行数据
            if data_length >= 20:
                close_mean = result_df['close'].rolling(window=20).mean()
                close_std = result_df['close'].rolling(window=20).std()
                result_df['Volatility'] = (close_std / close_mean.where(close_mean != 0, 1)) * 100
                calculated_indicators.append('Volatility')
            else:
                logger.debug(f"数据量不足，跳过波动率计算（需要20行，实际{data_length}行）")

            # 记录实际计算的指标 - 使用attrs避免pandas警告
            result_df.attrs['calculated_indicators'] = calculated_indicators
            logger.debug(f"技术指标计算完成，成功计算: {calculated_indicators}")
            return result_df

        except Exception as e:
            logger.error(f"计算技术指标时出错: {str(e)}")
            logger.exception(e)
            # 返回原始数据，不中断流程
            return df

    def get_calculated_indicators(self, df: pd.DataFrame) -> list[str]:
        """
        获取DataFrame中已计算的技术指标列表

        Args:
            df: 包含技术指标的DataFrame

        Returns:
            已计算的技术指标名称列表
        """
        if 'calculated_indicators' in df.attrs:
            return list(df.attrs['calculated_indicators'])

        # 如果没有记录，则通过列名推断
        all_possible_indicators = [
            'MA5', 'MA20', 'MA60', 'RSI', 'MACD', 'Signal', 'Histogram',
            'BB_Middle', 'BB_Upper', 'BB_Lower', 'Volume_MA', 'Volume_Ratio',
            'ATR', 'Volatility'
        ]

        return [indicator for indicator in all_possible_indicators if indicator in df.columns]


# 测试函数，用于验证技术指标计算
def test_technical_indicators():
    """测试技术指标计算功能"""
    import pandas as pd
    import numpy as np

    # 创建测试数据 - 使用小写列名（模拟从data_provider获取的数据）
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    np.random.seed(42)  # 确保可重现的结果

    # 生成模拟股价数据
    base_price = 100.0
    price_changes = np.random.normal(0, 2, 100)
    prices = [base_price]

    for change in price_changes[1:]:
        new_price = max(float(prices[-1] + change), 1.0)  # 确保价格为正
        prices.append(new_price)

    # 创建OHLCV数据
    test_data = pd.DataFrame({
        'date': dates,
        'open': [p * (1 + np.random.normal(0, 0.01)) for p in prices],
        'high': [p * (1 + abs(np.random.normal(0, 0.02))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.02))) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    })

    # 确保high >= low, open/close在high/low范围内
    test_data['high'] = test_data[['open', 'close', 'high']].max(axis=1)
    test_data['low'] = test_data[['open', 'close', 'low']].min(axis=1)

    print("测试数据样本:")
    print(test_data.head())
    print(f"数据列名: {list(test_data.columns)}")

    # 测试技术指标计算
    indicator = TechnicalIndicator()
    result = indicator.calculate_indicators(test_data)

    print(f"\n计算后的列名: {list(result.columns)}")
    print(f"新增的技术指标列: {[col for col in result.columns if col not in test_data.columns]}")

    # 检查关键指标是否计算成功
    expected_indicators = ['MA5', 'MA20', 'MA60', 'RSI', 'MACD', 'Signal', 'Histogram',
                          'BB_Middle', 'BB_Upper', 'BB_Lower', 'Volume_MA', 'Volume_Ratio',
                          'ATR', 'Volatility']

    missing_indicators = [ind for ind in expected_indicators if ind not in result.columns]
    if missing_indicators:
        print(f"警告：缺少以下指标: {missing_indicators}")
    else:
        print("✓ 所有预期的技术指标都已成功计算")

    # 显示最后几行数据以验证计算结果
    print("\n最后5行数据（包含技术指标）:")
    print(result.tail()[['close', 'MA5', 'MA20', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower', 'ATR']].round(2))

    return result


if __name__ == "__main__":
    test_technical_indicators()
