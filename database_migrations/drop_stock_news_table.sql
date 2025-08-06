-- 删除股票新闻数据表
-- 根据用户需求，新闻数据将仅使用Redis缓存，不再持久化到数据库

-- 删除相关索引（如果存在）
DROP INDEX IF EXISTS idx_stock_news_keyword_time;
DROP INDEX IF EXISTS idx_stock_news_publish_time;
DROP INDEX IF EXISTS idx_stock_news_keyword;

-- 删除股票新闻表
DROP TABLE IF EXISTS stock_news;

-- 确认删除操作
SELECT 'stock_news表及相关索引已成功删除' AS result;
