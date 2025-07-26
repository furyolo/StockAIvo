"""
数据源封装模块 - 重构版本

本模块实现了从多个数据源获取美股数据的功能，支持股票价格数据和新闻数据的获取。
采用面向对象设计，提供清晰的模块化结构和统一的接口。

主要功能：
- 股票价格数据获取（AKShare）
- 股票新闻数据获取（AKShare、TickerTick）
- 统一的错误处理和重试机制
- 数据标准化和验证
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal, Union, Any
from enum import Enum

import akshare as ak
import httpx
import pandas as pd
import pytz
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .database import get_fullsymbol_from_db
from .models import UsStocksName

# 配置日志
logger = logging.getLogger(__name__)

# 类型定义
PeriodType = Literal["daily", "weekly", "hourly"]
DataSourceType = Literal["akshare", "tickertick"]


class StoryType(Enum):
    """TickerTick 支持的新闻故事类型"""
    CURATED = ('T:curated', '来自顶级金融/科技新闻源的新闻')
    EARNING = ('T:earning', '公司财报新闻（如演示文稿、文字记录）')
    MARKET = ('T:market', '股市新闻')
    SEC = ('T:sec', 'SEC文件')
    SEC_FIN = ('T:sec_fin', '季度/年度财务报告')
    TRADE = ('T:trade', '交易新闻')
    UGC = ('T:ugc', '来自用户生成内容平台（如Reddit）的新闻')
    ANALYSIS = ('T:analysis', '来自精选来源的股票分析文章')
    INDUSTRY = ('T:industry', '来自精选来源的行业出版物')

    def __init__(self, code: str, description: str):
        self.code = code
        self.description = description

    @classmethod
    def get_supported_types(cls) -> Dict[str, str]:
        """获取所有支持的故事类型"""
        return {story_type.code: story_type.description for story_type in cls}

    @classmethod
    def is_valid(cls, code: str) -> bool:
        """验证故事类型是否受支持"""
        return any(story_type.code == code for story_type in cls)

    @classmethod
    def get_description(cls, code: str) -> Optional[str]:
        """获取故事类型的描述"""
        for story_type in cls:
            if story_type.code == code:
                return story_type.description
        return None


class DataProviderConfig:
    """数据提供者配置类"""

    # AKShare 配置
    AKSHARE_RETRY_ATTEMPTS = 3
    AKSHARE_RETRY_MIN_WAIT = 1
    AKSHARE_RETRY_MAX_WAIT = 10

    # TickerTick 配置
    TICKERTICK_RATE_LIMIT = 10  # 每分钟请求数
    TICKERTICK_RATE_LIMIT_WINDOW = 60  # 速率限制窗口（秒）
    TICKERTICK_MAX_RETRIES = 3  # 最大重试次数
    TICKERTICK_RETRY_DELAY = 65  # 重试延迟（秒）
    TICKERTICK_BASE_URL = "https://api.tickertick.com/feed"

    # 数据处理配置
    NEWS_FILTER_DAYS = 5  # 新闻数据过滤天数
    MIN_CONTENT_LENGTH = 30  # 新闻内容最小长度

    # 时区配置
    DEFAULT_SOURCE_TIMEZONE = 'Asia/Shanghai'
    TARGET_TIMEZONE = 'US/Eastern'

    # 数据验证配置
    REQUIRED_PRICE_COLUMNS = ['open', 'high', 'low', 'close']
    REQUIRED_VOLUME_COLUMNS = ['volume']

    # 公司名称清理配置
    COMPANY_SUFFIXES_TO_REMOVE = ["公司", "集团", "股份有限公司", "有限公司", "股份公司", "控股", "投资"]


def get_supported_story_types() -> Dict[str, str]:
    """
    获取所有支持的故事类型

    Returns:
        Dict[str, str]: 包含故事类型代码和描述的字典
    """
    return StoryType.get_supported_types()


def validate_story_type(story_type: str) -> bool:
    """
    验证故事类型是否受支持

    Args:
        story_type (str): 要验证的故事类型

    Returns:
        bool: 如果故事类型受支持返回True，否则返回False
    """
    return StoryType.is_valid(story_type)


def get_story_type_description(story_type: str) -> Optional[str]:
    """
    获取故事类型的描述

    Args:
        story_type (str): 故事类型代码

    Returns:
        Optional[str]: 故事类型的描述，如果类型不存在返回None
    """
    return StoryType.get_description(story_type)


# ===== 抽象基类和接口定义 =====

class BaseDataProvider(ABC):
    """数据提供者基类，定义统一的接口"""

    def __init__(self, config: DataProviderConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def fetch_data(self, **kwargs) -> Optional[pd.DataFrame]:
        """获取数据的抽象方法"""
        pass

    def _log_before_retry(self, retry_state):
        """在每次重试前记录日志"""
        self.logger.warning(
            f"Retrying API call, attempt {retry_state.attempt_number} "
            f"after error: {retry_state.outcome.exception()}"
        )


class DataValidator:
    """数据验证器类"""

    @staticmethod
    def validate_ticker(ticker: str) -> bool:
        """验证股票代码"""
        return bool(ticker and ticker.strip())

    @staticmethod
    def validate_period(period: str) -> bool:
        """验证时间周期"""
        return period in ["daily", "weekly", "hourly"]

    @staticmethod
    def validate_price_data(df: pd.DataFrame) -> bool:
        """验证价格数据的有效性"""
        if df is None or df.empty:
            return False

        # 检查必要的价格列
        required_columns = DataProviderConfig.REQUIRED_PRICE_COLUMNS
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            logger.warning(f"缺少价格列: {missing_columns}")
            return False

        # 检查价格逻辑关系
        if all(col in df.columns for col in ['high', 'low', 'open', 'close']):
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


class TimezoneConverter:
    """时区转换器类"""

    @staticmethod
    def convert_to_et(dt: pd.Timestamp, source_timezone: Optional[str] = None) -> Optional[pd.Timestamp]:
        """
        将时间从指定源时区转换为美国东部时间（ET）

        Args:
            dt: pandas Timestamp对象，假设为源时区的naive datetime
            source_timezone: 源时区名称，默认使用配置中的源时区

        Returns:
            转换后的美国东部时间（naive datetime），如果转换失败返回None
        """
        if pd.isna(dt):
            return None

        if source_timezone is None:
            source_timezone = DataProviderConfig.DEFAULT_SOURCE_TIMEZONE

        try:
            # 定义时区
            source_tz = pytz.timezone(source_timezone)
            et_tz = pytz.timezone(DataProviderConfig.TARGET_TIMEZONE)

            # 如果输入的时间没有时区信息，假设为源时区
            if dt.tz is None:
                dt_with_tz = source_tz.localize(dt)
            else:
                dt_with_tz = dt.tz_convert(source_tz)

            # 转换为美国东部时间
            et_time = dt_with_tz.astimezone(et_tz)

            # 返回naive datetime（移除时区信息）
            return pd.Timestamp(et_time.replace(tzinfo=None))

        except Exception as e:
            logger.warning(f"时区转换失败: {dt} ({source_timezone} -> US/Eastern) -> {e}")
            return None


# ===== 全局重试配置和辅助函数 =====

def _log_before_retry(retry_state):
    """全局重试日志函数"""
    logger.warning(
        f"Retrying API call, attempt {retry_state.attempt_number} "
        f"after error: {retry_state.outcome.exception()}"
    )


# --- 新的带重试的内部辅助函数 ---
@retry(
    stop=stop_after_attempt(DataProviderConfig.AKSHARE_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=DataProviderConfig.AKSHARE_RETRY_MIN_WAIT,
        max=DataProviderConfig.AKSHARE_RETRY_MAX_WAIT
    ),
    retry=retry_if_exception_type((requests.exceptions.RequestException, IOError)),
    before_sleep=_log_before_retry
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


# ===== 股票数据提供者类 =====

class StockDataProvider(BaseDataProvider):
    """股票价格数据提供者类"""

    def __init__(self, config: Optional[DataProviderConfig] = None):
        if config is None:
            config = DataProviderConfig()
        super().__init__(config)

    async def fetch_data(self, db: Session, ticker: str, period: str,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        从 AKShare 获取指定股票的指定周期数据

        Args:
            db: 数据库会话
            ticker: 股票代码，如 'AAPL', 'TSLA'
            period: 数据周期，支持 'daily', 'weekly', 'hourly'
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            包含股票数据的 DataFrame，失败时返回 None
        """
        # 输入验证
        if not DataValidator.validate_ticker(ticker):
            self.logger.error("股票代码不能为空")
            return None

        if not DataValidator.validate_period(period):
            self.logger.error(f"不支持的时间周期: {period}，支持的周期: daily, weekly, hourly")
            return None

        try:
            self.logger.info(f"开始处理 {ticker} 的 {period} 数据获取请求 (从 {start_date} 到 {end_date})")

            # 获取完整股票代码
            fullsymbol = get_fullsymbol_from_db(db, ticker)
            if not fullsymbol:
                self.logger.error(f"由于无法从数据库获取 fullsymbol，终止为 {ticker} 的数据获取。")
                return None

            # 格式化日期
            ak_start_date = start_date.replace('-', '') if start_date else '19700101'
            ak_end_date = end_date.replace('-', '') if end_date else (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

            # 调用带重试逻辑的辅助函数
            df = await _fetch_data_with_retry(fullsymbol, period, ak_start_date, ak_end_date)

            if df is None or df.empty:
                self.logger.warning(f"获取到的数据为空，股票代码: {ticker}, 周期: {period}")
                return None

            # 标准化列名
            df = self._standardize_columns(df, period)

            # 数据验证
            if not DataValidator.validate_price_data(df):
                self.logger.error(f"数据验证失败，股票代码: {ticker}, 周期: {period}")
                return None

            self.logger.info(f"成功获取并验证了 {ticker} 的 {period} 数据，共 {len(df)} 条记录")

            df['ticker'] = ticker
            return df

        except Exception as e:
            self.logger.error(f"获取 {ticker} 的 {period} 数据最终失败，经过多次重试后仍然出错: {str(e)}")
            return None

    def _standardize_columns(self, df: pd.DataFrame, period: str) -> pd.DataFrame:
        """标准化 DataFrame 的列名，确保列名一致性"""
        try:
            # AKShare 返回的中文列名映射
            column_mapping = {
                '日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low',
                '成交量': 'volume', '成交额': 'turnover', '振幅': 'amplitude',
                '涨跌幅': 'price_change_percent', '涨跌额': 'price_change', '换手率': 'turnover_rate',
                # 英文列名映射（防御性编程）
                'date': 'date', 'open': 'open', 'close': 'close', 'high': 'high',
                'low': 'low', 'volume': 'volume', 'turnover': 'turnover',
            }

            # 重命名列
            df = df.rename(columns=column_mapping)

            # 处理时间列
            self._process_time_columns(df, period)

            # 数据类型转换和清理
            df = self._clean_and_convert_data(df)

            return df

        except Exception as e:
            self.logger.error(f"标准化列名时发生错误: {str(e)}")
            return df

    def _process_time_columns(self, df: pd.DataFrame, period: str) -> None:
        """处理时间列"""
        if period in ["daily", "weekly"]:
            # 确保有 date 列
            if 'date' not in df.columns and 'dates' in df.columns:
                df.rename(columns={'dates': 'date'}, inplace=True)
            elif 'date' not in df.columns:
                # 如果索引是日期，将其重置为列
                if df.index.name == 'date' or pd.api.types.is_datetime64_any_dtype(df.index):
                    df.reset_index(inplace=True)
                    if 'index' in df.columns:
                        df.rename(columns={'index': 'date'}, inplace=True)
        elif period == "hourly":
            # 对于小时数据，使用 timestamp 列名
            if 'date' in df.columns:
                df.rename(columns={'date': 'timestamp'}, inplace=True)

    def _clean_and_convert_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清理和转换数据类型"""
        # 数据类型转换和清理
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


# ===== 全局实例和向后兼容性函数 =====

# 创建全局实例
_stock_data_provider = StockDataProvider()


# 保持向后兼容性的函数
async def fetch_from_akshare(db: Session, ticker: str, period: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    向后兼容性函数：从 AKShare 获取指定股票的指定周期数据
    """
    return await _stock_data_provider.fetch_data(db, ticker, period, start_date, end_date)


# 向后兼容性函数
def _standardize_columns(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """向后兼容性函数：标准化 DataFrame 的列名"""
    return _stock_data_provider._standardize_columns(df, period)


def _validate_data(df: pd.DataFrame) -> bool:
    """向后兼容性函数：验证数据的有效性"""
    return DataValidator.validate_price_data(df)


# 测试函数已移除，因为它依赖于数据库会话且未被使用


def _clean_company_name(cname: str) -> str:
    """
    向后兼容性函数：清理公司名称，删除"公司"、"集团"等字样
    """
    if not cname:
        return ""

    cleaned_name = cname
    for suffix in DataProviderConfig.COMPANY_SUFFIXES_TO_REMOVE:
        cleaned_name = cleaned_name.replace(suffix, "")

    return cleaned_name.strip()





# 保持向后兼容性的别名函数
def _convert_timezone_cst_to_et(dt: pd.Timestamp) -> Optional[pd.Timestamp]:
    """
    向后兼容性函数：将时间从中国标准时间转换为美国东部时间
    """
    return TimezoneConverter.convert_to_et(dt, 'Asia/Shanghai')


def _convert_timezone_to_et(dt: pd.Timestamp, source_timezone: str = 'Asia/Shanghai') -> Optional[pd.Timestamp]:
    """
    向后兼容性函数：将时间从指定源时区转换为美国东部时间（ET）
    """
    return TimezoneConverter.convert_to_et(dt, source_timezone)


# ===== 新闻数据提供者类 =====

class NewsDataProvider(BaseDataProvider):
    """新闻数据提供者基类"""

    def __init__(self, config: Optional[DataProviderConfig] = None):
        if config is None:
            config = DataProviderConfig()
        super().__init__(config)

    async def fetch_data(self, **kwargs) -> Optional[pd.DataFrame]:
        """基础实现，子类应该重写此方法"""
        raise NotImplementedError("子类必须实现 fetch_data 方法")

    def _clean_company_name(self, cname: str) -> str:
        """清理公司名称，删除"公司"、"集团"等字样"""
        if not cname:
            return ""

        cleaned_name = cname
        for suffix in self.config.COMPANY_SUFFIXES_TO_REMOVE:
            cleaned_name = cleaned_name.replace(suffix, "")

        return cleaned_name.strip()

    def _get_company_chinese_name(self, db: Session, ticker: str) -> Optional[str]:
        """从us_stocks_name表获取股票的中文名称"""
        try:
            stmt = select(UsStocksName.cname).where(UsStocksName.symbol == ticker)
            result = db.execute(stmt).scalar_one_or_none()

            if result:
                return self._clean_company_name(result)
            else:
                self.logger.warning(f"未找到股票 {ticker} 的中文名称")
                return None

        except Exception as e:
            self.logger.error(f"查询股票 {ticker} 中文名称时发生错误: {e}")
            return None

    def _filter_news_by_date(self, df: pd.DataFrame, source_timezone: str) -> pd.DataFrame:
        """根据日期过滤新闻数据"""
        if 'publish_time' not in df.columns or len(df) == 0:
            return df

        # 获取当前时间并转换为数据源时区
        source_tz = pytz.timezone(source_timezone)
        current_local_time = datetime.now(source_tz)
        filter_days_ago = current_local_time - timedelta(days=self.config.NEWS_FILTER_DAYS)
        filter_days_ago_naive = filter_days_ago.replace(tzinfo=None)

        self.logger.info(f"基于数据源时区筛选: 当前{source_timezone}时间 {current_local_time}")
        self.logger.info(f"基于数据源时区筛选: {self.config.NEWS_FILTER_DAYS}天前{source_timezone}时间 {filter_days_ago}")

        # 记录筛选前的数据
        self.logger.info(f"筛选前数据条数: {len(df)}")
        if len(df) > 0:
            self.logger.info(f"筛选前时间范围: {df['publish_time'].min()} 到 {df['publish_time'].max()}")

        # 使用数据源时区进行筛选
        df_filtered = df.dropna(subset=['publish_time'])
        df_filtered = df_filtered[df_filtered['publish_time'] >= filter_days_ago_naive]

        self.logger.info(f"数据源时区筛选后剩余 {len(df_filtered)} 条记录")
        if len(df_filtered) > 0:
            self.logger.info(f"筛选后时间范围: {df_filtered['publish_time'].min()} 到 {df_filtered['publish_time'].max()}")

        return df_filtered


class AKShareNewsProvider(NewsDataProvider):
    """AKShare 新闻数据提供者"""

    async def fetch_data(self, db: Session, ticker: str, convert_timezone: bool = True) -> Optional[pd.DataFrame]:
        """
        从AKShare获取指定股票的新闻数据

        Args:
            db: 数据库会话
            ticker: 股票代码
            convert_timezone: 是否转换时区

        Returns:
            新闻数据DataFrame，失败时返回None
        """
        if not DataValidator.validate_ticker(ticker):
            self.logger.error("股票代码不能为空")
            return None

        # 获取股票的中文名称作为搜索关键词
        chinese_name = self._get_company_chinese_name(db, ticker)
        if not chinese_name:
            self.logger.error(f"无法获取股票 {ticker} 的中文名称，无法进行新闻搜索")
            return None

        self.logger.info(f"开始获取股票 {ticker} ({chinese_name}) 的新闻数据...")

        try:
            # 从AKShare获取新闻数据
            df = await self._fetch_stock_news_from_akshare(chinese_name)

            if df is None or df.empty:
                self.logger.warning(f"未获取到股票 {ticker} 的新闻数据")
                return None

            self.logger.info(f"成功获取到 {len(df)} 条新闻数据")

            # 数据预处理
            processed_df = self._process_news_data(df, ticker, convert_timezone=convert_timezone)

            return processed_df

        except Exception as e:
            self.logger.error(f"获取股票 {ticker} 新闻数据时发生错误: {e}")
            return None

    @retry(
        stop=stop_after_attempt(DataProviderConfig.AKSHARE_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1,
            min=DataProviderConfig.AKSHARE_RETRY_MIN_WAIT,
            max=DataProviderConfig.AKSHARE_RETRY_MAX_WAIT
        ),
        retry=retry_if_exception_type((IOError, requests.exceptions.RequestException))
    )
    async def _fetch_stock_news_from_akshare(self, keyword: str) -> Optional[pd.DataFrame]:
        """从AKShare获取股票新闻数据（带重试机制）"""
        def sync_akshare_call():
            return ak.stock_news_em(symbol=keyword)

        df = await asyncio.to_thread(sync_akshare_call)

        if df is None or df.empty:
            raise IOError("API returned empty news data.")

        return df

    def _process_news_data(self, df: pd.DataFrame, ticker: str, convert_timezone: bool = True,
                          source_timezone: str = 'Asia/Shanghai') -> pd.DataFrame:
        """处理新闻数据：字段重命名、数据清理、时间过滤"""
        try:
            processed_df = df.copy()
            processed_df['ticker'] = ticker

            # 字段重命名映射
            column_mapping = {
                '关键词': 'keyword', '新闻标题': 'title', '新闻内容': 'content',
                '发布时间': 'publish_time', '文章来源': 'source', '新闻链接': 'link'
            }

            processed_df = processed_df.rename(columns=column_mapping)

            # 删除不需要的字段
            columns_to_drop = ['source', 'link']
            for col in columns_to_drop:
                if col in processed_df.columns:
                    processed_df = processed_df.drop(columns=[col])

            # 处理发布时间
            if 'publish_time' in processed_df.columns:
                processed_df['publish_time'] = pd.to_datetime(processed_df['publish_time'], errors='coerce')

            # 过滤日期
            processed_df = self._filter_news_by_date(processed_df, source_timezone)

            # 时区转换
            if convert_timezone and 'publish_time' in processed_df.columns and len(processed_df) > 0:
                self.logger.info(f"开始时区转换: {source_timezone} -> US/Eastern")
                processed_df['publish_time'] = processed_df['publish_time'].apply(
                    lambda dt: TimezoneConverter.convert_to_et(dt, source_timezone)
                )
                processed_df = processed_df.dropna(subset=['publish_time'])
                self.logger.info(f"时区转换后剩余 {len(processed_df)} 条记录")

            # 按发布时间倒序排列
            if 'publish_time' in processed_df.columns:
                processed_df = processed_df.sort_values('publish_time', ascending=False)

            processed_df = processed_df.reset_index(drop=True)
            self.logger.info(f"新闻数据处理完成，过滤后剩余 {len(processed_df)} 条记录")

            return processed_df

        except Exception as e:
            self.logger.error(f"处理新闻数据时发生错误: {e}")
            return df


class TickerTickNewsProvider(NewsDataProvider):
    """TickerTick 新闻数据提供者"""

    def __init__(self, config: Optional[DataProviderConfig] = None):
        super().__init__(config)
        self._request_times = deque()

    async def fetch_data(self, ticker: str, story_type: str = 'T:curated', num_stories: int = 30) -> Optional[pd.DataFrame]:
        """
        从TickerTick API获取指定股票的新闻数据

        Args:
            ticker: 股票代码
            story_type: 新闻类型
            num_stories: 获取的新闻数量

        Returns:
            新闻数据DataFrame，失败时返回None
        """
        if not DataValidator.validate_ticker(ticker):
            self.logger.error("股票代码不能为空")
            return None

        self.logger.info(f"开始从TickerTick获取股票 {ticker} 的新闻数据，类型: {story_type}")

        try:
            # 从TickerTick API获取新闻数据
            df = await self._fetch_stock_news_from_tickertick(ticker, num_stories, story_type)

            if df is None or df.empty:
                self.logger.warning(f"未从TickerTick获取到股票 {ticker} 的新闻数据")
                return None

            self.logger.info(f"成功从TickerTick获取到 {len(df)} 条新闻数据")

            # 数据预处理
            processed_df = self._process_tickertick_news_data(df, ticker)

            return processed_df

        except Exception as e:
            self.logger.error(f"从TickerTick获取股票 {ticker} 新闻数据时发生错误: {e}")
            return None

    def _check_rate_limit(self):
        """检查并等待以确保遵守TickerTick API速率限制"""
        current_time = time.time()

        # 移除超出速率限制窗口的请求时间
        while (self._request_times and
               current_time - self._request_times[0] >= self.config.TICKERTICK_RATE_LIMIT_WINDOW):
            self._request_times.popleft()

        # 如果已达到速率限制，等待
        if len(self._request_times) >= self.config.TICKERTICK_RATE_LIMIT:
            oldest_request = self._request_times[0]
            wait_time = self.config.TICKERTICK_RATE_LIMIT_WINDOW - (current_time - oldest_request)
            if wait_time > 0:
                self.logger.info(f"遵守TickerTick速率限制，等待 {wait_time:.2f} 秒...")
                time.sleep(wait_time)
                # 等待后再次清理过期的请求时间
                current_time = time.time()
                while (self._request_times and
                       current_time - self._request_times[0] >= self.config.TICKERTICK_RATE_LIMIT_WINDOW):
                    self._request_times.popleft()

        # 记录当前请求时间
        self._request_times.append(current_time)

    async def _fetch_stock_news_from_tickertick(self, ticker: str, num_stories: int = 30,
                                               story_type: str = 'T:curated') -> Optional[pd.DataFrame]:
        """从TickerTick API获取股票新闻数据（带重试机制）"""
        # 验证故事类型
        if not StoryType.is_valid(story_type):
            self.logger.warning(f"不支持的故事类型: {story_type}，使用默认类型 'T:curated'")
            story_type = StoryType.CURATED.code

        description = StoryType.get_description(story_type)
        self.logger.info(f"使用故事类型: {story_type} - {description}")

        # 构建查询参数
        params = {
            'q': f"(and {story_type} tt:{ticker.lower()})",
            'n': min(max(num_stories, 1), 1000)
        }

        try:
            # 重试机制
            for attempt in range(self.config.TICKERTICK_MAX_RETRIES):
                try:
                    # 检查速率限制
                    self._check_rate_limit()

                    # 使用httpx发送异步请求
                    async with httpx.AsyncClient() as client:
                        response = await client.get(self.config.TICKERTICK_BASE_URL, params=params)
                        response.raise_for_status()

                    # 解析 JSON 响应
                    data = response.json()

                    # 检查是否有stories数据
                    if not data or 'stories' not in data or not data['stories']:
                        self.logger.warning(f"TickerTick API返回空数据: {ticker}")
                        return None

                    # 转换为DataFrame
                    stories = data['stories']
                    df = pd.DataFrame(stories)

                    self.logger.info(f"成功从TickerTick获取 {len(df)} 条 {ticker} 新闻数据")
                    return df

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < self.config.TICKERTICK_MAX_RETRIES - 1:
                        self.logger.warning(f"TickerTick API 429错误，等待 {self.config.TICKERTICK_RETRY_DELAY} 秒后重试... (尝试 {attempt + 1}/{self.config.TICKERTICK_MAX_RETRIES})")
                        await asyncio.sleep(self.config.TICKERTICK_RETRY_DELAY)
                        continue
                    else:
                        self.logger.error(f"TickerTick API HTTP错误: {e}")
                        return None

                except Exception as e:
                    self.logger.error(f"TickerTick API请求异常: {e}")
                    if attempt < self.config.TICKERTICK_MAX_RETRIES - 1:
                        await asyncio.sleep(5)
                        continue
                    return None

        except Exception as e:
            self.logger.error(f"TickerTick API调用失败: {e}")
            return None

    def _process_tickertick_news_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """处理TickerTick新闻数据：字段重命名、数据清理、时间过滤"""
        try:
            processed_df = df.copy()
            processed_df['ticker'] = ticker

            # 处理keyword字段 - 从tags中提取或使用ticker
            if 'tags' in processed_df.columns:
                processed_df['keyword'] = processed_df['tags'].apply(
                    lambda tags: ', '.join(tags) if isinstance(tags, list) and tags else ticker
                )
            else:
                processed_df['keyword'] = ticker

            # 字段重命名
            column_mapping = {
                'title': 'title',
                'description': 'content',
                'time': 'publish_time'
            }

            for old_col, new_col in column_mapping.items():
                if old_col in processed_df.columns:
                    processed_df = processed_df.rename(columns={old_col: new_col})

            # 删除不需要的字段
            columns_to_drop = ['tags', 'id', 'url', 'site']
            for col in columns_to_drop:
                if col in processed_df.columns:
                    processed_df = processed_df.drop(columns=[col])

            # 处理发布时间 - 使用datetime.fromtimestamp()直接转换为美国东部时区
            if 'publish_time' in processed_df.columns:
                et_tz = pytz.timezone(self.config.TARGET_TIMEZONE)

                def convert_timestamp_to_et(timestamp_ms):
                    """将毫秒时间戳转换为ET时间"""
                    if pd.isna(timestamp_ms):
                        return None
                    try:
                        timestamp_s = timestamp_ms / 1000
                        dt_et = datetime.fromtimestamp(timestamp_s, tz=et_tz)
                        return dt_et.replace(tzinfo=None)
                    except Exception as e:
                        self.logger.warning(f"时间戳转换失败: {timestamp_ms} -> {e}")
                        return None

                processed_df['publish_time'] = processed_df['publish_time'].apply(convert_timestamp_to_et)

            # 过滤掉description为空或字符数少于30个字符的记录
            if 'content' in processed_df.columns:
                processed_df = processed_df.dropna(subset=['content'])
                processed_df = processed_df[processed_df['content'].str.len() >= self.config.MIN_CONTENT_LENGTH]

            # 过滤最近几天的数据
            processed_df = self._filter_news_by_date_et(processed_df)

            # 按发布时间倒序排列
            if 'publish_time' in processed_df.columns:
                processed_df = processed_df.sort_values('publish_time', ascending=False)

            processed_df = processed_df.reset_index(drop=True)
            self.logger.info(f"TickerTick新闻数据处理完成，过滤后剩余 {len(processed_df)} 条记录")

            return processed_df

        except Exception as e:
            self.logger.error(f"处理TickerTick新闻数据时发生错误: {e}")
            return df

    def _filter_news_by_date_et(self, df: pd.DataFrame) -> pd.DataFrame:
        """基于美国东部时间过滤新闻数据"""
        if 'publish_time' not in df.columns or len(df) == 0:
            return df

        # 获取当前美国东部时间
        et_tz = pytz.timezone(self.config.TARGET_TIMEZONE)
        current_et_time = datetime.now(et_tz)
        filter_days_ago_et = current_et_time - timedelta(days=self.config.NEWS_FILTER_DAYS)
        filter_days_ago_et_naive = filter_days_ago_et.replace(tzinfo=None)

        self.logger.info(f"TickerTick数据筛选: 当前ET时间 {current_et_time}")
        self.logger.info(f"TickerTick数据筛选: {self.config.NEWS_FILTER_DAYS}天前ET时间 {filter_days_ago_et}")

        # 记录筛选前的数据
        self.logger.info(f"TickerTick筛选前数据条数: {len(df)}")
        if len(df) > 0:
            self.logger.info(f"TickerTick筛选前时间范围: {df['publish_time'].min()} 到 {df['publish_time'].max()}")

        # 筛选数据
        df_filtered = df.dropna(subset=['publish_time'])
        df_filtered = df_filtered[df_filtered['publish_time'] >= filter_days_ago_et_naive]

        self.logger.info(f"TickerTick筛选后剩余 {len(df_filtered)} 条记录")
        if len(df_filtered) > 0:
            self.logger.info(f"TickerTick筛选后时间范围: {df_filtered['publish_time'].min()} 到 {df_filtered['publish_time'].max()}")

        return df_filtered


# ===== 全局新闻数据提供者实例 =====

# 创建全局实例
_akshare_news_provider = AKShareNewsProvider()
_tickertick_news_provider = TickerTickNewsProvider()


def _get_company_chinese_name(db: Session, ticker: str) -> Optional[str]:
    """
    向后兼容性函数：从us_stocks_name表获取股票的中文名称
    """
    try:
        stmt = select(UsStocksName.cname).where(UsStocksName.symbol == ticker)
        result = db.execute(stmt).scalar_one_or_none()

        if result:
            return _clean_company_name(result)
        else:
            logger.warning(f"未找到股票 {ticker} 的中文名称")
            return None

    except Exception as e:
        logger.error(f"查询股票 {ticker} 中文名称时发生错误: {e}")
        return None


# 旧的 _fetch_stock_news_from_akshare 函数已移至 AKShareNewsProvider 类中


async def fetch_stock_news_from_akshare(db: Session, ticker: str, convert_timezone: bool = True) -> Optional[pd.DataFrame]:
    """
    向后兼容性函数：从AKShare获取指定股票的新闻数据
    """
    return await _akshare_news_provider.fetch_data(db, ticker, convert_timezone)


def _process_news_data(df: pd.DataFrame, ticker: str, convert_timezone: bool = True, source_timezone: str = 'Asia/Shanghai') -> pd.DataFrame:
    """向后兼容性函数：处理新闻数据"""
    return _akshare_news_provider._process_news_data(df, ticker, convert_timezone, source_timezone)


# ===== TickerTick API 新闻数据源 =====

# 旧的 TickerTick 常量和函数已移至 DataProviderConfig 和 TickerTickNewsProvider 类中

# 向后兼容性函数（旧的实现已移至 TickerTickNewsProvider 类中）
def _fetch_stock_news_from_tickertick(ticker: str, num_stories: int = 30, story_type: str = 'T:curated') -> Optional[pd.DataFrame]:
    """向后兼容性函数：从TickerTick API获取股票新闻数据"""
    # 注意：这是一个同步函数，但调用异步方法，需要在异步上下文中使用
    import asyncio
    return asyncio.run(_tickertick_news_provider._fetch_stock_news_from_tickertick(ticker, num_stories, story_type))


def _process_tickertick_news_data(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """向后兼容性函数：处理TickerTick新闻数据"""
    return _tickertick_news_provider._process_tickertick_news_data(df, ticker)


# 旧的重复实现已删除，功能已移至 TickerTickNewsProvider 类中


async def fetch_stock_news_from_tickertick(ticker: str, story_type: str = 'T:curated', num_stories: int = 30) -> Optional[pd.DataFrame]:
    """
    向后兼容性函数：从TickerTick API获取指定股票的新闻数据
    """
    return await _tickertick_news_provider.fetch_data(ticker, story_type, num_stories)


# ===== 模块导出 =====

# 主要类
__all__ = [
    # 配置和枚举
    'DataProviderConfig',
    'StoryType',

    # 核心类
    'BaseDataProvider',
    'StockDataProvider',
    'NewsDataProvider',
    'AKShareNewsProvider',
    'TickerTickNewsProvider',

    # 工具类
    'DataValidator',
    'TimezoneConverter',

    # 向后兼容性函数
    'fetch_from_akshare',
    'fetch_stock_news_from_akshare',
    'fetch_stock_news_from_tickertick',
    'get_supported_story_types',
    'validate_story_type',
    'get_story_type_description',
]


if __name__ == "__main__":
    print("数据提供者模块已重构完成。")
    print("主要改进：")
    print("- 面向对象设计，清晰的类结构")
    print("- 统一的配置管理")
    print("- 完善的类型注解和文档")
    print("- 保持向后兼容性")
    print("- 更好的错误处理和重试机制")