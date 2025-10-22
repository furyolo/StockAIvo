"""
Redis缓存管理器模块
负责处理从AKShare获取的股票数据的临时缓存，在用户空闲时批量持久化到PostgreSQL
"""

import json
import logging
import pandas as pd
import redis
from typing import Dict, List, Optional, Tuple, Union, Any, TypedDict
from datetime import datetime, date, timedelta, timezone
import os
import threading
import hashlib
from dotenv import load_dotenv
from enum import Enum, auto
import pandas_market_calendars as mcal


class CacheType(Enum):
    """缓存类型的枚举"""
    PENDING_SAVE = auto()  # 表示数据等待被持久化
    GENERAL_CACHE = auto()  # 表示通用的查询结果缓存
    SEARCH_CACHE = auto()  # 表示搜索结果缓存
    TECHNICAL_ANALYSIS = auto()  # 表示技术分析结果缓存
    STRUCTURED_PREDICTION_PENDING = auto()  # 表示结构化预测待持久化

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

PREDICTION_PENDING_TTL_SECONDS = int(os.getenv("PREDICTION_PENDING_TTL_SECONDS", "259200"))  # 默认3天

class RedisConnectionError(Exception):
    """Redis连接异常"""
    pass

class RedisSerializationError(Exception):
    """Redis序列化异常"""
    pass


class TechnicalAnalysisCacheEntry(TypedDict):
    """技术分析缓存数据结构"""
    ticker: str
    market_aware_date: str
    analysis_text: str
    generated_at: str
    agent_version: str


class StructuredPredictionPendingEntry(TypedDict, total=False):
    """结构化预测待持久化的数据结构"""
    ticker: str
    market_aware_date: str
    target_date: str
    trading_days_count: int
    prediction_probability: Optional[float]
    direction: str
    confidence_level: str
    reasoning: Optional[str]
    prediction_timestamp: str
    enqueued_at: str


_NYSE_CALENDAR = None


def _get_nyse_calendar():
    """获取NYSE日历实例，避免重复初始化"""
    global _NYSE_CALENDAR
    if _NYSE_CALENDAR is None:
        _NYSE_CALENDAR = mcal.get_calendar('NYSE')
    return _NYSE_CALENDAR


def _convert_to_et(dt_obj: Any, et_tz) -> datetime:
    """将任意时间戳转换为美东时区时间"""
    if isinstance(dt_obj, datetime):
        dt = dt_obj
    elif hasattr(dt_obj, 'to_pydatetime'):
        dt = dt_obj.to_pydatetime()
    else:
        dt = datetime.fromisoformat(str(dt_obj))

    if dt.tzinfo is None:
        return et_tz.localize(dt)
    return dt.astimezone(et_tz)


def _find_next_market_open(now_et: datetime) -> Optional[datetime]:
    """查找下一次开盘时间，最多向前滚动6周"""
    nyse = _get_nyse_calendar()
    et_tz = nyse.tz
    search_start = now_et.date()

    for _ in range(6):
        search_end = search_start + timedelta(days=7)
        schedule = nyse.schedule(start_date=search_start, end_date=search_end)
        if not schedule.empty:
            for _, row in schedule.iterrows():
                market_open = _convert_to_et(row['market_open'], et_tz)
                if market_open > now_et:
                    return market_open
        search_start = search_end + timedelta(days=1)

    return None


def _calculate_market_aware_ttl(now_et: Optional[datetime] = None) -> int:
    """
    根据市场状态计算技术分析缓存TTL

    - 交易时间内固定180秒
    - 交易时间外设置为距离下一次开盘的秒数
    """
    try:
        nyse = _get_nyse_calendar()
        et_tz = nyse.tz
        current_time = _convert_to_et(now_et, et_tz) if now_et else datetime.now(et_tz)
        today = current_time.date()
        schedule = nyse.schedule(start_date=today, end_date=today)

        if not schedule.empty:
            market_open = _convert_to_et(schedule.iloc[0]['market_open'], et_tz)
            market_close = _convert_to_et(schedule.iloc[0]['market_close'], et_tz)

            if market_open <= current_time <= market_close:
                logger.debug("技术分析TTL计算：交易时间内，TTL设为180秒")
                return 180

            if current_time < market_open:
                ttl = int((market_open - current_time).total_seconds())
                logger.debug(f"技术分析TTL计算：开盘前缓存，TTL={ttl}秒")
                return max(ttl, 1)

        next_open = _find_next_market_open(current_time)
        if next_open:
            ttl = int((next_open - current_time).total_seconds())
            logger.debug(f"技术分析TTL计算：交易时间外，距离下次开盘{ttl}秒")
            return max(ttl, 1)

        logger.warning("技术分析TTL计算失败，使用退化TTL 600 秒")
        return 600

    except Exception as e:
        logger.warning(f"技术分析TTL计算异常: {e}，使用退化TTL 600 秒")
        return 600


def _is_market_open(now_et: Optional[datetime] = None) -> bool:
    """
    判断当前时间是否在美股交易时间内

    Returns:
        bool: True表示在交易时间内，False表示不在交易时间内
    """
    try:
        nyse = _get_nyse_calendar()
        et_tz = nyse.tz  # 自动处理EST/EDT时区转换

        current_time = _convert_to_et(now_et, et_tz) if now_et else datetime.now(et_tz)
        current_date_et = current_time.date()

        schedule = nyse.schedule(start_date=current_date_et, end_date=current_date_et)
        if schedule.empty:
            return False

        market_open = _convert_to_et(schedule.iloc[0]['market_open'], et_tz)
        market_close = _convert_to_et(schedule.iloc[0]['market_close'], et_tz)

        is_open = market_open <= current_time <= market_close

        logger.debug(
            "Market status check: current=%s, open=%s, close=%s, is_open=%s",
            current_time.strftime('%H:%M:%S'),
            market_open.strftime('%H:%M:%S'),
            market_close.strftime('%H:%M:%S'),
            is_open
        )

        return is_open

    except Exception as e:
        logger.warning(f"Failed to check market status: {e}, assuming market is closed")
        return False


class CacheManager:
    """Redis缓存管理器"""
    
    def __init__(self):
        """初始化Redis连接"""
        self.redis_client = None
        self._connect_to_redis()
    
    def _connect_to_redis(self) -> None:
        """
        配置并连接到Redis服务器
        支持从环境变量读取配置，提供默认值
        """
        try:
            # 从环境变量获取Redis配置
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_db = int(os.getenv('REDIS_DB', 0))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            
            # 创建Redis连接
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,  # 自动解码为字符串
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # 测试连接
            self.redis_client.ping()
            logger.info(f"成功连接到Redis服务器: {redis_host}:{redis_port}")
            
        except redis.ConnectionError as e:
            error_msg = f"无法连接到Redis服务器: {e}"
            logger.error(error_msg)
            raise RedisConnectionError(error_msg)
        except Exception as e:
            error_msg = f"Redis连接配置错误: {e}"
            logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    def _serialize_dataframe(self, df: pd.DataFrame) -> str:
        """
        将pandas DataFrame序列化为JSON字符串
        
        Args:
            df: 要序列化的DataFrame
            
        Returns:
            序列化后的JSON字符串
            
        Raises:
            RedisSerializationError: 序列化失败时抛出
        """
        try:
            # 处理可能的时间戳和日期列
            df_copy = df.copy()
            
            # 将所有日期时间列转换为字符串格式
            for col in df_copy.columns:
                if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                    # 对于日期列（date），只保留日期部分，不包含时间
                    if col.lower() in ['date']:
                        df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d')
                    else:
                        # 对于其他时间戳列，保留完整的日期时间格式
                        df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # 转换为字典，然后序列化为JSON
            data_dict = {
                'data': df_copy.to_dict('records'),
                'columns': df_copy.columns.tolist(),
                'timestamp': datetime.now().isoformat(),
                'row_count': len(df_copy)
            }
            
            return json.dumps(data_dict, ensure_ascii=False, default=str)
            
        except Exception as e:
            error_msg = f"DataFrame序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)
    
    def _deserialize_dataframe(self, json_str: str) -> pd.DataFrame:
        """
        将JSON字符串反序列化为pandas DataFrame
        
        Args:
            json_str: 序列化的JSON字符串
            
        Returns:
            反序列化后的DataFrame
            
        Raises:
            RedisSerializationError: 反序列化失败时抛出
        """
        try:
            data_dict = json.loads(json_str)
            df = pd.DataFrame(data_dict['data'])
            
            # 如果DataFrame不为空，尝试恢复日期时间格式
            if not df.empty:
                # 根据列名推断可能的日期列
                date_columns = ['date', 'timestamp', 'time', 'hour_timestamp']
                for col in df.columns:
                    if col.lower() in date_columns:
                        try:
                            df[col] = pd.to_datetime(df[col])
                        except:
                            # 如果转换失败，保持原格式
                            pass
            
            logger.info(f"成功反序列化为DataFrame，包含 {len(df)} 行数据")
            return df
            
        except Exception as e:
            error_msg = f"DataFrame反序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        """统一Ticker格式为大写"""
        return ticker.strip().upper()

    @staticmethod
    def _normalize_market_aware_date(value: Union[str, date]) -> str:
        """统一市场感知日期格式为YYYYMMDD"""
        if isinstance(value, date):
            return value.strftime('%Y%m%d')
        normalized = value.strip()
        if len(normalized) == 10 and '-' in normalized:
            normalized = normalized.replace('-', '')
        return normalized

    @staticmethod
    def _normalize_iso_date(value: Union[str, date]) -> str:
        """统一日期格式为 YYYY-MM-DD 字符串"""
        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        normalized = str(value).strip()
        if len(normalized) == 8 and normalized.isdigit():
            return f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}"
        return normalized

    @staticmethod
    def _normalize_date_compact(value: Union[str, date]) -> str:
        """统一日期格式为紧凑的 YYYYMMDD 字符串"""
        if isinstance(value, date):
            return value.strftime('%Y%m%d')
        normalized = str(value).strip()
        if len(normalized) == 10 and '-' in normalized:
            return normalized.replace('-', '')
        return normalized

    @classmethod
    def _build_technical_analysis_key(cls, ticker: str, market_aware_date: Union[str, date]) -> str:
        """构造技术分析缓存键"""
        normalized_ticker = cls._normalize_ticker(ticker)
        normalized_date = cls._normalize_market_aware_date(market_aware_date)
        return f"technical_analysis:{normalized_ticker}:{normalized_date}"

    @classmethod
    def _build_prediction_pending_key(
        cls,
        ticker: str,
        market_aware_date: Union[str, date],
        target_date: Union[str, date],
    ) -> str:
        """构造结构化预测待持久化键"""
        normalized_ticker = cls._normalize_ticker(ticker)
        market_date_compact = cls._normalize_date_compact(market_aware_date)
        target_date_compact = cls._normalize_date_compact(target_date)
        return f"prediction:pending:{normalized_ticker}:{market_date_compact}:{target_date_compact}"

    @staticmethod
    def _format_generated_at(value: Any) -> str:
        """将生成时间格式化为易读字符串"""
        if not value:
            return "未知"

        try:
            if isinstance(value, datetime):
                dt_value = value
            else:
                dt_value = datetime.fromisoformat(str(value))

            if dt_value.tzinfo is None:
                dt_value = dt_value.replace(tzinfo=timezone.utc)

            dt_utc = dt_value.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(value)

    @staticmethod
    def _serialize_technical_analysis(payload: TechnicalAnalysisCacheEntry) -> str:
        """序列化技术分析缓存数据"""
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            error_msg = f"技术分析缓存序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    @staticmethod
    def _deserialize_technical_analysis(json_str: str) -> TechnicalAnalysisCacheEntry:
        """反序列化技术分析缓存数据"""
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                raise ValueError("技术分析缓存内容格式非法")

            # 兼容旧版本缓存中的 metrics 字段，直接忽略
            if 'metrics' in data:
                data.pop('metrics', None)

            ticker_value = str(data.get('ticker', '')).strip()
            market_date_value = str(data.get('market_aware_date', '')).strip()

            return TechnicalAnalysisCacheEntry(
                ticker=CacheManager._normalize_ticker(ticker_value),
                market_aware_date=CacheManager._normalize_market_aware_date(market_date_value) if market_date_value else '',
                analysis_text=str(data.get('analysis_text', '')),
                generated_at=str(data.get('generated_at', '')),
                agent_version=str(data.get('agent_version', '')),
            )
        except Exception as e:
            error_msg = f"技术分析缓存反序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    @staticmethod
    def _deserialize_prediction_pending(json_str: str) -> StructuredPredictionPendingEntry:
        """反序列化结构化预测待持久化数据"""
        try:
            raw_data = json.loads(json_str)
            if not isinstance(raw_data, dict):
                raise ValueError("结构化预测待持久化缓存格式非法")

            ticker = CacheManager._normalize_ticker(str(raw_data.get("ticker", "")))
            market_date = CacheManager._normalize_iso_date(raw_data.get("market_aware_date", ""))
            target_date = CacheManager._normalize_iso_date(raw_data.get("target_date", ""))

            if not ticker or not market_date or not target_date:
                raise ValueError("结构化预测待持久化数据缺少必要字段")

            payload: StructuredPredictionPendingEntry = StructuredPredictionPendingEntry(
                ticker=ticker,
                market_aware_date=market_date,
                target_date=target_date,
                trading_days_count=int(raw_data.get("trading_days_count", 0)),
                prediction_probability=raw_data.get("prediction_probability"),
                direction=str(raw_data.get("direction", "")).upper(),
                confidence_level=str(raw_data.get("confidence_level", "")).upper(),
                reasoning=raw_data.get("reasoning"),
                prediction_timestamp=str(raw_data.get("prediction_timestamp", "")),
                enqueued_at=str(raw_data.get("enqueued_at", "")),
            )
            return payload
        except Exception as e:
            error_msg = f"结构化预测待持久化数据反序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    def save_to_redis(self, ticker: str, period: str, data: pd.DataFrame, cache_type: CacheType) -> Optional[str]:
        """
        将股票数据保存到Redis缓存，支持不同类型的缓存。

        Args:
            ticker: 股票代码 (例如: "AAPL")
            period: 时间周期 ("daily", "weekly", "10min", "minute")
            data: 股票数据DataFrame
            cache_type: 缓存类型 (CacheType.PENDING_SAVE 或 CacheType.GENERAL_CACHE)

        Returns:
            Optional[str]: 保存成功返回缓存键名，失败返回None
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        if data is None or data.empty:
            logger.warning(f"尝试保存空数据到Redis: {ticker}_{period} (类型: {cache_type.name})")
            return None

        try:
            # 根据缓存类型构建不同的键名和设置不同的过期时间
            if cache_type == CacheType.PENDING_SAVE:
                cache_key = f"pending_save:{ticker}:{period}"
                ttl = 86400  # 24小时，等待持久化
            elif cache_type == CacheType.GENERAL_CACHE:
                cache_key = f"general_cache:{ticker}:{period}"
                # {{ AURA-X: Modify - 为新闻数据设置30分钟TTL. Approval: 寸止(ID:1737364800). }}
                if period == "news":
                    ttl = 1800  # 30分钟，新闻数据更新频繁
                elif period == "minute":
                    # 分时数据动态TTL：交易时间内短缓存，交易时间外长缓存
                    if _is_market_open():
                        ttl = 120  # 2分钟，交易时间内数据更新频繁
                        logger.debug(f"分时数据缓存：交易时间内，设置短TTL: {ttl}秒")
                    else:
                        ttl = 3600  # 1小时，交易时间外数据相对稳定
                        logger.debug(f"分时数据缓存：交易时间外，设置长TTL: {ttl}秒")
                else:
                    ttl = 3600  # 1小时，作为通用查询缓存
            elif cache_type == CacheType.SEARCH_CACHE:
                cache_key = f"search_cache:{ticker}:{period}"
                ttl = 300  # 5分钟，搜索结果缓存
            else:
                logger.error(f"未知的缓存类型: {cache_type}")
                return None

            # 序列化DataFrame
            serialized_data = self._serialize_dataframe(data)

            # 保存到Redis
            self.redis_client.setex(
                name=cache_key,
                time=ttl,
                value=serialized_data
            )

            # 为分时数据添加更详细的日志信息
            if period == "minute":
                market_status = "交易时间内" if _is_market_open() else "交易时间外"
                logger.info(f"成功保存分时数据到Redis: {cache_key}, 行数: {len(data)}, TTL: {ttl}s ({market_status})")
            else:
                logger.info(f"成功保存数据到Redis: {cache_key}, 行数: {len(data)}, TTL: {ttl}s")
            return cache_key
            
        except RedisSerializationError:
            # 序列化错误已经在上层记录，这里直接返回None
            return None
        except redis.RedisError as e:
            logger.error(f"Redis操作失败: {e}")
            return None
        except Exception as e:
            logger.error(f"保存数据到Redis时发生未知错误: {e}")
            return None

    def get_data_from_redis(self, ticker: str, period: str, cache_type: CacheType) -> Optional[pd.DataFrame]:
        """
        从Redis缓存中获取单个股票数据，支持不同类型的缓存。

        Args:
            ticker: 股票代码 (例如: "AAPL")
            period: 时间周期 ("daily", "weekly", "10min", "minute")
            cache_type: 缓存类型 (CacheType.PENDING_SAVE 或 CacheType.GENERAL_CACHE)

        Returns:
            Optional[pd.DataFrame]: 如果找到数据则返回DataFrame，否则返回None。
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        try:
            # 根据缓存类型构建键名
            if cache_type == CacheType.PENDING_SAVE:
                cache_key = f"pending_save:{ticker}:{period}"
            elif cache_type == CacheType.GENERAL_CACHE:
                cache_key = f"general_cache:{ticker}:{period}"
            elif cache_type == CacheType.SEARCH_CACHE:
                cache_key = f"search_cache:{ticker}:{period}"
            else:
                logger.error(f"未知的缓存类型: {cache_type}")
                return None

            serialized_data = self.redis_client.get(cache_key)

            if serialized_data:
                logger.info(f"在Redis缓存中找到数据: {cache_key}")
                return self._deserialize_dataframe(str(serialized_data))
            else:
                logger.info(f"在Redis缓存中未找到数据: {cache_key}")
                return None

        except RedisSerializationError:
            return None
        except redis.RedisError as e:
            logger.error(f"从Redis获取数据时出错: {e}")
            return None
        except Exception as e:
            logger.error(f"从Redis获取数据时发生未知错误: {e}")
            return None

    def save_technical_analysis(self, payload: TechnicalAnalysisCacheEntry) -> Optional[str]:
        """保存技术分析结果到Redis缓存"""
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        try:
            payload_dict = dict(payload)
            payload_dict.pop('metrics', None)
            raw_ticker = payload_dict.get('ticker')
            ticker_value = str(raw_ticker or '')

            raw_market_aware_date = payload_dict.get('market_aware_date')
            if isinstance(raw_market_aware_date, date):
                market_aware_date_value: Union[str, date] = raw_market_aware_date
            else:
                market_aware_date_value = str(raw_market_aware_date or '')

            normalized_payload: TechnicalAnalysisCacheEntry = TechnicalAnalysisCacheEntry(
                ticker=self._normalize_ticker(ticker_value),
                market_aware_date=self._normalize_market_aware_date(market_aware_date_value),
                analysis_text=str(payload_dict.get('analysis_text', '')),
                generated_at=str(payload_dict.get('generated_at') or datetime.now(timezone.utc).isoformat()),
                agent_version=str(payload_dict.get('agent_version', 'unknown')),
            )

            if not normalized_payload['ticker'] or not normalized_payload['market_aware_date']:
                logger.warning("技术分析缓存缺少必要字段，放弃缓存")
                return None

            cache_key = self._build_technical_analysis_key(
                normalized_payload['ticker'],
                normalized_payload['market_aware_date']
            )
            ttl = _calculate_market_aware_ttl()
            serialized_value = self._serialize_technical_analysis(normalized_payload)

            self.redis_client.setex(name=cache_key, time=ttl, value=serialized_value)
            logger.info(
                "技术分析结果已写入缓存: %s, TTL=%s秒, 模型=%s",
                cache_key,
                ttl,
                normalized_payload['agent_version']
            )
            return cache_key

        except RedisSerializationError:
            return None
        except redis.RedisError as e:
            logger.error(f"写入技术分析缓存失败: {e}")
            return None
        except Exception as e:
            logger.error(f"写入技术分析缓存发生未知错误: {e}")
            return None

    def get_technical_analysis(self, ticker: str, market_aware_date: Union[str, date]) -> Optional[TechnicalAnalysisCacheEntry]:
        """读取技术分析结果缓存"""
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        cache_key = self._build_technical_analysis_key(ticker, market_aware_date)
        try:
            cached_value = self.redis_client.get(cache_key)
            if not cached_value:
                logger.info(f"技术分析缓存未命中: {cache_key}")
                return None

            entry = self._deserialize_technical_analysis(str(cached_value))
            logger.info(
                "技术分析缓存命中: %s, 生成时间=%s",
                cache_key,
                self._format_generated_at(entry.get('generated_at'))
            )
            return entry

        except RedisSerializationError:
            try:
                self.redis_client.delete(cache_key)
            except Exception:
                pass
            logger.warning(f"技术分析缓存内容损坏，已清理键: {cache_key}")
            return None
        except redis.RedisError as e:
            logger.error(f"读取技术分析缓存失败: {e}")
            return None
        except Exception as e:
            logger.error(f"读取技术分析缓存发生未知错误: {e}")
            return None

    def save_structured_prediction_pending(self, payload: StructuredPredictionPendingEntry) -> Optional[str]:
        """保存结构化预测待持久化数据到Redis"""
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        try:
            ticker = self._normalize_ticker(payload.get("ticker", ""))
            market_date_raw = payload.get("market_aware_date")
            target_date_raw = payload.get("target_date")

            if not ticker or not market_date_raw or not target_date_raw:
                logger.warning("结构化预测待持久化数据缺少必要字段，放弃写入")
                return None

            pending_key = self._build_prediction_pending_key(ticker, market_date_raw, target_date_raw)

            normalized_payload: StructuredPredictionPendingEntry = StructuredPredictionPendingEntry(
                ticker=ticker,
                market_aware_date=self._normalize_iso_date(market_date_raw),
                target_date=self._normalize_iso_date(target_date_raw),
                trading_days_count=int(payload.get("trading_days_count", 0)),
                prediction_probability=payload.get("prediction_probability"),
                direction=str(payload.get("direction", "")).upper(),
                confidence_level=str(payload.get("confidence_level", "")).upper(),
                reasoning=payload.get("reasoning"),
                prediction_timestamp=str(payload.get("prediction_timestamp") or datetime.now(timezone.utc).isoformat()),
                enqueued_at=str(payload.get("enqueued_at") or datetime.now(timezone.utc).isoformat()),
            )

            serialized_value = json.dumps(normalized_payload, ensure_ascii=False, default=str)
            previous_exists = bool(self.redis_client.exists(pending_key))

            self.redis_client.setex(
                name=pending_key,
                time=PREDICTION_PENDING_TTL_SECONDS,
                value=serialized_value,
            )

            logger.info(
                "结构化预测待持久化已写入Redis: %s (覆盖=%s)",
                pending_key,
                previous_exists,
            )
            return pending_key

        except redis.RedisError as e:
            logger.error(f"写入结构化预测待持久化失败: {e}")
            return None
        except Exception as e:
            logger.error(f"保存结构化预测待持久化发生未知错误: {e}")
            return None

    def get_structured_prediction_pending(self) -> List[Tuple[str, StructuredPredictionPendingEntry]]:
        """获取全部结构化预测待持久化数据"""
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return []

        try:
            pattern = "prediction:pending:*"
            keys_result = self.redis_client.keys(pattern)
            pending_keys = keys_result if isinstance(keys_result, list) else list(keys_result) if keys_result else []  # type: ignore

            if not pending_keys:
                logger.debug("未发现结构化预测待持久化数据")
                return []

            results: List[Tuple[str, StructuredPredictionPendingEntry]] = []
            broken_keys: List[str] = []

            for key in pending_keys:
                try:
                    serialized = self.redis_client.get(key)
                    if serialized is None:
                        logger.debug("结构化预测待持久化键已过期: %s", key)
                        continue
                    payload = self._deserialize_prediction_pending(str(serialized))
                    results.append((key, payload))
                except RedisSerializationError as e:
                    logger.error("结构化预测待持久化数据解析失败 %s: %s", key, e)
                    broken_keys.append(key)
                except Exception as e:
                    logger.error("处理结构化预测待持久化键时发生错误 %s: %s", key, e)
                    broken_keys.append(key)

            if broken_keys:
                try:
                    self.redis_client.delete(*broken_keys)
                    logger.info("清理了 %d 个损坏的结构化预测待持久化键", len(broken_keys))
                except Exception as cleanup_error:
                    logger.error("清理损坏的结构化预测待持久化键失败: %s", cleanup_error)

            return results

        except redis.RedisError as e:
            logger.error(f"扫描结构化预测待持久化数据失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取结构化预测待持久化数据时发生未知错误: {e}")
            return []

    def delete_structured_prediction_pending(self, key: str) -> bool:
        """删除指定的结构化预测待持久化键"""
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return False

        try:
            result = self.redis_client.delete(key)
            if result:
                logger.info("已移除结构化预测待持久化键: %s", key)
                return True
            logger.warning("尝试删除不存在的结构化预测待持久化键: %s", key)
            return False
        except redis.RedisError as e:
            logger.error(f"删除结构化预测待持久化键失败 {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"删除结构化预测待持久化键发生未知错误 {key}: {e}")
            return False
    
    def get_pending_data_keys(self) -> List[str]:
        """
        扫描并返回所有待持久化数据的键。
        
        Returns:
            List[str]: 待处理数据键的列表。
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return []
        
        try:
            patterns = ["pending_save:*", "prediction:pending:*"]
            all_keys: List[str] = []
            for pattern in patterns:
                keys_result = self.redis_client.keys(pattern)
                if isinstance(keys_result, list):
                    all_keys.extend(keys_result)
                elif keys_result:
                    all_keys.extend(list(keys_result))  # type: ignore

            if not all_keys:
                return []

            # 去重并按照字典序排序，方便日志和调度
            unique_keys = sorted(set(all_keys))
            return unique_keys
        except redis.RedisError as e:
            logger.error(f"扫描Redis键时出错: {e}")
            return []

    def get_pending_data_from_redis(self) -> List[Tuple[str, str, pd.DataFrame]]:
        """
        扫描并获取所有待持久化的股票数据
        
        Returns:
            List[Tuple[str, str, pd.DataFrame]]:
            每个元组包含 (ticker, period, dataframe)
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return []
        
        try:
            # 扫描所有pending_save开头的键
            pattern = "pending_save:*"
            keys_result = self.redis_client.keys(pattern)
            pending_keys = keys_result if isinstance(keys_result, list) else list(keys_result) if keys_result else []  # type: ignore
            
            if not pending_keys:
                logger.info("Redis中没有待持久化的数据")
                return []
            
            logger.info(f"发现 {len(pending_keys)} 个待持久化的数据条目")
            
            pending_data = []
            failed_keys = []
            
            for key in pending_keys:
                try:
                    # 解析键名获取ticker和period
                    # 格式: pending_save:{ticker}:{period}
                    key_parts = key.split(':')
                    if len(key_parts) != 3:
                        logger.warning(f"无效的键名格式: {key}")
                        failed_keys.append(key)
                        continue
                    
                    ticker = key_parts[1]
                    period = key_parts[2]
                    
                    # 获取数据
                    serialized_data = self.redis_client.get(key)
                    if serialized_data is None:
                        logger.warning(f"键 {key} 对应的数据不存在或已过期")
                        continue
                    
                    # 反序列化数据
                    dataframe = self._deserialize_dataframe(str(serialized_data))
                    
                    pending_data.append((ticker, period, dataframe))
                    logger.info(f"成功获取待持久化数据: {ticker}_{period}, 行数: {len(dataframe)}")
                    
                except RedisSerializationError as e:
                    logger.error(f"反序列化数据失败 {key}: {e}")
                    failed_keys.append(key)
                    continue
                except Exception as e:
                    logger.error(f"处理键 {key} 时发生错误: {e}")
                    failed_keys.append(key)
                    continue
            
            # 清理失败的键
            if failed_keys:
                try:
                    self.redis_client.delete(*failed_keys)
                    logger.info(f"清理了 {len(failed_keys)} 个无效的缓存键")
                except Exception as e:
                    logger.error(f"清理无效键时发生错误: {e}")
            
            return pending_data
            
        except redis.RedisError as e:
            logger.error(f"Redis操作失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取待持久化数据时发生未知错误: {e}")
            return []
    
    def clear_saved_data(self, ticker: str, period: str) -> bool:
        """
        清除已持久化的缓存数据
        
        Args:
            ticker: 股票代码
            period: 时间周期
            
        Returns:
            bool: 清除成功返回True
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return False
        
        try:
            cache_key = f"pending_save:{ticker}:{period}"
            result = self.redis_client.delete(cache_key)
            
            if result:
                logger.info(f"成功清除缓存数据: {cache_key}")
                return True
            else:
                logger.warning(f"缓存键不存在或已过期: {cache_key}")
                return False
                
        except redis.RedisError as e:
            logger.error(f"清除缓存数据失败: {e}")
            return False
        except Exception as e:
            logger.error(f"清除缓存数据时发生未知错误: {e}")
            return False

    def delete_from_redis(self, key: str) -> bool:
        """
        从Redis中删除指定的键。

        Args:
            key (str): 要删除的键。

        Returns:
            bool: 如果成功删除则返回True，否则返回False。
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return False
        
        try:
            result = self.redis_client.delete(key)
            if result:
                logger.info(f"成功从Redis中删除了键: {key}")
                return True
            else:
                logger.warning(f"尝试删除一个不存在的键: {key}")
                return False
        except redis.RedisError as e:
            logger.error(f"从Redis删除键 {key} 时出错: {e}")
            return False
        except Exception as e:
            logger.error(f"从Redis删除键 {key} 时发生未知错误: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Union[int, str]]:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 包含缓存统计信息的字典
        """
        if self.redis_client is None:
            return {"error": "Redis连接未建立"}
        
        try:
            patterns = ["pending_save:*", "prediction:pending:*"]
            pending_keys: List[str] = []
            for pattern in patterns:
                keys_result = self.redis_client.keys(pattern)
                if isinstance(keys_result, list):
                    pending_keys.extend(keys_result)
                elif keys_result:
                    pending_keys.extend(list(keys_result))  # type: ignore

            stats: Dict[str, Union[int, str]] = {
                "total_pending": len(pending_keys),
                "memory_usage": 0
            }
            
            # 计算内存使用情况
            for key in pending_keys:
                try:
                    memory_result = self.redis_client.memory_usage(key)
                    if memory_result and isinstance(memory_result, (int, str)):
                        memory_value = int(memory_result)  # type: ignore
                        current_usage = int(stats["memory_usage"])
                        stats["memory_usage"] = current_usage + memory_value
                except:
                    # 如果Redis版本不支持MEMORY USAGE命令，跳过
                    pass
            
            return stats
            
        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {e}")
            return {"error": str(e)}
    
    def health_check(self) -> bool:
        """
        检查Redis连接健康状态

        Returns:
            bool: 连接正常返回True
        """
        try:
            if self.redis_client is None:
                return False

            self.redis_client.ping()
            return True
        except Exception:
            return False

    def _generate_search_cache_key(self, query: str, limit: int = 10, offset: int = 0) -> str:
        """
        生成搜索缓存键

        Args:
            query: 搜索查询词
            limit: 结果限制数量
            offset: 分页偏移量

        Returns:
            str: 搜索缓存键
        """
        # 创建查询参数的哈希值
        query_params = f"{query.lower().strip()}:{limit}:{offset}"
        query_hash = hashlib.md5(query_params.encode('utf-8')).hexdigest()
        return f"search_cache:{query_hash}"

    def _serialize_search_results(self, results: List[Dict[str, Any]]) -> str:
        """
        序列化搜索结果

        Args:
            results: 搜索结果列表

        Returns:
            str: 序列化后的JSON字符串
        """
        try:
            data_dict = {
                'results': results,
                'timestamp': datetime.now().isoformat(),
                'count': len(results)
            }
            return json.dumps(data_dict, ensure_ascii=False, default=str)
        except Exception as e:
            error_msg = f"搜索结果序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    def _deserialize_search_results(self, json_str: str) -> List[Dict[str, Any]]:
        """
        反序列化搜索结果

        Args:
            json_str: 序列化的JSON字符串

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            data_dict = json.loads(json_str)
            return data_dict.get('results', [])
        except Exception as e:
            error_msg = f"搜索结果反序列化失败: {e}"
            logger.error(error_msg)
            raise RedisSerializationError(error_msg)

    def save_search_results(self, query: str, results: List[Dict[str, Any]],
                           limit: int = 10, offset: int = 0) -> Optional[str]:
        """
        保存搜索结果到缓存

        Args:
            query: 搜索查询词
            results: 搜索结果列表
            limit: 结果限制数量
            offset: 分页偏移量

        Returns:
            Optional[str]: 保存成功返回缓存键名，失败返回None
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        if not results:
            logger.warning(f"尝试保存空搜索结果: {query}")
            return None

        try:
            cache_key = self._generate_search_cache_key(query, limit, offset)
            serialized_data = self._serialize_search_results(results)

            # 设置5分钟的TTL
            self.redis_client.setex(
                name=cache_key,
                time=300,  # 5分钟
                value=serialized_data
            )

            logger.info(f"成功保存搜索结果到Redis: {cache_key}, 结果数: {len(results)}")
            return cache_key

        except RedisSerializationError:
            return None
        except redis.RedisError as e:
            logger.error(f"Redis操作失败: {e}")
            return None
        except Exception as e:
            logger.error(f"保存搜索结果时发生未知错误: {e}")
            return None

    def get_search_results(self, query: str, limit: int = 10, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
        """
        从缓存中获取搜索结果

        Args:
            query: 搜索查询词
            limit: 结果限制数量
            offset: 分页偏移量

        Returns:
            Optional[List[Dict[str, Any]]]: 搜索结果列表，未找到返回None
        """
        if self.redis_client is None:
            logger.error("Redis连接未建立")
            return None

        try:
            cache_key = self._generate_search_cache_key(query, limit, offset)
            serialized_data = self.redis_client.get(cache_key)

            if serialized_data:
                logger.info(f"在Redis缓存中找到搜索结果: {cache_key}")
                return self._deserialize_search_results(str(serialized_data))
            else:
                logger.info(f"在Redis缓存中未找到搜索结果: {cache_key}")
                return None

        except RedisSerializationError:
            return None
        except redis.RedisError as e:
            logger.error(f"从Redis获取搜索结果时出错: {e}")
            return None
        except Exception as e:
            logger.error(f"从Redis获取搜索结果时发生未知错误: {e}")
            return None


# --- Lazy Loading Singleton Pattern ---
_cache_manager_instance: Optional[CacheManager] = None
_lock = threading.Lock()

def get_cache_manager() -> CacheManager:
    """
    获取CacheManager的单例实例（线程安全）。
    仅在第一次调用时创建实例。
    """
    global _cache_manager_instance
    if _cache_manager_instance is None:
        with _lock:
            if _cache_manager_instance is None:
                _cache_manager_instance = CacheManager()
    return _cache_manager_instance

# 导出主要函数供其他模块使用
def save_to_redis(ticker: str, period: str, data: pd.DataFrame, cache_type: CacheType) -> Optional[str]:
    """保存数据到Redis缓存"""
    return get_cache_manager().save_to_redis(ticker, period, data, cache_type)

def get_pending_data_keys() -> List[str]:
    """获取所有待持久化数据的键"""
    return get_cache_manager().get_pending_data_keys()

def get_pending_data_from_redis() -> List[Tuple[str, str, pd.DataFrame]]:
    """获取所有待持久化的数据"""
    return get_cache_manager().get_pending_data_from_redis()

def clear_saved_data(ticker: str, period: str) -> bool:
    """清除已保存的缓存数据"""
    return get_cache_manager().clear_saved_data(ticker, period)

def get_cache_stats() -> Dict[str, Union[int, str]]:
    """获取缓存统计信息"""
    return get_cache_manager().get_cache_stats()

def health_check() -> bool:
    """检查Redis连接健康状态"""
    return get_cache_manager().health_check()

def get_from_redis(ticker: str, period: str, cache_type: CacheType) -> Optional[pd.DataFrame]:
    """从Redis缓存中获取单个股票数据"""
    return get_cache_manager().get_data_from_redis(ticker, period, cache_type)

def delete_from_redis(key: str) -> bool:
    """从Redis中删除指定的键"""
    return get_cache_manager().delete_from_redis(key)

def save_technical_analysis_cache(payload: TechnicalAnalysisCacheEntry) -> Optional[str]:
    """保存技术分析缓存（便捷方法）"""
    return get_cache_manager().save_technical_analysis(payload)

def get_technical_analysis_cache(ticker: str, market_aware_date: Union[str, date]) -> Optional[TechnicalAnalysisCacheEntry]:
    """获取技术分析缓存（便捷方法）"""
    return get_cache_manager().get_technical_analysis(ticker, market_aware_date)

def save_structured_prediction_pending_cache(payload: StructuredPredictionPendingEntry) -> Optional[str]:
    """保存结构化预测待持久化缓存"""
    return get_cache_manager().save_structured_prediction_pending(payload)

def get_structured_prediction_pending_cache() -> List[Tuple[str, StructuredPredictionPendingEntry]]:
    """获取结构化预测待持久化缓存"""
    return get_cache_manager().get_structured_prediction_pending()

def delete_structured_prediction_pending_cache(key: str) -> bool:
    """删除结构化预测待持久化缓存"""
    return get_cache_manager().delete_structured_prediction_pending(key)

def save_search_results(query: str, results: List[Dict[str, Any]],
                       limit: int = 10, offset: int = 0) -> Optional[str]:
    """保存搜索结果到缓存"""
    return get_cache_manager().save_search_results(query, results, limit, offset)

def get_search_results(query: str, limit: int = 10, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
    """从缓存中获取搜索结果"""
    return get_cache_manager().get_search_results(query, limit, offset)
