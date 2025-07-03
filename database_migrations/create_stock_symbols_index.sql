-- 为stock_symbols表的symbol字段创建索引
-- 创建时间: 2025-07-03
-- 目的: 优化基于symbol字段的查询性能，特别是get_fullsymbol_from_db函数中的查询

-- 开始事务
BEGIN;

-- 为symbol字段创建B-tree索引
-- 使用CONCURRENTLY避免锁表，适合生产环境
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_symbols_symbol 
ON stock_symbols (symbol);

-- 提交事务
COMMIT;

-- 验证索引创建
-- 查看表的所有索引
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'stock_symbols'
ORDER BY indexname;

-- 分析表统计信息，帮助查询优化器
ANALYZE stock_symbols;

-- 性能测试查询示例（仅用于验证，不会执行）
/*
-- 测试symbol查询性能
EXPLAIN ANALYZE 
SELECT fullsymbol 
FROM stock_symbols 
WHERE symbol = 'AAPL';

-- 查看索引使用情况
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE tablename = 'stock_symbols';
*/
