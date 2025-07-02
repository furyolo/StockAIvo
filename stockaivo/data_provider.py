"""
数据源封装模块 - AKShare 数据提供者

本模块实现了从 AKShare 获取美股数据的功能，支持多种时间周期的数据获取。
根据项目文档 1.2 数据源封装 (AKShare) 的要求实现。
"""

import logging
import pandas as pd
import akshare as ak
import requests
import asyncio
from typing import Optional, Literal
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .database import get_fullsymbol_from_db

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义支持的时间周期类型
PeriodType = Literal["daily", "weekly", "hourly"]

# --- Tenacity 重试配置 ---
# 定义重试前的日志记录函数
def log_before_retry(retry_state):
    """在每次重试前记录日志"""
    logger.warning(
        f"Retrying API call for {retry_state.args[1]} ({retry_state.args[2]}), "
        f"attempt {retry_state.attempt_number} after error: {retry_state.outcome.exception()}"
    )

# --- 新的带重试的内部辅助函数 ---
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, IOError)),
    before_sleep=log_before_retry
)
async def _fetch_data_with_retry(fullsymbol: str, period: str, ak_start_date: str, ak_end_date: str) -> Optional[pd.DataFrame]:
    """
    使用 tenacity 重试逻辑调用 AKShare API
    """
    logger.info(f"Calling AKShare for {fullsymbol} ({period}) from {ak_start_date} to {ak_end_date}")

    def sync_akshare_call():
        if period == "daily":
            return ak.stock_us_hist(symbol=fullsymbol, period="daily", start_date=ak_start_date, end_date=ak_end_date, adjust="qfq")
        elif period == "weekly":
            return ak.stock_us_hist(symbol=fullsymbol, period="weekly", start_date=ak_start_date, end_date=ak_end_date, adjust="qfq")
        elif period == "hourly":
            logger.warning(f"AKShare does not support hourly data for {fullsymbol}, using daily data instead.")
            return ak.stock_us_hist(symbol=fullsymbol, period="daily", start_date=ak_start_date, end_date=ak_end_date, adjust="qfq")
        return None

    df = await asyncio.to_thread(sync_akshare_call)

    # 如果 API 返回 None 或空的 DataFrame，主动抛出 IOError 触发重试
    if df is None or df.empty:
        raise IOError("API returned empty data.")
        
    return df


async def fetch_from_akshare(db: Session, ticker: str, period: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    从 AKShare 获取指定股票的指定周期数据，并增加了自动重试功能
    
    Args:
        ticker (str): 股票代码，如 'AAPL', 'TSLA'
        period (str): 数据周期，支持 'daily', 'weekly', 'hourly'
        start_date (Optional[str]): 开始日期 (YYYY-MM-DD)
        end_date (Optional[str]): 结束日期 (YYYY-MM-DD)
    
    Returns:
        Optional[pd.DataFrame]: 成功时返回包含股票数据的 DataFrame，失败时返回 None
    """
    
    if not ticker:
        logger.error("股票代码不能为空")
        return None
        
    if period not in ["daily", "weekly", "hourly"]:
        logger.error(f"不支持的时间周期: {period}，支持的周期: daily, weekly, hourly")
        return None

    try:
        logger.info(f"开始处理 {ticker} 的 {period} 数据获取请求 (从 {start_date} 到 {end_date})")
        
        fullsymbol = get_fullsymbol_from_db(db, ticker)
        if not fullsymbol:
            logger.error(f"由于无法从数据库获取 fullsymbol，终止为 {ticker} 的数据获取。")
            return None
        
        ak_start_date = start_date.replace('-', '') if start_date else '19700101'
        ak_end_date = end_date.replace('-', '') if end_date else (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

        # 调用带重试逻辑的辅助函数
        df = await _fetch_data_with_retry(fullsymbol, period, ak_start_date, ak_end_date)
        
        if df is None or df.empty:
            # 这种情况理论上不应该发生，因为 _fetch_data_with_retry 会在获取失败时抛出异常
            logger.warning(f"获取到的数据为空，股票代码: {ticker}, 周期: {period}")
            return None
        
        # 标准化列名
        df = _standardize_columns(df, period)
        
        # 数据验证
        if not _validate_data(df):
            logger.error(f"数据验证失败，股票代码: {ticker}, 周期: {period}")
            return None
        
        logger.info(f"成功获取并验证了 {ticker} 的 {period} 数据，共 {len(df)} 条记录")
        
        df['ticker'] = ticker
        return df
        
    except Exception as e:
        # 当 tenacity 所有重试都失败后，会重新抛出最后的异常
        logger.error(f"获取 {ticker} 的 {period} 数据最终失败，经过多次重试后仍然出错: {str(e)}")
        return None


def _standardize_columns(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """
    标准化 DataFrame 的列名，确保列名一致性
    基于参考项目 D:\\Coding\\stockai 的列名映射
    
    Args:
        df (pd.DataFrame): 原始数据
        period (str): 数据周期
    
    Returns:
        pd.DataFrame: 标准化后的数据
    """
    try:
        # 根据参考项目的列名映射，AKShare 返回的是中文列名
        column_mapping = {
            # AKShare stock_us_hist 返回的中文列名映射
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'turnover',
            '振幅': 'amplitude',
            '涨跌幅': 'price_change_percent',
            '涨跌额': 'price_change',
            '换手率': 'turnover_rate',
            # 英文列名映射（防御性编程）
            'date': 'date',
            'open': 'open',
            'close': 'close',
            'high': 'high',
            'low': 'low',
            'volume': 'volume',
            'turnover': 'turnover',
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 确保包含必要的列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            logger.warning(f"缺少必要列: {missing_columns}")
        
        # 根据周期设置时间列
        if period in ["daily", "weekly"]:
            # 确保有 date 列
            if 'date' not in df.columns and 'dates' in df.columns:
                df = df.rename(columns={'dates': 'date'})
            elif 'date' not in df.columns:
                # 如果索引是日期，将其重置为列
                if df.index.name == 'date' or pd.api.types.is_datetime64_any_dtype(df.index):
                    df = df.reset_index()
                    if 'index' in df.columns:
                        df = df.rename(columns={'index': 'date'})
        elif period == "hourly":
            # 对于小时数据，使用 timestamp 列名
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'timestamp'})
        
        # 数据类型转换和清理（参考项目的处理方式）
        df = df.replace({pd.NA: None, float('nan'): None})
        
        # 转换数值列
        numeric_columns = ['open', 'close', 'high', 'low', 'amplitude', 'price_change_percent', 'price_change', 'turnover_rate']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].replace([float('inf'), float('-inf')], None)
        
        # 转换整数列
        integer_columns = ['volume', 'turnover']
        for col in integer_columns:
            if col in df.columns:
                try:
                    df[col] = df[col].apply(lambda x: int(x) if pd.notnull(x) else None)
                except Exception:
                    df[col] = None
        
        return df
        
    except Exception as e:
        logger.error(f"标准化列名时发生错误: {str(e)}")
        return df


def _validate_data(df: pd.DataFrame) -> bool:
    """
    验证数据的有效性
    
    Args:
        df (pd.DataFrame): 要验证的数据
    
    Returns:
        bool: 数据是否有效
    """
    try:
        # 检查基本要求
        if df is None or df.empty:
            return False
        
        # 检查必要的价格列
        price_columns = ['open', 'high', 'low', 'close']
        missing_price_columns = [col for col in price_columns if col not in df.columns]
        
        if missing_price_columns:
            logger.warning(f"缺少价格列: {missing_price_columns}")
            return False
        
        # 检查数据类型和有效性
        for col in price_columns:
            if col in df.columns:
                # 检查是否有非数值数据
                if not pd.api.types.is_numeric_dtype(df[col]):
                    try:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    except:
                        logger.warning(f"列 {col} 包含无效数据")
                        return False
                
                # 检查是否有负数价格（放宽验证，只记录警告）
                if (df[col] < 0).any():
                    logger.warning(f"列 {col} 包含负数价格，但继续处理")
                    # 将负数价格设为 NaN，而不是直接返回 False
                    df[col] = df[col].where(df[col] >= 0)
        
        # 检查价格逻辑关系（high >= low, open/close 在 high/low 范围内）
        if ('high' in df.columns and 'low' in df.columns and 
            'open' in df.columns and 'close' in df.columns):
            
            # high 应该 >= low
            if (df['high'] < df['low']).any():
                logger.warning("数据中存在最高价低于最低价的异常情况")
                return False
            
            # open 和 close 应该在 high 和 low 之间
            if ((df['open'] > df['high']) | (df['open'] < df['low']) |
                (df['close'] > df['high']) | (df['close'] < df['low'])).any():
                logger.warning("数据中存在开盘价或收盘价超出最高最低价范围的异常情况")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"数据验证时发生错误: {str(e)}")
        return False


def test_fetch_function():
    r"""
    测试函数，用于验证 fetch_from_akshare 函数的功能
    """
    # 注意：此测试函数需要一个有效的数据库会话(db: Session)才能运行。
    # 您需要手动创建一个数据库会e话并将其传递给 fetch_from_akshare。
    print("开始测试 fetch_from_akshare 函数...")
    
    # 测试用例
    test_cases = [
        ("AAPL", "daily"),
        ("TSLA", "weekly"),
        ("MSFT", "daily"),
        ("", "daily"),           # 空股票代码
        ("AAPL", "invalid"),     # 无效周期
    ]
    
    # for ticker, period in test_cases:
    #     print(f"\n测试: {ticker} - {period}")
    #     # result = fetch_from_akshare(db, ticker, period) # 需要传入 db session
        
    #     if result is not None:
    #         print(f"成功获取数据，行数: {len(result)}")
    #         print(f"列名: {result.columns.tolist()}")
    #         if not result.empty:
    #             print(f"数据预览:\n{result.head()}")
    #     else:
    #         print("获取数据失败")


if __name__ == "__main__":
    # 运行测试
    # test_fetch_function() # 需要数据库会话才能运行，暂时注释掉
    print("测试函数已注释，因为 fetch_from_akshare 现在需要数据库会话。")