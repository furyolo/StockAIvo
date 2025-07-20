-- 创建股票新闻数据表
-- 用于存储从东方财富获取的股票新闻数据

-- 删除已存在的表（如果存在）
DROP TABLE IF EXISTS stock_news;

-- 创建股票新闻表（使用复合主键，字段顺序：ticker, keyword, title, content, publish_time, created_at, updated_at）
CREATE TABLE stock_news (
    ticker VARCHAR(10) NOT NULL,
    keyword VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    publish_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, title, publish_time)
);

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_stock_news_ticker_time ON stock_news (ticker, publish_time);

CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news (publish_time);

CREATE INDEX IF NOT EXISTS idx_stock_news_keyword ON stock_news (keyword);

-- 添加表注释
COMMENT ON TABLE stock_news IS '股票新闻数据表，存储从东方财富获取的股票相关新闻';

COMMENT ON COLUMN stock_news.ticker IS '股票代码';

COMMENT ON COLUMN stock_news.title IS '新闻标题';

COMMENT ON COLUMN stock_news.publish_time IS '发布时间';

COMMENT ON COLUMN stock_news.keyword IS '搜索关键词，清理后的公司名称';

COMMENT ON COLUMN stock_news.content IS '新闻内容摘要';

COMMENT ON COLUMN stock_news.created_at IS '记录创建时间';

COMMENT ON COLUMN stock_news.updated_at IS '记录更新时间';