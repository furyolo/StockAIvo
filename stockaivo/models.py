"""
StockAIvo - SQLAlchemy ORM Models
智能美股数据与分析平台的数据模型定义

包含以下核心模型：
- StockPriceDaily: 日K线数据
- StockPriceWeekly: 周K线数据
- StockSymbols: 股票代码映射表
- UsStocksName: 美股名称表
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, String, DateTime, Date, Numeric, BigInteger, Text, ForeignKey, UniqueConstraint, Index, MetaData, TIMESTAMP
from sqlalchemy.orm import declarative_base, relationship

from .timezone_manager import get_current_time

# 定义元数据，并指定 schema
metadata_obj = MetaData(schema="public")

# 创建基础模型类，并关联元数据
Base = declarative_base(metadata=metadata_obj)




class StockSymbols(Base):
    """
    股票代码与完整代码映射表
    存储用于数据源查询的完整代码和实时行情数据

    注意：此模型匹配实际数据库表结构，包含完整的行情数据字段
    """
    __tablename__ = 'stock_symbols'

    # 主键和基础字段
    fullsymbol = Column(String, primary_key=True, nullable=False, comment='数据源使用的完整代码，如106.AAPL')
    symbol = Column(String, nullable=False, comment='股票代码，如AAPL')

    # 基础信息字段
    name = Column(String, nullable=False, comment='公司名称')

    # 价格相关字段
    price = Column(Numeric(10, 4), nullable=True, comment='最新价')
    price_change = Column(Numeric(10, 4), nullable=True, comment='涨跌额')
    price_change_percent = Column(Numeric(10, 4), nullable=True, comment='涨跌幅')
    open = Column(Numeric(10, 4), nullable=True, comment='开盘价')
    high = Column(Numeric(10, 4), nullable=True, comment='最高价')
    low = Column(Numeric(10, 4), nullable=True, comment='最低价')
    pre_close = Column(Numeric(10, 4), nullable=True, comment='昨收价')

    # 市场数据字段
    market_value = Column(BigInteger, nullable=True, comment='总市值')
    pe_ratio = Column(Numeric(10, 4), nullable=True, comment='市盈率')
    volume = Column(BigInteger, nullable=True, comment='成交量')
    turnover = Column(BigInteger, nullable=True, comment='成交额')
    amplitude = Column(Numeric(10, 4), nullable=True, comment='振幅')
    turnover_rate = Column(Numeric(10, 4), nullable=True, comment='换手率')

    # 时间戳字段
    created_at = Column(DateTime, nullable=False, default=get_current_time, comment='记录创建时间')
    updated_at = Column(DateTime, nullable=False, default=get_current_time, onupdate=get_current_time, comment='记录更新时间')

    # 创建索引以优化基于symbol的查询
    __table_args__ = (
        Index('idx_stock_symbols_symbol', 'symbol'),
        {'comment': '股票代码与完整代码映射表（包含实时行情数据）'}
    )

    def __repr__(self):
        return f"<StockSymbols(symbol='{self.symbol}', fullsymbol='{self.fullsymbol}', price={self.price})>"

class StockPriceDaily(Base):
    """
    日K线数据表
    存储股票的日频率价格和交易量数据
    """
    __tablename__ = 'stock_prices_daily'
    
    # 复合主键：股票代码 + 日期
    ticker = Column(String(10), primary_key=True, nullable=False, comment='股票代码')
    date = Column(Date, primary_key=True, nullable=False, comment='交易日期')
    
    # OHLCV数据
    open = Column(Numeric(10, 4), nullable=False, comment='开盘价')
    high = Column(Numeric(10, 4), nullable=False, comment='最高价')
    low = Column(Numeric(10, 4), nullable=False, comment='最低价')
    close = Column(Numeric(10, 4), nullable=False, comment='收盘价')
    volume = Column(BigInteger, nullable=True, comment='交易量')
    
    # 新增交易指标
    turnover = Column(BigInteger, nullable=True, comment='交易额')
    amplitude = Column(Numeric(10, 4), nullable=True, comment='振幅(%)')
    price_change_percent = Column(Numeric(10, 4), nullable=True, comment='涨跌幅(%)')
    price_change = Column(Numeric(10, 4), nullable=True, comment='涨跌额')
    turnover_rate = Column(Numeric(10, 4), nullable=True, comment='换手率(%)')
    
    # 时间戳字段
    created_at = Column(DateTime, default=get_current_time, comment='记录创建时间')
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time, comment='记录更新时间')
    
    # 表约束和索引
    __table_args__ = (
        UniqueConstraint('ticker', 'date', name='uk_daily_ticker_date'),
        Index('idx_daily_ticker', 'ticker'),
        Index('idx_daily_date', 'date'),
        Index('idx_daily_ticker_date', 'ticker', 'date'),
        {'comment': '股票日K线数据表'}
    )
    
    def __repr__(self):
        return f"<StockPriceDaily(ticker='{self.ticker}', date='{self.date}', close={self.close})>"


class StockPriceWeekly(Base):
    """
    周K线数据表
    存储股票的周频率价格和交易量数据
    """
    __tablename__ = 'stock_prices_weekly'
    
    # 复合主键：股票代码 + 日期
    ticker = Column(String(10), primary_key=True, nullable=False, comment='股票代码')
    date = Column(Date, primary_key=True, nullable=False, comment='周结束日期（周五）')
    
    # OHLCV数据
    open = Column(Numeric(10, 4), nullable=False, comment='周开盘价')
    high = Column(Numeric(10, 4), nullable=False, comment='周最高价')
    low = Column(Numeric(10, 4), nullable=False, comment='周最低价')
    close = Column(Numeric(10, 4), nullable=False, comment='周收盘价')
    volume = Column(BigInteger, nullable=True, comment='周总交易量')

    # 新增交易指标
    turnover = Column(BigInteger, nullable=True, comment='交易额')
    amplitude = Column(Numeric(10, 4), nullable=True, comment='振幅(%)')
    price_change_percent = Column(Numeric(10, 4), nullable=True, comment='涨跌幅(%)')
    price_change = Column(Numeric(10, 4), nullable=True, comment='涨跌额')
    turnover_rate = Column(Numeric(10, 4), nullable=True, comment='换手率(%)')
    
    # 时间戳字段
    created_at = Column(DateTime, default=get_current_time, comment='记录创建时间')
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time, comment='记录更新时间')
    
    # 表约束和索引
    __table_args__ = (
        UniqueConstraint('ticker', 'date', name='uk_weekly_ticker_week'),
        Index('idx_weekly_ticker', 'ticker'),
        Index('idx_weekly_date', 'date'),
        Index('idx_weekly_ticker_date', 'ticker', 'date'),
        {'comment': '股票周K线数据表'}
    )
    
    def __repr__(self):
        return f"<StockPriceWeekly(ticker='{self.ticker}', date='{self.date}', close={self.close})>"



class UsStocksName(Base):
    """
    美股名称表
    存储美国股票的英文名称、中文名称和股票代码的映射关系
    用于股票搜索和名称查询功能

    主要用途：
    - 股票代码与公司名称的映射
    - 支持中英文名称的模糊搜索
    - 为前端搜索功能提供数据支持
    """
    __tablename__ = 'us_stocks_name'

    # 主键：股票代码
    symbol = Column(String, primary_key=True, nullable=False, comment='股票代码，如AAPL、MSFT等，作为主键唯一标识')

    # 名称字段
    name = Column(String, nullable=False, comment='英文公司名称，如Apple Inc、Microsoft Corporation')
    cname = Column(String, nullable=True, comment='中文公司名称，如苹果公司、微软公司，可为空')

    # 时间戳字段
    created_at = Column(DateTime, nullable=False, default=get_current_time, comment='记录创建时间，使用环境变量时区')
    updated_at = Column(DateTime, nullable=False, default=get_current_time, onupdate=get_current_time, comment='记录更新时间，使用环境变量时区')

    # 表约束和索引配置
    __table_args__ = (
        # B-tree索引：优化单字段查询
        Index('idx_us_stocks_name_name', 'name'),
        Index('idx_us_stocks_name_cname', 'cname'),

        # 复合索引：优化多字段查询和排序操作
        Index('idx_us_stocks_name_composite', 'symbol', 'name', 'cname'),

        # GIN索引：支持全文搜索和模糊匹配（使用trigram）
        # 注意：这些索引需要在数据库中手动创建，因为SQLAlchemy不直接支持GIN索引语法
        # 实际创建语句在 database_migrations/create_search_indexes.py 中

        # 表注释
        {'comment': '美股名称表，存储股票代码与中英文名称的映射关系，支持搜索和查询功能'}
    )

    def __repr__(self):
        """
        字符串表示方法，用于调试和日志记录

        Returns:
            str: 包含关键字段信息的字符串表示
        """
        cname_display = f", cname='{self.cname}'" if self.cname is not None and self.cname.strip() else ""
        return f"<UsStocksName(symbol='{self.symbol}', name='{self.name}'{cname_display})>"


# StockNews模型已删除 - 新闻数据仅使用Redis缓存，不再持久化到数据库


class StockPrediction(Base):
    """
    股票预测结果表
    存储AI分析的结构化概率预测结果
    """
    __tablename__ = 'stock_predictions'
    
    # 复合主键：股票代码 + 市场感知日期
    ticker = Column(String(10), primary_key=True, nullable=False, comment='股票代码')
    market_aware_date = Column(Date, primary_key=True, nullable=False, comment='市场感知日期（分析基准日期）')
    
    # 预测相关日期信息
    target_date = Column(Date, nullable=False, comment='预测目标日期')
    trading_days_count = Column(BigInteger, nullable=False, comment='预测交易日数量')
    
    # 预测结果
    prediction_probability = Column(Numeric(5, 4), nullable=False, comment='预测概率值(0.0000-1.0000)')
    direction = Column(String(4), nullable=False, comment='预测方向(UP/DOWN)')
    confidence_level = Column(String(6), nullable=False, comment='置信度(HIGH/MEDIUM/LOW)')
    reasoning = Column(Text, nullable=True, comment='预测推理说明')
    
    # 时间戳字段
    created_at = Column(DateTime, nullable=False, default=get_current_time, comment='记录创建时间')
    updated_at = Column(DateTime, nullable=False, default=get_current_time, onupdate=get_current_time, comment='记录更新时间')
    
    # 表约束和索引
    __table_args__ = (
        # 复合主键约束
        UniqueConstraint('ticker', 'market_aware_date', name='uk_prediction_ticker_date'),
        
        # 基础索引
        Index('idx_stock_predictions_ticker', 'ticker'),
        Index('idx_stock_predictions_market_date', 'market_aware_date'),
        Index('idx_stock_predictions_target_date', 'target_date'),
        Index('idx_stock_predictions_direction', 'direction'),
        Index('idx_stock_predictions_confidence', 'confidence_level'),
        
        # 复合索引
        Index('idx_stock_predictions_ticker_direction', 'ticker', 'direction'),
        Index('idx_stock_predictions_date_range', 'market_aware_date', 'target_date'),
        
        # 表注释
        {'comment': '股票预测结果表，存储AI分析的结构化概率预测数据'}
    )
    
    def __repr__(self):
        return f"<StockPrediction(ticker='{self.ticker}', date='{self.market_aware_date}', direction='{self.direction}', probability={self.prediction_probability})>"


