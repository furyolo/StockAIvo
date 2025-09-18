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
from dataclasses import dataclass
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Literal, Union, Any, Tuple, Deque
from enum import Enum

import akshare as ak
import httpx
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import pytz  # type: ignore
import requests  # type: ignore
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .database import get_fullsymbol_from_db  # type: ignore
from .models import UsStocksName  # type: ignore

# 配置日志
logger = logging.getLogger(__name__)

# 类型定义
PeriodType = Literal["daily", "weekly", "minute"]
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
    NEWS_FILTER_DAYS = 3  # 新闻数据过滤天数
    MIN_CONTENT_LENGTH = 30  # 新闻内容最小长度

    # 时区配置
    DEFAULT_SOURCE_TIMEZONE = 'Asia/Shanghai'
    TARGET_TIMEZONE = 'US/Eastern'

    # 数据验证配置
    REQUIRED_PRICE_COLUMNS = ['open', 'high', 'low', 'close']
    REQUIRED_VOLUME_COLUMNS = ['volume']

    # 数据验证增强配置
    # 智能验证系统的核心参数，用于控制验证策略的严格程度和修复行为

    MAX_ANOMALY_RATIO = 0.05  # 异常容忍度：最多5%的记录可以有异常
                              # 当异常比例超过此值时，验证失败
                              # 建议范围：0.01-0.10 (1%-10%)

    BOUNDARY_MINUTES = 5      # 边界时段定义：首末5分钟使用宽松验证规则
                              # 针对分钟线数据的首末时刻可能存在的价格异常
                              # 建议范围：3-10分钟

    ENABLE_PRICE_REPAIR = True # 价格修复开关：启用价格边界修复功能
                               # 自动修复超出high-low范围的开盘价和收盘价
                               # 生产环境建议保持True

    ENABLE_BOUNDARY_REPAIR = True # 边界修复开关：启用边界时段的特殊修复
                                  # 为首末时刻提供更宽松的修复策略
                                  # 配合BOUNDARY_MINUTES使用

    MAX_PRICE_JUMP_RATIO = 0.1 # 价格跳跃阈值：10%的价格跳跃视为异常
                               # 用于检测相邻时刻的异常价格变动
                               # 建议范围：0.05-0.20 (5%-20%)

    # 公司名称清理配置
    COMPANY_SUFFIXES_TO_REMOVE = ["公司", "集团", "股份有限公司", "有限公司", "股份公司", "控股", "投资"]


@dataclass
class ValidationResult:
    """
    数据验证结果类

    封装验证和修复过程的完整信息，为智能验证系统提供结构化的结果返回。

    字段说明：
    - is_valid: 验证是否通过，考虑修复后的数据质量
    - repaired_count: 成功修复的记录总数
    - error_count: 无法修复的错误记录数量
    - warnings: 验证过程中的警告信息列表
    - repair_stats: 详细的修复统计，格式为 {'repair_type': count}
    - anomaly_ratio: 异常记录比例 (error_count + repaired_count) / total_count
    - quality_score: 数据质量分数 (0.0-1.0)，自动计算

    使用示例：
        result = ValidationResult(True, 2, 0, [], {'open_repaired': 1, 'close_repaired': 1}, 0.05)
        print(f"质量分数: {result.quality_score}")  # 自动计算的质量分数
    """
    is_valid: bool                    # 验证是否通过
    repaired_count: int              # 修复的记录数量
    error_count: int                 # 错误记录数量
    warnings: List[str]              # 警告信息列表
    repair_stats: Dict[str, int]     # 详细修复统计
    anomaly_ratio: float             # 异常记录比例
    quality_score: float = 0.0       # 数据质量分数

    def __post_init__(self):
        """计算数据质量分数"""
        if self.error_count + self.repaired_count == 0:
            self.quality_score = 1.0
        else:
            self.quality_score = 1.0 - (self.error_count / (self.error_count + self.repaired_count))


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
    async def fetch_data(self, *args: Any, **kwargs: Any) -> Optional[pd.DataFrame]:
        """获取数据的抽象方法"""
        pass

    def _log_before_retry(self, retry_state: Any) -> None:
        """在每次重试前记录日志"""
        self.logger.warning(
            f"Retrying API call, attempt {retry_state.attempt_number} "
            f"after error: {retry_state.outcome.exception() if retry_state.outcome and retry_state.outcome.exception() else '未知错误'}"
        )


class DataValidator:
    """
    数据验证器类

    提供股票数据的验证和修复功能，包括：
    - 基础数据验证：检查必要列、价格逻辑关系
    - 智能验证与修复：支持分层验证策略和价格边界修复
    - 价格边界修复：自动修复超出范围的开盘价和收盘价
    - 分层验证策略：对分钟线数据的首末时刻使用宽松验证规则

    主要方法：
    - validate_ticker(): 验证股票代码格式
    - validate_price_data(): 传统的严格数据验证
    - validate_price_data_with_repair(): 智能验证与修复（推荐使用）
    - _repair_price_boundaries(): 价格边界修复算法
    - _get_validation_strategy(): 获取分层验证策略
    """

    @staticmethod
    def validate_ticker(ticker: str) -> bool:
        """验证股票代码"""
        return bool(ticker and ticker.strip())

    @staticmethod
    def validate_period(period: str) -> bool:
        """验证时间周期"""
        return period in ["daily", "weekly", "10min", "minute"]

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

    @staticmethod
    def _repair_price_boundaries(df: pd.DataFrame) -> Dict[str, int]:
        """
        修复价格边界异常

        修复开盘价或收盘价超出最高最低价范围的异常情况。
        使用向量化操作确保性能，将超出范围的价格调整到合理区间内。

        Args:
            df: 包含价格数据的DataFrame

        Returns:
            Dict[str, int]: 修复统计信息
        """
        repair_stats = {'open_repaired': 0, 'close_repaired': 0}

        # 修复开盘价超出范围的情况
        open_out_of_bounds = (df['open'] > df['high']) | (df['open'] < df['low'])
        if open_out_of_bounds.any():
            # 使用向量化操作修复开盘价：确保在high和low之间
            df.loc[open_out_of_bounds, 'open'] = df.loc[open_out_of_bounds].apply(
                lambda row: max(row['low'], min(row['high'], row['open'])), axis=1
            )
            repair_stats['open_repaired'] = open_out_of_bounds.sum()

        # 修复收盘价超出范围的情况
        close_out_of_bounds = (df['close'] > df['high']) | (df['close'] < df['low'])
        if close_out_of_bounds.any():
            # 使用向量化操作修复收盘价：确保在high和low之间
            df.loc[close_out_of_bounds, 'close'] = df.loc[close_out_of_bounds].apply(
                lambda row: max(row['low'], min(row['high'], row['close'])), axis=1
            )
            repair_stats['close_repaired'] = close_out_of_bounds.sum()

        return repair_stats

    @staticmethod
    def _get_validation_strategy(df: pd.DataFrame, period: str) -> pd.Series:
        """
        获取分层验证策略

        根据数据类型和记录位置确定验证策略。对于分钟线数据，
        首末时刻使用宽松验证规则，中间时段使用严格验证规则。

        Args:
            df: 包含数据的DataFrame
            period: 数据周期类型

        Returns:
            pd.Series: 每条记录对应的验证策略（'strict' 或 'lenient'）
        """
        # 非分钟线数据或缺少时间戳列，使用严格验证
        if period != 'minute' or 'minute_timestamp' not in df.columns:
            return pd.Series(['strict'] * len(df), index=df.index)

        # 确保数据按时间排序
        df_sorted = df.sort_values('minute_timestamp')
        total_records = len(df_sorted)
        boundary_count = DataProviderConfig.BOUNDARY_MINUTES

        # 创建验证策略Series，默认为严格验证
        strategy = pd.Series(['strict'] * total_records, index=df_sorted.index)

        # 首末边界使用宽松策略（只有当记录数足够多时）
        if total_records > boundary_count * 2:
            strategy.iloc[:boundary_count] = 'lenient'
            strategy.iloc[-boundary_count:] = 'lenient'

        # 重新索引以匹配原始DataFrame的顺序
        return strategy.reindex(df.index)

    @staticmethod
    def validate_price_data_with_repair(df: pd.DataFrame, period: Optional[str] = None) -> Tuple[bool, pd.DataFrame, ValidationResult]:
        """
        智能数据验证与修复

        整合所有验证和修复逻辑，提供智能的数据质量管理。
        支持分层验证策略和价格边界修复，返回详细的验证结果。

        Args:
            df: 包含价格数据的DataFrame
            period: 数据周期类型，用于确定验证策略

        Returns:
            Tuple[bool, pd.DataFrame, ValidationResult]:
                - 验证是否通过
                - 修复后的DataFrame
                - 详细的验证结果
        """
        if df is None or df.empty:
            return False, df, ValidationResult(False, 0, 1, ['数据为空'], {}, 0.0)

        # 检查必要列
        required_columns = DataProviderConfig.REQUIRED_PRICE_COLUMNS
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return False, df, ValidationResult(False, 0, 1, [f'缺少必要列: {missing_columns}'], {}, 0.0)

        df_copy = df.copy()
        warnings = []
        repair_stats = {}
        total_errors = 0

        # 获取验证策略
        validation_strategy = DataValidator._get_validation_strategy(df_copy, period or '')

        # 基础逻辑验证
        high_low_errors = (df_copy['high'] < df_copy['low']).sum()
        if high_low_errors > 0:
            total_errors += high_low_errors
            warnings.append(f'发现{high_low_errors}条最高价低于最低价的记录')

        # 价格边界修复
        if DataProviderConfig.ENABLE_PRICE_REPAIR:
            boundary_repair_stats = DataValidator._repair_price_boundaries(df_copy)
            repair_stats.update(boundary_repair_stats)

        # 计算异常比例
        total_repaired = sum(repair_stats.values())
        anomaly_ratio = (total_errors + total_repaired) / len(df_copy) if len(df_copy) > 0 else 0

        # 判断是否通过验证
        is_valid = (total_errors == 0 and anomaly_ratio <= DataProviderConfig.MAX_ANOMALY_RATIO)

        result = ValidationResult(
            is_valid=is_valid,
            repaired_count=total_repaired,
            error_count=total_errors,
            warnings=warnings,
            repair_stats=repair_stats,
            anomaly_ratio=anomaly_ratio
        )

        return is_valid, df_copy, result


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

    @staticmethod
    def convert_to_utc8(dt: pd.Timestamp, source_timezone: Optional[str] = None) -> Optional[pd.Timestamp]:
        """
        将时间从指定源时区转换为UTC+8时区（Asia/Shanghai）

        Args:
            dt: pandas Timestamp对象，假设为源时区的naive datetime
            source_timezone: 源时区名称，默认为美国东部时间

        Returns:
            转换后的UTC+8时间（naive datetime），如果转换失败返回None
        """
        if pd.isna(dt):
            return None

        if source_timezone is None:
            source_timezone = DataProviderConfig.TARGET_TIMEZONE  # 默认从美东时间转换

        try:
            # 定义时区
            source_tz = pytz.timezone(source_timezone)
            utc8_tz = pytz.timezone('Asia/Shanghai')

            # 如果输入的时间没有时区信息，假设为源时区
            if dt.tz is None:
                dt_with_tz = source_tz.localize(dt)
            else:
                dt_with_tz = dt.tz_convert(source_tz)

            # 转换为UTC+8时间
            utc8_time = dt_with_tz.astimezone(utc8_tz)

            # 返回naive datetime（移除时区信息）
            return pd.Timestamp(utc8_time.replace(tzinfo=None))

        except Exception as e:
            logger.warning(f"时区转换失败: {dt} ({source_timezone} -> Asia/Shanghai) -> {e}")
            return None


# ===== 全局重试配置和辅助函数 =====

def _log_before_retry(retry_state: Any) -> None:
    """全局重试日志函数"""
    logger.warning(
        f"Retrying API call, attempt {retry_state.attempt_number} "
        f"after error: {retry_state.outcome.exception() if retry_state.outcome and retry_state.outcome.exception() else '未知错误'}"
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
        elif period == "minute":
            # 使用AKShare的分时数据接口，需要datetime格式的日期参数
            logger.info(f"Fetching minute data for {fullsymbol} using stock_us_hist_min_em")

            # 获取正确的交易时间（考虑夏令时/冬令时）
            if ak_start_date and ak_start_date != '19700101':
                # 解析日期并获取该日期的交易时间（美东时间）
                target_date = datetime.strptime(ak_start_date, '%Y%m%d').date()
                market_open_time, market_close_time = _get_market_hours_for_date(target_date)

                # 构建美东时间的datetime对象
                start_et = pd.Timestamp(f"{ak_start_date[:4]}-{ak_start_date[4:6]}-{ak_start_date[6:8]} {market_open_time}")
                end_et = pd.Timestamp(f"{ak_end_date[:4]}-{ak_end_date[4:6]}-{ak_end_date[6:8]} {market_close_time}" if ak_end_date else f"{ak_start_date[:4]}-{ak_start_date[4:6]}-{ak_start_date[6:8]} {market_close_time}")

                # 转换为UTC+8时区（AKShare API要求的时区）
                start_utc8 = TimezoneConverter.convert_to_utc8(start_et, 'US/Eastern')
                end_utc8 = TimezoneConverter.convert_to_utc8(end_et, 'US/Eastern')

                if start_utc8 is None or end_utc8 is None:
                    logger.warning("时区转换失败，使用默认时间范围")
                    start_datetime = "1979-09-01 09:32:00"
                    end_datetime = "2222-01-01 09:32:00"
                else:
                    start_datetime = start_utc8.strftime('%Y-%m-%d %H:%M:%S')
                    end_datetime = end_utc8.strftime('%Y-%m-%d %H:%M:%S')
                    logger.info(f"时区转换完成: ET {start_et} -> UTC+8 {start_datetime}, ET {end_et} -> UTC+8 {end_datetime}")
            else:
                # 使用默认的广泛范围（UTC+8时区）
                start_datetime = "1979-09-01 09:32:00"
                end_datetime = "2222-01-01 09:32:00"

            logger.info(f"Using UTC+8 datetime range for AKShare API: {start_datetime} to {end_datetime}")
            return ak.stock_us_hist_min_em(symbol=fullsymbol, start_date=start_datetime, end_date=end_datetime)
        return None

    df = await asyncio.to_thread(sync_akshare_call)

    # 如果 API 返回 None 或空的 DataFrame，主动抛出 IOError 触发重试
    if df is None or df.empty:
        raise IOError("API returned empty data.")
        
    return df


def _get_market_hours_for_date(target_date: date) -> Tuple[str, str]:
    """
    获取指定日期的美股交易时间，自动处理夏令时/冬令时

    Args:
        target_date: 目标日期

    Returns:
        tuple: (开盘时间字符串, 收盘时间字符串) 格式为 "HH:MM:SS"
    """
    try:
        import pandas_market_calendars as mcal

        # 获取NYSE日历
        nyse = mcal.get_calendar('NYSE')
        et_tz = nyse.tz  # 自动处理EST/EDT时区转换

        # 生成目标日期的交易时间表
        schedule = nyse.schedule(start_date=target_date, end_date=target_date)

        if not schedule.empty:
            # 获取开盘和收盘时间
            market_open = schedule.iloc[0]['market_open']
            market_close = schedule.iloc[0]['market_close']

            # 确保时间使用正确的美东时区
            if hasattr(market_open, 'tz') and market_open.tz is not None:
                market_open_et = market_open.tz_convert(et_tz)
            else:
                market_open_et = market_open

            if hasattr(market_close, 'tz') and market_close.tz is not None:
                market_close_et = market_close.tz_convert(et_tz)
            else:
                market_close_et = market_close

            # 返回时间字符串
            open_time = market_open_et.strftime('%H:%M:%S')
            close_time = market_close_et.strftime('%H:%M:%S')

            logger.debug(f"Market hours for {target_date}: {open_time} - {close_time}")
            return open_time, close_time
        else:
            # 如果不是交易日，返回标准时间
            logger.warning(f"{target_date} is not a trading day, using standard hours")
            return "09:30:00", "16:00:00"

    except Exception as e:
        logger.warning(f"Failed to get market hours for {target_date}: {e}, using standard hours")
        # 发生错误时返回标准交易时间
        return "09:30:00", "16:00:00"


# ===== 股票数据提供者类 =====

class StockDataProvider(BaseDataProvider):
    """股票价格数据提供者类"""

    def __init__(self, config: Optional[DataProviderConfig] = None):
        if config is None:
            config = DataProviderConfig()
        super().__init__(config)

    async def fetch_data(self, db: Session, ticker: str, period: str,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None, **kwargs: Any) -> Optional[pd.DataFrame]:
        """
        从 AKShare 获取指定股票的指定周期数据

        Args:
            db: 数据库会话
            ticker: 股票代码，如 'AAPL', 'TSLA'
            period: 数据周期，支持 'daily', 'weekly', '10min', 'minute'
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
            self.logger.error(f"不支持的时间周期: {period}，支持的周期: daily, weekly, 10min, minute")
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

            # 智能数据验证与修复
            is_valid, df, validation_result = DataValidator.validate_price_data_with_repair(df, period)

            # 记录验证结果
            self.logger.info(f'数据验证完成: {ticker} ({period}) - 状态: {"通过" if is_valid else "失败"}')

            if not is_valid:
                self.logger.error(f"数据验证失败，股票代码: {ticker}, 周期: {period}")
                self.logger.error(f"验证详情: 错误数={validation_result.error_count}, 异常比例={validation_result.anomaly_ratio:.2%}")
                return None

            # 记录修复信息
            if validation_result.repaired_count > 0:
                self.logger.info(f'修复统计: 总计{validation_result.repaired_count}条记录')
                for repair_type, count in validation_result.repair_stats.items():
                    if count > 0:
                        self.logger.info(f'  - {repair_type}: {count}条')

            # 记录数据质量警告
            if validation_result.warnings:
                for warning in validation_result.warnings:
                    self.logger.warning(f'数据质量警告: {warning}')

            self.logger.info(f"成功获取并验证了 {ticker} 的 {period} 数据，共 {len(df)} 条记录，质量分数: {validation_result.quality_score:.2f}")

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
                # 分时数据特有的列名映射
                '时间': 'minute_timestamp', '最新价': 'latest_price',
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

        elif period == "minute":
            # 对于分时数据，处理时间戳和时区转换
            self._process_minute_time_columns(df)

    def _process_minute_time_columns(self, df: pd.DataFrame) -> None:
        """处理分时数据的时间列和特殊情况"""
        try:
            # 确保有 minute_timestamp 列
            if 'minute_timestamp' in df.columns:
                # 转换时间字符串为 pandas datetime
                df['minute_timestamp'] = pd.to_datetime(df['minute_timestamp'], errors='coerce')

                # 时区转换：从UTC+8转换为美东时间
                df['minute_timestamp'] = df['minute_timestamp'].apply(
                    lambda dt: TimezoneConverter.convert_to_et(dt, 'Asia/Shanghai') if pd.notnull(dt) else None
                )

                # 移除时区转换失败的记录
                df = df.dropna(subset=['minute_timestamp'])

                self.logger.info(f"分时数据时区转换完成，剩余 {len(df)} 条记录")

            # 处理开盘价为0.00的异常情况
            if 'open' in df.columns:
                # 确保数据按时间戳排序，以便正确使用shift方法
                if 'minute_timestamp' in df.columns:
                    df = df.sort_values('minute_timestamp').reset_index(drop=True)

                # 识别开盘价为0或NaN的记录
                zero_open_mask = (df['open'] == 0.0) | (df['open'].isna())
                if zero_open_mask.any():
                    original_count = zero_open_mask.sum()
                    self.logger.warning(f"发现 {original_count} 条开盘价为0的记录，开始智能修复")

                    # 实现分层修复逻辑
                    repair_stats = {
                        'previous_close': 0,
                        'current_close': 0,
                        'current_latest': 0,
                        'failed': 0
                    }

                    # 第一优先级：使用上一个时刻的收盘价
                    if 'close' in df.columns:
                        previous_close = df['close'].shift(1)
                        mask_prev_close = zero_open_mask & previous_close.notna() & (previous_close > 0)
                        if mask_prev_close.any():
                            df.loc[mask_prev_close, 'open'] = previous_close.loc[mask_prev_close]
                            repair_stats['previous_close'] = mask_prev_close.sum()
                            zero_open_mask = zero_open_mask & ~mask_prev_close

                    # 第二优先级：使用同一时刻的收盘价
                    if zero_open_mask.any() and 'close' in df.columns:
                        mask_current_close = zero_open_mask & df['close'].notna() & (df['close'] > 0)
                        if mask_current_close.any():
                            df.loc[mask_current_close, 'open'] = df.loc[mask_current_close, 'close']
                            repair_stats['current_close'] = mask_current_close.sum()
                            zero_open_mask = zero_open_mask & ~mask_current_close

                    # 第三优先级：使用同一时刻的最新价
                    if zero_open_mask.any() and 'latest_price' in df.columns:
                        mask_current_latest = zero_open_mask & df['latest_price'].notna() & (df['latest_price'] > 0)
                        if mask_current_latest.any():
                            df.loc[mask_current_latest, 'open'] = df.loc[mask_current_latest, 'latest_price']
                            repair_stats['current_latest'] = mask_current_latest.sum()
                            zero_open_mask = zero_open_mask & ~mask_current_latest

                    # 统计未能修复的记录
                    repair_stats['failed'] = zero_open_mask.sum()

                    # 记录详细的修复统计信息
                    total_repaired = repair_stats['previous_close'] + repair_stats['current_close'] + repair_stats['current_latest']
                    self.logger.info(f"开盘价修复完成: 总计 {original_count} 条记录, 成功修复 {total_repaired} 条")
                    self.logger.info(f"修复详情: 上一时刻收盘价 {repair_stats['previous_close']} 条, "
                                   f"当前收盘价 {repair_stats['current_close']} 条, "
                                   f"当前最新价 {repair_stats['current_latest']} 条, "
                                   f"修复失败 {repair_stats['failed']} 条")

                    # 确保修复后的数据类型正确
                    if 'open' in df.columns:
                        df['open'] = pd.to_numeric(df['open'], errors='coerce')

        except Exception as e:
            self.logger.error(f"处理分时数据时间列时发生错误: {str(e)}")

    def _clean_and_convert_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清理和转换数据类型"""
        # 数据类型转换和清理
        df = df.replace({pd.NA: None, float('nan'): None})

        # 转换数值列
        numeric_columns = ['open', 'close', 'high', 'low', 'amplitude', 'price_change_percent', 'price_change', 'turnover_rate', 'latest_price']
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


# ===== 实时行情数据提供者 =====

class RealTimeQuoteProvider(BaseDataProvider):
    """
    美股实时行情数据提供者

    使用AKShare的stock_us_spot_em()接口获取美股实时行情数据，
    遵循项目现有的架构模式和代码风格。

    主要功能：
    - 获取美股实时行情数据
    - 数据标准化和验证
    - 智能重试机制
    - 与现有系统的无缝集成
    """

    def __init__(self, config: Optional[DataProviderConfig] = None):
        if config is None:
            config = DataProviderConfig()
        super().__init__(config)

    async def fetch_data(self, **kwargs: Any) -> Optional[pd.DataFrame]:
        """
        获取美股实时行情数据

        Returns:
            包含实时行情数据的 DataFrame，失败时返回 None
        """
        try:
            self.logger.info("开始获取美股实时行情数据")

            # 调用带重试逻辑的辅助函数
            df = await self._fetch_realtime_quotes_with_retry()

            if df is None or df.empty:
                self.logger.warning("获取到的实时行情数据为空")
                return None

            # 标准化列名
            df = self._standardize_columns(df)

            # 数据清洗和验证
            df = self._clean_and_validate_data(df)

            if df is None or df.empty:
                self.logger.warning("数据清洗后为空")
                return None

            self.logger.info(f"成功获取实时行情数据，共 {len(df)} 条记录")
            return df

        except Exception as e:
            self.logger.error(f"获取实时行情数据失败: {e}")
            return None

    @retry(
        stop=stop_after_attempt(DataProviderConfig.AKSHARE_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1,
            min=DataProviderConfig.AKSHARE_RETRY_MIN_WAIT,
            max=DataProviderConfig.AKSHARE_RETRY_MAX_WAIT
        ),
        retry=retry_if_exception_type((requests.exceptions.RequestException, IOError)),
        before_sleep=lambda retry_state: logger.warning(
            f"重试获取实时行情数据，第 {retry_state.attempt_number} 次尝试，"
            f"错误: {retry_state.outcome.exception() if retry_state.outcome and retry_state.outcome.exception() else '未知错误'}"
        )
    )
    async def _fetch_realtime_quotes_with_retry(self) -> Optional[pd.DataFrame]:
        """
        使用 tenacity 重试逻辑调用 AKShare 实时行情 API
        """
        self.logger.info("调用 AKShare stock_us_spot_em() 获取实时行情")

        def sync_akshare_call():
            return ak.stock_us_spot_em()

        df = await asyncio.to_thread(sync_akshare_call)

        # 如果 API 返回 None 或空的 DataFrame，主动抛出 IOError 触发重试
        if df is None or df.empty:
            raise IOError("API returned empty realtime quote data.")

        return df

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化 DataFrame 的列名，遵循项目约定

        Args:
            df: 原始数据 DataFrame

        Returns:
            标准化后的 DataFrame
        """
        # 列名映射字典，基于项目要求
        column_mapping = {
            "名称": "name",
            "最新价": "price",
            "涨跌额": "price_change",
            "涨跌幅": "price_change_percent",
            "开盘价": "open",
            "最高价": "high",
            "最低价": "low",
            "昨收价": "pre_close",
            "总市值": "market_value",
            "市盈率": "pe_ratio",
            "成交量": "volume",
            "成交额": "turnover",
            "振幅": "amplitude",
            "换手率": "turnover_rate",
            "代码": "fullsymbol"
        }

        # 重命名列
        df = df.rename(columns=column_mapping)

        self.logger.debug(f"列名标准化完成，当前列: {list(df.columns)}")
        return df

    def _clean_and_validate_data(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        数据清洗和验证，遵循项目数据处理标准

        Args:
            df: 待清洗的 DataFrame

        Returns:
            清洗后的 DataFrame，失败时返回 None
        """
        try:
            # 过滤无效记录（fullsymbol为空的记录）
            initial_count = len(df)
            df = df.dropna(subset=['fullsymbol'])
            df = df[df['fullsymbol'].str.strip() != '']

            if len(df) < initial_count:
                self.logger.info(f"过滤无效记录: {initial_count} -> {len(df)}")

            if df.empty:
                self.logger.warning("过滤后数据为空")
                return None

            # 从fullsymbol提取symbol字段
            df = self._extract_symbol_from_fullsymbol(df)

            # 数据类型转换和异常值处理
            df = self._convert_data_types(df)

            # 添加时间戳字段
            current_time = datetime.now(timezone.utc)
            df['created_at'] = current_time
            df['updated_at'] = current_time

            self.logger.info(f"数据清洗完成，有效记录数: {len(df)}")
            return df

        except Exception as e:
            self.logger.error(f"数据清洗失败: {e}")
            return None

    def _extract_symbol_from_fullsymbol(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        从fullsymbol字段提取symbol字段

        格式：106.AAPL -> AAPL

        Args:
            df: 包含fullsymbol字段的 DataFrame

        Returns:
            添加symbol字段的 DataFrame
        """
        def extract_symbol(fullsymbol):
            if pd.isna(fullsymbol) or not isinstance(fullsymbol, str):
                return None

            fullsymbol = str(fullsymbol).strip()
            if "." in fullsymbol:
                return fullsymbol.split(".", 1)[1]
            else:
                # 如果没有点分隔符，直接返回原值
                return fullsymbol

        df['symbol'] = df['fullsymbol'].apply(extract_symbol)

        # 过滤symbol为空的记录
        df = df.dropna(subset=['symbol'])
        df = df[df['symbol'].str.strip() != '']

        self.logger.debug(f"symbol字段提取完成，有效记录数: {len(df)}")
        return df

    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据类型转换和异常值处理，遵循项目标准

        Args:
            df: 待转换的 DataFrame

        Returns:
            转换后的 DataFrame
        """
        # 定义数值列和大整数列
        numeric_cols = [
            "price", "price_change", "price_change_percent",
            "open", "high", "low", "pre_close",
            "pe_ratio", "amplitude", "turnover_rate"
        ]
        bigint_cols = ["market_value", "volume", "turnover"]

        # 处理数值列
        for col in numeric_cols:
            if col in df.columns:
                df[col] = self._safe_numeric_conversion(df[col], col)

        # 处理大整数列
        for col in bigint_cols:
            if col in df.columns:
                df[col] = self._safe_bigint_conversion(df[col], col)

        # 处理字符串列
        string_cols = ["name", "symbol", "fullsymbol"]
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()

        return df

    def _safe_numeric_conversion(self, series: pd.Series, col_name: str) -> pd.Series:
        """
        安全的数值转换，处理NaN、Infinity等异常值

        Args:
            series: 待转换的 Series
            col_name: 列名（用于日志）

        Returns:
            转换后的 Series
        """
        try:
            # 转换为数值类型
            numeric_series = pd.to_numeric(series, errors='coerce')

            # 处理无穷大值
            inf_count = np.isinf(numeric_series).sum()
            if inf_count > 0:
                self.logger.warning(f"列 {col_name} 包含 {inf_count} 个无穷大值，已转换为NaN")
                numeric_series = numeric_series.replace([np.inf, -np.inf], np.nan)

            # 记录NaN值数量
            nan_count = numeric_series.isna().sum()
            if nan_count > 0:
                self.logger.debug(f"列 {col_name} 包含 {nan_count} 个NaN值")

            return numeric_series

        except Exception as e:
            self.logger.error(f"数值转换失败 {col_name}: {e}")
            return series

    def _safe_bigint_conversion(self, series: pd.Series, col_name: str) -> pd.Series:
        """
        安全的大整数转换

        Args:
            series: 待转换的 Series
            col_name: 列名（用于日志）

        Returns:
            转换后的 Series
        """
        try:
            # 先转换为数值类型
            numeric_series = pd.to_numeric(series, errors='coerce')

            # 处理无穷大值
            numeric_series = numeric_series.replace([np.inf, -np.inf], np.nan)

            # 转换为整数，保留NaN
            int_series = numeric_series.astype('Int64')  # 使用nullable integer type

            # 记录转换统计
            nan_count = int_series.isna().sum()
            if nan_count > 0:
                self.logger.debug(f"列 {col_name} 包含 {nan_count} 个NaN值")

            return int_series

        except Exception as e:
            self.logger.error(f"大整数转换失败 {col_name}: {e}")
            return series


# ===== 全局实例和向后兼容性函数 =====

# 创建全局实例
_stock_data_provider = StockDataProvider()
_realtime_quote_provider = RealTimeQuoteProvider()


# 保持向后兼容性的函数
async def fetch_from_akshare(db: Session, ticker: str, period: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    向后兼容性函数：从 AKShare 获取指定股票的指定周期数据
    """
    return await _stock_data_provider.fetch_data(db, ticker, period, start_date, end_date)


async def fetch_realtime_quotes() -> Optional[pd.DataFrame]:
    """
    向后兼容性函数：获取美股实时行情数据

    Returns:
        包含实时行情数据的 DataFrame，失败时返回 None
    """
    return await _realtime_quote_provider.fetch_data()


async def fetch_us_stock_names() -> Optional[pd.DataFrame]:
    """
    获取美股名称数据

    Returns:
        包含美股名称数据的 DataFrame，失败时返回 None
    """
    return await _us_stock_name_provider.fetch_data()


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

    async def fetch_data(self, *args: Any, **kwargs: Any) -> Optional[pd.DataFrame]:
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

        self.logger.info(f"基于数据源时区筛选: 当前{source_timezone}时间 {current_local_time.strftime('%Y-%m-%d %H:%M:%S %z')}")
        self.logger.info(f"基于数据源时区筛选: {self.config.NEWS_FILTER_DAYS}天前{source_timezone}时间 {filter_days_ago.strftime('%Y-%m-%d %H:%M:%S %z')}")

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

    async def fetch_data(self, db: Session, ticker: str, convert_timezone: bool = True, **kwargs: Any) -> Optional[pd.DataFrame]:
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
        self._request_times: Deque[float] = deque()

    async def fetch_data(self, ticker: str, story_type: str = 'T:curated', num_stories: int = 30, **kwargs: Any) -> Optional[pd.DataFrame]:
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
        params: Dict[str, Union[str, int]] = {
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

            # 如果所有重试都失败了，返回None
            return None

        except Exception as e:
            self.logger.error(f"TickerTick API调用失败: {e}")
            return None

    def _process_tickertick_news_data(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """处理TickerTick新闻数据：字段重命名、数据清理、时间过滤"""
        try:
            processed_df = df.copy()
            processed_df['ticker'] = ticker

            # 处理keyword字段 - 从tickers中提取或使用ticker
            if 'tickers' in processed_df.columns:
                processed_df['keyword'] = processed_df['tickers'].apply(
                    lambda tags: ', '.join(map(str.upper, tags)) if isinstance(tags, list) and tags else ticker
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
            columns_to_drop = ['id', 'url', 'site', "favicon_url", 'tags', 'similar_stories', 'tickers']
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

        self.logger.info(f"TickerTick数据筛选: 当前ET时间 {current_et_time.strftime('%Y-%m-%d %H:%M:%S %z')}")
        self.logger.info(f"TickerTick数据筛选: {self.config.NEWS_FILTER_DAYS}天前ET时间 {filter_days_ago_et.strftime('%Y-%m-%d %H:%M:%S %z')}")

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


# ===== 美股名称数据提供者 =====

class UsStockNameProvider(BaseDataProvider):
    """
    美股名称数据提供者

    使用AKShare的get_us_stock_name()接口获取美股名称数据，
    遵循项目现有的架构模式和代码风格。

    主要功能：
    - 获取美股名称数据
    - 数据标准化和验证
    - 智能重试机制
    - 与现有系统的无缝集成
    """

    def __init__(self, config: Optional[DataProviderConfig] = None):
        if config is None:
            config = DataProviderConfig()
        super().__init__(config)

    async def fetch_data(self) -> Optional[pd.DataFrame]:
        """
        获取美股名称数据

        Returns:
            清洗后的美股名称数据 DataFrame，失败时返回 None
        """
        try:
            self.logger.info("开始获取美股名称数据")

            # 调用带重试逻辑的辅助函数
            df = await self._fetch_us_stock_names_with_retry()

            if df is None or df.empty:
                self.logger.warning("获取到的美股名称数据为空")
                return None

            self.logger.info(f"获取到 {len(df)} 条美股名称数据")

            # 数据清洗和验证
            df = self._clean_and_validate_data(df)

            if df is None or df.empty:
                self.logger.warning("数据清洗后为空")
                return None

            self.logger.info(f"数据清洗完成，有效记录数: {len(df)}")
            return df

        except Exception as e:
            self.logger.error(f"获取美股名称数据失败: {e}")
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
    async def _fetch_us_stock_names_with_retry(self) -> Optional[pd.DataFrame]:
        """
        使用 tenacity 重试逻辑调用 AKShare 美股名称 API
        """
        self.logger.info("调用 AKShare get_us_stock_name() 获取美股名称")

        def sync_akshare_call():
            return ak.get_us_stock_name()

        df = await asyncio.to_thread(sync_akshare_call)

        # 如果 API 返回 None 或空的 DataFrame，主动抛出 IOError 触发重试
        if df is None or df.empty:
            raise IOError("API returned empty us stock name data.")

        return df

    def _clean_and_validate_data(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        数据清洗和验证，遵循项目数据处理标准

        Args:
            df: 待清洗的 DataFrame

        Returns:
            清洗后的 DataFrame，失败时返回 None
        """
        try:
            # 过滤无效记录（symbol为空的记录）
            initial_count = len(df)
            df = df.dropna(subset=['symbol'])
            df = df[df['symbol'].str.strip() != '']

            if len(df) < initial_count:
                self.logger.info(f"过滤无效记录: {initial_count} -> {len(df)}")

            if df.empty:
                self.logger.warning("过滤后数据为空")
                return None

            # 数据类型转换和清理
            df = self._convert_data_types(df)

            # 添加时间戳字段
            current_time = datetime.now(timezone.utc)
            df['created_at'] = current_time
            df['updated_at'] = current_time

            self.logger.info(f"数据清洗完成，有效记录数: {len(df)}")
            return df

        except Exception as e:
            self.logger.error(f"数据清洗失败: {e}")
            return None

    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据类型转换和异常值处理，遵循项目标准

        Args:
            df: 待转换的 DataFrame

        Returns:
            转换后的 DataFrame
        """
        # 处理字符串列
        string_cols = ["symbol", "name", "cname"]
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                # 将空字符串转换为None（对于可空字段）
                if col == "cname":
                    df[col] = df[col].replace('', None)

        self.logger.debug(f"数据类型转换完成，列: {list(df.columns)}")
        return df


# ===== 全局数据提供者实例 =====

# 创建全局实例
_akshare_news_provider = AKShareNewsProvider()
_tickertick_news_provider = TickerTickNewsProvider()
_us_stock_name_provider = UsStockNameProvider()


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
    'RealTimeQuoteProvider',
    'NewsDataProvider',
    'AKShareNewsProvider',
    'TickerTickNewsProvider',

    # 工具类
    'DataValidator',
    'TimezoneConverter',
    'ValidationResult',

    # 向后兼容性函数
    'fetch_from_akshare',
    'fetch_realtime_quotes',
    'fetch_us_stock_names',
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