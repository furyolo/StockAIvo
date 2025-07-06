"""
数据查询主逻辑模块

本模块实现了股票数据查询的核心逻辑，协调数据库查询、外部数据获取和缓存管理。
根据项目文档 1.4 数据查询主逻辑 的要求实现。
"""

import logging
import pandas as pd
import pandas_market_calendars as mcal
from pandas.tseries.frequencies import to_offset
from typing import Optional, Literal, List, Tuple
from datetime import datetime, date, timedelta
from fastapi import BackgroundTasks

# 导入数据库会话管理和模型
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from . import database
from . import database_writer
from .models import StockPriceDaily, StockPriceWeekly, StockPriceHourly

 # 导入数据提供者和缓存管理器
from . import data_provider
from . import cache_manager
from .cache_manager import CacheType

 # 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义支持的时间周期类型
PeriodType = Literal["daily", "weekly", "hourly"]


def _filter_dataframe_by_date(df: pd.DataFrame, period: PeriodType, start_date: Optional[str], end_date: Optional[str]) -> pd.DataFrame:
    """根据日期范围过滤DataFrame"""
    if df.empty or (not start_date and not end_date):
        return df

    date_col = _get_date_col(period)
    if date_col not in df.columns:
        logger.warning(f"在DataFrame中找不到预期的日期列 '{date_col}' 进行过滤: {df.columns}")
        # 作为后备，检查 'date' 或 'timestamp' 是否存在
        if 'date' in df.columns:
            date_col = 'date'
        elif 'timestamp' in df.columns:
            date_col = 'timestamp'
        else:
            logger.error(f"无法在DataFrame中找到任何可用的日期列进行过滤。")
            return df


    # 确保日期列是datetime类型
    try:
        if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
            df[date_col] = pd.to_datetime(df[date_col])
    except Exception as e:
        logger.error(f"无法将列 '{date_col}' 转换为datetime: {e}")
        return df

    original_count = len(df)
    if start_date:
        df = df[df[date_col] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df[date_col] <= pd.to_datetime(end_date)]
    
    logger.info(f"DataFrame过滤: 原始行数={original_count}, 过滤后行数={len(df)}")
    return df


async def get_stock_data(db: Session, ticker: str, period: PeriodType, start_date: Optional[str] = None, end_date: Optional[str] = None, background_tasks: Optional[BackgroundTasks] = None) -> Optional[pd.DataFrame]:
    """
    获取股票数据的核心函数（缓存优先策略）

    实现逻辑流程：
    1.  **查询 Redis 缓存**: 首先尝试从 Redis 获取数据。
    2.  **检查数据完整性**: 使用新的日期点感知逻辑检查缓存数据是否覆盖所需范围。
    3.  **获取缺失数据**: 如果数据不完整，计算出所有缺失的、不连续的日期范围，并从数据库或远程API获取。
    4.  **合并与更新**: 将新获取的数据与缓存数据合并，并更新Redis缓存。
    5.  **清理与过滤**: 在返回数据之前，清理数据类型并根据 start_date 和 end_date 进行过滤。
    
    Args:
        db (Session): SQLAlchemy 数据库会话。
        ticker (str): 股票代码。
        period (PeriodType): 数据周期 ('daily', 'weekly', 'hourly')。
        start_date (Optional[str]): 开始日期 (YYYY-MM-DD)。
        end_date (Optional[str]): 结束日期 (YYYY-MM-DD)。
    
    Returns:
        Optional[pd.DataFrame]: 包含股票数据的 DataFrame，或在失败时返回 None。
    """
    if not ticker or period not in ["daily", "weekly", "hourly"]:
        logger.error(f"无效的参数: ticker='{ticker}', period='{period}'")
        return None

    # =================================================================
    # == 新增：默认日期范围逻辑 ==
    # =================================================================
    # 如果没有提供开始和结束日期，则应用默认值
    if start_date is None and end_date is None:
        logger.info(f"未提供日期范围，为 '{period}' 周期应用默认值。")
        today = date.today()

        # 先计算end_date_obj，如果遇到休市日，则继续往前直到非休市日为止
        yesterday = today - timedelta(days=1)
        end_date_obj = _get_latest_trading_day(yesterday)

        if period == "daily":
            # start_date_obj在end_date_obj基础上往前30天
            start_date_obj = end_date_obj - timedelta(days=30)
            start_date = start_date_obj.strftime('%Y-%m-%d')
            end_date = end_date_obj.strftime('%Y-%m-%d')
            logger.info(f"日线数据默认范围设置为: {start_date} -> {end_date}")
        elif period == "weekly":
            # start_date_obj在end_date_obj基础上往前180天
            start_date_obj = end_date_obj - timedelta(days=180)
            start_date = start_date_obj.strftime('%Y-%m-%d')
            end_date = end_date_obj.strftime('%Y-%m-%d')
            logger.info(f"周线数据默认范围设置为: {start_date} -> {end_date}")
    # =================================================================
    # == 默认逻辑结束 ==
    # =================================================================

    logger.info(f"开始获取数据: {ticker} ({period}) | 范围: {start_date} -> {end_date}")

    # 修正结束日期，确保不包含今天及以后的日期
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if end_date and end_date > yesterday:
        logger.info(f"请求的结束日期 {end_date} 超出允许范围，已自动修正为昨天: {yesterday}")
        end_date = yesterday

    # =================================================================
    # == 新增的前置检查逻辑 ==
    # =================================================================
    # 在进行任何昂贵操作之前，首先计算出理论上需要的所有日期点。
    required_dates = _get_required_dates(period, start_date, end_date)

    # 如果必需日期列表为空，说明请求的日期范围内没有有效的数据点
    # (例如，请求一个不包含任何周五的周线数据范围)。
    if required_dates is not None and len(required_dates) == 0 and start_date and end_date:
        logger.info(f"请求的日期范围 {start_date} -> {end_date} 内不包含周期为 '{period}' 的有效数据点，提前返回。")
        return pd.DataFrame()
    # =================================================================
    # == 检查结束 ==
    # =================================================================

    # --- 1. 查询 Redis 缓存并进行数据完整性检查 ---
    try:
        # 首先检查通用缓存
        redis_data = cache_manager.get_from_redis(ticker, period, CacheType.GENERAL_CACHE)
        if redis_data is not None and not redis_data.empty:
            logger.info(f"在 Redis 通用缓存中找到 {ticker} 的 {period} 数据 ({len(redis_data)} 条)")
            
            # 确定必需的日期点
            required_dates = _get_required_dates(period, start_date, end_date)
            if not required_dates:
                # 如果没有必需的日期（例如范围无效），直接过滤并返回缓存数据
                return _filter_dataframe_by_date(redis_data, period, start_date, end_date)

            date_col = _get_date_col(period)
            cached_dates = pd.to_datetime(redis_data[date_col]).dt.date.tolist()

            # 找出所有缺失的、不连续的日期范围
            missing_ranges = _find_missing_date_ranges(required_dates, cached_dates)

            if not missing_ranges:
                logger.info("缓存数据完全覆盖请求范围")
                filtered_data = _filter_dataframe_by_date(redis_data, period, start_date, end_date)
                return _clean_dataframe(filtered_data)

            logger.info(f"缓存数据不完整，发现 {len(missing_ranges)} 个缺失的日期范围: {missing_ranges}")
            
            all_newly_fetched_data = [] # 存储从DB和远程获取的所有新数据
            data_from_remote_only = [] # 只存储从远程API获取的数据

            # --- 2. 循环获取所有缺失范围的数据 ---
            for missing_start, missing_end in missing_ranges:
                ms_str = missing_start.strftime('%Y-%m-%d')
                me_str = missing_end.strftime('%Y-%m-%d')
                logger.info(f"正在处理缺失范围: {ms_str} -> {me_str}")

                # 步骤 2.1: 优先从数据库获取
                data_from_db = _query_database(db, ticker, period, ms_str, me_str)
                
                if data_from_db is not None and not data_from_db.empty:
                    logger.info(f"在数据库中为范围 {ms_str}-{me_str} 找到 {len(data_from_db)} 条数据。")
                    all_newly_fetched_data.append(data_from_db)
                    
                    # 步骤 2.2: 重新计算仍然缺失的日期
                    db_dates = pd.to_datetime(data_from_db[date_col]).dt.date.tolist()
                    required_dates_in_range = [d for d in required_dates if missing_start <= d <= missing_end]
                    still_missing_ranges = _find_missing_date_ranges(required_dates_in_range, db_dates)
                else:
                    # 如果数据库完全没有这个范围的数据，则整个范围都需要从远程获取
                    logger.info(f"数据库中未找到范围 {ms_str}-{me_str} 的数据。")
                    still_missing_ranges = [(missing_start, missing_end)]

                # 步骤 2.3: 从远程API获取仍然缺失的数据
                if still_missing_ranges:
                    for sub_start, sub_end in still_missing_ranges:
                        ss_str = sub_start.strftime('%Y-%m-%d')
                        se_str = sub_end.strftime('%Y-%m-%d')
                        logger.info(f"从远程 API 获取细分缺失范围: {ss_str} -> {se_str}")
                        
                        new_data_remote = await data_provider.fetch_from_akshare(db, ticker, period, ss_str, se_str)
                        if new_data_remote is not None and not new_data_remote.empty:
                            all_newly_fetched_data.append(new_data_remote)
                            data_from_remote_only.append(new_data_remote)

            # --- 3. 合并数据并更新缓存 ---
            if all_newly_fetched_data:
                new_data_df = pd.concat(all_newly_fetched_data, ignore_index=True)
                
                # 确保日期列类型一致以便合并
                redis_data[date_col] = pd.to_datetime(redis_data[date_col])
                new_data_df[date_col] = pd.to_datetime(new_data_df[date_col])

                # 合并、去重、排序
                combined_data = pd.concat([redis_data, new_data_df]).drop_duplicates(subset=[date_col]).sort_values(by=date_col).reset_index(drop=True)
                
                # 更新通用缓存
                cache_manager.save_to_redis(ticker, period, combined_data, CacheType.GENERAL_CACHE)
                logger.info(f"成功合并并更新了 {ticker} 的 {period} 通用缓存，总条数: {len(combined_data)}")

                # 只将从远程API获取的数据存入待保存缓存
                if data_from_remote_only:
                    remote_data_df = pd.concat(data_from_remote_only, ignore_index=True)
                    _append_to_pending_save(ticker, period, remote_data_df)

                filtered_data = _filter_dataframe_by_date(combined_data, period, start_date, end_date)
                return _clean_dataframe(filtered_data)
            else:
                logger.warning(f"无法获取任何缺失的数据，仅返回当前缓存的数据")
                filtered_data = _filter_dataframe_by_date(redis_data, period, start_date, end_date)
                return _clean_dataframe(filtered_data)

    except Exception as e:
        logger.error(f"处理缓存或获取缺失数据时出错: {e}", exc_info=True)

    # =================================================================
    # 步骤 2: 缓存未命中，查询 PostgreSQL 数据库 (核心修改区域)
    # =================================================================
    logger.info("缓存未命中，开始查询数据库...")
    db_data = _query_database(db, ticker, period, start_date, end_date)

    if db_data is not None and not db_data.empty:
        logger.info(f"在数据库中找到 {len(db_data)} 条数据，开始检查数据完整性。")

        date_col = _get_date_col(period)
        # 确保日期列存在
        if date_col not in db_data.columns:
            logger.error(f"数据库返回的数据中缺少关键日期列: '{date_col}'")
            # 即使数据格式有问题，也尝试返回能给出的部分
            return _filter_dataframe_by_date(db_data, period, start_date, end_date)

        db_dates = pd.to_datetime(db_data[date_col]).dt.date.tolist()
        missing_ranges = _find_missing_date_ranges(required_dates, db_dates)

        if not missing_ranges:
            # 数据库数据是完整的
            logger.info("数据库数据完全覆盖请求范围。")
            cache_manager.save_to_redis(ticker, period, db_data, CacheType.GENERAL_CACHE)
            filtered_data = _filter_dataframe_by_date(db_data, period, start_date, end_date)
            return _clean_dataframe(filtered_data)
        else:
            # 数据库数据不完整，需要补充
            logger.info(f"数据库数据不完整，发现 {len(missing_ranges)} 个缺失的日期范围: {missing_ranges}")
            all_newly_fetched_data = []

            # 2. 调用 data_provider 获取缺失数据
            for missing_start, missing_end in missing_ranges:
                ms_str = missing_start.strftime('%Y-%m-%d')
                me_str = missing_end.strftime('%Y-%m-%d')
                
                # 新增：在调用API前检查缺失范围是否包含交易日
                try:
                    nyse_calendar = mcal.get_calendar('NYSE')
                    schedule = nyse_calendar.schedule(start_date=ms_str, end_date=me_str)
                    if schedule.empty:
                        logger.info(f"跳过非交易日范围: {ms_str} -> {me_str}")
                        continue
                except Exception as e:
                    logger.warning(f"无法检查交易日历，将继续尝试获取数据: {e}")

                logger.info(f"正在从远程 API 获取缺失范围: {ms_str} -> {me_str}")
                new_data = await data_provider.fetch_from_akshare(db, ticker, period, ms_str, me_str)
                if new_data is not None and not new_data.empty:
                    all_newly_fetched_data.append(new_data)

            # 3. 合并数据库数据和新获取的数据
            combined_data = db_data
            if all_newly_fetched_data:
                new_data_df = pd.concat(all_newly_fetched_data)
                
                if not new_data_df.empty:
                    # 确保列类型一致
                    db_data[date_col] = pd.to_datetime(db_data[date_col])
                    new_data_df[date_col] = pd.to_datetime(new_data_df[date_col])
                    
                    combined_data = pd.concat([db_data, new_data_df]).drop_duplicates(subset=[date_col]).sort_values(by=date_col).reset_index(drop=True)

                    # 4. (可选但推荐) 将新数据保存到数据库
                    _append_to_pending_save(ticker, period, new_data_df)
                    logger.info(f"检测到新的远程数据 (ticker: {ticker}, period: {period})，已存入待持久化缓存。")
                    # The background scheduler will pick this up.

            # 将合并后的完整数据更新到 Redis 通用缓存
            cache_manager.save_to_redis(ticker, period, combined_data, CacheType.GENERAL_CACHE)
            logger.info(f"成功合并数据库和远程数据，总条数: {len(combined_data)}")

            # 5. 返回最终的完整数据
            filtered_data = _filter_dataframe_by_date(combined_data, period, start_date, end_date)
            return _clean_dataframe(filtered_data)

    # --- 3. 查询远程 API (AKShare) ---
    logger.info(f"缓存和数据库中均未找到数据，从远程 API (AKShare) 获取...")
    try:
        # 从远程获取全部历史数据以填充缓存和数据库
        remote_data = await data_provider.fetch_from_akshare(db, ticker, period, start_date, end_date)
        if remote_data is None or remote_data.empty:
            logger.warning(f"无法从远程 API 获取 {ticker} 的 {period} 数据")
            return None
        
        logger.info(f"成功从远程 API 获取 {len(remote_data)} 条数据")

        # 将数据同时存入数据库和 Redis 缓存
        # 使用后台任务异步保存到数据库
        # 此处的后台任务逻辑已移至下方与 PENDING_SAVE 缓存键关联

        # 新数据：存入 PENDING_SAVE 以便持久化，也存入 GENERAL_CACHE 以便快速访问
        _append_to_pending_save(ticker, period, remote_data)
        cache_manager.save_to_redis(ticker, period, remote_data, CacheType.GENERAL_CACHE)

        # 异步保存到数据库后，需要清理 pending_key
        logger.info(f"检测到新的远程数据 (ticker: {ticker}, period: {period})，已存入待持久化缓存。")
        # The background scheduler will pick this up.


        final_data = _filter_dataframe_by_date(remote_data, period, start_date, end_date)
        return _clean_dataframe(final_data)

    except Exception as e:
        logger.error(f"获取和处理远程数据时发生严重错误: {e}")
        return None


def _clean_dataframe(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    在序列化之前清理DataFrame，特别是处理整数列中的NaN值。
    """
    if df is None or df.empty:
        return df

    # 在此可以添加对其他列的清理逻辑
    
    return df

def _get_date_col(period: PeriodType) -> str:
    """获取日期列名"""
    if period == 'hourly':
        return 'hour_timestamp'
    # For daily and weekly
    return 'date'


def _get_latest_trading_day(target_date: date) -> date:
    """
    获取指定日期或之前的最近交易日

    Args:
        target_date (date): 目标日期

    Returns:
        date: 最近的交易日
    """
    try:
        # 使用NYSE日历获取交易日
        nyse_calendar = mcal.get_calendar('NYSE')

        # 从目标日期往前查找30天，确保能找到交易日
        search_start = target_date - timedelta(days=30)
        schedule = nyse_calendar.schedule(start_date=search_start, end_date=target_date)

        if schedule.empty:
            logger.warning(f"在 {search_start} 到 {target_date} 范围内未找到交易日，使用目标日期")
            return target_date

        # 获取最后一个交易日
        latest_trading_day = schedule.index[-1].date()
        logger.info(f"目标日期 {target_date} 的最近交易日: {latest_trading_day}")
        return latest_trading_day

    except Exception as e:
        logger.warning(f"获取最近交易日时出错: {e}，使用目标日期")
        return target_date

def _get_required_dates(period: PeriodType, start_date_str: Optional[str], end_date_str: Optional[str]) -> List[date]:
    """
    根据周期和日期范围，生成所有必需的数据点日期列表。
    此函数现在使用 pandas_market_calendars 来获取真实的交易日，以处理节假日。
    """
    if not start_date_str or not end_date_str:
        return []
    try:
        start_date = pd.to_datetime(start_date_str)
        end_date = pd.to_datetime(end_date_str)
    except (ValueError, TypeError):
        logger.error(f"无效的日期格式: start={start_date_str}, end={end_date_str}")
        return []

    if start_date > end_date:
        return []

    try:
        # 使用pandas_market_calendars获取真实交易日
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=start_date, end_date=end_date)
        
        # 将所有交易日存储在一个Set中以便快速查找
        trading_days_set = {d.date() for d in schedule.index}

        if period == "daily":
            # daily 逻辑保持不变
            return sorted(list(trading_days_set))
        
        elif period == "weekly":
            # 1. 获取所有交易日（Datetime对象）
            all_trading_days = pd.to_datetime([d.date() for d in schedule.index])

            # 2. 将每个交易日向前滚动到其所在周的周五
            potential_fridays = all_trading_days.to_series().apply(
                lambda x: x + pd.offsets.Week(weekday=4, n=0)
            ).dt.date

            # 3. (核心修复) 过滤，只保留那些本身也是交易日的周五
            actual_fridays = [
                friday for friday in potential_fridays
                if friday in trading_days_set
            ]

            # 4. 返回去重和排序后的结果
            return sorted(list(set(actual_fridays)))

        elif period == "monthly":
            # monthly 逻辑保持不变
            trading_days = pd.to_datetime([d.date() for d in schedule.index])
            month_ends = trading_days[trading_days.is_month_end]
            # Pylance has trouble with series.dt.date
            return [d.date() for d in month_ends]

    except Exception as e:
        logger.error(f"无法从 pandas_market_calendars 获取日历: {e}. 回退到旧的 'B' 频率逻辑。")
        # 回退逻辑
        if period == "daily":
            return pd.date_range(start=start_date, end=end_date, freq='B').date.tolist()
        elif period == "weekly":
            return pd.date_range(start=start_date, end=end_date, freq='W-FRI').date.tolist()
        elif period == "monthly":
            return pd.date_range(start=start_date, end=end_date, freq='M').date.tolist()
            
    # 'hourly' 周期不进行日期点检查，依赖于 start/end date 范围查询
    return []

def _find_missing_date_ranges(required_dates: List[date], cached_dates: List[date]) -> List[Tuple[date, date]]:
    """
    通过状态转换法，准确比较必需日期和已缓存日期，找出所有缺失的、不连续的日期范围。
    """
    cached_dates_set = set(cached_dates)
    missing_ranges = []
    
    if required_dates is None or len(required_dates) == 0:
        return missing_ranges
        
    start_of_current_range = None

    # 使用 None 作为哨兵来简化循环结束逻辑
    # 确保 required_dates 是列表，以便与 [None] 拼接
    extended_dates = list(required_dates) + [None]

    for i, current_date in enumerate(extended_dates):
        
        is_missing = (current_date is not None) and (current_date not in cached_dates_set)

        if is_missing and start_of_current_range is None:
            # 进入一个新的缺失范围
            start_of_current_range = current_date
            
        elif not is_missing and start_of_current_range is not None:
            # 结束当前的缺失范围
            end_of_current_range = extended_dates[i-1]
            
            missing_ranges.append((start_of_current_range, end_of_current_range))
            
            # 重置状态
            start_of_current_range = None
            
    if not missing_ranges:
        return []

    today = date.today()
    adjusted_ranges = []
    for start, end in missing_ranges:
        if start > today:
            # 如果整个范围都在未来，则跳过
            continue
        
        # 如果结束日期在未来，则将其截断为今天
        adjusted_end = min(end, today)
        adjusted_ranges.append((start, adjusted_end))

    if adjusted_ranges != missing_ranges:
        logger.info(f"原始缺失范围: {missing_ranges}")
        logger.info(f"调整后的缺失范围 (不超过今天): {adjusted_ranges}")

    return adjusted_ranges

def _query_database(db: Session, ticker: str, period: PeriodType, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    从数据库查询股票数据。

    Args:
        db (Session): SQLAlchemy 数据库会话。
        ticker (str): 股票代码。
        period (str): 数据周期 ('daily', 'weekly', 'hourly')。
        start_date (Optional[str]): 开始日期 (YYYY-MM-DD)。
        end_date (Optional[str]): 结束日期 (YYYY-MM-DD)。

    Returns:
        Optional[pd.DataFrame]: 如果找到数据则返回DataFrame，否则返回None。
    """
    logger.info(f"开始从数据库查询 {ticker} 的 {period} 数据 (从 {start_date} 到 {end_date})...")
    
    model_map = {
        "daily": StockPriceDaily,
        "weekly": StockPriceWeekly,
        "hourly": StockPriceHourly,
    }
    
    model = model_map.get(period)
    if not model:
        logger.error(f"无效的数据周期: {period}")
        return None

    try:
        # 获取模型中除了 'created_at' 和 'updated_at' 之外的所有列
        columns_to_select = [
            column
            for column in inspect(model).c
            if column.name not in ['created_at', 'updated_at']
        ]

        # 构建查询
        if period == 'hourly':
            date_column = model.hour_timestamp
        else:  # For daily and weekly
            date_column = model.date
        
        query = select(*columns_to_select).where(model.ticker == ticker)

        if start_date:
            query = query.where(date_column >= start_date)
        if end_date:
            query = query.where(date_column <= end_date)
            
        query = query.order_by(date_column)

        # 执行查询并将结果读入DataFrame
        assert db.bind is not None, "Database connection is not available"
        df = pd.read_sql(query, db.bind)
        
        if df.empty:
            logger.info(f"数据库中未找到 {ticker} 的 {period} 数据。")
            return None
            
        logger.info(f"成功从数据库查询到 {len(df)} 条 {ticker} 的 {period} 数据。")
        return df

    except Exception as e:
        logger.error(f"查询数据库时发生错误: {e}")
        return None

def _append_to_pending_save(ticker: str, period: PeriodType, new_data: pd.DataFrame):
    """
    安全地将新数据追加到 PENDING_SAVE 缓存中。

    它会先读取现有数据，合并新数据，去重，然后写回。
    """
    if new_data is None or new_data.empty:
        return

    # 1. 从Redis读取现有的pending_save数据
    existing_data = cache_manager.get_from_redis(ticker, period, CacheType.PENDING_SAVE)

    if existing_data is not None and not existing_data.empty:
        # 2. 合并新旧数据
        date_col = _get_date_col(period)
        
        # 确保日期列类型一致
        if not pd.api.types.is_datetime64_any_dtype(existing_data[date_col]):
            existing_data[date_col] = pd.to_datetime(existing_data[date_col])
        if not pd.api.types.is_datetime64_any_dtype(new_data[date_col]):
            new_data[date_col] = pd.to_datetime(new_data[date_col])

        combined_data = pd.concat([existing_data, new_data]).drop_duplicates(subset=[date_col]).sort_values(by=date_col).reset_index(drop=True)
        logger.info(f"已将 {len(new_data)} 条新数据与 {len(existing_data)} 条现有待保存数据合并，总计 {len(combined_data)} 条。")
    else:
        # 如果没有现有数据，直接使用新数据
        combined_data = new_data
        logger.info(f"待保存缓存中无现有数据，直接存入 {len(combined_data)} 条新数据。")

    # 3. 将合并后的数据写回 PENDING_SAVE 缓存
    pending_key = cache_manager.save_to_redis(ticker, period, combined_data, CacheType.PENDING_SAVE)
    if pending_key:
        logger.info(f"成功更新待持久化缓存: {pending_key}, 总行数: {len(combined_data)}")



def get_cached_data_summary() -> dict:
    """
    获取缓存数据摘要信息
    
    Returns:
        dict: 包含缓存统计信息的字典
    """
    try:
        return cache_manager.get_cache_stats()
    except Exception as e:
        logger.error(f"获取缓存数据摘要失败: {e}")
        return {"error": str(e)}


def check_data_service_health() -> dict:
    """
    检查数据服务健康状态
    
    Returns:
        dict: 包含各组件健康状态的字典
    """
    health_status = {
        "timestamp": datetime.now().isoformat(),
        "redis_connection": False,
        "database_connection": False,
        "akshare_available": True  # 假设AKShare总是可用的
    }
    
    try:
        # 检查Redis连接
        health_status["redis_connection"] = cache_manager.health_check()
        
        # 检查数据库连接
        health_status["database_connection"] = database.check_db_connection()
        
        logger.info("数据服务健康检查完成")
        
    except Exception as e:
        logger.error(f"数据服务健康检查失败: {e}")
        health_status["error"] = str(e)
    
    return health_status


async def test_data_service():
    """
    测试数据服务功能
    """
    print("开始测试数据查询主逻辑...")

    # 测试用例
    test_cases = [
        ("AAPL", "daily"),
        ("TSLA", "weekly"),
        ("MSFT", "daily"),
        ("", "daily"),           # 空股票代码
        ("AAPL", "invalid"),     # 无效周期
    ]

    # 创建一个临时的数据库会话用于测试
    if not database.SessionLocal:
        print("数据库未初始化，跳过测试。")
        return

    db_session = database.SessionLocal()
    try:
        for ticker, period in test_cases:
            print(f"\n测试: {ticker} - {period}")
            # 注意：现在需要传入db_session
            result = await get_stock_data(db_session, ticker, period) # type: ignore

            if result is not None and not result.empty:
                print(f"成功获取数据，行数: {len(result)}")
                print(f"列名: {result.columns.tolist()}")
                print(f"数据预览:\n{result.head()}")
            else:
                print("获取数据失败或返回空数据框")
    finally:
        db_session.close()

    # 测试健康检查
    print("\n=== 健康检查 ===")
    health = check_data_service_health()
    print(f"健康状态: {health}")

    # 测试缓存统计
    print("\n=== 缓存统计 ===")
    stats = get_cached_data_summary()
    print(f"缓存统计: {stats}")


if __name__ == "__main__":
    # 运行测试
    import asyncio
    asyncio.run(test_data_service())