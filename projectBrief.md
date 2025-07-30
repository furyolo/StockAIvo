# StockAIvo 技术架构文档

## 1. 项目概述与技术定位

### 1.1 项目定位
StockAIvo 是一个现代化的**全栈美股数据与分析平台**，采用前后端分离架构，为投资者和研究人员提供专业级的股票数据服务和AI驱动的智能分析。

### 1.2 核心技术创新
- **智能数据管理**：三级缓存策略（Redis → PostgreSQL → AKShare）确保高效可靠的数据获取
- **AI分析引擎**：基于LangGraph的多Agent并行分析架构，提供技术分析、基本面分析和新闻情感分析
- **现代化界面**：集成TradingView Lightweight Charts的专业级用户体验

### 1.3 目标用户
- **开发者**：需要集成股票数据API的应用开发者
- **量化研究员**：需要历史数据和AI分析的研究人员
- **投资者**：需要专业分析工具的个人和机构投资者

## 2. 系统架构设计

### 2.1 整体架构模式
采用**分层架构模式**结合**微服务化设计思想**：

```
┌─────────────────────────────────────────────────────────────┐
│                    表现层 (Presentation Layer)                │
│  React 19 + TypeScript + TailwindCSS 4 + shadcn/ui        │
│  TradingView Lightweight Charts                            │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      API层 (API Layer)                      │
│  FastAPI + Pydantic + 依赖注入 + 异常处理                    │
│  RESTful API + Server-Sent Events                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   业务逻辑层 (Business Layer)                 │
│  数据服务 │ 搜索服务 │ AI分析引擎 │ 缓存管理                   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据访问层 (Data Access Layer)              │
│  SQLAlchemy 2.0 ORM + Redis Client                        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据存储层 (Storage Layer)                  │
│  PostgreSQL (主数据库) + Redis (缓存) + AKShare (外部API)     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则
- **模块化设计**：清晰的模块边界和接口定义
- **依赖注入**：基于 `Annotated` 类型的现代化依赖注入模式
- **异常处理**：分层异常类设计和全局处理器
- **类型安全**：完整的类型注解和MyPy类型检查
- **缓存优先**：智能缓存策略减少外部API调用

## 3. 核心技术栈

### 3.1 后端技术栈
| 组件         | 技术                    | 版本      | 用途               |
| ------------ | ----------------------- | --------- | ------------------ |
| **Web框架**  | FastAPI                 | 0.115.13+ | 高性能异步Web框架  |
| **数据库**   | PostgreSQL              | 15+       | 主数据存储         |
| **缓存**     | Redis                   | 7+        | 高速缓存和消息队列 |
| **ORM**      | SQLAlchemy              | 2.0.41+   | 现代化ORM框架      |
| **AI工作流** | LangGraph               | 0.4.8+    | AI Agent编排引擎   |
| **LLM框架**  | LangChain               | 0.3.15+   | 大语言模型集成     |
| **数据源**   | AKShare                 | 1.15.0+   | 美股数据API        |
| **交易日历** | pandas-market-calendars | 5.1.1+    | 交易日历管理       |

### 3.2 前端技术栈
| 组件         | 技术                           | 版本   | 用途                 |
| ------------ | ------------------------------ | ------ | -------------------- |
| **框架**     | React                          | 19.1.0 | 现代化前端框架       |
| **语言**     | TypeScript                     | 5.8.3  | 类型安全的JavaScript |
| **构建工具** | Vite                           | 7.0.0  | 快速构建工具         |
| **样式系统** | TailwindCSS                    | 4.1.11 | 原子化CSS框架        |
| **UI组件**   | shadcn/ui                      | latest | 现代化组件库         |
| **图表库**   | TradingView Lightweight Charts | 5.0.8  | 专业金融图表         |

### 3.3 开发工具链
| 工具               | 技术              | 用途                     |
| ------------------ | ----------------- | ------------------------ |
| **Python依赖管理** | uv                | 替代pip/venv的现代化工具 |
| **Node.js包管理**  | pnpm              | 高效的包管理器           |
| **Python类型检查** | MyPy              | 静态类型检查             |
| **前端代码质量**   | ESLint + Prettier | 代码规范和格式化         |
| **测试框架**       | pytest + Vitest   | 后端和前端测试           |

## 4. 后端架构详解

### 4.1 API路由设计
采用模块化路由器设计，每个路由器负责特定的业务领域：

#### 4.1.1 股票数据API (`routers/stocks.py`)
```python
# 核心端点设计
GET  /api/stocks/{symbol}/daily     # 获取日线数据
GET  /api/stocks/{symbol}/weekly    # 获取周线数据
GET  /api/stocks/{symbol}/10min     # 获取10分钟线数据
GET  /api/stocks/{symbol}/1min      # 获取分钟线数据
GET  /api/stocks/{symbol}/news      # 获取股票新闻
```

**特性**：
- 支持多时间粒度数据查询
- 智能日期范围处理（交易日历感知）
- 统一的响应格式和异常处理
- 基于 `DatabaseDep` 的依赖注入

#### 4.1.2 AI分析API (`routers/ai.py`)
```python
# AI分析端点
POST /api/ai/analyze               # 启动AI分析
GET  /api/ai/analyze/{task_id}     # 获取分析状态
GET  /api/ai/stream/{task_id}      # 流式获取分析结果
```

**特性**：
- 支持顺序和并行两种分析模式
- Server-Sent Events流式响应
- 实时进度反馈和错误处理
- 可配置的AI模型选择

#### 4.1.3 搜索API (`routers/search.py`)
```python
# 智能搜索端点
GET /api/search/stocks             # 股票搜索建议
GET /api/search/suggestions        # 实时搜索建议
```

**特性**：
- 模糊匹配算法（symbol、name、cname）
- 实时搜索建议
- 缓存优化的搜索性能

### 4.2 数据服务层架构

#### 4.2.1 三级缓存策略 (`data_service.py`)
```
用户请求 → Redis缓存 → PostgreSQL数据库 → AKShare API
    ↓         ↓            ↓              ↓
  立即返回   缓存+返回    数据库+缓存+返回  获取+存储+缓存+返回
```

**核心特性**：
- **智能缓存TTL**：交易时间内外采用不同的缓存策略
- **数据完整性检查**：自动检测和补全缺失数据
- **异步持久化**：使用PENDING_SAVE缓存机制
- **交易日历感知**：自动跳过非交易日

#### 4.2.2 多时间粒度支持
| 时间粒度     | 存储策略         | 缓存策略  | 数据来源    |
| ------------ | ---------------- | --------- | ----------- |
| **日线**     | PostgreSQL持久化 | Redis缓存 | AKShare API |
| **周线**     | PostgreSQL持久化 | Redis缓存 | AKShare API |
| **10分钟线** | 仅缓存           | Redis缓存 | 分钟线聚合  |
| **分钟线**   | 仅缓存           | Redis缓存 | AKShare API |
| **新闻**     | 异步持久化       | Redis缓存 | AKShare API |

### 4.3 AI分析引擎架构

#### 4.3.1 LangGraph工作流设计
```
数据收集Agent
    ↓
┌─────────────────────────────────────────┐
│  并行执行 (Parallel Execution)           │
├─────────────┬─────────────┬─────────────┤
│ 技术分析Agent │ 基本面分析Agent │ 新闻情感Agent │
└─────────────┴─────────────┴─────────────┘
    ↓
综合分析Agent
    ↓
最终分析报告
```

#### 4.3.2 Agent详细设计
| Agent               | 功能             | 输入               | 输出                       |
| ------------------- | ---------------- | ------------------ | -------------------------- |
| **数据收集Agent**   | 获取分析所需数据 | 股票代码、时间范围 | 股票数据、新闻数据         |
| **技术分析Agent**   | 计算技术指标     | OHLCV数据          | MA、RSI、MACD、布林带、ATR |
| **基本面分析Agent** | 基本面评估       | 公司信息、财务数据 | 估值分析、成长性评估       |
| **新闻情感Agent**   | 情感分析         | 新闻文本           | 情感评分、关键事件         |
| **综合分析Agent**   | 整合分析结果     | 所有Agent输出      | 最终投资建议               |

#### 4.3.3 技术指标计算 (`technical_indicator.py`)
```python
class TechnicalIndicator:
    def calculate_ma(self, data: pd.DataFrame, window: int) -> pd.Series
    def calculate_rsi(self, data: pd.DataFrame, window: int = 14) -> pd.Series
    def calculate_macd(self, data: pd.DataFrame) -> Dict[str, pd.Series]
    def calculate_bollinger_bands(self, data: pd.DataFrame) -> Dict[str, pd.Series]
    def calculate_atr(self, data: pd.DataFrame, window: int = 14) -> pd.Series
```

### 4.4 缓存管理架构 (`cache_manager.py`)

#### 4.4.1 缓存策略设计
```python
# 缓存键命名规范
stock_data:{symbol}:{period}:{date_range}    # 股票数据缓存
search_results:{query_hash}                  # 搜索结果缓存
pending_save:{symbol}:{period}               # 待持久化数据
ai_analysis:{task_id}                        # AI分析结果缓存
```

#### 4.4.2 智能TTL策略
- **交易时间内**：短TTL（5-15分钟），确保数据实时性
- **交易时间外**：长TTL（1-4小时），减少不必要的API调用
- **历史数据**：超长TTL（24小时+），历史数据变化频率低
- **搜索结果**：中等TTL（30分钟），平衡性能和准确性

## 5. 前端架构详解

### 5.1 组件架构设计
采用现代化的React组件架构，基于功能模块进行组织：

#### 5.1.1 主应用组件 (`App.tsx`)
```typescript
// 主应用结构
function App() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-4 py-8">
        <StockSearch />
        <TradingViewChart />
        <AIAnalysis />
      </main>
    </div>
  )
}
```

**职责**：
- 全局状态管理和布局控制
- 主题和样式系统初始化
- 路由和导航管理
- 错误边界和异常处理

#### 5.1.2 智能搜索组件 (`StockSearch.tsx`)
```typescript
interface StockSearchProps {
  onStockSelect: (symbol: string) => void
  placeholder?: string
}

// 核心功能
- 实时搜索建议 (debounced input)
- 模糊匹配算法 (symbol, name, cname)
- 键盘导航支持 (↑↓ 选择, Enter 确认)
- 搜索历史记录
```

**特性**：
- **实时建议**：300ms防抖，减少API调用
- **智能匹配**：优先匹配symbol，其次name和cname
- **缓存优化**：本地缓存搜索结果，提升用户体验
- **无障碍支持**：完整的键盘导航和屏幕阅读器支持

#### 5.1.3 图表组件 (`TradingViewChart.tsx`)
```typescript
interface ChartProps {
  symbol: string
  timeframe: '1D' | '1W' | '10m' | '1m'
  data: CandlestickData[]
}

// TradingView Lightweight Charts 集成
- 专业K线图表显示
- 多时间粒度切换
- 技术指标叠加
- 交互式图表操作
```

**特性**：
- **专业图表**：基于TradingView Lightweight Charts
- **多时间粒度**：支持日线、周线、10分钟线、分钟线
- **技术指标**：MA、RSI、MACD、布林带等
- **响应式设计**：适配不同屏幕尺寸

#### 5.1.4 AI分析组件 (`AIAnalysis.tsx`)
```typescript
interface AIAnalysisProps {
  symbol: string
  mode: 'sequential' | 'parallel'
}

// AI分析界面
- 分析模式选择 (顺序/并行)
- 实时进度显示
- 流式结果展示
- 分析历史记录
```

**特性**：
- **流式显示**：Server-Sent Events实时更新
- **并行模式**：多Agent分析结果并行展示
- **进度反馈**：实时显示分析进度和状态
- **结果缓存**：本地缓存分析结果，支持历史查看

### 5.2 状态管理策略

#### 5.2.1 React Hooks模式
```typescript
// 自定义Hooks设计
const useStockData = (symbol: string, timeframe: string) => {
  const [data, setData] = useState<StockData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 数据获取逻辑
  // 缓存管理
  // 错误处理
}

const useAIAnalysis = (symbol: string) => {
  // AI分析状态管理
  // 流式数据处理
  // 任务状态跟踪
}
```

#### 5.2.2 数据流设计
```
用户交互 → 组件状态更新 → API调用 → 数据处理 → UI更新
    ↓           ↓            ↓        ↓         ↓
  搜索输入    loading状态   HTTP请求  数据转换   图表渲染
```

### 5.3 UI系统设计

#### 5.3.1 设计系统 (shadcn/ui + TailwindCSS)
```typescript
// 组件库使用
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

// 主题配置
const theme = {
  colors: {
    primary: "hsl(var(--primary))",
    secondary: "hsl(var(--secondary))",
    background: "hsl(var(--background))",
    foreground: "hsl(var(--foreground))",
  }
}
```

#### 5.3.2 响应式设计
- **移动优先**：基于TailwindCSS的响应式断点
- **自适应布局**：Flexbox和Grid布局系统
- **触摸友好**：移动设备优化的交互设计
- **性能优化**：组件懒加载和代码分割

## 6. 数据库设计

### 6.1 核心表结构

#### 6.1.1 股票代码映射表 (`stock_symbols`)
```sql
CREATE TABLE stock_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,           -- 简化代码 (如 AAPL)
    fullsymbol VARCHAR(20) NOT NULL,       -- 完整代码 (如 AAPL.US)
    name VARCHAR(255),                     -- 英文名称
    cname VARCHAR(255),                    -- 中文名称
    exchange VARCHAR(50),                  -- 交易所
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(symbol),
    UNIQUE(fullsymbol)
);

-- 索引优化
CREATE INDEX idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX idx_stock_symbols_name ON stock_symbols(name);
```

#### 6.1.2 股票价格表 (`stock_prices_daily/weekly`)
```sql
CREATE TABLE stock_prices_daily (
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,4) NOT NULL,
    high DECIMAL(10,4) NOT NULL,
    low DECIMAL(10,4) NOT NULL,
    close DECIMAL(10,4) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (ticker, date)
);

-- 性能优化索引
CREATE INDEX idx_stock_prices_daily_ticker ON stock_prices_daily(ticker);
CREATE INDEX idx_stock_prices_daily_date ON stock_prices_daily(date);
```

#### 6.1.3 新闻数据表 (`stock_news`)
```sql
CREATE TABLE stock_news (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    url VARCHAR(500),
    publish_time TIMESTAMP,
    sentiment_score DECIMAL(3,2),          -- 情感评分 (-1 到 1)
    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (ticker) REFERENCES stock_symbols(symbol)
);

-- 查询优化索引
CREATE INDEX idx_stock_news_ticker ON stock_news(ticker);
CREATE INDEX idx_stock_news_publish_time ON stock_news(publish_time);
```

### 6.2 索引策略

#### 6.2.1 查询优化索引
- **复合索引**：`(ticker, date)` 优化时间范围查询
- **覆盖索引**：包含常用查询字段，减少回表操作
- **部分索引**：针对活跃股票的条件索引

#### 6.2.2 搜索优化
```sql
-- 全文搜索索引 (PostgreSQL)
CREATE INDEX idx_stock_symbols_search
ON stock_symbols
USING gin(to_tsvector('english', name || ' ' || cname));

-- 模糊匹配优化
CREATE INDEX idx_stock_symbols_symbol_pattern
ON stock_symbols(symbol varchar_pattern_ops);
```

## 7. 现代化架构模式

### 7.1 依赖注入设计 (`dependencies.py`)
```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

# 现代化类型别名
DatabaseDep = Annotated[Session, Depends(get_database)]
CacheDep = Annotated[Redis, Depends(get_redis)]
ConfigDep = Annotated[Settings, Depends(get_settings)]

# 使用示例
async def get_stock_data(
    symbol: str,
    db: DatabaseDep,
    cache: CacheDep,
    config: ConfigDep
) -> StockData:
    # 业务逻辑实现
    pass
```

### 7.2 异常处理架构 (`exceptions.py`)
```python
# 分层异常类设计
class StockAIvoException(Exception):
    """基础异常类"""
    pass

class ValidationException(StockAIvoException):
    """数据验证异常"""
    pass

class DataServiceException(StockAIvoException):
    """数据服务异常"""
    pass

class AIServiceException(StockAIvoException):
    """AI服务异常"""
    pass

# 全局异常处理器
@app.exception_handler(StockAIvoException)
async def handle_stockaivo_exception(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "type": type(exc).__name__}
    )
```

### 7.3 中间件系统 (`middleware.py`)
```python
# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(f"{request.method} {request.url} - {response.status_code} - {process_time:.3f}s")
    return response

# 性能监控中间件
@app.middleware("http")
async def performance_monitoring(request: Request, call_next):
    # 慢请求检测和性能指标收集
    pass
```

## 8. 开发环境与工具链

### 8.1 现代化依赖管理

#### 8.1.1 Python环境 (uv)
```bash
# 环境初始化
uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/simple

# 开发服务器启动
uv run uvicorn main:app --reload

# 脚本配置 (pyproject.toml)
[tool.uv.scripts]
dev = "uvicorn main:app --reload"
start = "uvicorn main:app --host 0.0.0.0 --port 3227"
test = "pytest tests/"
lint = "mypy stockaivo/"
```

#### 8.1.2 前端环境 (pnpm)
```bash
# 依赖安装
pnpm install

# 开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 类型检查
pnpm type-check
```

### 8.2 代码质量保证

#### 8.2.1 Python代码质量
```python
# MyPy配置 (pyproject.toml)
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

# pytest配置
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

#### 8.2.2 前端代码质量
```typescript
// ESLint配置 (eslint.config.js)
export default [
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'error',
      '@typescript-eslint/explicit-function-return-type': 'warn',
      'react-hooks/exhaustive-deps': 'warn'
    }
  }
]

// TypeScript配置 (tsconfig.json)
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

### 8.3 部署配置

#### 8.3.1 Docker容器化
```dockerfile
# 后端Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
EXPOSE 3227
CMD ["uv", "run", "start"]

# 前端Dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build
EXPOSE 3000
CMD ["pnpm", "preview"]
```

#### 8.3.2 环境配置
```python
# 环境变量配置 (.env)
DATABASE_URL=postgresql://user:pass@localhost:5432/stockaivo
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your_gemini_api_key
AKSHARE_TOKEN=your_akshare_token

# 配置管理 (config.py)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    gemini_api_key: str
    akshare_token: str

    class Config:
        env_file = ".env"
```

## 9. 代码规范与最佳实践

### 9.1 API设计规范
- **RESTful风格**：遵循REST API设计原则
- **版本控制**：API路径包含版本号 `/api/v1/`
- **统一响应格式**：成功和错误响应的一致性
- **文档自动生成**：基于FastAPI的自动API文档

### 9.2 数据处理规范
- **类型安全**：完整的类型注解和验证
- **异常处理**：分层异常处理和错误传播
- **缓存策略**：智能缓存TTL和失效机制
- **数据验证**：Pydantic模型验证和序列化

### 9.3 前端开发规范
- **组件设计**：单一职责原则和可复用性
- **状态管理**：React Hooks模式和数据流控制
- **性能优化**：懒加载、代码分割、缓存策略
- **用户体验**：响应式设计和无障碍支持

### 9.4 AI系统规范
- **Agent设计**：清晰的角色定义和职责分离
- **工作流管理**：LangGraph编排和状态跟踪
- **模型配置**：按Agent类型的专用模型配置
- **结果处理**：流式响应和实时进度反馈

## 10. 系统特色与技术优势

### 10.1 核心技术创新
- **三级缓存架构**：Redis → PostgreSQL → AKShare的智能数据获取策略
- **多Agent并行分析**：基于LangGraph的AI工作流编排，提升分析效率2-3倍
- **实时流式响应**：Server-Sent Events技术实现AI分析的实时进度展示
- **交易日历感知**：智能日期处理，自动跳过非交易日和节假日

### 10.2 架构设计优势
- **现代化技术栈**：采用最新版本的React 19、Python 3.12、FastAPI等
- **类型安全保证**：前后端完整的类型系统，减少运行时错误
- **模块化设计**：清晰的模块边界和接口定义，易于扩展和维护
- **性能优化**：多层缓存、异步处理、并行计算等性能优化策略

### 10.3 用户体验优势
- **专业级图表**：集成TradingView Lightweight Charts，提供专业的金融图表体验
- **智能搜索**：实时搜索建议和模糊匹配，提升用户操作效率
- **响应式设计**：适配桌面和移动设备，确保跨平台一致性
- **实时反馈**：AI分析过程的实时进度显示，提升用户体验

---

**文档版本**: v2.0
**最后更新**: 2025年7月
**维护者**: StockAIvo开发团队
