"""
时区管理模块

统一管理应用中的时区设置，支持从环境变量读取时区配置，
并为数据库模型的created_at和updated_at字段提供统一的时区支持。
"""

import os
import pytz
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class TimezoneManager:
    """
    时区管理器
    
    负责从环境变量读取时区配置，并提供统一的时区处理方法。
    """
    
    def __init__(self):
        self._timezone = None
        self._load_timezone_from_env()
    
    def _load_timezone_from_env(self):
        """从环境变量加载时区配置"""
        tz_env = os.getenv('TZ', 'Etc/UTC')
        
        try:
            # 尝试使用zoneinfo (Python 3.9+推荐)
            self._timezone = ZoneInfo(tz_env)
        except Exception:
            try:
                # 降级到pytz
                self._timezone = pytz.timezone(tz_env)
            except Exception:
                # 最后降级到UTC
                self._timezone = ZoneInfo('UTC')
                print(f"警告: 无法解析时区 '{tz_env}'，使用UTC作为默认时区")
    
    @property
    def timezone(self):
        """获取当前时区对象"""
        return self._timezone
    
    def now(self) -> datetime:
        """
        获取当前时区的当前时间
        
        Returns:
            datetime: 带时区信息的当前时间
        """
        return datetime.now(self._timezone)
    
    def get_tz_name(self) -> str:
        """
        获取时区名称
        
        Returns:
            str: 时区名称
        """
        if self._timezone is None:
            return "UTC"
        
        # 尝试获取时区名称，使用 try-except 避免属性访问错误
        try:
            # ZoneInfo 对象使用 key 属性
            if hasattr(self._timezone, 'key'):
                key_val = getattr(self._timezone, 'key', None)
                if key_val:
                    return str(key_val)
        except (AttributeError, TypeError):
            pass
        
        try:
            # pytz 对象使用 zone 属性
            if hasattr(self._timezone, 'zone'):
                zone_val = getattr(self._timezone, 'zone', None)
                if zone_val:
                    return str(zone_val)
        except (AttributeError, TypeError):
            pass
        
        # 最后的后备方案
        return str(self._timezone)


# 全局时区管理器实例
timezone_manager = TimezoneManager()


def get_current_timezone():
    """
    获取当前应用时区
    
    Returns:
        时区对象
    """
    return timezone_manager.timezone


def get_current_time() -> datetime:
    """
    获取当前时区的当前时间
    
    返回符合.env中TZ设置的当前时间，用于数据库时间戳字段。
    
    Returns:
        datetime: 带时区信息的当前时间
    """
    return timezone_manager.now()


def get_timezone_name() -> str:
    """
    获取当前时区名称
    
    Returns:
        str: 时区名称
    """
    return timezone_manager.get_tz_name()


__all__ = [
    'TimezoneManager',
    'timezone_manager', 
    'get_current_timezone',
    'get_current_time',
    'get_timezone_name'
]