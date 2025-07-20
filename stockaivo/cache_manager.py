"""
Redis缓存管理器模块
负责处理从AKShare获取的股票数据的临时缓存，在用户空闲时批量持久化到PostgreSQL
"""

import json
import logging
import pandas as pd
import redis
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime
import os
import threading
import hashlib
from dotenv import load_dotenv
from enum import Enum, auto


class CacheType(Enum):
    """缓存类型的枚举"""
    PENDING_SAVE = auto()  # 表示数据等待被持久化
    GENERAL_CACHE = auto()  # 表示通用的查询结果缓存
    SEARCH_CACHE = auto()  # 表示搜索结果缓存

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RedisConnectionError(Exception):
    """Redis连接异常"""
    pass

class RedisSerializationError(Exception):
    """Redis序列化异常"""
    pass

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
    
    def save_to_redis(self, ticker: str, period: str, data: pd.DataFrame, cache_type: CacheType) -> Optional[str]:
        """
        将股票数据保存到Redis缓存，支持不同类型的缓存。

        Args:
            ticker: 股票代码 (例如: "AAPL")
            period: 时间周期 ("daily", "weekly", "hourly")
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
            period: 时间周期 ("daily", "weekly", "hourly")
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
            pattern = "pending_save:*"
            keys_result = self.redis_client.keys(pattern)
            return keys_result if isinstance(keys_result, list) else list(keys_result) if keys_result else [] # type: ignore
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
            pattern = "pending_save:*"
            keys_result = self.redis_client.keys(pattern)
            pending_keys = keys_result if isinstance(keys_result, list) else list(keys_result) if keys_result else []  # type: ignore
            
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

def save_search_results(query: str, results: List[Dict[str, Any]],
                       limit: int = 10, offset: int = 0) -> Optional[str]:
    """保存搜索结果到缓存"""
    return get_cache_manager().save_search_results(query, results, limit, offset)

def get_search_results(query: str, limit: int = 10, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
    """从缓存中获取搜索结果"""
    return get_cache_manager().get_search_results(query, limit, offset)