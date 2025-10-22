# StockAIvo 项目启动指南

## 🚀 快速启动

### 开发环境

#### Windows 系统
```bash
# 一键启动开发环境
./start-dev.bat
```

#### Linux/Mac 系统
```bash
# 一键启动开发环境
./start-dev.sh

# 查看服务状态
./start-dev.sh status

# 停止所有服务
./start-dev.sh stop

# 查看日志
./start-dev.sh logs
```

> 💡 提示：后端 FastAPI 代码与依赖已移动至 `backend/` 子目录。若需手动运行 `uv ...` 或 `python database_migrations/...` 命令，请先 `cd backend`。

### 生产环境

#### 跨平台（推荐）
```bash
# 启动生产环境
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止所有服务
docker-compose down

# 重启服务
docker-compose restart

# 清理数据（谨慎使用）
docker-compose down -v
```

## 🐳 Docker 容器化部署说明

### 开发环境（本地脚本 - 推荐）
```bash
# Windows
./start-dev.bat

# Linux/Mac  
./start-dev.sh
```

### 生产环境（Docker - 推荐）
```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止所有服务
docker-compose down

# 清理数据（谨慎使用）
docker-compose down -v
```

### 为什么选择这种架构？

- **开发环境**: 本地脚本提供快速热重载和开发便利性
- **生产环境**: Docker容器化提供环境一致性、可移植性和生产级特性

## 📋 服务信息

### 开发环境
- **前端服务**: http://localhost:3223
- **后端API**: http://127.0.0.1:8000
- **API文档**: http://127.0.0.1:8000/docs
- **健康检查**: http://127.0.0.1:8000/health

### 生产环境
- **前端服务**: http://localhost:3223
- **后端API**: http://127.0.0.1:3224
- **API文档**: http://127.0.0.1:3224/docs
- **健康检查**: http://127.0.0.1:3224/health

## 🔧 环境配置

### 必需环境变量
```bash
# 数据库连接
DATABASE_URL=postgresql://user:password@localhost/dbname

# Redis 连接
REDIS_URL=redis://localhost:6379/0

# AI 服务配置
OPENAI_API_BASE=your_ai_api_base
OPENAI_API_KEY=your_ai_api_key
```

### 可选环境变量
```bash
# AI 模型配置
AI_DEFAULT_MODEL=gemini-2.5-flash
AI_TECHNICAL_ANALYSIS_MODEL=gemini-2.5-pro
AI_SYNTHESIS_MODEL=gemini-2.5-pro

# 服务配置
API_BASE_URL=http://127.0.0.1:3224
FRONTEND_URL=http://localhost:3223
```

## 🛠️ 数据库管理

### 初始化数据库
```bash
# 启动应用后自动创建表结构（通过SQLAlchemy）
cd backend && uv run dev

# Docker 环境初始化（包含自动迁移）
docker-compose up -d
```

### 自动数据库迁移
**Docker环境和生产环境会自动执行性能优化迁移：**

- ✅ **自动创建搜索索引**：为us_stocks_name表创建GIN和B-tree索引，优化搜索性能
- ✅ **自动创建stock_symbols索引**：为stock_symbols表创建symbol字段索引，提升查询速度
- ❌ **不执行废弃表清理**：新数据库不需要清理废弃表（如stock_prices_minute、stock_prices_hourly）

**迁移控制环境变量：**
```bash
# 启用自动迁移（默认）
RUN_DATABASE_MIGRATIONS=true

# 禁用自动迁移（适用于已有数据库）
RUN_DATABASE_MIGRATIONS=false
```

### 手动数据迁移
如果需要手动执行迁移或清理废弃表：

```bash
# 创建搜索索引（优化模糊搜索性能）
cd backend && python database_migrations/create_search_indexes.py

# 创建stock_symbols索引（优化symbol查询）
cd backend && python database_migrations/create_stock_symbols_index.py

# 清理废弃表（仅在新数据库需要时执行）
cd backend && python database_migrations/drop_minute_table.py
cd backend && python database_migrations/drop_hourly_table.py

# 查看详细的迁移说明
cd backend && cat database_migrations/MIGRATIONS.md
```

### 健康检查
```bash
# 检查后端服务健康状态
curl http://127.0.0.1:8000/health

# 检查缓存统计信息
curl http://127.0.0.1:8000/cache-stats
```

## 📊 监控和日志

### 日志文件位置
- **前端日志**: `logs/frontend/`
- **后端日志**: `logs/backend/`
- **Nginx日志**: `logs/nginx/`

### 实时监控
```bash
# 查看前端日志
tail -f logs/frontend/production.log

# 查看后端日志
tail -f logs/backend/production.log

# Docker 日志
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 系统状态
```bash
# 缓存统计
curl http://127.0.0.1:3224/cache-stats

# 数据库连接测试
python -c "import sqlalchemy; print('Database OK')"
```

## 🔄 开发工作流

### 日常开发
1. **启动开发环境**: `./start-dev.sh` 或 `./start-dev.bat`
2. **代码修改**: 实时热重载
3. **测试运行**: `uv run pytest tests/ -v`
4. **类型检查**: `uv run mypy stockaivo/`
5. **停止服务**: 关闭对应窗口或运行停止命令

### 部署流程
1. **代码更新**: `git pull origin main`
2. **依赖更新**: 
   - 后端: `uv sync`
   - 前端: `pnpm install`
3. **构建应用**: `pnpm build`
4. **启动生产环境**: `docker-compose up -d`
5. **健康检查**: `curl http://localhost:3223/health`

## 🚨 故障排除

### 常见问题

#### 端口冲突
```bash
# 检查端口占用
netstat -tulpn | grep :3223
netstat -tulpn | grep :3224
netstat -tulpn | grep :8000

# 更改端口配置
# 编辑 .env 文件中的相关配置
```

#### 数据库连接失败
```bash
# 检查数据库服务
systemctl status postgresql

# 测试连接
psql -h localhost -U username -d dbname

# 查看连接日志
tail -f /var/log/postgresql/postgresql-*.log
```

#### Redis 连接失败
```bash
# 检查 Redis 服务
systemctl status redis

# 测试连接
redis-cli ping

# 查看 Redis 日志
tail -f /var/log/redis/redis-server.log
```

#### 依赖问题
```bash
# 重新安装后端依赖
rm -rf .venv
uv venv
uv sync --extra dev

# 重新安装前端依赖
rm -rf frontend/node_modules
cd frontend && pnpm install
```

### 性能优化

### 缓存优化
```bash
# 清理 Redis 缓存
redis-cli FLUSHDB

# 查看缓存统计
redis-cli INFO memory
```

### 数据库优化
```bash
# 数据库索引优化
python -c "
from stockaivo.models import *
# 在这里添加索引优化代码
"
```

## 📞 支持

如果遇到问题，请：
1. 查看日志文件获取详细信息
2. 运行健康检查脚本诊断问题
3. 检查环境变量配置
4. 参考项目文档和CLAUDE.md

---

**提示**: 建议在开发时使用一键启动脚本，在生产环境使用Docker容器化部署以获得最佳的性能和稳定性。

---

## 📝 更新日志

### v3.0.5 (2025-09-22)
- 实现自动数据库迁移机制，Docker环境自动执行性能优化迁移
- 新增 `stockaivo/migration_manager.py` 模块管理数据库迁移
- 在应用启动时自动创建搜索索引和stock_symbols索引
- 添加 `RUN_DATABASE_MIGRATIONS` 环境变量控制迁移执行
- 优化数据库初始化流程，确保生产环境开箱即用的性能

### v3.0.4 (2025-09-22)
- 删除冗余的 `start-prod.bat` 和 `start-prod.sh` 脚本
- 统一使用 `docker-compose.yml` 进行生产环境部署
- 删除不必要的 `docker-compose.dev.yml` 和 `Dockerfile.dev`
- 简化部署架构，提高维护效率
