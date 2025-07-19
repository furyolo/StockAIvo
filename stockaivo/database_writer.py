"""
数据库写入器模块
负责将Redis缓存中的待处理数据批量写入PostgreSQL数据库
"""

import logging
import pandas as pd
from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime, date, timezone

from . import database
from .models import StockPriceDaily, StockPriceWeekly, StockPriceHourly
from .cache_manager import get_pending_data_from_redis, clear_saved_data, delete_from_redis

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseWriter:
    """数据库写入管理器"""
    
    def __init__(self):
        """初始化数据库写入器"""
        pass
    

    
    def _prepare_daily_price_data(self, ticker: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备日K线数据
        
        Args:
            ticker: 股票代码
            df: 股票价格数据DataFrame
            
        Returns:
            List[Dict]: 日K线数据字典列表
        """
        daily_data = []
        
        for _, row in df.iterrows():
            try:
                # 处理日期字段
                trade_date = row.get('date', row.get('日期'))
                if isinstance(trade_date, str):
                    trade_date = pd.to_datetime(trade_date).date()
                elif isinstance(trade_date, pd.Timestamp):
                    trade_date = trade_date.date()
                elif not isinstance(trade_date, date):
                    logger.warning(f"无效的日期格式: {trade_date}")
                    continue
                
                # 准备价格数据
                price_data = {
                    'ticker': ticker,
                    'date': trade_date,
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': int(row.get('volume', 0)),
                    'turnover': float(row.get('turnover', 0.0)),
                    'amplitude': float(row.get('amplitude', 0.0)),
                    'price_change_percent': float(row.get('price_change_percent', 0.0)),
                    'price_change': float(row.get('price_change', 0.0)),
                    'turnover_rate': float(row.get('turnover_rate', 0.0)),
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
                
                daily_data.append(price_data)
                
            except Exception as e:
                logger.error(f"处理日K线数据行时出错: {e}, 行数据: {row.to_dict()}")
                continue
        
        return daily_data
    
    def _prepare_weekly_price_data(self, ticker: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备周K线数据
        
        Args:
            ticker: 股票代码
            df: 股票价格数据DataFrame
            
        Returns:
            List[Dict]: 周K线数据字典列表
        """
        weekly_data = []
        
        for _, row in df.iterrows():
            try:
                # 处理周开始日期字段
                trade_date = row.get('date', row.get('日期'))
                if isinstance(trade_date, str):
                    trade_date = pd.to_datetime(trade_date).date()
                elif isinstance(trade_date, pd.Timestamp):
                    trade_date = trade_date.date()
                elif isinstance(trade_date, date):
                    pass # trade_date is already a date object
                else:
                    logger.warning(f"无效的日期格式: {trade_date}")
                    continue
                
                # 对于周K线，我们使用该日期作为周开始日期
                # 实际应用中可能需要计算真正的周一日期
                
                price_data = {
                    'ticker': ticker,
                    'date': trade_date,
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': int(row.get('volume', 0)),
                    'turnover': float(row.get('turnover', 0.0)),
                    'amplitude': float(row.get('amplitude', 0.0)),
                    'price_change_percent': float(row.get('price_change_percent', 0.0)),
                    'price_change': float(row.get('price_change', 0.0)),
                    'turnover_rate': float(row.get('turnover_rate', 0.0)),
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
                
                weekly_data.append(price_data)
                
            except Exception as e:
                logger.error(f"处理周K线数据行时出错: {e}, 行数据: {row.to_dict()}")
                continue
        
        return weekly_data
    
    def _prepare_hourly_price_data(self, ticker: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备小时K线数据
        
        Args:
            ticker: 股票代码
            df: 股票价格数据DataFrame
            
        Returns:
            List[Dict]: 小时K线数据字典列表
        """
        hourly_data = []
        
        for _, row in df.iterrows():
            try:
                # 处理时间戳字段
                timestamp = row.get('date', row.get('日期'))
                if isinstance(timestamp, str):
                    hour_timestamp = pd.to_datetime(timestamp)
                elif isinstance(timestamp, pd.Timestamp):
                    hour_timestamp = timestamp
                elif isinstance(timestamp, date):
                    # 如果只有日期，设置为当日9:30（美股开盘时间）
                    hour_timestamp = datetime.combine(timestamp, datetime.min.time().replace(hour=9, minute=30))
                else:
                    logger.warning(f"无效的时间戳格式: {timestamp}")
                    continue
                
                price_data = {
                    'ticker': ticker,
                    'hour_timestamp': hour_timestamp,
                    'open': float(row.get('open', row.get('开盘', 0))),
                    'high': float(row.get('high', row.get('最高', 0))),
                    'low': float(row.get('low', row.get('最低', 0))),
                    'close': float(row.get('close', row.get('收盘', 0))),
                    'volume': int(row.get('volume', row.get('成交量', 0))),
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
                
                hourly_data.append(price_data)
                
            except Exception as e:
                logger.error(f"处理小时K线数据行时出错: {e}, 行数据: {row.to_dict()}")
                continue
        
        return hourly_data
    

    
    def _batch_upsert_prices(self, db: Session, table_class, price_data: List[Dict[str, Any]], 
                           conflict_columns: List[str]) -> int:
        """
        批量插入或更新价格数据
        
        Args:
            db: 数据库会话
            table_class: 价格表模型类
            price_data: 价格数据列表
            conflict_columns: 冲突检测列
            
        Returns:
            int: 成功处理的记录数
        """
        if not price_data:
            return 0
        
        try:
            # 使用PostgreSQL的批量UPSERT
            stmt = insert(table_class).values(price_data)
            update_dict = {
                'open': stmt.excluded.open,
                'high': stmt.excluded.high,
                'low': stmt.excluded.low,
                'close': stmt.excluded.close,
                'volume': stmt.excluded.volume,
                'turnover': stmt.excluded.turnover,
                'amplitude': stmt.excluded.amplitude,
                'price_change_percent': stmt.excluded.price_change_percent,
                'price_change': stmt.excluded.price_change,
                'turnover_rate': stmt.excluded.turnover_rate,
                'updated_at': datetime.now(timezone.utc)
            }
            
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_columns,
                set_=update_dict
            )
            
            db.execute(stmt)
            
            logger.info(f"成功批量处理 {len(price_data)} 条 {table_class.__tablename__} 数据")
            return len(price_data)
            
        except Exception as e:
            logger.error(f"批量处理 {table_class.__tablename__} 数据失败: {e}")
            return 0
    
    def persist_pending_data(self, db: Session) -> Dict[str, Any]:
        """
        持久化待处理数据的核心函数
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict: 包含处理结果的字典
        """
        result = {
            'success': True,
            'processed_count': 0,
            'failed_count': 0,
            'details': [],
            'errors': []
        }
        
        try:
            # 1. 从Redis获取待处理数据
            logger.info("开始从Redis获取待处理数据...")
            pending_data = get_pending_data_from_redis()
            
            if not pending_data:
                logger.info("Redis中没有待处理数据")
                result['message'] = "没有待处理的数据"
                return result
            
            logger.info(f"从Redis获取到 {len(pending_data)} 个待处理数据条目")
            
            # 2. 按ticker分组处理数据
            processed_keys = []
            
            for ticker, period, dataframe in pending_data:
                try:
                    # 开始事务处理这个数据条目
                    with db.begin():
                        # 根据period类型处理价格数据
                        processed_rows = 0
                        
                        if period == 'daily':
                            daily_data = self._prepare_daily_price_data(ticker, dataframe)
                            processed_rows = self._batch_upsert_prices(
                                db, StockPriceDaily, daily_data, ['ticker', 'date']
                            )
                            
                        elif period == 'weekly':
                            weekly_data = self._prepare_weekly_price_data(ticker, dataframe)
                            processed_rows = self._batch_upsert_prices(
                                db, StockPriceWeekly, weekly_data, ['ticker', 'date']
                            )
                            
                        elif period == 'hourly':
                            hourly_data = self._prepare_hourly_price_data(ticker, dataframe)
                            processed_rows = self._batch_upsert_prices(
                                db, StockPriceHourly, hourly_data, ['ticker', 'hour_timestamp']
                            )
                        
                        else:
                            raise Exception(f"不支持的period类型: {period}")
                        
                        # 2.3 记录处理结果
                        result['processed_count'] += processed_rows
                        result['details'].append({
                            'ticker': ticker,
                            'period': period,
                            'rows_processed': processed_rows,
                            'status': 'success'
                        })
                        
                        # 标记这个键可以从Redis中删除
                        processed_keys.append((ticker, period))
                        
                        logger.info(f"成功处理数据: {ticker}_{period}, 处理行数: {processed_rows}")
                
                except Exception as e:
                    logger.error(f"处理数据失败 {ticker}_{period}: {e}")
                    result['failed_count'] += 1
                    result['errors'].append({
                        'ticker': ticker,
                        'period': period,
                        'error': str(e)
                    })
                    # 发生错误时回滚当前事务
                    db.rollback()
                    continue
            
            # 3. 提交所有成功的操作
            db.commit()

            # 4. 在事务成功后，清除已处理的Redis数据
            cleared_count = 0
            for ticker, period in processed_keys:
                try:
                    if clear_saved_data(ticker, period):
                        cleared_count += 1
                except Exception as e:
                    logger.error(f"清除Redis数据失败 {ticker}_{period}: {e}")
            
            logger.info(f"清除了 {cleared_count} 个Redis缓存条目")
            
            result['message'] = f"成功处理 {result['processed_count']} 条记录，失败 {result['failed_count']} 条"
            logger.info(result['message'])
            
        except Exception as e:
            logger.error(f"持久化数据过程中发生严重错误: {e}")
            db.rollback()
            result['success'] = False
            result['message'] = f"持久化过程失败: {str(e)}"
            result['errors'].append({'general_error': str(e)})
        
        return result

    def save_dataframe_to_db(self, ticker: str, period: str, dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
        """
        将单个DataFrame直接持久化到数据库。
        此函数独立管理自己的数据库会话，并在成功后可选地删除一个Redis缓存键。

        Args:
            ticker: 股票代码
            period: 时间周期
            dataframe: 待保存的数据
            pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键。

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            with database.SessionLocal() as db:
                with db.begin():
                    # 根据period类型处理价格数据
                    processed_rows = 0
                    if period == 'daily':
                        daily_data = self._prepare_daily_price_data(ticker, dataframe)
                        processed_rows = self._batch_upsert_prices(
                            db, StockPriceDaily, daily_data, ['ticker', 'date']
                        )
                    elif period == 'weekly':
                        weekly_data = self._prepare_weekly_price_data(ticker, dataframe)
                        processed_rows = self._batch_upsert_prices(
                            db, StockPriceWeekly, weekly_data, ['ticker', 'date']
                        )
                    elif period == 'hourly':
                        hourly_data = self._prepare_hourly_price_data(ticker, dataframe)
                        processed_rows = self._batch_upsert_prices(
                            db, StockPriceHourly, hourly_data, ['ticker', 'hour_timestamp']
                        )
                    else:
                        raise Exception(f"不支持的period类型: {period}")

                    logger.info(f"成功将DataFrame存入数据库: {ticker}_{period}, 处理行数: {processed_rows}")
                # db.commit() is handled by `with db.begin()`
            
            # 如果提供了缓存键，并且数据库操作成功，则删除它
            if pending_cache_key:
                logger.info(f"数据库写入成功，现在删除 pending_save 缓存键: {pending_cache_key}")
                delete_from_redis(pending_cache_key)

            return True
        except Exception as e:
            logger.error(f"保存DataFrame到数据库失败 {ticker}_{period}: {e}")
            # db.rollback() is handled by the `with db.begin()` context manager on error
            return False


# 创建全局数据库写入器实例
database_writer = DatabaseWriter()

# 导出主要函数供其他模块使用
def persist_pending_data(db: Session) -> Dict[str, Any]:
    """
    持久化Redis中的待处理数据到PostgreSQL
    
    Args:
        db: 数据库会话
        
    Returns:
        Dict: 处理结果
    """
    return database_writer.persist_pending_data(db)

def save_dataframe_to_db(ticker: str, period: str, dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
    """
    将单个DataFrame直接持久化到数据库。
    """
    return database_writer.save_dataframe_to_db(ticker, period, dataframe, pending_cache_key)


# 导出主要组件
__all__ = [
    'DatabaseWriter',
    'database_writer',
    'persist_pending_data',
    'save_dataframe_to_db'
]