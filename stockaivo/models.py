"""
StockAIvo - SQLAlchemy ORM Models
智能美股数据与分析平台的数据模型定义

包含以下核心模型：
- Stock: 股票基本信息
- StockPriceDaily: 日K线数据
- StockPriceWeekly: 周K线数据  
- StockPriceHourly: 小时K线数据
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Date, Numeric, BigInteger, ForeignKey, UniqueConstraint, Index, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# 定义元数据，并指定 schema
metadata_obj = MetaData(schema="public")

# 创建基础模型类，并关联元数据
Base = declarative_base(metadata=metadata_obj)


class Stock(Base):
    """
    股票基本信息表
    存储美国股票市场中股票的基础信息
    """
    __tablename__ = 'stocks'
    
    # 主键：股票代码
    ticker = Column(String(10), primary_key=True, comment='股票代码，如AAPL, TSLA')
    
    # 基本信息字段
    company_name = Column(String(255), nullable=False, comment='公司名称')
    exchange = Column(String(10), nullable=False, comment='交易所代码，如NASDAQ, NYSE')
    sector = Column(String(100), nullable=True, comment='所属行业')
    industry = Column(String(100), nullable=True, comment='细分行业')
    market_cap = Column(BigInteger, nullable=True, comment='市值（美元）')
    
    # 时间戳字段
    created_at = Column(DateTime, default=datetime.utcnow, comment='记录创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='记录更新时间')
    
    # 建立与价格数据表的关系
    daily_prices = relationship("StockPriceDaily", back_populates="stock", cascade="all, delete-orphan")
    weekly_prices = relationship("StockPriceWeekly", back_populates="stock", cascade="all, delete-orphan")
    hourly_prices = relationship("StockPriceHourly", back_populates="stock", cascade="all, delete-orphan")
    
    # 创建索引
    __table_args__ = (
        Index('idx_stocks_exchange', 'exchange'),
        Index('idx_stocks_sector', 'sector'),
        {'comment': '股票基本信息表'}
    )
    
    def __repr__(self):
        return f"<Stock(ticker='{self.ticker}', company_name='{self.company_name}', exchange='{self.exchange}')>"

class StockSymbols(Base):
    """
    股票代码与完整代码映射表
    存储用于数据源查询的完整代码
    """
    __tablename__ = 'stock_symbols'

    symbol = Column(String(10), primary_key=True, comment='股票代码，如AAPL')
    full_symbol = Column("fullsymbol", String(255), nullable=False, comment='数据源使用的完整代码，如105.AAPL')

    def __repr__(self):
        return f"<StockSymbols(symbol='{self.symbol}', full_symbol='{self.full_symbol}')>"

class StockPriceDaily(Base):
    """
    日K线数据表
    存储股票的日频率价格和交易量数据
    """
    __tablename__ = 'stock_prices_daily'
    
    # 复合主键：股票代码 + 日期
    ticker = Column(String(10), ForeignKey('stocks.ticker'), primary_key=True, nullable=False, comment='股票代码')
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
    created_at = Column(DateTime, default=datetime.utcnow, comment='记录创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='记录更新时间')
    
    # 外键关系
    stock = relationship("Stock", back_populates="daily_prices")
    
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
    ticker = Column(String(10), ForeignKey('stocks.ticker'), primary_key=True, nullable=False, comment='股票代码')
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
    created_at = Column(DateTime, default=datetime.utcnow, comment='记录创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='记录更新时间')
    
    # 外键关系
    stock = relationship("Stock", back_populates="weekly_prices")
    
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


class StockPriceHourly(Base):
    """
    小时K线数据表
    存储股票的小时频率价格和交易量数据
    """
    __tablename__ = 'stock_prices_hourly'
    
    # 复合主键：股票代码 + 小时时间戳
    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键ID')
    ticker = Column(String(10), ForeignKey('stocks.ticker'), nullable=False, comment='股票代码')
    hour_timestamp = Column(DateTime, nullable=False, comment='小时时间戳')
    
    # OHLCV数据
    open = Column(Numeric(10, 4), nullable=False, comment='小时开盘价')
    high = Column(Numeric(10, 4), nullable=False, comment='小时最高价')
    low = Column(Numeric(10, 4), nullable=False, comment='小时最低价')
    close = Column(Numeric(10, 4), nullable=False, comment='小时收盘价')
    volume = Column(BigInteger, nullable=True, comment='小时交易量')
    
    # 时间戳字段
    created_at = Column(DateTime, default=datetime.utcnow, comment='记录创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='记录更新时间')
    
    # 外键关系
    stock = relationship("Stock", back_populates="hourly_prices")
    
    # 表约束和索引
    __table_args__ = (
        UniqueConstraint('ticker', 'hour_timestamp', name='uk_hourly_ticker_hour'),
        Index('idx_hourly_ticker', 'ticker'),
        Index('idx_hourly_timestamp', 'hour_timestamp'),
        Index('idx_hourly_ticker_timestamp', 'ticker', 'hour_timestamp'),
        {'comment': '股票小时K线数据表'}
    )
    
    def __repr__(self):
        return f"<StockPriceHourly(ticker='{self.ticker}', hour_timestamp='{self.hour_timestamp}', close={self.close})>"