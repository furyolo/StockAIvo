# 数据库迁移指南

## 概述

本项目使用SQLAlchemy ORM进行数据库管理，主要数据表由FastAPI应用自动创建。迁移文件主要用于性能优化、架构调整和数据清理。

> **详细操作指南** 请参考 [README.md](./README.md)

## 迁移文件列表

### 当前活跃迁移文件

| 文件名 | 作用 | 状态 | 执行顺序 |
|--------|------|------|----------|
| `create_search_indexes.py` | 为us_stocks_name表创建搜索优化索引 | ✅ 活跃 | 1 |
| `create_stock_symbols_index.py` | 为stock_symbols表创建symbol字段索引 | ✅ 活跃 | 2 |
| `drop_minute_table.py` | 删除stock_prices_minute表（数据迁移到Redis） | ✅ 活跃 | 3 |
| `drop_hourly_table.py` | 删除stock_prices_hourly表（功能废弃） | ✅ 活跃 | 4 |

### 已废弃迁移文件

以下文件已被删除，因为存在逻辑矛盾、架构已调整或功能重复：

- ~~`create_stock_news_table.py`~~ - 新闻表改为仅Redis缓存
- ~~`drop_stock_news_table.py`~~ - 对应创建文件已删除
- ~~`create_stock_news_table.sql`~~ - 对应Python脚本已删除
- ~~`drop_stock_news_table.sql`~~ - 对应Python脚本已删除
- ~~`add_search_indexes.sql`~~ - 功能由Python脚本实现，避免重复
- ~~`create_stock_symbols_index.sql`~~ - 功能由Python脚本实现，避免重复

## 数据库架构

### 核心数据表

#### 1. StockSymbols
```sql
-- 股票代码映射表，包含实时行情数据
-- 由SQLAlchemy自动创建，无需手动迁移
```

#### 2. StockPriceDaily
```sql
-- 日K线数据表 (ticker + date 复合主键)
-- 由SQLAlchemy自动创建，无需手动迁移
```

#### 3. StockPriceWeekly  
```sql
-- 周K线数据表 (ticker + date 复合主键)
-- 由SQLAlchemy自动创建，无需手动迁移
```

#### 4. UsStocksName
```sql
-- 美股名称表，支持中英文搜索
-- 由SQLAlchemy自动创建，需要手动创建搜索索引
```

### 缓存策略

#### Redis缓存（热点数据）
- 股票新闻数据（最近3天）
- 分钟线数据（实时性要求高）
- 搜索结果缓存

#### PostgreSQL（持久化存储）
- 历史K线数据（日线、周线）
- 股票基础信息
- 实时行情数据

## 迁移执行规范

### 新迁移文件创建

1. **文件命名规范**
   - 创建操作：`create_{object}_{type}.py`
   - 删除操作：`drop_{object}_{type}.py`
   - 索引操作：`create_{table}_index.py`

2. **代码规范**
   - 使用SQLAlchemy的`text()`函数执行原生SQL
   - 包含详细的错误处理和日志记录
   - 支持CONCURRENTLY选项避免锁表
   - 提供验证功能确保迁移成功

3. **文档要求**
   - 清晰的文件头注释说明迁移目的
   - 包含回滚方案（如有必要）
   - 列出执行前提和要求

4. **数据库连接配置**
   - 统一使用`get_database_url()`函数获取数据库连接
   - 优先使用`DATABASE_URL`环境变量
   - 支持向后兼容的独立环境变量配置
   - 避免硬编码的默认连接参数

### 迁移执行顺序

```bash
# 1. 创建搜索索引（提升搜索性能）
uv run database_migrations/create_search_indexes.py

# 2. 创建stock_symbols索引（优化symbol查询）
uv run database_migrations/create_stock_symbols_index.py

# 3. 删除分钟线表（数据已迁移到Redis）
uv run database_migrations/drop_minute_table.py

# 4. 删除小时线表（功能被10分钟线取代）
uv run database_migrations/drop_hourly_table.py
```

> **详细执行步骤和参数说明** 请参考 [README.md](./README.md#使用方法)

## 架构变更历史

### v3.0.0+ 架构优化

#### 变更内容
1. **新闻数据迁移**：从PostgreSQL迁移到Redis缓存
   - 删除stock_news表
   - 新闻数据仅保留最近3天在Redis中

2. **分钟线数据迁移**：从PostgreSQL迁移到Redis缓存
   - 删除stock_prices_minute表
   - 分钟线数据通过API实时获取

3. **小时线功能废弃**：被10分钟线取代
   - 删除stock_prices_hourly表
   - 使用10分钟粒度数据替代

#### 性能优化
- 为us_stocks_name表创建GIN索引优化模糊搜索
- 为stock_symbols表创建symbol索引提升查询性能
- 使用CONCURRENTLY选项创建索引避免锁表

> **索引技术细节和性能优化指南** 请参考 [README.md](./README.md#索引说明)

### 数据初始化流程

```
1. 启动应用 → 2. 自动创建表结构 → 3. 执行性能优化迁移 → 4. 手动更新基础数据
     ↓               ↓                      ↓                      ↓
  main.py lifespan    SQLAlchemy          迁移脚本              API接口调用
   自动创建           ORM管理              索引优化              数据获取
```

## 最佳实践

### 1. 索引创建
- 使用`CONCURRENTLY`选项避免锁表
- 先检查索引是否存在再创建
- 创建后执行`ANALYZE`更新统计信息

### 2. 表删除
- 先删除相关索引和约束
- 使用`DROP TABLE ... CASCADE`确保清理干净
- 提供验证功能确认删除成功

### 3. 错误处理
- 使用事务确保操作原子性
- 提供详细的错误日志和回滚方案
- 支持dry-run模式预览操作

### 4. 性能考虑
- 大表操作选择在低峰期执行
- 使用CONCURRENTLY避免影响线上服务
- 监控操作执行时间和资源使用

## 故障排除

> **详细故障排除步骤和解决方案** 请参考 [README.md](./README.md#故障排除)

### 常见问题速查

1. **权限错误** - 参考README.md中的权限设置
2. **锁表问题** - 参考README.md中的锁表解决方案  
3. **索引创建失败** - 参考README.md中的pg_trgm扩展检查

### 验证迁移结果

> **详细的验证SQL和性能测试** 请参考 [README.md](./README.md#验证索引效果)

## 未来规划

### 计划中的迁移
1. **分区表优化**：为大型历史数据表创建分区
2. **读写分离**：配置主从数据库支持
3. **缓存层增强**：引入多层缓存策略

### 迁移自动化
- 集成到CI/CD流程
- 自动回滚机制
- 迁移前备份策略

---

**注意**: 所有迁移操作都应在测试环境充分验证后再在生产环境执行。