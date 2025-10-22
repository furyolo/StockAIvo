# 数据初始化指南

## 概述

由于优化了Docker配置，移除了存在问题的自动数据初始化服务。现在提供更灵活的手动数据初始化方式。

## 首次部署后的数据初始化

### 1. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 检查服务状态
docker-compose ps
docker-compose logs backend
```

### 2. 等待服务就绪

等待所有服务启动完成（大约30秒），然后检查健康状态：

```bash
# 检查后端服务健康状态
curl http://localhost:3224/health

# 检查缓存状态
curl http://localhost:3224/cache-stats
```

### 3. 初始化基础数据

#### 方法一：使用curl命令

```bash
# 更新美股名称数据
curl -X POST "http://localhost:3224/stocks/us-stock-names/update"

# 更新实时行情数据
curl -X POST "http://localhost:3224/stocks/realtime-quotes/update"
```

#### 方法二：使用API文档

1. 打开浏览器访问：`http://localhost:3224/docs`
2. 在"股票数据"部分找到：
   - `POST /stocks/us-stock-names/update`
   - `POST /stocks/realtime-quotes/update`
3. 点击"Try it out"按钮执行

#### 方法三：使用Postman或其他API工具

导入以下请求：

```http
### 更新美股名称数据
POST http://localhost:3224/stocks/us-stock-names/update
Content-Type: application/json

{}

### 更新实时行情数据
POST http://localhost:3224/stocks/realtime-quotes/update
Content-Type: application/json

{}
```

### 4. 验证数据初始化

```bash
# 检查美股名称数据
curl "http://localhost:3224/search/stocks?q=AAPL"

# 获取股票数据测试
curl "http://localhost:3224/stocks/AAPL/daily"

# 检查待处理数据状态
curl "http://localhost:3224/check-pending-data"
```

## 开发环境数据初始化

开发环境推荐使用以下方式：

```bash
# 使用启动脚本（推荐）
./start-dev.sh

# 或手动启动
cd backend && uv run dev

# 然后调用API接口
curl -X POST "http://127.0.0.1:8000/stocks/us-stock-names/update"
curl -X POST "http://127.0.0.1:8000/stocks/realtime-quotes/update"
```

## 定期数据更新

### 手动更新

```bash
# 更新美股名称数据（建议每周一次）
curl -X POST "http://localhost:3224/stocks/us-stock-names/update"

# 更新实时行情数据（建议每日开盘前）
curl -X POST "http://localhost:3224/stocks/realtime-quotes/update"
```

### 自动化脚本

创建定期更新的cron任务：

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天早上8:30更新数据）
30 8 * * 1-5 curl -X POST "http://localhost:3224/stocks/realtime-quotes/update"
0 9 * * 1 curl -X POST "http://localhost:3224/stocks/us-stock-names/update"
```

## 常见问题排查

### 1. 服务启动失败

```bash
# 检查容器状态
docker-compose ps

# 查看错误日志
docker-compose logs backend
docker-compose logs postgres
docker-compose logs redis
```

### 2. 数据更新失败

```bash
# 检查API服务状态
curl http://localhost:3224/health

# 检查数据库连接
docker-compose exec postgres psql -U stockaivo -d stock -c "SELECT COUNT(*) FROM stock_symbols;"

# 检查Redis连接
docker-compose exec redis redis-cli ping
```

### 3. 数据为空

```bash
# 检查缓存统计
curl http://localhost:3224/cache-stats

# 手动触发数据持久化
curl -X POST "http://localhost:3224/persist-data"
```

## 数据初始化流程图

```
1. 启动服务 → 2. 健康检查 → 3. 更新美股名称 → 4. 更新实时行情 → 5. 验证数据
     ↓               ↓               ↓                  ↓               ↓
  docker-compose    /health       /us-stock-names    /realtime-quotes   /search/stocks
     up -d            API            API                  API              API
```

## 性能建议

1. **首次初始化**：建议在非高峰期进行，数据获取可能需要几分钟
2. **定期更新**：美股名称数据每周更新一次，实时行情数据每个交易日更新
3. **缓存利用**：系统会自动缓存数据，后续请求会更快
4. **监控**：定期检查 `/cache-stats` 和 `/health` 端点

## 备份策略

```bash
# 备份数据库
docker-compose exec postgres pg_dump -U stockaivo stock > backup_$(date +%Y%m%d).sql

# 备份Redis数据
docker-compose exec redis redis-cli BGSAVE
```

通过这种手动初始化方式，可以获得更可靠和灵活的数据管理体验。
