# StockAIvo - 智能美股数据与分析平台

StockAIvo 是一个全栈的智能美股数据与分析平台，提供实时股票数据查询、可视化图表展示和基于多Agent协同的AI投资分析服务。项目采用现代化技术栈，实现了高效的数据处理、智能缓存策略和流式AI分析功能。

## 🏗️ 系统架构

### 整体架构
系统采用现代化的微服务架构，实现了前后端分离，确保了各模块的独立性和可扩展性：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端 (React)   │────│  后端 (FastAPI)  │────│  数据源 (AKShare) │
│                 │    │                 │    │                 │
│ • TradingView   │    │ • 数据服务       │    │ • 美股实时数据   │
│ • 股票搜索      │    │ • AI分析引擎     │    │ • 历史K线数据    │
│ • AI分析展示    │    │ • 缓存管理       │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
            ┌───────▼────────┐  ┌───────▼────────┐
            │ Redis (缓存)    │  │ PostgreSQL     │
            │                │  │ (持久化存储)    │
            │ • 热点数据缓存  │  │ • 股票基础信息  │
            │ • 待保存数据    │  │ • 历史价格数据  │
            └────────────────┘  └────────────────┘
```

### 核心组件

#### 🎨 前端 (Frontend)
- **技术栈:** React 19 + TypeScript + Vite + TailwindCSS + shadcn/ui
- **核心功能:**
  - 📊 **TradingView图表:** 基于 `lightweight-charts` 的专业K线图表
  - 🔍 **智能股票搜索:** 支持模糊匹配和实时建议
  - 🤖 **AI分析展示:** 流式显示多Agent分析结果
  - 📱 **响应式设计:** 适配各种设备尺寸

#### ⚡ 后端 (Backend)
- **API层:** FastAPI + Uvicorn，提供高性能异步RESTful API
- **核心服务:**
  - **数据服务 (`DataService`):** 实现三级缓存策略 (Redis → PostgreSQL → AKShare)
    - 智能周线数据处理，确保数据完整性
    - 自动处理市场假期和交易日历
  - **AI编排器 (`LangGraphOrchestrator`):** 基于LangGraph的多Agent协同分析
  - **搜索服务 (`SearchService`):** 高性能股票符号搜索和建议
  - **后台调度器:** APScheduler驱动的数据持久化任务

#### 🗄️ 数据存储层
- **PostgreSQL:** 主数据库，存储股票基础信息和历史价格数据
- **Redis:** 高速缓存，支持通用缓存和待保存数据缓存
- **AKShare:** 第三方数据源，提供实时美股数据

#### 🤖 AI分析引擎
基于 **LangGraph** 构建的多Agent协同系统：
- **数据收集Agent:** 获取和预处理股票数据
- **技术分析Agent:** 技术指标分析和趋势判断
- **基本面分析Agent:** 财务数据和公司基本面评估
- **新闻情感Agent:** 新闻舆情和市场情绪分析
- **综合分析Agent:** 整合各Agent结果，生成最终投资建议

## ✨ 核心特性

### 📈 数据管理
- **三级缓存策略:** Redis → PostgreSQL → AKShare，确保数据获取的高效性和可靠性
- **多时间粒度支持:** 日线、周线、小时线数据，满足不同分析需求
- **智能数据补全:** 自动检测缺失数据并从最优数据源获取
- **数据完整性保障:** 智能处理周线数据，避免获取不完整的当前周数据
- **市场日历集成:** 自动处理美股交易日历和假期，确保数据准确性
- **后台持久化:** 异步数据持久化，不影响用户体验
- **交易日历感知:** 基于NYSE交易日历的智能日期处理

### 🤖 AI分析系统
- **多Agent协同:** 基于LangGraph的分布式AI分析架构
- **流式分析:** 实时流式输出分析结果，提升用户体验
- **多维度分析:** 技术面、基本面、情感面的综合分析
- **自定义时间范围:** 支持灵活的分析时间窗口设置
- **智能报告生成:** 自动生成结构化的投资分析报告

### 🔍 搜索与交互
- **智能股票搜索:** 支持股票代码、公司名称的模糊匹配
- **实时搜索建议:** 输入时的实时搜索建议功能
- **专业图表展示:** 基于TradingView的专业级K线图表
- **响应式界面:** 适配桌面和移动设备的现代化UI

### 🛠️ 开发与运维
- **现代化工具链:** uv (Python) + pnpm (Node.js) 的高效包管理
- **完善的测试覆盖:** 单元测试、集成测试和性能测试
- **数据库迁移:** 自动化的数据库结构管理
- **健康检查:** 完整的系统健康监控端点
- **容器化支持:** Docker友好的项目结构

## 🛠️ 技术栈

### 后端技术
- **核心框架:** Python 3.12+ + FastAPI + Uvicorn
- **数据处理:** Pandas + SQLAlchemy + Alembic
- **AI框架:** LangGraph + LangChain + Google Gemini/OpenAI
- **缓存:** Redis + 自定义缓存管理器
- **任务调度:** APScheduler
- **数据源:** AKShare + pandas-market-calendars

### 前端技术
- **核心框架:** React 19 + TypeScript + Vite
- **UI组件:** TailwindCSS + shadcn/ui + Radix UI
- **图表库:** TradingView Lightweight Charts
- **工具库:** date-fns + clsx + lucide-react
- **测试:** Vitest + Testing Library

### 数据库与缓存
- **主数据库:** PostgreSQL (股票数据持久化)
- **缓存系统:** Redis (多级缓存策略)
- **数据源:** AKShare API (实时美股数据)

### 开发工具
- **包管理:** uv (Python) + pnpm (Node.js)
- **代码质量:** ESLint + TypeScript + pytest
- **版本控制:** Git + 自动化测试流水线

## 🚀 快速开始

### 📋 环境要求

- **Python:** 3.12+
- **Node.js:** 18+
- **PostgreSQL:** 12+
- **Redis:** 6+
- **包管理器:** uv (Python) + pnpm (Node.js)

### 1️⃣ 克隆项目

```bash
git clone https://github.com/your-username/StockAIvo.git
cd StockAIvo
```

### 2️⃣ 环境配置

在项目根目录创建 `.env` 文件：

```env
# 数据库配置
DATABASE_URL="postgresql://postgres:password@localhost:5432/stockaivo"

# Redis配置 (可选，默认使用本地Redis)
REDIS_URL="redis://localhost:6379"

# AI服务配置 (二选一)
# 选项1: Google Gemini (推荐)
GEMINI_API_KEY="your_google_api_key"
GEMINI_MODEL_NAME="gemini-1.5-pro-latest"

# 选项2: OpenAI兼容API
# OPENAI_API_BASE="http://localhost:1234/v1"
# OPENAI_API_KEY="sk-your-key-here"
# OPENAI_MODEL_NAME="gpt-4"
```

> 💡 **提示:** 详细的配置说明请参考 [CONFIGURATION.md](CONFIGURATION.md)

### 3️⃣ 后端设置

```bash
# 安装uv (如果尚未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv sync

# 安装开发依赖 (可选)
uv sync --extra dev

# 数据库初始化 (可选，首次运行时自动创建表)
# 如需手动迁移，可运行数据库迁移脚本
```

### 4️⃣ 前端设置

```bash
# 进入前端目录
cd frontend

# 安装pnpm (如果尚未安装)
npm install -g pnpm

# 安装依赖
pnpm install
```

### 5️⃣ 启动服务

#### 🔧 开发环境

**启动后端服务** (终端1):
```bash
# 在项目根目录
uv run dev
```
- 服务地址: `http://127.0.0.1:8000`
- API文档: `http://127.0.0.1:8000/docs`
- 支持热重载

**启动前端服务** (终端2):
```bash
# 在frontend目录
cd frontend
pnpm dev
```
- 服务地址: `http://localhost:5173`
- 支持热重载和快速刷新

#### 🚀 生产环境

**后端生产部署:**
```bash
uv run start
# 或者
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

**前端生产构建:**
```bash
cd frontend
pnpm build
pnpm preview  # 预览构建结果
```

### 6️⃣ 验证安装

访问 `http://localhost:5173` 查看前端界面，或访问 `http://127.0.0.1:8000/health` 检查后端健康状态。

## 📚 API 文档

### 🔗 核心端点

#### 📊 股票数据 API
```http
GET /stocks/{ticker}/daily?start_date=2024-01-01&end_date=2024-12-31
GET /stocks/{ticker}/weekly?start_date=2024-01-01&end_date=2024-12-31
GET /stocks/{ticker}/hourly?start_date=2024-01-01&end_date=2024-12-31
```

**参数说明:**
- `ticker`: 股票代码 (如: AAPL, TSLA, MSFT)
- `start_date`: 开始日期 (YYYY-MM-DD, 可选)
- `end_date`: 结束日期 (YYYY-MM-DD, 可选)

**响应示例:**
```json
{
  "ticker": "AAPL",
  "period": "daily",
  "data": [
    {
      "date": "2024-01-01",
      "open": 150.00,
      "high": 155.00,
      "low": 149.00,
      "close": 154.00,
      "volume": 1000000
    }
  ]
}
```

#### 🔍 股票搜索 API
```http
GET /search/stocks?q=apple
GET /search/stocks/suggestions?q=app
GET /search/health
```

#### 🤖 AI 分析 API
```http
POST /ai/analyze
Content-Type: application/json

{
  "ticker": "AAPL",
  "date_range_option": "3m",
  "custom_date_range": {
    "start_date": "2024-01-01",
    "end_date": "2024-03-31"
  }
}
```

**流式响应:** 支持Server-Sent Events (SSE)，实时返回各Agent的分析结果。

#### 🏥 系统监控 API
```http
GET /health              # 系统健康检查
GET /cache-stats         # 缓存统计信息
GET /check-pending-data  # 检查待持久化数据
POST /persist-data       # 手动触发数据持久化
```

## 📁 项目结构

```
StockAIvo/
├── 📁 frontend/                    # 🎨 React前端应用
│   ├── 📁 src/
│   │   ├── 📁 components/          # UI组件
│   │   │   ├── StockSearch.tsx     # 股票搜索组件
│   │   │   ├── TradingViewChart.tsx # 图表组件
│   │   │   ├── AIAnalysis.tsx      # AI分析展示
│   │   │   └── 📁 ui/              # shadcn/ui组件
│   │   ├── App.tsx                 # 主应用组件
│   │   └── main.tsx                # 应用入口
│   ├── package.json                # 前端依赖配置
│   ├── vite.config.ts              # Vite配置
│   └── tailwind.config.js          # TailwindCSS配置
│
├── 📁 stockaivo/                   # 🚀 后端核心代码
│   ├── 📁 ai/                      # 🤖 AI分析引擎
│   │   ├── orchestrator.py         # LangGraph编排器
│   │   ├── agents.py               # 各类分析Agent
│   │   ├── llm_service.py          # LLM服务封装
│   │   ├── tools.py                # AI工具集
│   │   └── state.py                # 状态管理
│   ├── 📁 routers/                 # 🛣️ API路由
│   │   ├── stocks.py               # 股票数据API
│   │   ├── search.py               # 搜索API
│   │   └── ai.py                   # AI分析API
│   ├── 📁 scripts/                 # 🔧 运行脚本
│   │   └── run.py                  # 启动脚本
│   ├── data_service.py             # 📊 核心数据服务
│   ├── data_provider.py            # 🔌 数据源适配器
│   ├── cache_manager.py            # 💾 缓存管理器
│   ├── database.py                 # 🗄️ 数据库连接
│   ├── database_writer.py          # ✍️ 数据库写入
│   ├── search_service.py           # 🔍 搜索服务
│   ├── background_scheduler.py     # ⏰ 后台调度器
│   ├── models.py                   # 📋 数据模型
│   └── schemas.py                  # 📝 API模式
│
├── 📁 database_migrations/         # 🔄 数据库迁移
│   ├── create_search_indexes.py    # 搜索索引创建
│   └── *.sql                       # SQL迁移脚本
│
├── 📁 tests/                       # 🧪 测试代码
│   ├── test_data_service.py        # 数据服务测试
│   ├── test_search_*.py            # 搜索功能测试
│   └── test_*.py                   # 其他测试
│
├── 📁 memory-bank/                 # 📚 项目文档
│   ├── productContext.md          # 产品上下文
│   ├── progress.md                 # 开发进度
│   └── *.md                        # 其他文档
│
├── main.py                         # 🚪 FastAPI应用入口
├── pyproject.toml                  # 📦 Python项目配置
├── CONFIGURATION.md                # ⚙️ 配置说明
├── projectBrief.md                 # 📋 项目简介
└── README.md                       # 📖 项目说明
```

## 🧪 测试

### 运行测试

```bash
# 安装开发依赖
uv sync --extra dev

# 运行所有后端测试
uv run pytest tests/ -v

# 运行特定测试文件
uv run pytest tests/test_data_service.py -v

# 运行性能测试
uv run python tests/test_search_performance.py

# 前端测试
cd frontend
pnpm test
```

### 测试覆盖

项目包含以下测试类型：
- **单元测试:** 核心业务逻辑测试
- **集成测试:** API端点和数据库交互测试
- **性能测试:** 搜索和数据查询性能测试
- **AI测试:** LangGraph工作流测试

## 🔧 开发指南

### 代码规范

- **Python:** 遵循PEP 8规范，使用类型注解
- **TypeScript:** 严格模式，使用ESLint规范
- **提交信息:** 使用约定式提交格式

### 调试技巧

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
uv run dev

# 查看缓存状态
curl http://127.0.0.1:8000/cache-stats

# 检查系统健康
curl http://127.0.0.1:8000/health
```

## 📋 更新日志

### v1.1.0 (2025-07-08)

#### 🔧 重要修复
- **周线数据获取优化**: 修复了周线数据获取时可能包含不完整当前周数据的问题
  - 新增 `_get_latest_complete_weekly_end_date()` 函数，智能处理周线数据结束日期
  - **周一到周四**: 使用上一个完整周的最后交易日，避免不完整数据
  - **周五（交易日）**: 使用当前周五，确保数据完整性
  - **周五（假期）**: 使用本周最后交易日（如周四），保持数据连续性
  - **周末**: 使用本周最后交易日
  - 优化日志显示，使用中文星期名称（"周二"而非"周2"）

#### ✨ 技术改进
- 增强了市场假期处理逻辑（如美国独立日等）
- 完善了单元测试覆盖，确保各种边界情况的正确处理
- 改进了错误日志的可读性和调试信息

#### 🎯 影响范围
- 所有周线数据API调用 (`/stocks/{ticker}/weekly`)
- AI分析中的周线数据处理
- 数据缓存和持久化逻辑

---

## 🤝 贡献指南

我们欢迎各种形式的贡献！

### 如何贡献

1. **Fork** 本仓库
2. 创建特性分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 提交 **Pull Request**

### 贡献类型

- 🐛 Bug修复
- ✨ 新功能开发
- 📚 文档改进
- 🎨 UI/UX优化
- ⚡ 性能优化
- 🧪 测试覆盖

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

- [AKShare](https://github.com/akfamily/akshare) - 优秀的金融数据接口
- [LangGraph](https://github.com/langchain-ai/langgraph) - 强大的AI工作流框架
- [TradingView](https://www.tradingview.com/) - 专业的图表库
- [shadcn/ui](https://ui.shadcn.com/) - 现代化的UI组件库

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给我们一个星标！**

[🐛 报告Bug](https://github.com/your-username/StockAIvo/issues) • [✨ 请求功能](https://github.com/your-username/StockAIvo/issues) • [💬 讨论](https://github.com/your-username/StockAIvo/discussions)

</div>