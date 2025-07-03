# 数据库迁移脚本

本目录包含用于优化数据库查询性能的索引创建脚本。

## 文件说明

### 搜索功能优化
- `add_search_indexes.sql` - 原始SQL脚本，包含所有搜索索引创建语句
- `create_search_indexes.py` - Python执行脚本，自动化搜索索引创建过程

### stock_symbols表优化
- `create_stock_symbols_index.sql` - 为stock_symbols表创建索引的SQL脚本
- `create_stock_symbols_index.py` - Python执行脚本，自动化stock_symbols索引创建

- `README.md` - 本说明文件

## 索引说明

为 `us_stocks_name` 表创建以下索引以优化搜索性能：

### 1. GIN索引（全文搜索）
- `idx_us_stocks_name_name_gin` - name字段的trigram索引
- `idx_us_stocks_name_cname_gin` - cname字段的trigram索引

**用途**: 支持模糊匹配查询（ILIKE '%keyword%'），特别适合包含匹配。

### 2. B-tree索引（前缀匹配）
- `idx_us_stocks_name_name_btree` - name字段的标准索引
- `idx_us_stocks_name_cname_btree` - cname字段的标准索引

**用途**: 支持前缀匹配查询（ILIKE 'keyword%'）和排序操作。

### 3. 复合索引
- `idx_us_stocks_name_composite` - (symbol, name, cname)复合索引

**用途**: 优化多字段查询和排序操作。

## stock_symbols表索引

为 `stock_symbols` 表创建以下索引以优化AKShare数据获取性能：

### symbol字段索引
- `idx_stock_symbols_symbol` - symbol字段的B-tree索引

**用途**: 优化 `get_fullsymbol_from_db` 函数中的查询，该函数在每次从AKShare获取数据前都会被调用。

**查询模式**: `SELECT fullsymbol FROM stock_symbols WHERE symbol = ?`

**性能影响**:
- 当前表有11,841条记录
- 没有索引时会进行全表扫描
- 创建索引后查询时间从O(n)降低到O(log n)

## 使用方法

### 方法1: 使用Python脚本

#### 创建搜索索引
```bash
# 在项目根目录执行
cd database_migrations
uv run create_search_indexes.py
```

#### 创建stock_symbols索引
```bash
# 在项目根目录执行
cd database_migrations
uv run create_stock_symbols_index.py

# 可选：创建索引后测试查询性能
uv run create_stock_symbols_index.py --test
```

**优势**:
- 自动检查依赖（pg_trgm扩展）
- 错误处理和日志记录
- 验证索引创建结果
- 使用CONCURRENTLY避免锁表

### 方法2: 直接执行SQL

```bash
# 连接到PostgreSQL数据库
psql -h localhost -U your_username -d stockaivo_db

# 执行SQL脚本
\i add_search_indexes.sql
```

## 前置条件

1. **数据库表存在**: 确保 `us_stocks_name` 表已创建
2. **pg_trgm扩展**: 需要PostgreSQL的pg_trgm扩展支持trigram索引
3. **数据库权限**: 需要CREATE INDEX权限

## 性能预期

创建索引后，搜索查询性能预期提升：

- **前缀匹配** (name ILIKE 'Apple%'): 从全表扫描到索引查找
- **模糊匹配** (name ILIKE '%apple%'): 显著提升，特别是大数据集
- **排序操作**: ORDER BY symbol/name 性能提升
- **复合查询**: 多条件搜索性能优化

## 注意事项

### 生产环境
- 使用 `CONCURRENTLY` 选项避免锁表
- 建议在低峰期执行
- 监控索引创建进度和系统资源

### 存储空间
- GIN索引会占用额外存储空间
- 预估每个GIN索引占用原表20-30%的空间
- 确保有足够的磁盘空间

### 维护
- 新数据插入时索引会自动更新
- 定期运行 `ANALYZE us_stocks_name` 更新统计信息
- 监控索引使用情况和查询性能

## 验证索引效果

### 查看索引列表
```sql
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'us_stocks_name'
ORDER BY indexname;
```

### 性能测试
```sql
-- 测试前缀匹配
EXPLAIN ANALYZE 
SELECT symbol, name, cname 
FROM us_stocks_name 
WHERE name ILIKE 'Apple%' 
LIMIT 10;

-- 测试模糊匹配
EXPLAIN ANALYZE 
SELECT symbol, name, cname 
FROM us_stocks_name 
WHERE name ILIKE '%apple%' OR cname ILIKE '%苹果%'
LIMIT 10;
```

### 索引使用统计
```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE tablename = 'us_stocks_name'
ORDER BY idx_scan DESC;
```

## 回滚方案

如果需要删除索引：

```sql
-- 删除GIN索引
DROP INDEX CONCURRENTLY IF EXISTS idx_us_stocks_name_name_gin;
DROP INDEX CONCURRENTLY IF EXISTS idx_us_stocks_name_cname_gin;

-- 删除B-tree索引
DROP INDEX CONCURRENTLY IF EXISTS idx_us_stocks_name_name_btree;
DROP INDEX CONCURRENTLY IF EXISTS idx_us_stocks_name_cname_btree;

-- 删除复合索引
DROP INDEX CONCURRENTLY IF EXISTS idx_us_stocks_name_composite;
```

## 故障排除

### 常见问题

1. **pg_trgm扩展不存在**
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

2. **权限不足**
   - 确保用户有CREATE权限
   - 检查数据库连接配置

3. **索引创建失败**
   - 检查表是否存在
   - 确认字段名称正确
   - 查看PostgreSQL日志

4. **CONCURRENTLY失败**
   - 不能在事务中使用CONCURRENTLY
   - 确保没有长时间运行的事务

### 日志查看
```bash
# 查看PostgreSQL日志
tail -f /var/log/postgresql/postgresql-*.log
```
