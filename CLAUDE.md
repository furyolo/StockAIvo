# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用开发命令

### 后端开发 (Python 3.12 + FastAPI)
```bash
# 安装依赖
uv sync --extra dev

# 开发服务器启动
uv run dev                          # 开发服务器 (http://127.0.0.1:8000)

# 类型检查和测试
uv run mypy stockaivo/              # MyPy类型检查
uv run pytest tests/ -v            # 运行所有后端测试
uv run pytest tests/test_file.py -v # 运行单个测试文件
uv run pytest tests/test_file.py::test_func -v # 运行单个测试函数

# 生产环境启动
uv run start                        # 生产服务器
```

### 前端开发 (React 19 + TypeScript)
```bash
# 安装依赖
cd frontend && pnpm install

# 开发服务器
cd frontend && pnpm dev             # 开发服务器 (http://localhost:5173)

# 构建和测试
cd frontend && pnpm build           # 生产构建
cd frontend && pnpm test            # 运行测试
cd frontend && pnpm lint            # ESLint检查
cd frontend && pnpm test:ui         # UI测试界面
```

### 数据库和缓存
```bash
# 数据库迁移
python database_migrations/create_stock_news_table.py
python database_migrations/drop_stock_news_table.py

# 系统监控
curl http://127.0.0.1:8000/health  # 健康检查
curl http://127.0.0.1:8000/cache-stats # 缓存统计
```

## 项目架构概览

### 整体架构
StockAIvo是一个现代化的全栈美股分析平台，采用前后端分离架构：

- **前端**: React 19 + TypeScript + Vite + TailwindCSS + TradingView图表
- **后端**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + LangGraph
- **数据库**: PostgreSQL (主存储) + Redis (三级缓存)
- **数据源**: AKShare (美股数据) + TickerTick (新闻数据)

### 核心架构模式

#### 1. 三级缓存数据管理
```
Redis → PostgreSQL → AKShare
```
- **Redis缓存**: 热点数据和新闻数据，毫秒级响应
- **PostgreSQL**: 历史数据和基础信息，持久化存储
- **AKShare**: 外部数据源，当缓存和数据库都缺失时调用

#### 2. 多Agent并行AI分析
基于LangGraph的并行分析架构：
- **技术分析Agent**: MA、RSI、MACD、布林带等技术指标
- **基本面分析Agent**: 公司基本面数据分析
- **新闻情感Agent**: 基于实时新闻的情绪分析
- **综合分析Agent**: 整合多个Agent的分析结果

#### 3. 现代化依赖注入
使用FastAPI的`Annotated`类型系统：
```python
DatabaseDep = Annotated[Session, Depends(get_db)]
CacheDep = Annotated[redis.Redis, Depends(get_redis)]
```

### 数据库架构

#### 核心数据模型
- **StockSymbols**: 股票代码映射表，包含实时行情数据
- **StockPriceDaily**: 日K线数据表 (ticker + date 复合主键)
- **StockPriceWeekly**: 周K线数据表 (ticker + date 复合主键)
- **UsStocksName**: 美股名称表，支持中英文搜索

#### 数据流设计
1. **数据获取**: AKShare API获取美股数据
2. **数据验证**: `ValidationResult`类 + 价格边界修复 + 5%异常容忍
3. **缓存策略**: Redis优先，数据库次之，API最后
4. **持久化**: 后台调度器批量写入PostgreSQL

### 关键服务模块

#### data_service.py
核心数据查询逻辑，协调数据库、缓存和外部数据源：
- `MarketStateManager`: 统一市场状态和交易日管理
- `get_stock_data()`: 多时间粒度数据获取 (daily/weekly/10min/minute)
- 智能缓存失效策略

#### ai/orchestrator.py
LangGraph多Agent工作流编排：
- 并行执行多个分析Agent
- 流式响应支持
- 状态管理和错误处理

#### cache_manager.py
Redis缓存管理：
- 三级缓存策略实现
- 缓存统计和健康检查
- 待处理数据管理

### API设计模式

#### RESTful API结构
- `/stocks/{ticker}/{period}`: 股票数据获取
- `/ai/analyze-parallel`: 并行AI分析 (推荐)
- `/ai/analyze-stream`: 流式AI分析
- `/search/stocks`: 股票搜索和建议
- `/stocks/realtime-quotes/update`: 实时行情更新
- `/stocks/us-stock-names/update`: 美股名称数据更新

#### 统一响应格式
所有API返回统一的JSON结构：
```json
{
  "success": true,
  "data": {},
  "message": "操作成功",
  "timestamp": "2025-08-11T00:00:00Z"
}
```

### 测试策略

#### 后端测试
- **单元测试**: 核心业务逻辑测试 (`tests/test_data_service.py`)
- **集成测试**: API端点测试 (`tests/test_*.py`)
- **性能测试**: 搜索性能和数据获取性能测试

#### 前端测试
- **组件测试**: React组件测试 (`src/components/__tests__/`)
- **集成测试**: Vitest + Testing Library
- **端到端测试**: 用户交互流程测试

### 开发注意事项

#### 数据验证机制
- 使用`ValidationResult`类进行分层验证
- 价格边界修复：异常数据自动修复 (5%容忍度)
- 交易日历感知：基于NYSE交易日历的智能日期处理

#### 异常处理
- 分层异常类：`ValidationException`、`DataServiceException`、`AIServiceException`
- 全局异常处理器：`stockaivo.exceptions.register_exception_handlers()`
- 中间件系统：请求日志、性能监控、安全头

#### AI模型配置
- 支持按Agent类型配置专用AI模型
- 默认使用Google Gemini，可通过环境变量配置：
  ```bash
  AI_DEFAULT_MODEL="gemini-2.5-flash"
  AI_TECHNICAL_ANALYSIS_MODEL="gemini-2.5-pro"
  AI_SYNTHESIS_MODEL="gemini-2.5-pro"
  ```

### 性能优化

#### 数据库优化
- 索引策略：为常用查询字段创建索引
- 批量操作：使用批量UPSERT减少数据库调用
- 连接池：SQLAlchemy连接池管理

#### 缓存优化
- Redis缓存热点数据，减少数据库查询
- 智能缓存失效：基于市场状态和数据更新时间
- 新闻数据仅使用Redis缓存，避免持久化

#### AI分析优化
- 并行Agent执行，分析速度提升2-3倍
- 流式响应：实时输出分析结果
- 模型专用化：不同分析类型使用专用模型

### 环境配置

#### 必需环境变量
```bash
DATABASE_URL=postgresql://user:password@localhost/dbname
REDIS_URL=redis://localhost:6379/0
OPENAI_API_BASE=your_ai_api_base
OPENAI_API_KEY=your_ai_api_key
```

#### 可选环境变量
```bash
AI_DEFAULT_MODEL="gemini-2.5-flash"
AI_TECHNICAL_ANALYSIS_MODEL="gemini-2.5-pro"
AI_SYNTHESIS_MODEL="gemini-2.5-pro"
```