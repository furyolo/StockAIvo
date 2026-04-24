[English](./README.md) | [简体中文](./README.zh-CN.md)

# StockAIvo - Intelligent US Stock Data And Analysis Platform

> 🚀 A modern full-stack US stock analysis platform with layered cache
> management, parallel multi-agent AI analysis, and professional
> TradingView-powered charts

## ✨ Three Core Capabilities

### 📊 Intelligent Data Management
**A layered cache strategy plus smart validation ensures efficient and reliable market data retrieval**
- 🔄 **Redis → PostgreSQL → AKShare** intelligent cache chain
- ⏰ **Multiple timeframes**: daily, weekly, 10-minute, and minute-level data
- 🧠 **Trading-calendar awareness**: smart date handling based on the NYSE trading calendar
- 📰 **News integration**: real-time TickerTick news with Redis-backed caching
- 🛡️ **Smart data validation**: `ValidationResult`, price-bound repair, and layered validation policies
- 🔧 **Automatic repair**: 5% anomaly tolerance with smart fixing for out-of-range price data
- 🔄 **Data management APIs**: real-time quote updates and US stock name synchronization

### 🤖 AI Analysis Engine
**A LangGraph-based parallel multi-agent analysis architecture**
- ⚡ **Parallel analysis**: technical, fundamental, and news sentiment agents run together for a **2-3x speed boost**
- 🎯 **Smart model routing**: agent-specific AI model configuration for Google Gemini compatible workflows
- 📊 **Technical indicators**: MA, RSI, MACD, Bollinger Bands, ATR, and more
- 🧠 **Technical analysis cache**: Redis key `technical_analysis:{TICKER}:{marketAwareDate}` with 180-second TTL during trading hours and automatic alignment to next market open after close
- 📈 **Streaming responses**: SSE output works consistently in both local and containerized deployments, with Nginx buffering disabled to prevent truncation
- 🗞️ **News sentiment**: market emotion assessment based on live news flows
- 🏢 **Company context enhancement**: automatic company-name lookup for more accurate analysis
- 🎲 **Structured prediction**: probabilistic price prediction with direction, probability, confidence, and detailed reasoning
- ⚠️ **Execution dependency policy**: synthesis runs only when technical analysis succeeds, protecting output quality
- ✅ **Validation-first agent execution**: all agents skip LLM calls when required data is missing, avoiding waste

### 🎨 Modern Interface
**Professional user experience across devices • v3.0.0 UI refresh**
- 📈 **TradingView charts**: professional candlestick charts with real-time OHLC display
- 🔍 **Smart search**: fuzzy matching for tickers and company names with live suggestions
- 🧭 **Dynamic navigation bar**: sticky, hide/show-on-scroll, and hover-responsive navigation
- 📱 **Responsive design**: optimized for both desktop and mobile
- 🎯 **Consistent visual language**: aligned color behavior across charts and data modules
- ✨ **UI framework upgrade**: migrated from shadcn/ui to Mantine UI 8.3.1
  - 🎨 unified design system and modern component API
  - ⚡ stronger performance and TypeScript integration
  - 🌙 built-in light and dark theme support
  - 📦 smaller bundles with rich built-in functionality

## 🏗️ System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React 19 + TypeScript)        │
│  TradingView Charts • Smart Search • AI Analysis • Mantine │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP / WebSocket
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI + Python 3.14)         │
│   REST API • AI Analysis Engine • Data Service • Cache     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│ Redis (cache) │ PostgreSQL (database) │ AKShare (source)   │
│ • hot cache   │ • stock metadata      │ • real-time data   │
│ • news cache  │ • historical prices   │ • historical bars  │
│ • pending DB  │                        │ • TickerTick news  │
└─────────────────────────────────────────────────────────────┘
```

## 🛠️ Tech Stack

| Layer        | Technology                     | Version                  | Purpose                    |
| ------------ | ------------------------------ | ------------------------ | -------------------------- |
| **Frontend** | React + TypeScript + Vite      | 19.1.0 + 5.8.3 + 7.0.0   | Modern frontend stack      |
| **UI**       | Mantine UI                     | 8.3.1                    | Modern React component kit |
| **Charts**   | Lightweight Charts             | 5.0.8                    | Professional finance chart |
| **Backend**  | Python + FastAPI + SQLAlchemy  | 3.14 + 0.115.13 + 2.0.41 | High-performance API       |
| **Data**     | PostgreSQL + Redis             | 17+ + 8+                 | Primary store + fast cache |
| **AI**       | LangGraph + LangChain + Gemini | 0.4.8 + 0.3.15 + 2.5     | Multi-agent workflow       |
| **Source**   | AKShare + Trading Calendar     | 1.15.0 + 5.1.1           | Market data + schedule     |
| **Tooling**  | uv + pnpm + MyPy + ESLint      | latest                   | Modern developer tooling   |

## 🚀 Quick Start

### 📋 Requirements
```bash
Python 3.14+  •  Node.js 18+  •  PostgreSQL 17+  •  Redis 8+
```

> ℹ️ Note: backend code and dependencies now live in the `backend/`
> subdirectory. Run any `uv ...` or `python database_migrations/...` command
> from there, or prefix it with `cd backend &&`.

### ⚡ One-Command Setup

```bash
# 1️⃣ Clone the repository
git clone https://github.com/furyolo/StockAIvo.git
cd StockAIvo

# 2️⃣ Configure environment variables (.env)
OPENAI_API_BASE=""
OPENAI_API_KEY=""

# 3️⃣ Install dependencies
cd backend && uv sync --extra dev     # backend dependencies
cd frontend && pnpm install           # frontend dependencies

# 4️⃣ Start services
cd backend && uv run dev              # backend: http://127.0.0.1:8000
cd frontend && pnpm dev               # frontend: http://localhost:3223
```

### 🐳 Docker Deployment Notes
```bash
# Build and start all services (FastAPI / Redis / frontend / Nginx)
docker-compose up --build -d

# Stream backend logs to verify SSE output and scheduled jobs
docker logs -f stockaivo-backend-1
```
- **Image size optimization**: the backend image uses multi-stage builds with `uv sync --frozen`, keeping production size around 1.3GB
- **One-time health check**: `HEALTHCHECK` hits `/health` only on first readiness and writes a marker file, avoiding 30-second polling that can interrupt SSE
- **SSE proxy tuning**: Nginx proxies `/api/` with request/response buffering and gzip disabled, preserving long streaming responses
- **LLM service address**: containers cannot reach the host `localhost` directly; use `OPENAI_API_BASE="http://host.docker.internal:3222/v1"` or another reachable host/domain
- **Cross-platform host mapping**: `docker-compose.yml` already sets `extra_hosts: "host.docker.internal:host-gateway"`, which works on Windows, macOS, and modern Linux Docker environments
- **Environment loading**: `docker-compose` automatically reads `.env`; after updates, rebuild with `docker-compose up -d --build`

### 📝 Logging And Hot Reload

- **Unified log output**: backend logs are written to `logs/backend/<YYYY-MM-DD>.log` through `logging.dictConfig`; configurable via:
  - `LOG_FILE_DIR`: log root, default `logs/backend`
  - `LOG_FILE_MAX_BYTES`: single file rotation size, default `10_485_760` (10MB)
  - `LOG_FILE_BACKUP_COUNT`: retained rotated files, default `5`
  - `LOG_LEVEL`: root log level, default `INFO`
- **Development watch scope**: `uv run dev` and `python main.py` inside `backend/` only watch `stockaivo/`, `database_migrations/`, and `tests/`, while ignoring `logs/` and `*.log`
- **Logs plus console output**: file rotation and console streaming coexist to support both real-time debugging and historical traceability

## 🗂️ Documents And Task History

- `docs/task-history/`: archive for completed TODOs and implementation notes, using the naming format `YYYY-MM-topic.md`
- `TODO.md`: active iteration tasks are still maintained at the repo root before being archived
- `docs/operations/data-initialization.md`: container startup order, health checks, and first-batch data initialization flow

### 🔧 AI Model Configuration (Optional)
```bash
# Advanced AI model configuration
AI_DEFAULT_MODEL="gemini-3-flash-preview"           # default model
AI_TECHNICAL_ANALYSIS_MODEL="gemini-3.1-pro-preview" # technical analysis agent
AI_SYNTHESIS_MODEL="gemini-3.1-pro-preview"          # synthesis agent
```

## 📚 API Reference

### 🔥 Core Endpoints

| Feature       | Endpoint                               | Description                       |
| ------------- | -------------------------------------- | --------------------------------- |
| **Stock Data**| `GET /stocks/{ticker}/daily`           | Daily candles                     |
|               | `GET /stocks/{ticker}/weekly`          | Weekly candles                    |
|               | `GET /stocks/{ticker}/10min`           | Aggregated 10-minute candles      |
|               | `GET /stocks/{ticker}/minute`          | Minute-level candles              |
|               | `GET /stocks/{ticker}/news`            | Cached news                       |
| **Search**    | `GET /search/stocks?q=apple`           | Stock lookup                      |
|               | `GET /search/stocks/suggestions?q=app` | Live suggestions                  |
| **AI**        | `POST /ai/analyze-parallel`            | **Parallel AI analysis**          |
|               | `POST /ai/analyze-sequential`          | Sequential AI analysis            |
|               | `POST /ai/predict-structured`          | **Structured probability output** |
|               | `POST /ai/predict-structured/batch`    | Batch structured prediction       |
| **Data Ops**  | `POST /stocks/realtime-quotes/update`  | Refresh real-time quotes          |
|               | `POST /stocks/us-stock-names/update`   | Refresh US stock names            |
| **System**    | `GET /health`                          | Health check                      |
|               | `GET /cache-stats`                     | Cache statistics                  |

### 💡 AI Analysis Examples

```bash
# Parallel AI analysis (recommended) with default date range
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL"}'

# Use a custom end date
curl -X POST "http://127.0.0.1:8000/ai/analyze-parallel" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "end_date": "2024-12-31"}'

# Structured probability prediction
curl -X POST "http://127.0.0.1:8000/ai/predict-structured" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "end_date": "2024-12-31"}'
```

### 🎲 Structured Prediction

**A quantitative probability prediction system** that converts multi-dimensional analysis into an actionable stock forecast.

#### 📊 Response Format
```json
{
  "success": true,
  "data": {
    "prediction_probability": 0.72,
    "direction": "UP",
    "confidence_level": "MEDIUM",
    "reasoning": "RSI rebounded from oversold territory and MACD shows a bullish crossover...",
    "ticker": "AAPL",
    "timestamp": "2025-09-13T14:30:00"
  }
}
```

#### 🎯 Response Fields
- **prediction_probability**: a value between `0.0` and `1.0` showing the chance of the predicted move
- **direction**: `UP` or `DOWN`, based on combined agent reasoning
- **confidence_level**: `HIGH`, `MEDIUM`, or `LOW`
- **reasoning**: detailed explanation of the major signals and weighting logic

### 🧵 Batch Structured Prediction API

- **Endpoint**: `POST /ai/predict-structured/batch`
- **Use case**: process multiple tickers in one request while controlling TickerTick, AKShare, and LLM rate limits
- **Key features**:
  - supports `tickers`, `max_concurrency`, `max_retries`, and `retry_delay_seconds`
  - uses `asyncio.Semaphore` and `RateLimiter` to coordinate concurrency and upstream throttling
  - supports both full prediction mode (`full`) and data-only mode (`data_collection_only`)
  - successful full-mode results are written to Redis as `prediction:pending:*` and later persisted by scheduled jobs

```bash
curl -X POST "http://127.0.0.1:8000/ai/predict-structured/batch" \
  -H "Content-Type: application/json" \
  -d '{
        "tickers": ["AAPL", "MSFT", "TSLA"],
        "save_to_db": true,
        "max_concurrency": 3,
        "max_retries": 1,
        "retry_delay_seconds": 5.0,
        "execution_mode": "full"
      }'
```

> 💡 If you only need daily and weekly data collection, set `execution_mode`
> to `data_collection_only` to skip news fetching, AI analysis, and persistence.

> 📘 See `docs/operations/batch-prediction-guide.md` for the full workflow,
> environment variables, and troubleshooting notes.

#### ⚡ Smart Characteristics
- **Multi-dimensional reasoning**: combines technical, fundamental, and news sentiment signals
- **Dynamic adaptation**: adjusts prediction strategy and confidence based on which inputs are available
- **Quantified output**: turns qualitative analysis into numerical decision support
- **Risk framing**: includes explicit confidence levels for better interpretation

### 🔄 Data Management Examples

```bash
# Refresh US stock names
curl -X POST "http://127.0.0.1:8000/stocks/us-stock-names/update" \
  -H "Content-Type: application/json"

# Response example
{
  "success": true,
  "message": "US stock names updated successfully",
  "updated_count": 11841,
  "timestamp": "2025-08-06T12:00:00"
}

# Refresh real-time quotes
curl -X POST "http://127.0.0.1:8000/stocks/realtime-quotes/update" \
  -H "Content-Type: application/json"
```

**What these endpoints do**
- `POST /stocks/us-stock-names/update`: fetches the latest US stock name set from AKShare and updates `us_stocks_name`
- `POST /stocks/realtime-quotes/update`: refreshes the `stock_symbols` quote dataset
- supports both manual triggers and scheduled execution
- includes validation, normalization, and de-duplication flow

> 🔗 Full API docs: `http://127.0.0.1:8000/docs`

## 📁 Project Structure

```text
StockAIvo/
├── 🚀 backend/                     # FastAPI backend subproject
│   ├── stockaivo/                  # Core business and AI modules
│   ├── database_migrations/        # Migration scripts
│   ├── tests/                      # Pytest suites and performance checks
│   ├── main.py                     # FastAPI entry point
│   ├── pyproject.toml              # uv project config
│   └── Dockerfile                  # Backend container build
├── 🎨 frontend/                    # React 19 frontend
│   ├── src/components/             # Core UI components
│   └── package.json                # Frontend dependencies
├── 🐳 docker/                      # Container and Nginx config
├── 📚 docs/                        # Ops guides and task history
├── 🗂️ logs/                        # Local debug logs
├── 🧾 README.md / STARTUP.md       # Main project docs
└── 🛠️ start-dev.sh(.bat)           # One-command local development scripts
```

## 🧪 Development & Testing

```bash
# 🔧 Development
cd backend && uv run dev              # backend dev server
cd frontend && pnpm dev               # frontend dev server

# ✅ Tests
cd backend && uv run pytest tests/ -v # backend tests
cd backend && uv run mypy stockaivo/  # type checking
cd frontend && pnpm test              # frontend tests

# 📊 Monitoring
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/cache-stats
```

## 🕒 Background Jobs And Monitoring

- APScheduler triggers `persist_pending_data` every 8 minutes with `coalesce=True`, `misfire_grace_time=300`, and `max_instances=1`
- completion logs include scheduled UTC start time, runtime, and processed counts
- use `cd backend && uv run dev` or `docker logs` to watch job execution in local or containerized environments
- if you pause scheduled work temporarily, make sure no in-flight tasks remain before restarting

## 🏗️ Architecture Characteristics

- ⚡ **Modern dependency injection**: `Annotated`, `DatabaseDep`, and `CacheDep`
- 🛡️ **Layered exception handling**: `ValidationException`, `DataServiceException`, `AIServiceException`
- 🔧 **Middleware system**: request logging, performance monitoring, security headers, unified exception handling
- 🎯 **Type safety**: MyPy and TypeScript protect both backend and frontend paths
- 🤖 **LangGraph workflow**: modular multi-agent orchestration with 2-3x faster parallel analysis
- 🚀 **Layered cache strategy**: Redis → PostgreSQL → AKShare
- 🛡️ **Smart validation**: `ValidationResult`, price repair, and anomaly tolerance
- 📰 **News cache system**: TickerTick + Redis for fast real-time news retrieval
- 🔄 **Data management APIs**: automated refresh with both manual and scheduled triggers

## 📋 Version History

### 🚀 v3.1.1 (2025-10) - Batch Structured Prediction And Rate-Limit Control
- 🔄 reusable structured prediction coroutine extracted from single-symbol flow
- ⚡ new `POST /ai/predict-structured/batch` endpoint with concurrency and retry controls
- 📦 Redis `prediction:pending:*` cache layer for delayed persistence
- 🛡️ multi-source rate-limiter components
- 🧪 expanded unit and integration coverage
- 📋 CLI batch prediction utility
- 📚 richer operational documentation

### 🎲 v3.1.0 (2025-10) - Well-Known Symbol Import And Batch Prediction Planning
- 📊 well-known US stock symbol import workflow
- 🎯 detailed batch structured prediction planning
- 📋 large task decomposition into independently deliverable slices
- 🏗️ architecture design for rate limiting, concurrency, and Redis persistence
- 📚 stronger documentation and task history structure

### 🎲 v3.0.0 (2025-09) - Structured Prediction And UI Architecture Upgrade
- 🚀 structured prediction agent for probability-based stock movement output
- 🧠 unified structured LLM output for Gemini and OpenAI-compatible APIs
- 🔧 automatic schema conversion from Pydantic to OpenAI-style formats
- ✅ pre-agent data validation to avoid invalid LLM calls
- 🏷️ normalized agent naming for model selection
- 📊 cleaner frontend request format
- 🎨 Mantine UI migration and modernized frontend architecture

## 🤝 Contribution & Credits

### 🔧 Contributing
```bash
# 1. Fork the repository
# 2. Create a feature branch
git checkout -b feature/amazing-feature

# 3. Commit your changes
git commit -m "feat: add amazing feature"

# 4. Push the branch
git push origin feature/amazing-feature

# 5. Open a Pull Request
```

### 🙏 Credits
| Project         | Use Case            | Link                                                |
| --------------- | ------------------- | --------------------------------------------------- |
| **AKShare**     | Financial data API  | [GitHub](https://github.com/akfamily/akshare)       |
| **LangGraph**   | AI workflow engine  | [GitHub](https://github.com/langchain-ai/langgraph) |
| **TradingView** | Professional charts | [Website](https://www.tradingview.com/)             |
| **Mantine**     | UI framework        | [Website](https://mantine.dev/)                     |

---

<div align="center">

### ⭐ If this project helps you, a star would mean a lot

[![GitHub stars](https://img.shields.io/github/stars/StockAIvo/StockAIvo?style=social)](https://github.com/StockAIvo/StockAIvo)
[![GitHub forks](https://img.shields.io/github/forks/StockAIvo/StockAIvo?style=social)](https://github.com/StockAIvo/StockAIvo)

[🐛 Report a Bug](https://github.com/StockAIvo/StockAIvo/issues) • [✨ Request a Feature](https://github.com/StockAIvo/StockAIvo/issues) • [💬 Discussions](https://github.com/StockAIvo/StockAIvo/discussions)

**StockAIvo** - Let AI strengthen your investment decisions 🚀

</div>
