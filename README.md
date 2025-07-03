# StockAIvo - 智能美股数据与分析平台

StockAIvo 是一个专为美股市场设计的后端服务，旨在提供稳定、高效的数据接口，并通过一个由多 Agent 协同的 AI 系统，为投资者提供深度的决策辅助。

## 系统架构

系统采用现代化的服务导向架构，实现了前后端分离，确保了各模块的独立性和可扩展性。

*   **前端 (Frontend):** 基于 **React (Vite)** 构建的现代化单页应用，负责数据可视化和用户交互。
*   **后端 (Backend):**
    *   **API 层:** 使用 **FastAPI** 构建，提供高性能的异步 RESTful API。
    *   **核心逻辑层:**
        *   **数据服务 (`Data Service`):** 负责股票数据的获取、缓存和持久化，集成了 `AKShare` 作为数据源。
        *   **AI 编排器 (`AI Orchestrator`):** 基于 **LangGraph** 构建，管理一个由多个 AI Agent（如技术分析、基本面分析、新闻舆情分析等）组成的协同工作流，以生成综合性的市场分析报告。
    *   **数据存储层:**
        *   **主数据库:** 使用 **PostgreSQL** 进行结构化数据的持久化存储。
        *   **缓存:** 使用 **Redis** 缓存热点数据，提升响应速度。
*   **后台任务:** 使用 **APScheduler** 执行定期的后台任务，例如将缓存中的新数据持久化到数据库。

## 功能特性

*   **高效数据管道:** 实现了从数据源获取、Redis 缓存到 PostgreSQL 持久化的一整套高效流程。
*   **多时间粒度数据:** 提供稳定、多时间粒度的股票数据查询接口（日线、周线、小时线）。
*   **AI 投资决策辅助:** 通过 LangGraph 驱动的多 Agent 系统，提供全面的市场解读和投资建议。
*   **股票搜索与建议:** 提供基于关键词的股票搜索功能及输入建议。
*   **全面的环境配置:** 使用 `uv` 进行依赖管理，并通过环境变量进行灵活配置。
*   **前后端分离:** 清晰的项目结构，前端使用 React/Vite，后端使用 FastAPI。

## 技术栈

*   **后端:** Python, FastAPI, Pydantic, SQLAlchemy, LangGraph, Pandas
*   **前端:** TypeScript, React, Vite, Tailwind CSS, Shadcn/ui
*   **数据库 & 缓存:** PostgreSQL, Redis
*   **包管理 & 工具:** uv, pre-commit

## 安装与配置

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/StockAIvo.git
cd StockAIvo
```

### 2. 配置环境变量

复制 `projectBrief.md` 中提供的 `.env.example` 内容，在项目根目录创建一个 `.env` 文件，并填入必要的环境变量。

**`.env` 文件核心配置:**
```env
DATABASE_URL="postgresql://user:password@host:port/database"
REDIS_URL="redis://host:port"
GOOGLE_API_KEY="your_google_api_key" # 用于 Google AI (Gemini)
# 可选，用于其他 AI 服务
OPENAI_API_KEY="your_openai_api_key"
SERPER_API_KEY="your_serper_api_key"
```

### 3. 后端设置

本项目使用 [uv](https://github.com/astral-sh/uv) 作为包管理器。

```bash
# 创建虚拟环境并安装所有依赖
uv sync

# 如果需要进行开发（例如运行测试），请安装开发依赖
uv sync --extra dev
```

### 4. 前端设置

```bash
# 进入前端目录
cd frontend

# 安装依赖 (推荐使用 pnpm)
pnpm install
```

## 如何运行

请确保在不同的终端中分别启动后端和前端服务。

### 1. 启动后端开发服务器

```bash
# 在项目根目录运行
uv run dev
```
服务将在 `http://127.0.0.1:8000` 上可用，并支持热重载。

### 2. 启动前端开发服务器

```bash
# 进入前端目录
cd frontend

# 启动 Vite 开发服务器
pnpm dev
```
服务通常会在 `http://localhost:5173` 上可用。

## API 端点

所有 API 均以 `/api` 为前缀。

### 股票数据 (`/api/stocks`)

*   `GET /{ticker}/daily`: 获取日线数据。
*   `GET /{ticker}/weekly`: 获取周线数据。
*   `GET /{ticker}/hourly`: 获取小时线数据。

**查询参数:**
*   `start_date` (str, 可选): 开始日期, 格式 `YYYY-MM-DD`。
*   `end_date` (str, 可选): 结束日期, 格式 `YYYY-MM-DD`。

### 股票搜索 (`/api/search`)

*   `GET /stocks`: 根据查询参数 `q` 搜索股票。
*   `GET /stocks/suggestions`: 根据查询参数 `q` 获取搜索建议。
*   `GET /health`: 搜索服务的健康检查端点。

### AI 分析 (`/api/ai`)

*   `POST /analyze`: 发起一次 AI 分析请求。需要提供 `ticker`, `date_range_option` (如 `1m`, `3m`, `1y`) 或自定义的日期范围。

## 项目结构

```
.
├── database_migrations/ # 数据库迁移与索引优化脚本
├── frontend/            # React 前端应用
├── memory-bank/         # "记忆库"，包含项目上下文、决策日志等
├── stockaivo/           # 后端应用核心代码
│   ├── ai/              # AI Agent、工具链和编排器
│   ├── routers/         # FastAPI 路由模块
│   ├── scripts/         # 启动与运维脚本 (run.py)
│   ├── data_service.py  # 核心数据服务
│   ├── database.py      # 数据库连接与模型
│   └── ...
├── tests/               # 后端测试代码
├── main.py              # FastAPI 应用入口
├── pyproject.toml       # 后端项目依赖与配置
└── README.md            # 本文件
```

## 测试

```bash
# 确保已安装开发依赖
uv sync --extra dev

# 运行所有测试
uv run pytest tests/
```

## 贡献

欢迎通过提交 Issue 和 Pull Request 来为项目做出贡献。请确保代码风格一致，并在提交前通过所有测试。

## License

MIT