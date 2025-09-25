# StockAIvo - 智能美股数据与分析平台

> 🚀 现代化的全栈美股分析平台，集成三级缓存数据管理、多Agent并行AI分析和专业级TradingView图表

## ✨ 三大核心特性

### 📊 智能数据管理
**三级缓存策略 + 智能验证系统确保高效可靠的数据获取**
- 🔄 **Redis → PostgreSQL → AKShare** 智能缓存链路
- ⏰ **多时间粒度**：日线、周线、10分钟线、分钟线数据
- 🧠 **交易日历感知**：基于NYSE交易日历的智能日期处理
- 📰 **新闻数据集成**：TickerTick API实时新闻，Redis缓存优化
- 🛡️ **智能数据验证**：`ValidationResult`类 + 价格边界修复 + 分层验证策略
- 🔧 **自动修复机制**：异常容忍度5%，智能修复超范围价格数据
- 🔄 **数据管理API**：实时行情更新、美股名称数据同步

### 🤖 AI分析引擎
**基于LangGraph的多Agent并行分析架构**
- ⚡ **并行分析**：技术分析、基本面分析、新闻情感分析同时执行，**速度提升2-3倍**
- 🎯 **智能模型配置**：按Agent类型配置专用AI模型（Google Gemini）
- 📊 **技术指标**：MA、RSI、MACD、布林带、ATR等完整技术分析
- 📈 **流式响应**：SSE 流式输出在本地与容器环境保持一致，Nginx 关闭缓冲确保长文本不被截断
- 🗞️ **新闻情感**：基于实时新闻的市场情绪评估
- 🏢 **公司信息增强**：自动获取公司名称，优化分析准确性
- 🎲 **结构化预测**：基于多维分析生成概率化股价预测，包含方向、概率值、置信度和详细推理
- ⚠️ **执行依赖策略**：综合分析(synthesis)仅在技术分析成功时执行，确保分析质量
- ✅ **数据验证增强**：所有Agent在数据缺失时统一跳过LLM调用，避免无效分析和资源浪费

### 🎨 现代化界面
**专业级用户体验，适配多设备 • v3.0.0全新UI升级**
- 📈 **TradingView图表**：专业K线图表，实时OHLC数据显示
- 🔍 **智能搜索**：股票代码、公司名称模糊匹配和实时建议
- 🧭 **动态导航栏**：智能吸顶导航，滚动隐藏/显示，鼠标悬停交互
- 📱 **响应式设计**：完美适配桌面和移动设备
- 🎯 **一致性体验**：图表与数据颜色逻辑统一
- ✨ **UI框架升级**：从shadcn/ui迁移至Mantine UI 8.3.1
  - 🎨 统一设计系统与现代化组件API
  - ⚡ 更好的性能与TypeScript集成
  - 🌙 内置明暗主题切换支持
  - 📦 更小包体积，丰富内置功能

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (React 19 + TypeScript)              │
│  TradingView Charts • 智能搜索 • AI分析界面 • Mantine UI    │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI + Python 3.12)             │
│  RESTful API • AI分析引擎 • 数据服务 • 缓存管理              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  Redis (缓存)     │  PostgreSQL (数据库)  │  AKShare (数据源) │
│  • 热点数据缓存   │  • 股票基础信息        │  • 美股实时数据    │
│  • 新闻数据缓存   │  • 历史价格数据        │  • 历史K线数据     │
│  • 待保存数据     │                        │  • TickerTick新闻  │
└─────────────────────────────────────────────────────────────┘
```

## 🛠️ 技术栈

| 层级       | 技术                           | 版本                     | 特色                   |
| ---------- | ------------------------------ | ------------------------ | ---------------------- |
| **前端**   | React + TypeScript + Vite      | 19.1.0 + 5.8.3 + 7.0.0   | 现代化前端框架         |
| **UI**     | Mantine UI                     | 8.3.1                    | 现代React组件库        |
| **图表**   | TradingView Lightweight Charts | 5.0.8                    | 专业金融图表           |
| **后端**   | Python + FastAPI + SQLAlchemy  | 3.12 + 0.115.13 + 2.0.41 | 高性能异步API          |
| **数据库** | PostgreSQL + Redis             | 15+ + 7+                 | 主存储 + 高速缓存      |
| **AI**     | LangGraph + LangChain + Gemini | 0.4.8 + 0.3.15 + 2.5     | 多Agent工作流          |
| **数据源** | AKShare + 交易日历             | 1.15.0 + 5.1.1           | 美股数据 + 日历管理    |
| **工具链** | uv + pnpm + MyPy + ESLint      | latest                   | 现代化开发工具         |

## 🚀 快速开始

### 📋 环境要求
```
Python 3.12+  •  Node.js 18+  •  PostgreSQL 12+  •  Redis 6+
```

### ⚡ 一键部署

```bash
# 1️⃣ 克隆项目
git clone https://github.com/furyolo/StockAIvo.git
cd StockAIvo

# 2️⃣ 环境配置 (.env)
OPENAI_API_BASE=""
OPENAI_API_KEY=""

# 3️⃣ 安装依赖
uv sync --extra dev                    # 后端依赖
cd frontend && pnpm install           # 前端依赖

# 4️⃣ 启动服务
uv run dev                            # 后端: http://127.0.0.1:8000
cd frontend && pnpm dev               # 前端: http://localhost:3223
```

### 🐳 Docker 部署要点
```bash
# 首次构建并启动所有服务（FastAPI / Redis / PostgreSQL / 前端 / Nginx）
docker-compose up --build -d

# 查看后端实时日志，确认 SSE 推送与定时任务执行情况
docker logs -f stockaivo-backend-1
```
- **镜像体积优化**：后端镜像采用多阶段构建与 `uv sync --frozen`，最终体积约 1.3GB，满足生产部署需求。
- **健康检查一次性执行**：`HEALTHCHECK` 仅在容器首次就绪时请求 `/health` 并写入标记文件，避免 30 秒轮询打断 SSE。
- **SSE 代理优化**：Nginx 上游统一代理 `/api/`，关闭请求/响应缓冲与 gzip，确保流式分析在容器环境不中断。
- **LLM 服务地址**：容器内默认无法访问宿主 `localhost`，请在 `.env` 中将 `OPENAI_API_BASE` 指向 `http://host.docker.internal:3222/v1`（或对应的服务域名）。
- **环境变量加载**：`docker-compose` 会自动读取 `.env`，更新后记得 `docker-compose up -d --build` 重新加载。

### 🔧 AI模型配置 (可选)
```bash
# 高级AI模型配置
AI_DEFAULT_MODEL="gemini-2.5-flash"              # 默认模型
AI_TECHNICAL_ANALYSIS_MODEL="gemini-2.5-pro"    # 技术分析专用
AI_SYNTHESIS_MODEL="gemini-2.5-pro"             # 综合分析专用
```

## 📚 API 接口

### 🔥 核心端点

| 功能         | 端点                                   | 说明                   |
| ------------ | -------------------------------------- | ---------------------- |
| **股票数据** | `GET /stocks/{ticker}/daily`           | 日线数据               |
|              | `GET /stocks/{ticker}/weekly`          | 周线数据               |
|              | `GET /stocks/{ticker}/10min`           | 10分钟线（聚合）       |
|              | `GET /stocks/{ticker}/minute`          | 分钟线数据             |
|              | `GET /stocks/{ticker}/news`            | 新闻数据（缓存）       |
| **智能搜索** | `GET /search/stocks?q=apple`           | 股票搜索               |
|              | `GET /search/stocks/suggestions?q=app` | 实时建议               |
| **AI分析**   | `POST /ai/analyze-parallel`            | **并行AI分析（推荐）** |
|              | `POST /ai/analyze-sequential`          | 顺序AI分析             |
|              | `POST /ai/predict-structured`          | **结构化概率预测**     |
| **数据管理** | `POST /stocks/realtime-quotes/update`  | 更新实时行情数据       |
|              | `POST /stocks/us-stock-names/update`   | 更新美股名称数据       |
| **系统监控** | `GET /health`                          | 健康检查               |
|              | `GET /cache-stats`                     | 缓存统计               |

### 💡 AI分析示例

```bash
# 并行AI分析 (推荐) - 使用默认日期范围
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL"}'

# 使用自定义结束日期
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "end_date": "2024-12-31"}'

# 结构化概率预测 - 基于分析结果生成量化预测
curl -X POST "http://127.0.0.1:8000/ai/predict-structured" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "end_date": "2024-12-31"}'
```

### 🎲 结构化预测功能

**量化概率预测系统**，基于多维度分析生成精确的股价预测：

#### 📊 预测输出格式
```json
{
  "success": true,
  "data": {
    "prediction_probability": 0.72,
    "direction": "UP",
    "confidence_level": "MEDIUM",
    "reasoning": "技术分析显示RSI从超卖区域反弹，MACD出现金叉信号...",
    "ticker": "AAPL",
    "timestamp": "2025-09-13T14:30:00"
  }
}
```

#### 🎯 预测参数说明
- **prediction_probability**: 预测概率值（0.0-1.0），表示达成目标的可能性
- **direction**: 预测方向（UP/DOWN），基于多Agent分析综合判断
- **confidence_level**: 置信度等级（HIGH/MEDIUM/LOW），反映预测可靠性
- **reasoning**: 详细推理过程，解释概率计算依据和关键信号

#### ⚡ 智能特性
- **多维度分析**：整合技术分析、基本面分析、新闻情感的综合信号
- **动态适配**：根据可用分析维度自动调整预测策略和置信度评估
- **概率量化**：将定性分析转化为定量概率值，支持量化投资决策
- **风险评估**：提供置信度等级，帮助用户评估预测可靠性

### 🔄 数据管理示例

```bash
# 更新美股名称数据
curl -X POST "http://127.0.0.1:8000/stocks/us-stock-names/update" \
  -H "Content-Type: application/json"

# 响应示例
{
  "success": true,
  "message": "美股名称数据更新成功",
  "updated_count": 11841,
  "timestamp": "2025-08-06T12:00:00"
}

# 更新实时行情数据
curl -X POST "http://127.0.0.1:8000/stocks/realtime-quotes/update" \
  -H "Content-Type: application/json"
```

**功能说明**：
- `POST /stocks/us-stock-names/update`：从AKShare获取最新美股名称数据并更新`us_stocks_name`表
- `POST /stocks/realtime-quotes/update`：从AKShare获取实时行情数据并更新`stock_symbols`表
- 支持手动触发或定时任务调用
- 包含完整的数据验证、清洗和去重机制

> 🔗 **完整API文档**: http://127.0.0.1:8000/docs

## 📁 项目结构

```
StockAIvo/
├── 🎨 frontend/                    # React 19 前端
│   ├── src/components/             # 核心组件
│   │   ├── StockSearch.tsx         # 智能搜索
│   │   ├── TradingViewChart.tsx    # 专业图表
│   │   ├── AIAnalysis.tsx          # AI分析界面
│   │   └── ui/                     # shadcn/ui组件库
│   └── package.json                # 前端依赖 (pnpm)
├── 🚀 stockaivo/                   # Python 3.12 后端
│   ├── ai/                         # AI分析引擎
│   │   ├── agents.py               # 多Agent定义 (含结构化预测Agent)
│   │   ├── orchestrator.py         # LangGraph编排
│   │   └── technical_indicator.py  # 技术指标计算
│   ├── routers/                    # FastAPI路由
│   │   ├── stocks.py               # 股票数据API
│   │   ├── ai.py                   # AI分析API
│   │   └── search.py               # 搜索API
│   ├── data_service.py             # 三级缓存数据服务
│   ├── models.py                   # SQLAlchemy模型
│   └── dependencies.py             # 现代化依赖注入
├── 🧪 tests/                       # 测试代码
├── main.py                         # 应用入口
└── pyproject.toml                  # uv项目配置
```

## 🧪 开发 & 测试

```bash
# 🔧 开发调试
uv run dev                          # 后端开发服务器 (热重载)
cd frontend && pnpm dev             # 前端开发服务器

# ✅ 测试运行
uv run pytest tests/ -v            # 后端测试
uv run mypy stockaivo/              # 类型检查
cd frontend && pnpm test            # 前端测试

# 📊 系统监控
curl http://127.0.0.1:8000/health      # 健康检查
curl http://127.0.0.1:8000/cache-stats # 缓存统计
```

### 🕒 后台任务调度
- APScheduler 以 8 分钟间隔触发 `persist_pending_data`，启用 `coalesce=True`、`misfire_grace_time=300`、`max_instances=1`，确保容器启动抖动不会导致重复执行。
- 日志输出会在任务结束时记录计划开始时间（UTC，精确到秒）、实际耗时以及处理数量摘要，可在本地或容器中通过 `uv run dev`、`docker logs` 观察。
- 如需临时暂停，可调用 `stockaivo.background_scheduler.stop_scheduler()`，重新启动前确保无并发任务残留。

### 🏗️ 架构特色
- ⚡ **现代化依赖注入**：`DatabaseDep`、`CacheDep` 类型别名，`Annotated` 类型系统
- 🛡️ **分层异常处理**：`ValidationException`、`DataServiceException`、`AIServiceException`
- 🔧 **中间件系统**：请求日志、性能监控、安全头、统一异常处理
- 🎯 **完整类型安全**：MyPy + TypeScript 双重保障，运行时错误最小化
- 🤖 **LangGraph工作流**：模块化多Agent架构，并行分析提升2-3倍效率
- 🚀 **三级缓存策略**：Redis → PostgreSQL → AKShare，智能数据获取
- 🛡️ **智能数据验证**：`ValidationResult` + 价格修复 + 异常容忍机制
- 📰 **新闻缓存系统**：TickerTick API + Redis缓存，实时新闻获取
- 🔄 **数据管理API**：自动化数据更新，支持手动触发和定时任务

## 📋 版本历史

### 🎲 v3.0.0 (2025-09) - 结构化预测与UI架构升级
**AI分析系统增强**
- 🚀 **结构化预测Agent**：基于多维分析生成概率化股价预测，支持量化投资决策
- 🧠 **LLM结构化输出**：统一Google GenAI和OpenAI API，支持Pydantic模型返回
- 🔧 **Schema自动转换**：Pydantic模型到OpenAI格式的智能转换器
- ✅ **智能数据验证**：Agent执行前自动检查数据可用性，避免无效LLM调用
- 🏷️ **Agent名称规范化**：统一所有Agent调用的agent_name参数，支持专用模型配置
- 📊 **API格式优化**：简化前端请求JSON结构，提升开发效率和用户体验

**前端UI架构重构 (2025-09-17)**
- 🎨 **UI框架迁移**：shadcn/ui + TailwindCSS → Mantine UI 8.3.1
- 🗑️ **依赖清理**：移除@radix-ui系列、class-variance-authority、tailwind-merge等
- 🔄 **组件升级**：Card→Paper, Input→TextInput, Select→Select等现代组件
- 🎭 **图标更新**：lucide-react → @tabler/icons-react
- 🏗️ **布局重构**：div+className → Stack/Group/Grid组件化布局
- 🎯 **样式系统**：CSS-in-JS + Mantine主题变量替代TailwindCSS
- 🌙 **主题支持**：内置明暗主题自动切换
- ⚡ **性能优化**：更小包体积，更好的TypeScript集成

### 🚀 v2.1.0 (2025-08) - 数据管理与AI增强
- 🔄 **数据管理API**：新增实时行情和美股名称数据更新端点
- 🗃️ **数据库优化**：移除StockSymbols表index字段，完善UsStocksName模型
- 📰 **新闻系统重构**：移除新闻数据持久化，改为仅使用Redis缓存
- 🤖 **AI分析增强**：news_agent添加公司名称获取功能，优化分析准确性
- 🔧 **架构改进**：完善数据验证、清洗和批量UPSERT机制
- 📚 **文档完善**：更新API文档，添加数据管理示例和响应格式

### 🚀 v2.0.0 (2025-07) - 技术架构重构
- 📚 **文档重构**：完全重写技术架构文档，面向开发者的专业文档
- 🏗️ **架构升级**：React 19 + Python 3.12 + FastAPI 0.115 + SQLAlchemy 2.0
- 🎯 **技术栈现代化**：TailwindCSS 4 + shadcn/ui + TradingView Lightweight Charts 5.0
- 🔧 **工具链优化**：uv + pnpm + MyPy + ESLint 现代化开发工具链
- 🛡️ **智能数据验证**：`ValidationResult`类 + 价格边界修复 + 分层验证策略
- 📰 **新闻系统重构**：TickerTick API集成 + Redis缓存优化 + 时区智能处理
- ⚡ **现代化依赖注入**：`Annotated`类型系统 + 分层异常处理 + 中间件架构

### ⚡ v1.8.0 - 性能优化与逻辑统一
- 🧹 **代码清理**：移除小时线功能，10分钟线实时聚合优化
- 📊 **数据库优化**：简化表结构，提升查询性能67%
- 🔧 **兼容性修复**：Pandas FutureWarning 修复，时间频率标准化
- 🎯 **逻辑统一**：市场感知日期获取优化，减少冗余调用
- 📅 **周线数据完整性**：统一周线数据完整性判断逻辑

### 🤖 v1.7.0 - 并行AI分析
- ⚡ **并行分析引擎**：多Agent并行执行，**分析速度提升2-3倍**
- 🎯 **智能界面**：默认并行模式，实时进度显示
- 🚀 **用户体验**：流式输出，动态进度反馈

### 📰 v1.5.0 - 新闻数据集成与重构
- 📰 **新闻缓存系统**：TickerTick API + Redis缓存，实时新闻获取
- 🕐 **时区智能处理**：统一美东时间，1小时缓冲期优化
- 🗃️ **缓存优化**：新闻数据仅使用Redis缓存，提升响应速度
- 🤖 **AI情感增强**：基于实际新闻的时间序列情感演化分析
- 🔧 **智能去重**：新闻数据去重机制 + 内存缓存优化

### 🏗️ v1.2.0 - 架构现代化基础
- ⚡ **现代化依赖注入**：`Annotated` 类型系统，`DatabaseDep`/`CacheDep`别名
- 🛡️ **统一异常处理**：分层异常类设计，全局异常处理器
- 🔧 **中间件系统**：请求日志、性能监控、安全头中间件
- 🎯 **类型安全**：完整的 MyPy 类型检查，运行时类型验证

## 🤝 贡献 & 致谢

### 🔧 贡献指南
```bash
# 1. Fork 本仓库
# 2. 创建特性分支
git checkout -b feature/amazing-feature

# 3. 提交更改
git commit -m 'Add amazing feature'

# 4. 推送分支
git push origin feature/amazing-feature

# 5. 提交 Pull Request
```

### 🙏 致谢
| 项目            | 用途         | 链接                                                |
| --------------- | ------------ | --------------------------------------------------- |
| **AKShare**     | 金融数据接口 | [GitHub](https://github.com/akfamily/akshare)       |
| **LangGraph**   | AI工作流框架 | [GitHub](https://github.com/langchain-ai/langgraph) |
| **TradingView** | 专业图表库   | [官网](https://www.tradingview.com/)                |
| **shadcn/ui**   | UI组件库     | [官网](https://ui.shadcn.com/)                      |

---

<div align="center">

### ⭐ 如果项目对你有帮助，请给个星标！

[![GitHub stars](https://img.shields.io/github/stars/StockAIvo/StockAIvo?style=social)](https://github.com/StockAIvo/StockAIvo)
[![GitHub forks](https://img.shields.io/github/forks/StockAIvo/StockAIvo?style=social)](https://github.com/StockAIvo/StockAIvo)

[🐛 报告Bug](https://github.com/StockAIvo/StockAIvo/issues) • [✨ 功能请求](https://github.com/StockAIvo/StockAIvo/issues) • [💬 讨论](https://github.com/StockAIvo/StockAIvo/discussions)

**StockAIvo** - 让AI赋能你的投资决策 🚀

</div>