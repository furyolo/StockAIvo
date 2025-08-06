"""
数据库写入器模块
负责将Redis缓存中的待处理数据批量写入PostgreSQL数据库
"""

import logging
import pandas as pd
from typing import List, Tuple, Dict, Any, Optional, Type, Union
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from datetime import datetime, date, timezone

from . import database
from .models import StockPriceDaily, StockPriceWeekly, StockSymbols, UsStocksName
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
    

    def _prepare_minute_price_data(self, ticker: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备分时数据

        Args:
            ticker: 股票代码
            df: 股票价格数据DataFrame

        Returns:
            List[Dict]: 分时数据字典列表
        """
        minute_data = []

        for _, row in df.iterrows():
            try:
                # 处理分时时间戳字段
                timestamp = row.get('minute_timestamp', row.get('时间'))
                if isinstance(timestamp, str):
                    minute_timestamp = pd.to_datetime(timestamp)
                elif isinstance(timestamp, pd.Timestamp):
                    minute_timestamp = timestamp
                elif isinstance(timestamp, datetime):
                    minute_timestamp = pd.Timestamp(timestamp)
                else:
                    logger.warning(f"无效的分时时间戳格式: {timestamp}")
                    continue

                # 准备分时价格数据
                price_data = {
                    'ticker': ticker,
                    'minute_timestamp': minute_timestamp,
                    'open': float(row.get('open', row.get('开盘', 0))),
                    'high': float(row.get('high', row.get('最高', 0))),
                    'low': float(row.get('low', row.get('最低', 0))),
                    'close': float(row.get('close', row.get('收盘', 0))),
                    'volume': int(row.get('volume', row.get('成交量', 0))),
                    'turnover': int(row.get('turnover', row.get('成交额', 0))),
                    'latest_price': float(row.get('latest_price', row.get('最新价', 0))),
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }

                minute_data.append(price_data)

            except Exception as e:
                logger.error(f"处理分时数据行时出错: {e}, 行数据: {row.to_dict()}")
                continue

        return minute_data

    def _prepare_realtime_quote_data(self, dataframe: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备实时行情数据用于stock_symbols表更新

        Args:
            dataframe: 实时行情数据DataFrame

        Returns:
            List[Dict]: 实时行情数据字典列表
        """
        quote_data = []
        current_time = datetime.now(timezone.utc)

        # 定义期望的字段列表，确保字段顺序和名称的一致性
        expected_fields = [
            'fullsymbol', 'symbol', 'name', 'price', 'price_change',
            'price_change_percent', 'open', 'high', 'low', 'pre_close',
            'market_value', 'pe_ratio', 'volume', 'turnover', 'amplitude',
            'turnover_rate', 'created_at', 'updated_at'
        ]

        logger.info(f"开始处理实时行情数据，原始记录数: {len(dataframe)}")
        logger.debug(f"DataFrame列名: {list(dataframe.columns)}")

        for idx, row in dataframe.iterrows():
            try:
                # 验证必需字段
                fullsymbol = row.get('fullsymbol')
                symbol = row.get('symbol')
                name = row.get('name')

                if pd.isna(fullsymbol) or pd.isna(symbol) or pd.isna(name):
                    logger.warning(f"跳过第{idx}行，缺少必需字段: fullsymbol={fullsymbol}, symbol={symbol}, name={name}")
                    continue

                if not str(fullsymbol).strip() or not str(symbol).strip() or not str(name).strip():
                    logger.warning(f"跳过第{idx}行，必需字段为空: fullsymbol='{fullsymbol}', symbol='{symbol}', name='{name}'")
                    continue

                # 构建记录字典，严格按照期望字段顺序
                quote_record = {}

                # 基础字段
                quote_record['fullsymbol'] = str(fullsymbol).strip()
                quote_record['symbol'] = str(symbol).strip()
                quote_record['name'] = str(name).strip()

                # 价格字段
                quote_record['price'] = self._safe_convert_to_decimal(row.get('price'))
                quote_record['price_change'] = self._safe_convert_to_decimal(row.get('price_change'))
                quote_record['price_change_percent'] = self._safe_convert_to_decimal(row.get('price_change_percent'))
                quote_record['open'] = self._safe_convert_to_decimal(row.get('open'))
                quote_record['high'] = self._safe_convert_to_decimal(row.get('high'))
                quote_record['low'] = self._safe_convert_to_decimal(row.get('low'))
                quote_record['pre_close'] = self._safe_convert_to_decimal(row.get('pre_close'))

                # 市场数据字段
                quote_record['market_value'] = self._safe_convert_to_bigint(row.get('market_value'))
                quote_record['pe_ratio'] = self._safe_convert_to_decimal(row.get('pe_ratio'))
                quote_record['volume'] = self._safe_convert_to_bigint(row.get('volume'))
                quote_record['turnover'] = self._safe_convert_to_bigint(row.get('turnover'))
                quote_record['amplitude'] = self._safe_convert_to_decimal(row.get('amplitude'))
                quote_record['turnover_rate'] = self._safe_convert_to_decimal(row.get('turnover_rate'))

                # 时间戳字段
                quote_record['created_at'] = current_time
                quote_record['updated_at'] = current_time

                # 验证记录字段完整性
                if len(quote_record) != len(expected_fields):
                    logger.error(f"记录字段数量不匹配: 期望{len(expected_fields)}个，实际{len(quote_record)}个")
                    continue

                # 验证字段名是否匹配
                if set(quote_record.keys()) != set(expected_fields):
                    logger.error(f"记录字段名不匹配: 期望{expected_fields}, 实际{list(quote_record.keys())}")
                    continue

                quote_data.append(quote_record)

            except Exception as e:
                logger.warning(f"处理第{idx}行实时行情记录时出错: {e}, 跳过该记录")
                continue

        logger.info(f"准备实时行情数据完成，有效记录数: {len(quote_data)}")
        return quote_data

    def _prepare_us_stock_name_data(self, dataframe: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        准备美股名称数据用于us_stocks_name表更新

        Args:
            dataframe: 美股名称数据DataFrame

        Returns:
            List[Dict]: 美股名称数据字典列表
        """
        name_data = []
        current_time = datetime.now(timezone.utc)

        # 定义期望的字段列表
        expected_fields = [
            'symbol', 'name', 'cname', 'created_at', 'updated_at'
        ]

        logger.info(f"开始处理美股名称数据，原始记录数: {len(dataframe)}")
        logger.debug(f"DataFrame列名: {list(dataframe.columns)}")

        for idx, row in dataframe.iterrows():
            try:
                # 验证必需字段
                symbol = row.get('symbol')
                name = row.get('name')

                if pd.isna(symbol) or pd.isna(name):
                    logger.warning(f"跳过第{idx}行，缺少必需字段: symbol={symbol}, name={name}")
                    continue

                if not str(symbol).strip() or not str(name).strip():
                    logger.warning(f"跳过第{idx}行，必需字段为空: symbol='{symbol}', name='{name}'")
                    continue

                # 构建记录字典
                name_record = {
                    'symbol': str(symbol).strip(),
                    'name': str(name).strip(),
                    'cname': str(row.get('cname', '')).strip() if pd.notna(row.get('cname')) else None,
                    'created_at': current_time,
                    'updated_at': current_time
                }

                # 验证记录字段完整性
                if len(name_record) != len(expected_fields):
                    logger.error(f"记录字段数量不匹配: 期望{len(expected_fields)}个，实际{len(name_record)}个")
                    continue

                name_data.append(name_record)

            except Exception as e:
                logger.warning(f"处理第{idx}行美股名称记录时出错: {e}, 跳过该记录")
                continue

        logger.info(f"准备美股名称数据完成，有效记录数: {len(name_data)}")
        return name_data

    def _safe_convert_to_decimal(self, value) -> Optional[float]:
        """安全转换为decimal类型"""
        if pd.isna(value) or value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_convert_to_bigint(self, value) -> Optional[int]:
        """安全转换为bigint类型"""
        if pd.isna(value) or value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _batch_upsert_prices(self, db: Session, table_class: Type[Union[StockPriceDaily, StockPriceWeekly]], price_data: List[Dict[str, Any]],
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

            # 基础更新字段（所有表都有）
            update_dict = {
                'open': stmt.excluded.open,
                'high': stmt.excluded.high,
                'low': stmt.excluded.low,
                'close': stmt.excluded.close,
                'volume': stmt.excluded.volume,
                'updated_at': datetime.now(timezone.utc)
            }

            # 根据表类型添加特定字段
            if hasattr(table_class, 'turnover'):
                update_dict['turnover'] = stmt.excluded.turnover
            if hasattr(table_class, 'latest_price'):
                update_dict['latest_price'] = stmt.excluded.latest_price
            if hasattr(table_class, 'amplitude'):
                update_dict['amplitude'] = stmt.excluded.amplitude
            if hasattr(table_class, 'price_change_percent'):
                update_dict['price_change_percent'] = stmt.excluded.price_change_percent
            if hasattr(table_class, 'price_change'):
                update_dict['price_change'] = stmt.excluded.price_change
            if hasattr(table_class, 'turnover_rate'):
                update_dict['turnover_rate'] = stmt.excluded.turnover_rate
            
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

    def _batch_upsert_realtime_quotes(self, db: Session, quote_data: List[Dict[str, Any]]) -> int:
        """
        批量插入或更新实时行情数据到stock_symbols表

        Args:
            db: 数据库会话
            quote_data: 实时行情数据列表

        Returns:
            int: 成功处理的记录数
        """
        if not quote_data:
            logger.warning("没有实时行情数据需要处理")
            return 0

        try:
            logger.info(f"开始批量处理实时行情数据，原始记录数: {len(quote_data)}")

            # 数据验证和清理
            valid_data = []
            for idx, item in enumerate(quote_data):
                try:
                    # 验证必需字段
                    fullsymbol = item.get('fullsymbol')
                    if not fullsymbol or not str(fullsymbol).strip():
                        logger.warning(f"跳过第{idx}条记录：fullsymbol为空")
                        continue

                    # 验证数据结构
                    expected_keys = {
                        'fullsymbol', 'symbol', 'name', 'price', 'price_change',
                        'price_change_percent', 'open', 'high', 'low', 'pre_close',
                        'market_value', 'pe_ratio', 'volume', 'turnover', 'amplitude',
                        'turnover_rate', 'created_at', 'updated_at'
                    }

                    item_keys = set(item.keys())
                    if item_keys != expected_keys:
                        missing_keys = expected_keys - item_keys
                        extra_keys = item_keys - expected_keys
                        logger.warning(f"跳过第{idx}条记录：字段不匹配。缺少: {missing_keys}, 多余: {extra_keys}")
                        continue

                    valid_data.append(item)

                except Exception as e:
                    logger.warning(f"验证第{idx}条记录时出错: {e}")
                    continue

            if not valid_data:
                logger.warning("没有有效的实时行情数据需要处理")
                return 0

            logger.info(f"数据验证完成，有效记录数: {len(valid_data)}")

            # 数据去重：基于fullsymbol主键
            unique_quotes: Dict[str, Dict[str, Any]] = {}
            for item in valid_data:
                fullsymbol = item['fullsymbol']
                # 保留最新的记录（基于updated_at）
                if fullsymbol not in unique_quotes:
                    unique_quotes[fullsymbol] = item
                else:
                    existing_time = unique_quotes[fullsymbol]['updated_at']
                    new_time = item['updated_at']
                    if new_time > existing_time:
                        unique_quotes[fullsymbol] = item

            deduplicated_data = list(unique_quotes.values())
            if len(deduplicated_data) != len(valid_data):
                logger.info(f"数据去重完成: {len(valid_data)} 条 -> {len(deduplicated_data)} 条")

            # 分批处理，避免单次插入过多数据
            # 使用更保守的批次大小来避免PostgreSQL InternalError
            batch_size = 500  # 从1000减少到500
            total_processed = 0

            for i in range(0, len(deduplicated_data), batch_size):
                batch_data = deduplicated_data[i:i + batch_size]
                logger.info(f"处理批次 {i//batch_size + 1}: {len(batch_data)} 条记录")

                try:
                    # 使用PostgreSQL的批量UPSERT
                    stmt = insert(StockSymbols).values(batch_data)

                    # 定义更新字段（除主键和created_at外的所有字段）
                    update_dict = {
                        'symbol': stmt.excluded.symbol,
                        'name': stmt.excluded.name,
                        'price': stmt.excluded.price,
                        'price_change': stmt.excluded.price_change,
                        'price_change_percent': stmt.excluded.price_change_percent,
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'pre_close': stmt.excluded.pre_close,
                        'market_value': stmt.excluded.market_value,
                        'pe_ratio': stmt.excluded.pe_ratio,
                        'volume': stmt.excluded.volume,
                        'turnover': stmt.excluded.turnover,
                        'amplitude': stmt.excluded.amplitude,
                        'turnover_rate': stmt.excluded.turnover_rate,
                        'updated_at': stmt.excluded.updated_at
                    }

                    # 基于主键fullsymbol进行冲突处理
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['fullsymbol'],
                        set_=update_dict
                    )

                    db.execute(stmt)
                    total_processed += len(batch_data)
                    logger.info(f"批次 {i//batch_size + 1} 处理完成")

                except Exception as e:
                    error_type = type(e).__name__
                    logger.error(f"批次 {i//batch_size + 1} 处理失败: {e}")
                    logger.error(f"失败批次包含 {len(batch_data)} 条记录，从索引 {i} 到 {i + len(batch_data) - 1}")
                    logger.error(f"错误类型: {error_type}")

                    # 对于InternalError，尝试使用更小的子批次
                    if error_type == "InternalError" and len(batch_data) > 50:
                        logger.info(f"检测到InternalError，尝试将批次分解为更小的子批次...")

                        sub_batch_size = min(50, len(batch_data) // 4)  # 使用更小的子批次
                        sub_batch_success = 0

                        for j in range(0, len(batch_data), sub_batch_size):
                            sub_batch = batch_data[j:j + sub_batch_size]
                            try:
                                stmt = insert(StockSymbols).values(sub_batch)
                                update_dict = {
                                    'symbol': stmt.excluded.symbol,
                                    'name': stmt.excluded.name,
                                    'price': stmt.excluded.price,
                                    'price_change': stmt.excluded.price_change,
                                    'price_change_percent': stmt.excluded.price_change_percent,
                                    'open': stmt.excluded.open,
                                    'high': stmt.excluded.high,
                                    'low': stmt.excluded.low,
                                    'pre_close': stmt.excluded.pre_close,
                                    'market_value': stmt.excluded.market_value,
                                    'pe_ratio': stmt.excluded.pe_ratio,
                                    'volume': stmt.excluded.volume,
                                    'turnover': stmt.excluded.turnover,
                                    'amplitude': stmt.excluded.amplitude,
                                    'turnover_rate': stmt.excluded.turnover_rate,
                                    'updated_at': stmt.excluded.updated_at
                                }
                                stmt = stmt.on_conflict_do_update(
                                    index_elements=['fullsymbol'],
                                    set_=update_dict
                                )
                                db.execute(stmt)
                                sub_batch_success += len(sub_batch)

                            except Exception as sub_e:
                                logger.error(f"子批次也失败: {sub_e}")
                                continue

                        if sub_batch_success > 0:
                            total_processed += sub_batch_success
                            logger.info(f"通过子批次成功处理了 {sub_batch_success}/{len(batch_data)} 条记录")
                        else:
                            logger.error("所有子批次都失败了")
                    else:
                        # 其他类型的错误，记录详细信息
                        if "more expressions than target columns" in str(e):
                            logger.error("检测到字段数量不匹配错误")
                        elif "duplicate key" in str(e).lower():
                            logger.error("检测到主键冲突，这通常是正常的UPSERT行为")

                    # 继续处理下一批次
                    continue

            logger.info(f"批量处理完成，总计处理 {total_processed} 条实时行情数据")
            return total_processed

        except Exception as e:
            logger.error(f"批量处理实时行情数据失败: {e}")

            # 只在特定错误类型时记录详细traceback
            error_str = str(e)
            if ("more expressions than target columns" in error_str or
                "column" in error_str.lower() or
                "field" in error_str.lower()):
                import traceback
                logger.error("由于可能的Schema问题，记录详细错误信息:")
                logger.error(f"错误详情: {traceback.format_exc()}")
            else:
                logger.error(f"错误类型: {type(e).__name__}")

            return 0

    def _batch_upsert_us_stock_names(self, db: Session, name_data: List[Dict[str, Any]]) -> int:
        """
        批量插入或更新美股名称数据到us_stocks_name表

        Args:
            db: 数据库会话
            name_data: 美股名称数据列表

        Returns:
            int: 成功处理的记录数
        """
        if not name_data:
            logger.warning("没有美股名称数据需要处理")
            return 0

        try:
            logger.info(f"开始批量处理美股名称数据，原始记录数: {len(name_data)}")

            # 数据去重：基于symbol主键
            unique_names: Dict[str, Dict[str, Any]] = {}
            for item in name_data:
                symbol = item['symbol']
                if symbol not in unique_names:
                    unique_names[symbol] = item
                else:
                    existing_time = unique_names[symbol]['updated_at']
                    new_time = item['updated_at']
                    if new_time > existing_time:
                        unique_names[symbol] = item

            deduplicated_data = list(unique_names.values())
            if len(deduplicated_data) != len(name_data):
                logger.info(f"数据去重完成: {len(name_data)} 条 -> {len(deduplicated_data)} 条")

            # 分批处理
            batch_size = 500
            total_processed = 0

            for i in range(0, len(deduplicated_data), batch_size):
                batch_data = deduplicated_data[i:i + batch_size]
                logger.info(f"处理批次 {i//batch_size + 1}: {len(batch_data)} 条记录")

                try:
                    # 使用PostgreSQL的批量UPSERT
                    stmt = insert(UsStocksName).values(batch_data)

                    # 定义更新字段（除主键和created_at外的所有字段）
                    update_dict = {
                        'name': stmt.excluded.name,
                        'cname': stmt.excluded.cname,
                        'updated_at': stmt.excluded.updated_at
                    }

                    # 基于主键symbol进行冲突处理
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['symbol'],
                        set_=update_dict
                    )

                    db.execute(stmt)
                    total_processed += len(batch_data)
                    logger.info(f"批次 {i//batch_size + 1} 处理完成")

                except Exception as e:
                    logger.error(f"批次 {i//batch_size + 1} 处理失败: {e}")

            logger.info(f"成功批量处理 {total_processed} 条美股名称数据")
            return total_processed

        except Exception as e:
            logger.error(f"批量处理美股名称数据失败: {e}")
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
            processed_keys: List[Tuple[str, str]] = []

            for ticker, period, dataframe in pending_data:
                try:
                    # 开始事务处理这个数据条目
                    with db.begin():
                        # 扩展持久化函数支持新闻数据批量处理
                        processed_rows = 0

                        # 根据period类型处理不同数据
                        if period == 'news':
                            # 新闻数据不再持久化到数据库，跳过处理
                            logger.info(f"跳过新闻数据持久化: {ticker} (新闻数据仅使用Redis缓存)")
                            processed_rows = 0

                        elif period == 'daily':
                            daily_data = self._prepare_daily_price_data(ticker, dataframe)
                            processed_rows = self._batch_upsert_prices(
                                db, StockPriceDaily, daily_data, ['ticker', 'date']
                            )

                        elif period == 'weekly':
                            weekly_data = self._prepare_weekly_price_data(ticker, dataframe)
                            processed_rows = self._batch_upsert_prices(
                                db, StockPriceWeekly, weekly_data, ['ticker', 'date']
                            )

                        elif period == 'minute':
                            # 分钟线数据不持久化到PostgreSQL，只保存在Redis缓存中
                            logger.info(f"跳过分钟线数据持久化: {ticker} (分钟线数据仅保存在Redis缓存中)")
                            processed_rows = 0

                        elif period == 'realtime_quotes':
                            # 处理实时行情数据
                            quote_data = self._prepare_realtime_quote_data(dataframe)
                            processed_rows = self._batch_upsert_realtime_quotes(db, quote_data)

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
            period: 时间周期 ('daily', 'weekly', '10min', 'minute')
            dataframe: 待保存的数据
            pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键。

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 检查数据库会话是否已初始化
            if database.SessionLocal is None:
                logger.error("数据库会话未初始化，无法保存数据")
                return False

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
                    elif period == 'minute':
                        # 分钟线数据不持久化到PostgreSQL，只保存在Redis缓存中
                        logger.info(f"跳过分钟线数据持久化: {ticker} (分钟线数据仅保存在Redis缓存中)")
                        processed_rows = 0
                    elif period == 'realtime_quotes':
                        # 处理实时行情数据
                        quote_data = self._prepare_realtime_quote_data(dataframe)
                        processed_rows = self._batch_upsert_realtime_quotes(db, quote_data)
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

    # _prepare_news_data方法已删除 - 新闻数据不再持久化到数据库

    # _batch_upsert_news方法已删除 - 新闻数据不再持久化到数据库

    # save_news_dataframe_to_db方法已删除 - 新闻数据不再持久化到数据库

    def save_realtime_quotes_to_db(self, dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
        """
        将实时行情数据直接持久化到stock_symbols表

        Args:
            dataframe: 实时行情数据DataFrame
            pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 检查数据库会话是否已初始化
            if database.SessionLocal is None:
                logger.error("数据库会话未初始化，无法保存实时行情数据")
                return False

            with database.SessionLocal() as db:
                with db.begin():
                    # 准备实时行情数据
                    quote_data = self._prepare_realtime_quote_data(dataframe)

                    if not quote_data:
                        logger.warning("没有有效的实时行情数据需要保存")
                        return True

                    # 批量插入实时行情数据
                    processed_rows = self._batch_upsert_realtime_quotes(db, quote_data)

                    logger.info(f"成功将实时行情数据存入数据库，处理行数: {processed_rows}")

            # 如果提供了缓存键，并且数据库操作成功，则删除它
            if pending_cache_key:
                logger.info(f"实时行情数据写入成功，现在删除 pending_save 缓存键: {pending_cache_key}")
                delete_from_redis(pending_cache_key)

            return True
        except Exception as e:
            logger.error(f"保存实时行情数据到数据库失败: {e}")
            return False

    def save_us_stock_names_to_db(self, dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
        """
        将美股名称数据直接持久化到us_stocks_name表

        Args:
            dataframe: 美股名称数据DataFrame
            pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 检查数据库会话是否已初始化
            if database.SessionLocal is None:
                logger.error("数据库会话未初始化，无法保存美股名称数据")
                return False

            with database.SessionLocal() as db:
                with db.begin():
                    # 准备美股名称数据
                    name_data = self._prepare_us_stock_name_data(dataframe)

                    if not name_data:
                        logger.warning("没有有效的美股名称数据需要保存")
                        return True

                    # 批量插入美股名称数据
                    processed_rows = self._batch_upsert_us_stock_names(db, name_data)

                    logger.info(f"成功将美股名称数据存入数据库，处理行数: {processed_rows}")

            # 如果提供了缓存键，并且数据库操作成功，则删除它
            if pending_cache_key:
                logger.info(f"美股名称数据写入成功，现在删除 pending_save 缓存键: {pending_cache_key}")
                delete_from_redis(pending_cache_key)

            return True
        except Exception as e:
            logger.error(f"保存美股名称数据到数据库失败: {e}")
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

def save_realtime_quotes_to_db(dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
    """
    将实时行情数据直接持久化到stock_symbols表

    Args:
        dataframe: 实时行情数据DataFrame
        pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键

    Returns:
        bool: 保存成功返回True，失败返回False
    """
    return database_writer.save_realtime_quotes_to_db(dataframe, pending_cache_key)


def save_us_stock_names_to_db(dataframe: pd.DataFrame, pending_cache_key: Optional[str] = None) -> bool:
    """
    将美股名称数据直接持久化到us_stocks_name表

    Args:
        dataframe: 美股名称数据DataFrame
        pending_cache_key (Optional[str]): 如果提供，操作成功后将从Redis中删除此键

    Returns:
        bool: 保存成功返回True，失败返回False
    """
    return database_writer.save_us_stock_names_to_db(dataframe, pending_cache_key)


# 导出主要组件
__all__ = [
    'DatabaseWriter',
    'database_writer',
    'persist_pending_data',
    'save_dataframe_to_db',
    'save_realtime_quotes_to_db',
    'save_us_stock_names_to_db'
]