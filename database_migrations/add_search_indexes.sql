-- 为us_stocks_name表创建搜索优化索引
-- 创建时间: 2025-07-02
-- 目的: 优化股票名称模糊搜索的查询性能

-- 开始事务
BEGIN;

-- 1. 为name字段创建GIN索引，支持全文搜索和模糊匹配
-- 使用gin_trgm_ops操作符类支持trigram匹配
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_name_gin 
ON us_stocks_name USING gin (name gin_trgm_ops);

-- 2. 为cname字段创建GIN索引，支持中文名称搜索
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_cname_gin 
ON us_stocks_name USING gin (cname gin_trgm_ops);

-- 3. 为name字段创建B-tree索引，支持前缀匹配和排序
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_name_btree 
ON us_stocks_name (name);

-- 4. 为cname字段创建B-tree索引，支持中文前缀匹配
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_cname_btree 
ON us_stocks_name (cname);

-- 5. 创建复合索引，优化常见的搜索和排序模式
-- 支持按symbol排序的搜索结果
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_composite 
ON us_stocks_name (symbol, name, cname);

-- 6. 为symbol字段创建唯一索引（如果还没有的话）
-- 注意：由于symbol是主键，这个索引可能已经存在
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_us_stocks_name_symbol_unique 
ON us_stocks_name (symbol);

-- 提交事务
COMMIT;

-- 验证索引创建
-- 查看表的所有索引
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'us_stocks_name'
ORDER BY indexname;

-- 分析表统计信息，帮助查询优化器
ANALYZE us_stocks_name;

-- 性能测试查询示例（仅用于验证，不会执行）
/*
-- 测试前缀匹配性能
EXPLAIN ANALYZE 
SELECT symbol, name, cname 
FROM us_stocks_name 
WHERE name ILIKE 'Apple%' 
ORDER BY symbol 
LIMIT 10;

-- 测试模糊匹配性能
EXPLAIN ANALYZE 
SELECT symbol, name, cname 
FROM us_stocks_name 
WHERE name ILIKE '%apple%' OR cname ILIKE '%苹果%'
ORDER BY 
    CASE 
        WHEN name ILIKE 'Apple%' THEN 1
        WHEN name ILIKE '%Apple%' THEN 2
        WHEN cname ILIKE '苹果%' THEN 1
        WHEN cname ILIKE '%苹果%' THEN 2
        ELSE 3
    END,
    symbol
LIMIT 10;

-- 测试复合查询性能
EXPLAIN ANALYZE 
SELECT symbol, name, cname 
FROM us_stocks_name 
WHERE (name ILIKE '%tech%' OR cname ILIKE '%科技%')
AND symbol IS NOT NULL
ORDER BY symbol
LIMIT 20;
*/
