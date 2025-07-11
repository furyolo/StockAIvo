# StockAIvo - 智能美股数据与分析平台

一个现代化的全栈美股分析平台，集成实时数据查询、TradingView图表展示和多Agent协同的AI投资分析。

## 🏗️ 系统架构

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
            │ • 热点数据缓存  │  │ • 股票基础信息  │
            │ • 待保存数据    │  │ • 历史价格数据  │
            └────────────────┘  └────────────────┘
```

## ✨ 核心特性

### 📊 智能数据管理
- **三级缓存策略**: Redis → PostgreSQL → AKShare，确保高效可靠的数据获取
- **多时间粒度**: 支持日线、周线数据（小时线功能待开发）
- **智能数据补全**: 自动检测并补全缺失数据
- **交易日历感知**: 基于NYSE交易日历的智能日期处理
- **动态交易日计算**: AI分析中自动计算实际交易日数量

### 🤖 AI分析引擎
- **多Agent协同**: 基于LangGraph的分布式AI分析架构
- **流式分析**: 实时流式输出分析结果
- **技术分析**: 完整的技术指标计算（MA、RSI、MACD、布林带、ATR等）
- **基本面分析**: 基于市场认知的基本面评估（数据源待扩展）
- **情感分析**: 市场情绪评估（数据源待扩展）
- **智能时间范围**: 基于实际交易日的精确分析时间窗口

### 🎨 现代化界面
- **专业图表**: 基于TradingView Lightweight Charts的K线图表，支持实时OHLC数据显示
- **智能搜索**: 股票代码、公司名称的模糊匹配和实时建议
- **响应式设计**: 适配桌面和移动设备
- **一致性体验**: 图表K线与OHLC信息颜色逻辑统一，完整显示价格变化和百分比
- **实时分析**: 支持流式AI分析结果展示

## 🛠️ 技术栈

**后端**: Python 3.12 + FastAPI + PostgreSQL + Redis + LangGraph
**前端**: React 19 + TypeScript + Vite + TailwindCSS 4 + shadcn/ui
**AI**: LangGraph + LangChain + Google Gemini
**数据**: AKShare + pandas-market-calendars
**工具**: uv (Python) + pnpm (Node.js) + MyPy + ESLint + Vitest

## 🚀 快速开始

### 环境要求
Python 3.12+ • Node.js 18+ • PostgreSQL 12+ • Redis 6+

### 安装部署

```bash
# 1. 克隆项目
git clone https://github.com/your-username/StockAIvo.git
cd StockAIvo

# 2. 配置环境变量 (.env)
DATABASE_URL="postgresql://postgres:password@localhost:5432/stockaivo"
REDIS_URL="redis://localhost:6379"
GEMINI_API_KEY="your_google_api_key"

# 3. 安装后端依赖
uv sync --extra dev

# 4. 安装前端依赖
cd frontend && pnpm install

# 5. 启动服务
# 后端 (终端1)
uv run dev  # http://127.0.0.1:8000

# 前端 (终端2)
cd frontend && pnpm dev  # http://localhost:5173
```

详细配置说明请参考 [CONFIGURATION.md](CONFIGURATION.md)

## 📚 API 文档

### 主要端点

```http
# 股票数据
GET /stocks/{ticker}/daily?start_date=2024-01-01&end_date=2024-12-31
GET /stocks/{ticker}/weekly?start_date=2024-01-01&end_date=2024-12-31

# 股票搜索
GET /search/stocks?q=apple&page=1&page_size=10
GET /search/stocks/suggestions?q=app&limit=5

# AI分析 (支持流式和非流式响应)
POST /ai/analyze
{
  "ticker": "AAPL",
  "date_range_option": "past_90_days"
}

POST /ai/analyze-stream  # 流式响应
{
  "ticker": "AAPL",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}

# 系统监控
GET /health              # 健康检查
GET /cache-stats         # 缓存统计
POST /persist-data       # 手动数据持久化
```

**支持的日期范围选项**:
- `past_30_days`, `past_60_days`, `past_90_days`, `past_180_days`, `past_1_year`
- `past_8_weeks`, `past_16_weeks`, `past_24_weeks`, `past_52_weeks`

完整API文档: `http://127.0.0.1:8000/docs`

## 📁 项目结构

```
StockAIvo/
├── frontend/                   # React前端
│   ├── src/
│   │   ├── components/         # UI组件
│   │   │   ├── StockSearch.tsx      # 股票搜索组件
│   │   │   ├── TradingViewChart.tsx # 图表组件
│   │   │   ├── AIAnalysis.tsx       # AI分析组件
│   │   │   └── ui/                  # shadcn/ui组件
│   │   └── App.tsx             # 主应用组件
│   ├── package.json            # 前端依赖配置
│   └── vite.config.ts          # Vite配置
├── stockaivo/                  # 后端核心
│   ├── ai/                     # AI分析引擎
│   │   ├── agents.py           # AI Agent定义
│   │   ├── orchestrator.py     # LangGraph工作流编排
│   │   ├── llm_service.py      # LLM服务封装
│   │   ├── technical_indicator.py # 技术指标计算
│   │   └── state.py            # 状态管理
│   ├── routers/                # API路由
│   │   ├── stocks.py           # 股票数据API
│   │   ├── ai.py               # AI分析API
│   │   └── search.py           # 搜索API
│   ├── dependencies.py         # 依赖注入
│   ├── exceptions.py           # 异常处理
│   ├── middleware.py           # 中间件
│   ├── data_service.py         # 数据服务
│   ├── search_service.py       # 搜索服务
│   ├── database.py             # 数据库连接
│   ├── models.py               # 数据模型
│   └── schemas.py              # API模式
├── tests/                      # 测试代码
├── main.py                     # 应用入口
├── pyproject.toml              # 项目配置
├── CONFIGURATION.md            # 配置说明
└── README.md                   # 项目文档
```

## 🧪 测试 & 开发

```bash
# 后端测试
uv run pytest tests/ -v

# 类型检查
uv run mypy stockaivo/

# 前端测试
cd frontend && pnpm test
cd frontend && pnpm test:ui  # 可视化测试界面

# 开发调试
export LOG_LEVEL=DEBUG
uv run dev  # 后端开发服务器

cd frontend && pnpm dev  # 前端开发服务器

# 查看系统状态
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/cache-stats
```

### 架构最佳实践
- **依赖注入**: 使用 `DatabaseDep` 等类型别名
- **异常处理**: 使用 `ValidationException`、`DataServiceException`、`AIServiceException` 等自定义异常
- **中间件**: 可配置的请求日志、性能监控、安全头
- **类型安全**: 完整的 MyPy 类型检查支持
- **AI工作流**: 基于LangGraph的模块化Agent架构
- **缓存策略**: Redis优先的三级缓存机制

## 📋 更新日志

### v1.4.0 (2025-07-11) - AI分析优化
- 🤖 **智能交易日计算**: AI Prompt中动态显示实际交易日数量，排除周末和假期
- 📊 **技术指标增强**: 完善技术分析Agent的指标计算和展示逻辑
- ⚡ **代码优化**: 简化交易日计算逻辑，提高性能和可维护性
- 🎯 **精确时间范围**: 所有AI分析现在基于实际交易日进行精确预测

### v1.3.0 (2025-07-09) - 图表显示优化
- 🎨 **图表数据完整性**: 修复API响应中缺失的price_change和price_change_percent字段
- 🎯 **颜色逻辑统一**: 图表K线与OHLC信息颜色保持一致（基于当日开盘收盘比较）
- ✨ **完整价格信息**: 收盘价后正确显示涨跌额和涨跌幅百分比
- 🔧 **美股颜色标准**: 遵循美股习惯（绿色上涨，红色下跌）

### v1.2.0 (2025-07-08) - 架构现代化
- ⚡ **现代化依赖注入**: 新增 `dependencies.py`，基于 `Annotated` 类型
- 🛡️ **统一异常处理**: 新增 `exceptions.py`，自定义异常类和全局处理器
- 🔧 **中间件系统**: 新增 `middleware.py`，请求日志、性能监控、安全头
- 🎯 **类型安全**: MyPy 类型检查配置，新增 `types-redis` 支持
- 📈 **向后兼容**: 保持现有API完全兼容，渐进式迁移

### v1.1.0 (2025-07-08) - 数据优化
- 🔧 **周线数据修复**: 智能处理不完整当前周数据
- ✨ **市场假期处理**: 增强假期和交易日历逻辑
- 🎯 **数据完整性**: 完善单元测试和边界情况处理

## 🤝 贡献 & 致谢

### 贡献指南
1. Fork 本仓库
2. 创建特性分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 提交 Pull Request

### 致谢
- [AKShare](https://github.com/akfamily/akshare) - 金融数据接口
- [LangGraph](https://github.com/langchain-ai/langgraph) - AI工作流框架
- [TradingView](https://www.tradingview.com/) - 专业图表库
- [shadcn/ui](https://ui.shadcn.com/) - UI组件库

---

<div align="center">

**⭐ 如果项目对你有帮助，请给个星标！**

[🐛 报告Bug](https://github.com/your-username/StockAIvo/issues) • [✨ 功能请求](https://github.com/your-username/StockAIvo/issues) • [💬 讨论](https://github.com/your-username/StockAIvo/discussions)

</div>