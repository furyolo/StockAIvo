# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 一键启动脚本

### Windows 环境
```cmd
# 开发环境启动 (推荐)
.\start-dev.bat                     # 自动启动前端和后端开发服务器

# 生产环境启动
.\start-prod.bat                    # 构建并启动生产环境
```

### Linux/Mac 环境  
```bash
# 开发环境启动
./start-dev.sh                      # 后台启动服务，支持日志查看

# 生产环境启动
./start-prod.sh                     # 生产环境部署

# 管理命令
./start-dev.sh status              # 查看服务状态
./start-dev.sh stop                # 停止所有服务
./start-dev.sh logs                # 查看实时日志
```

**Windows启动脚本特性:**
- ✅ **智能颜色支持**: 自动检测PowerShell可用性，提供彩色输出
- ✅ **依赖检查**: 自动验证pnpm、uv、Node.js、Python环境
- ✅ **错误处理**: 详细的错误提示和安装指导
- ✅ **跨终端兼容**: 支持CMD、PowerShell、Windows Terminal

## 常用开发命令

### 后端开发 (Python 3.13 + FastAPI)
```bash
# 安装依赖
uv sync --extra dev

# 开发服务器启动
uv run dev                          # 开发服务器 (http://127.0.0.1:8000)

# 类型检查和测试
uv run mypy stockaivo/              # MyPy类型检查 (渐进式类型检查策略)
uv run pytest tests/ -v            # 运行所有后端测试
uv run pytest tests/test_file.py -v # 运行单个测试文件
uv run pytest tests/test_file.py::test_func -v # 运行单个测试函数

# 开发工作流建议
uv run mypy stockaivo/ && uv run pytest tests/ -v  # 类型检查+测试一键运行

# 生产环境启动
uv run start                        # 生产服务器
```

### 前端开发 (React 19 + TypeScript + Mantine UI)
```bash
# 安装依赖
cd frontend && pnpm install

# 开发服务器
cd frontend && pnpm dev             # 开发服务器 (http://localhost:3223)

# 构建和测试
cd frontend && pnpm build           # 生产构建
cd frontend && pnpm test            # 运行测试
cd frontend && pnpm lint            # ESLint检查
cd frontend && pnpm test:ui         # UI测试界面
```

## 容器部署与运维要点
- 使用 `docker-compose up --build -d` 一次性启动 FastAPI、Redis、PostgreSQL、前端与 Nginx；重新调整 `.env` 后需重新构建。
- 后端镜像基于多阶段构建与 `uv sync --frozen`，体积约 1.3GB；如要继续瘦身请评估 `akshare`、`google-api-python-client` 等大依赖。
- Dockerfile 的 `HEALTHCHECK` 仅在首次成功后写入 `/tmp/.healthcheck_done`，避免 30 秒轮询打断 SSE 长连接；如需恢复轮询请确认前端流式输出不会被截断。
- Nginx 代理 `/api/` 时已关闭请求/响应缓冲、`gzip` 与 `proxy_request_buffering`，强制 `chunked_transfer_encoding`，确保容器环境的流式响应与开发环境一致。
- 容器内无法访问宿主 `localhost`，若本地提供 LLM 服务，请将 `.env` 中 `OPENAI_API_BASE` 设置为 `http://host.docker.internal:3222/v1`（或对应内网地址）。
- 通过 `docker logs -f stockaivo-backend-1` 可同时观察健康检查、SSE 推送与 APScheduler 任务日志；日志条目会精确到秒并附带处理摘要。

#### 前端UI架构重构 (v3.0.0+)
**2025年9月17日完成了全面的UI框架迁移:**

**从 shadcn/ui + TailwindCSS → Mantine UI 8.3.1**

**重构详情:**
- **组件库升级**: 完全替换shadcn/ui组件为Mantine原生组件
  - Card → Paper, Button → Button, Input → TextInput
  - Select → Select, Date-picker → DateInput
  - 删除了@radix-ui系列依赖和class-variance-authority
- **样式系统重构**: 移除TailwindCSS，采用Mantine CSS-in-JS + 原生CSS
  - 保留自定义动画(spin, bounce, pulse)和滚动条样式
  - 使用Mantine颜色变量和主题系统
- **图标库迁移**: lucide-react → @tabler/icons-react
- **布局系统现代化**: 
  - div + className → Stack/Group/Grid组件
  - 支持响应式布局和灵活间距控制
- **主题配置**: 
  - 集成MantineProvider和Notifications
  - 支持auto色彩方案(自动适配明暗主题)

**核心组件重构:**
- **App.tsx**: 主布局使用Container/Stack/Paper重新设计，集成动态吸顶导航栏
- **StockSearch.tsx**: 智能搜索用TextInput/Paper重构，保持所有交互功能
- **AIAnalysis.tsx**: AI分析面板使用Alert/ScrollArea/DateInput等现代组件
- **DynamicNavbar.tsx**: 全新动态吸顶导航栏组件，支持滚动隐藏/显示和鼠标悬停交互

**交互体验优化:**
- **动态导航栏**: 
  - 固定定位，Logo左侧、搜索框居中的专业布局
  - 智能滚动检测：向下滚动自动隐藏，向上滚动自动显示
  - 鼠标悬停顶部80px区域自动显示导航栏
  - 平滑CSS动画过渡，使用GPU加速的transform属性
  - 响应式设计：移动端优化布局，禁用鼠标悬停功能
  - 防抖优化：避免频繁触发，提升性能

**开发体验提升:**
- 更好的TypeScript集成和类型安全
- 统一的设计系统和组件API
- 更丰富的内置功能(通知、日期选择、表单验证等)
- 更小的包体积和更好的性能优化

### 数据库和缓存
```bash
# 数据库迁移
python database_migrations/create_stock_news_table.py
python database_migrations/drop_stock_news_table.py

# 系统监控
curl http://127.0.0.1:8000/health  # 健康检查（容器模式下首次成功后即视为通过）
curl http://127.0.0.1:8000/cache-stats # 缓存统计
```

## 项目架构概览

### 整体架构
StockAIvo是一个现代化的全栈美股分析平台，采用前后端分离架构：

- **前端**: React 19.1.0 + TypeScript 5.8.3 + Vite 7.0.0 + Mantine UI 8.3.1 + TradingView Lightweight Charts 5.0.8
- **后端**: Python 3.13 + FastAPI 0.115.13+ + SQLAlchemy 2.0.41+ + LangGraph 0.4.8+
- **数据库**: PostgreSQL (主存储) + Redis 8.2.0+ (三级缓存)
- **数据源**: AKShare 1.17.6+ (美股数据) + TickerTick (新闻数据)
- **AI引擎**: Google Generative AI 0.8.5+ (Gemini模型)
- **工具链**: uv (Python包管理) + pnpm 10.14.0 (前端包管理) + MyPy 1.8.0+ (类型检查)

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
- **技术分析Agent**: MA、RSI、MACD、布林带等技术指标，增强数据验证机制
- **基本面分析Agent**: 公司基本面数据分析
- **新闻情感Agent**: 基于实时新闻的情绪分析
- **综合分析Agent**: 整合多个Agent的分析结果
- **结构化预测Agent**: 基于原始分析结果生成概率预测，支持动态Prompt适配
- **⚠️ 执行依赖策略**: 综合分析仅在技术分析成功时执行，确保分析质量
- **🔧 异常处理优化**: 并行执行时的类型安全异常处理，防止Exception对象调用.items()方法
- **✅ 数据验证增强**: 所有Agent在数据缺失时正确跳过LLM调用，统一返回None，避免无效分析和资源浪费

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

#### stockaivo/data_service.py
核心数据查询逻辑，协调数据库、缓存和外部数据源：
- `MarketStateManager`: 统一市场状态和交易日管理
- `get_stock_data()`: 多时间粒度数据获取 (daily/weekly/10min/minute)
- 智能缓存失效策略和数据验证

#### stockaivo/ai/orchestrator.py
LangGraph多Agent工作流编排：
- 并行执行多个分析Agent (技术分析、基本面分析、新闻情感分析)
- 流式响应支持和状态管理
- 错误处理和Agent间通信
- **执行依赖控制**: 综合分析仅在技术分析成功时执行

#### stockaivo/ai/agents.py
多Agent分析系统核心实现：
- **数据验证机制**: 所有Agent在执行前检查必需数据，确保只有在数据可用时才调用LLM
- **Agent名称规范化**: 统一所有Agent调用中的agent_name参数传递，支持专用模型配置和日志追踪
- **动态Prompt生成**: 结构化预测Agent根据实际可用分析结果动态调整提示词内容
- **智能文本适配**: 根据技术分析、基本面分析、新闻情感分析的可用性调整预测方向和置信度评估描述
- **自然语言优化**: 将技术性表述改为LLM易理解的自然语言，提升预测准确性

#### stockaivo/routers/ai.py  
AI分析API路由处理：
- **类型安全异常处理**: 在处理asyncio.gather()结果时添加isinstance检查，防止Exception对象调用.items()
- **并行执行优化**: 结构化预测支持并行Agent执行，提升性能
- **状态管理改进**: 优化分析结果合并逻辑，保留data_collector等关键信息

#### stockaivo/cache_manager.py
Redis缓存管理：
- 三级缓存策略实现 (Redis → PostgreSQL → AKShare)
- 缓存统计和健康检查
- 待处理数据管理和批量UPSERT优化

#### stockaivo/models.py
SQLAlchemy 2.0数据模型定义：
- `StockSymbols`: 股票基础信息和实时行情
- `StockPriceDaily/Weekly`: K线数据表 (复合主键优化)
- `UsStocksName`: 美股名称表 (支持中英文搜索)

#### stockaivo/dependencies.py
现代化依赖注入系统：
- `DatabaseDep = Annotated[Session, Depends(get_db)]`
- `CacheDep = Annotated[redis.Redis, Depends(get_redis)]`
- 统一的依赖管理和资源清理

### API设计模式

#### RESTful API结构
- `/stocks/{ticker}/{period}`: 股票数据获取 (daily/weekly/10min/minute)
- `/stocks/{ticker}/news`: 股票新闻数据获取 (Redis缓存)
- `/ai/analyze-parallel`: 并行AI分析 (推荐，速度提升2-3倍)
- `/ai/analyze-sequential`: 顺序AI分析
- `/search/stocks?q=keyword`: 股票搜索和建议
- `/search/stocks/suggestions?q=keyword`: 实时搜索建议
- `/stocks/realtime-quotes/update`: 更新实时行情数据
- `/stocks/us-stock-names/update`: 更新美股名称数据
- `/health`: 系统健康检查
- `/cache-stats`: 缓存统计信息

#### 数据管理API示例
```bash
# 更新美股名称数据
curl -X POST "http://127.0.0.1:8000/stocks/us-stock-names/update"

# 更新实时行情数据  
curl -X POST "http://127.0.0.1:8000/stocks/realtime-quotes/update"

# 并行AI分析（推荐）
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"summary": "分析股票 AAPL", "value": {"ticker": "AAPL"}}'

# 自定义日期范围分析
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"summary": "分析股票 AAPL", "value": {"ticker": "AAPL", "end_date": "2024-12-31"}}'
```

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

#### 前端交互优化
- **动态导航栏交互冲突修复** (v3.0.2):
  - **搜索下拉框状态感知**: 当搜索下拉框打开时，自动暂停滚动检测逻辑，避免鼠标移动时导航栏意外收缩
  - **AI分析完成状态管理**: AI分析完成后临时忽略滚动事件1秒，防止内容高度变化导致的误触发
  - **组件状态同步**: 通过回调机制实现组件间状态共享，确保动态UI行为的一致性
  - **关键技术点**: useState + useEffect + useCallback模式，防抖优化，事件监听器清理

#### 后台数据持久化调度
- APScheduler 以 8 分钟间隔运行 `persist_pending_data`，启用了 `coalesce=True`、`misfire_grace_time=300`、`max_instances=1` 来吸收容器冷启动带来的抖动。
- 任务开始与结束日志分别记录 UTC 时间（精确到秒）与执行耗时，`summary_payload` 中可获取处理成功/失败数量、待处理键数量等指标。
- 如需在测试中手动触发，请直接调用 `scheduled_persist_job()` 并确保关闭临时数据库会话；调试完成后可调用 `stop_scheduler()`/`start_scheduler()` 控制后台任务。

#### 数据验证机制
- 使用`ValidationResult`类进行分层验证
- 价格边界修复：异常数据自动修复 (5%容忍度)
- 交易日历感知：基于NYSE交易日历的智能日期处理

#### 异常处理
- 分层异常类：`ValidationException`、`DataServiceException`、`AIServiceException`
- 全局异常处理器：`stockaivo.exceptions.register_exception_handlers()`
- 中间件系统：请求日志、性能监控、安全头

#### MyPy类型检查策略
- **渐进式类型检查**：暂时允许未类型化的函数 (`disallow_untyped_defs = false`)
- **严格检查启用**：不完整定义检查、冗余转换警告、未使用忽略警告
- **第三方库兼容**：忽略AKShare、LangGraph等第三方库的类型检查
- **FastAPI装饰器兼容**：允许未类型化装饰器以支持FastAPI路由装饰器

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
- **新闻数据时间范围：最近3天**，确保时效性和分析相关性

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

## 项目结构详解

```
StockAIvo/
├── 📁 stockaivo/                   # 核心后端模块
│   ├── 🤖 ai/                      # AI分析引擎
│   │   ├── agents.py               # 多Agent定义 (技术/基本面/新闻)
│   │   ├── orchestrator.py         # LangGraph编排器 (并行工作流)
│   │   └── technical_indicator.py  # 技术指标计算 (MA/RSI/MACD等)
│   ├── 🌐 routers/                 # FastAPI路由模块
│   │   ├── stocks.py               # 股票数据API
│   │   ├── ai.py                   # AI分析API
│   │   └── search.py               # 搜索API
│   ├── 📊 data_service.py          # 核心数据服务 (三级缓存协调)
│   ├── 🗄️ models.py                # SQLAlchemy 2.0模型
│   ├── 🔧 dependencies.py          # 现代化依赖注入
│   ├── ⚡ cache_manager.py         # Redis缓存管理
│   └── 🛡️ exceptions.py            # 统一异常处理
├── 🎨 frontend/                    # React前端
│   ├── 📦 src/components/          # 核心React组件
│   │   ├── StockSearch.tsx         # 智能股票搜索
│   │   ├── TradingViewChart.tsx    # 专业K线图表
│   │   ├── AIAnalysis.tsx          # AI分析结果展示
│   │   └── ui/                     # shadcn/ui组件库
│   ├── 📱 src/hooks/               # React Hooks
│   └── 🎯 src/types/               # TypeScript类型定义
├── 🧪 tests/                       # 测试代码
│   ├── test_data_service.py        # 数据服务测试
│   ├── test_ai_analysis.py         # AI分析测试
│   └── conftest.py                 # 测试配置
├── 🗃️ database_migrations/         # 数据库迁移脚本
├── 📖 main.py                      # FastAPI应用入口
├── ⚙️ pyproject.toml               # uv项目配置 (Python依赖)
└── 📋 frontend/package.json        # pnpm配置 (前端依赖)
```

### 关键目录说明
- **stockaivo/ai/**: LangGraph多Agent并行分析系统核心
- **stockaivo/routers/**: RESTful API端点定义，按功能模块组织
- **frontend/src/components/**: React 19组件，使用TypeScript和shadcn/ui
- **tests/**: pytest测试套件，包含单元测试和集成测试
- **database_migrations/**: 数据库schema变更脚本