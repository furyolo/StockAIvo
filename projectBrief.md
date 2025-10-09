# StockAIvo 技术架构文档 v3.0.1

## 1. 项目概述与技术定位

### 1.1 项目定位
StockAIvo 是一个现代化的**全栈美股智能分析与数据平台**，采用最新的前后端分离架构，集成多Agent并行AI分析、结构化预测系统和智能数据验证，为投资者和研究人员提供企业级的股票数据服务和量化分析工具。

### 1.2 核心技术创新
- **智能数据管理**：三级缓存策略（Redis → PostgreSQL → AKShare）确保高效可靠的数据获取
- **多Agent并行AI分析**：基于LangGraph的并行分析架构，分析速度提升2-3倍
- **结构化预测系统**：基于多维分析生成概率化股价预测，支持量化投资决策
- **智能数据验证**：ValidationResult类 + 价格边界修复 + 分层验证策略
- **现代化界面**：Mantine UI 8.3.1 + TradingView Lightweight Charts专业级用户体验

### 1.3 技术特色
- **v3.0.1前端重构**：从shadcn/ui + TailwindCSS完全迁移至Mantine UI 8.3.1
- **类型安全保障**：Python 3.13 + TypeScript 5.8.3双重类型系统
- **AI模型专用化**：按Agent类型配置专用Google Gemini模型
- **实时流式响应**：Server-Sent Events实现AI分析实时进度展示

### 1.4 目标用户
- **量化开发者**：需要集成股票API和AI分析的应用开发者
- **金融研究员**：需要历史数据和智能分析工具的研究人员
- **机构投资者**：需要专业级分析平台和量化预测的投资机构

## 2. 系统架构设计

### 2.1 整体架构模式
采用**分层架构模式**结合**微服务化设计思想**：

```
┌─────────────────────────────────────────────────────────────┐
│                    表现层 (Presentation Layer)                │
│  React 19.1.0 + TypeScript 5.8.3 + Mantine UI 8.3.1      │
│  TradingView Lightweight Charts 5.0.8 + 流式响应            │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP/WebSocket/SSE
┌─────────────────────────────────────────────────────────────┐
│                      API层 (API Layer)                      │
│  FastAPI 0.115.13 + Pydantic 2.11.7 + 现代化依赖注入       │
│  RESTful API + Server-Sent Events + 统一异常处理            │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   业务逻辑层 (Business Layer)                 │
│  三级缓存数据服务 │ 智能搜索 │ 多Agent AI分析 │ 缓存管理    │
│  结构化预测 │ 智能数据验证 │ 并行工作流编排                  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据访问层 (Data Access Layer)              │
│  SQLAlchemy 2.0.41 ORM + Redis 8.2.1 + 智能验证           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据存储层 (Storage Layer)                  │
│  PostgreSQL 17+ (主数据库) + Redis (缓存)                  │
│  AKShare 1.17.6 (美股数据) + TickerTick (新闻数据)          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则
- **模块化设计**：清晰的模块边界和接口定义，支持微服务化扩展
- **现代化依赖注入**：基于 `Annotated` 类型的类型安全依赖注入模式
- **分层异常处理**：ValidationException、DataServiceException、AIServiceException
- **双重类型安全**：Python MyPy + TypeScript 完整类型系统保障
- **智能缓存优先**：三级缓存策略 + 交易日历感知的智能TTL管理
- **AI工作流编排**：LangGraph多Agent并行执行，支持动态依赖控制
- **数据驱动验证**：ValidationResult类 + 价格边界修复 + 5%异常容忍机制

## 3. 核心技术栈 v3.0.1

### 3.1 后端技术栈
| 组件         | 技术                    | 版本        | 用途                |
| ------------ | ----------------------- | ----------- | ------------------- |
| **Web框架**  | FastAPI                 | 0.115.13+   | 高性能异步Web框架   |
| **数据库**   | PostgreSQL              | 17+         | 主数据存储          |
| **缓存**     | Redis                   | 8.2.0+      | 高速缓存和消息队列  |
| **ORM**      | SQLAlchemy              | 2.0.41+     | 现代化ORM框架       |
| **AI工作流** | LangGraph               | 0.4.8+      | 多Agent并行编排引擎 |
| **LLM集成**  | Google Generative AI    | 0.8.5+      | Gemini模型集成      |
| **数据源**   | AKShare                 | 1.17.6+     | 美股数据API         |
| **新闻数据** | TickerTick              | Integration | 实时新闻数据        |
| **交易日历** | pandas-market-calendars | 5.1.1+      | NYSE交易日历管理    |

### 3.2 前端技术栈
| 组件         | 技术                           | 版本    | 用途                   |
| ------------ | ------------------------------ | ------- | ---------------------- |
| **框架**     | React                          | 19.1.0  | 现代化前端框架         |
| **语言**     | TypeScript                     | 5.8.3   | 类型安全的JavaScript   |
| **构建工具** | Vite                           | 7.0.0   | 快速构建工具           |
| **UI系统**   | Mantine UI                     | 8.3.1   | 现代化组件库和设计系统 |
| **图标库**   | @tabler/icons-react            | 3.35.0+ | 现代化图标库           |
| **图表库**   | TradingView Lightweight Charts | 5.0.8   | 专业金融图表           |
| **日期处理** | date-fns                       | 4.1.0   | 现代化日期处理库       |
| **Markdown** | react-markdown + remark-gfm    | 10.1.0+ | Markdown渲染和表格支持 |

### 3.3 开发工具链
| 工具               | 技术           | 用途                                |
| ------------------ | -------------- | ----------------------------------- |
| **Python依赖管理** | uv             | 现代化Python包和环境管理工具        |
| **Node.js包管理**  | pnpm 10.14.0+  | 高效的磁盘空间优化包管理器          |
| **Python类型检查** | MyPy 1.8.0+    | 渐进式类型检查，支持大型代码库      |
| **前端测试**       | Vitest 3.2.4+  | 现代化前端测试框架，支持UI测试      |
| **后端测试**       | pytest 8.4.1+  | 功能强大的Python测试框架            |
| **前端质量**       | ESLint 9.29.0+ | 现代化JavaScript/TypeScript代码检查 |
| **AI模型配置**     | 动态模型选择   | 按Agent类型配置专用Gemini模型       |

## 4. 后端架构详解

### 4.1 API路由设计
采用模块化路由器设计，每个路由器负责特定的业务领域：

#### 4.1.1 股票数据API (`routers/stocks.py`)
```python
# 核心端点设计 (RESTful API)
GET  /stocks/{ticker}/daily        # 获取日线数据
GET  /stocks/{ticker}/weekly       # 获取周线数据  
GET  /stocks/{ticker}/10min        # 获取10分钟线数据（聚合）
GET  /stocks/{ticker}/minute       # 获取分钟线数据
GET  /stocks/{ticker}/news         # 获取股票新闻（Redis缓存）
POST /stocks/realtime-quotes/update # 更新实时行情数据
POST /stocks/us-stock-names/update  # 更新美股名称数据
```

**特性**：
- 支持多时间粒度数据查询（daily/weekly/10min/minute）
- 智能日期范围处理（NYSE交易日历感知）
- 统一的JSON响应格式和分层异常处理
- 基于 `DatabaseDep` 和 `CacheDep` 的现代化依赖注入
- 数据管理API支持自动化数据更新和同步

#### 4.1.2 AI分析API (`routers/ai.py`)
```python
# AI分析端点 (多模式支持)
POST /ai/analyze-parallel          # 并行AI分析（推荐，速度提升2-3倍）
POST /ai/analyze-sequential        # 顺序AI分析（兼容模式）
POST /ai/predict-structured        # 结构化概率预测
```

**特性**：
- **并行分析模式**：技术分析、基本面分析、新闻情感分析同时执行
- **执行依赖控制**：综合分析仅在技术分析成功时执行，确保分析质量
- **结构化预测**：基于多维分析生成概率化股价预测，包含方向、概率值、置信度
- **类型安全异常处理**：防止Exception对象调用.items()方法的运行时错误
- **流式响应支持**：Server-Sent Events实现实时进度显示
- **专用模型配置**：按Agent类型配置不同的Gemini模型

#### 4.1.3 搜索API (`routers/search.py`)
```python
# 智能搜索端点
GET  /search/stocks?q={keyword}            # 股票搜索（模糊匹配）
GET  /search/stocks/suggestions?q={keyword} # 实时搜索建议
```

**特性**：
- **智能匹配算法**：支持symbol、name、cname多字段模糊匹配
- **实时搜索建议**：300ms防抖，减少API调用
- **缓存优化**：Redis缓存搜索结果，提升响应速度
- **中英文支持**：完美支持美股中英文名称搜索

### 4.2 数据服务层架构

#### 4.2.1 三级缓存策略 (`data_service.py`)
```
用户请求 → Redis缓存 → PostgreSQL数据库 → AKShare API
    ↓         ↓            ↓              ↓
  立即返回   缓存+返回    数据库+缓存+返回  获取+存储+缓存+返回
```

**核心特性**：
- **智能缓存TTL**：交易时间内外采用不同的缓存策略（交易时5-15分钟，非交易时1-4小时）
- **智能数据验证**：`ValidationResult`类 + 价格边界修复 + 5%异常容忍机制
- **数据完整性检查**：自动检测和补全缺失数据，基于NYSE交易日历
- **异步持久化**：使用PENDING_SAVE缓存机制，批量UPSERT优化
- **新闻数据优化**：仅Redis缓存，最近3天数据，确保时效性

#### 4.2.2 多时间粒度支持
| 时间粒度     | 存储策略         | 缓存策略  | 数据来源       | 特色                     |
| ------------ | ---------------- | --------- | -------------- | ------------------------ |
| **日线**     | PostgreSQL持久化 | Redis缓存 | AKShare API    | 复合主键(ticker+date)    |
| **周线**     | PostgreSQL持久化 | Redis缓存 | AKShare API    | 自动周线聚合和完整性检查 |
| **10分钟线** | 仅缓存           | Redis缓存 | 分钟线实时聚合 | 交易时间内高精度数据     |
| **分钟线**   | 仅缓存           | Redis缓存 | AKShare API    | 实时分钟级数据           |
| **新闻**     | 仅缓存           | Redis缓存 | TickerTick API | 最近3天，情感分析支持    |

### 4.3 AI分析引擎架构

#### 4.3.1 LangGraph多Agent并行工作流设计
```
数据收集与验证Agent
    ↓
┌─────────────────────────────────────────────────────────┐
│           并行执行 (Parallel Execution)                │
├──────────────────┬──────────────────┬──────────────────┤
│  技术分析Agent   │  基本面分析Agent │ 新闻情感分析Agent │
│  (MA/RSI/MACD)   │  (公司信息)      │  (情感评分)      │
└──────────────────┴──────────────────┴──────────────────┘
    ↓ (仅在技术分析成功时执行)
综合分析Agent
    ↓
结构化预测Agent
    ↓
概率化预测报告
```

#### 4.3.2 Agent详细设计与数据验证
| Agent               | 功能                   | 输入数据           | 输出结果                                | 数据验证机制                       |
| ------------------- | ---------------------- | ------------------ | --------------------------------------- | ---------------------------------- |
| **数据收集Agent**   | 多源数据获取与验证     | ticker、时间范围   | 验证后的OHLCV数据、新闻数据             | ValidationResult分层验证           |
| **技术分析Agent**   | 技术指标计算与趋势分析 | OHLCV数据          | MA、RSI、MACD、布林带、ATR、成交量分析  | 数据完整性检查 + 边界值修复        |
| **基本面分析Agent** | 公司基本面评估         | 公司名称、财务数据 | 估值分析、成长性、行业地位评估          | 公司名称自动获取 + 数据可用性检查  |
| **新闻情感Agent**   | 实时新闻情感分析       | 新闻文本、时间序列 | 情感评分、关键事件、情绪趋势            | 新闻时效性验证 + 去重处理          |
| **综合分析Agent**   | 多维度分析整合         | 所有可用分析结果   | 综合投资建议、风险评估                  | **执行依赖控制**：依赖技术分析成功 |
| **结构化预测Agent** | 概率化股价预测         | 综合分析结果       | 方向(UP/DOWN)、概率值、置信度、推理过程 | 动态Prompt适配 + 可用性检查        |

#### 4.3.3 智能数据验证系统 (`ValidationResult`类)
```python
class ValidationResult:
    """统一数据验证结果类"""
    def __init__(self, is_valid: bool, data=None, error_msg=None):
        self.is_valid = is_valid
        self.data = data  # 修复后的数据
        self.error_msg = error_msg
        
    def validate_price_data(self, df: pd.DataFrame) -> ValidationResult:
        """价格数据验证：边界检查 + 异常值修复（5%容忍度）"""
        # 1. 检查OHLCV数据完整性
        # 2. 验证价格逻辑关系（L<=O<=H, L<=C<=H）
        # 3. 边界值检查和自动修复
        # 4. 异常值检测和统计修复
        
    def validate_trading_days(self, dates: pd.DatetimeIndex) -> ValidationResult:
        """交易日历验证：基于NYSE交易日历"""
        # 1. 检查是否为交易日
        # 2. 处理时区转换
        # 3. 日期范围合理性验证
```

#### 4.3.4 技术指标计算 (`technical_indicator.py`)
```python
class TechnicalIndicator:
    """增强的技术指标计算，包含成交量观察和趋势验证"""
    
    def calculate_ma(self, data: pd.DataFrame, windows: List[int]) -> Dict[str, pd.Series]
    def calculate_rsi(self, data: pd.DataFrame, window: int = 14) -> pd.Series  
    def calculate_macd(self, data: pd.DataFrame) -> Dict[str, pd.Series]
    def calculate_bollinger_bands(self, data: pd.DataFrame) -> Dict[str, pd.Series]
    def calculate_atr(self, data: pd.DataFrame, window: int = 14) -> pd.Series
    
    def validate_indicator_data(self, indicator_data: pd.Series) -> ValidationResult:
        """技术指标数据验证：确保计算结果合理"""
        # 1. 检查数据完整性
        # 2. 验证指标值范围
        # 3. 趋势一致性检查
```

### 4.4 缓存管理架构 (`cache_manager.py`)

#### 4.4.1 三级缓存策略设计
```python
# 缓存键命名规范
stock_data:{symbol}:{period}:{date_range}      # 股票数据缓存
stock_news:{symbol}                           # 新闻数据缓存（最近3天）
search_results:{query_hash}                    # 搜索结果缓存（30分钟TTL）
pending_save:{symbol}:{period}                 # 待持久化数据（批量UPSERT）
ai_analysis:{task_id}                          # AI分析结果缓存（流式数据）
realtime_quotes:{symbol}                       # 实时行情缓存（交易时5分钟TTL）
```

#### 4.4.2 智能TTL与失效策略
| 数据类型        | 交易时间内TTL | 非交易时间TTL | 失效策略         | 特色说明               |
| --------------- | ------------- | ------------- | ---------------- | ---------------------- |
| **实时数据**    | 5分钟         | 1小时         | 价格变动触发失效 | 确保交易时段实时性     |
| **日/周线数据** | 15分钟        | 4小时         | 基于交易日历失效 | 历史数据减少API调用    |
| **分钟线数据**  | 10分钟        | 2小时         | 滚动时间窗口     | 交易时间内高精度       |
| **新闻数据**    | 30分钟        | 2小时         | 3天自动过期      | 仅缓存，确保时效性     |
| **搜索结果**    | 30分钟        | 2小时         | 用户查询触发更新 | 平衡性能和准确性       |
| **AI分析结果**  | 1小时         | 6小时         | 任务完成触发     | 支持历史查看和缓存复用 |

##### 技术分析结果缓存（2025年10月新增）
- 键命名规范：`technical_analysis:{ticker}:{market_aware_date}`，其中日期统一为 `YYYYMMDD`，便于按交易日排序与批量扫描。
- TTL 策略：交易时段固定 180 秒，闭市后延长至下一次开盘时间；若无法计算交易日历，则回退到 600 秒退化 TTL。
- 数据内容：序列化保存 `ticker`、`market_aware_date`、`analysis_text`、`metrics`、`generated_at`、`agent_version` 等字段，读写时确保类型安全。
- 故障降级：Redis 不可用或序列化失败时自动回退至直接调用 AI Agent，同时记录降级告警并跳过缓存写入。
- 监控改进：命中日志格式化 UTC 时间（如 `2025-10-09 06:57:07 UTC`），便于跨时区比对与审计。

#### 4.4.3 缓存统计与监控
```python
class CacheStats:
    """缓存统计和性能监控"""
    
    def get_cache_hit_rate(self) -> float:           # 缓存命中率
    def get_memory_usage(self) -> Dict[str, int]:    # 内存使用情况
    def get_ttl_distribution(self) -> Dict[str, int]: # TTL分布统计
    def cleanup_expired_keys(self) -> int:           # 清理过期键
    
    # 缓存健康检查端点
    # GET /cache-stats - 返回详细统计信息
```

## 5. 前端架构详解 (v3.0.1 Mantine UI重构)

### 5.1 组件架构设计
采用现代化的React组件架构，基于Mantine UI 8.3.1设计系统进行组织：

#### 5.1.1 主应用组件 (`App.tsx`)
```typescript
// Mantine UI重构后的主应用结构
function App() {
  return (
    <MantineProvider theme={theme}>
      <Notifications />
      <Container size="lg" px="md">
        <Stack gap="lg">
          <Paper shadow="sm" p="md" withBorder>
            <StockSearch />
          </Paper>
          <TradingViewChart />
          <AIAnalysis />
        </Stack>
      </Container>
    </MantineProvider>
  )
}
```

**重构亮点**：
- **MantineProvider集成**：统一主题和组件系统
- **现代化布局**：Container/Stack/Paper替代传统div布局
- **通知系统**：内置Notifications组件支持
- **设计系统**：完全遵循Mantine设计规范

#### 5.1.2 智能搜索组件 (`StockSearch.tsx`)
```typescript
interface StockSearchProps {
  onStockSelect: (symbol: string) => void
}

// Mantine UI重构后的搜索组件
function StockSearch({ onStockSelect }: StockSearchProps) {
  return (
    <Autocomplete
      placeholder="搜索股票代码或名称..."
      data={searchData}
      onOptionSubmit={onStockSelect}
      rightSection={<IconSearch />}
      limit={10}
    />
  )
}
```

**v3.0.1重构特性**：
- **Autocomplete组件**：替代原生input，提供更好的用户体验
- **图标集成**：@tabler/icons-react图标库支持
- **样式系统**：完全使用Mantine CSS-in-JS样式
- **无障碍优化**：完整的屏幕阅读器和键盘导航支持

#### 5.1.3 图表组件 (`TradingViewChart.tsx`)
```typescript
interface ChartProps {
  symbol: string
  timeframe: 'daily' | 'weekly' | '10min' | 'minute'
  data: CandlestickData[]
}

// 保持专业图表功能，UI集成Mantine
function TradingViewChart({ symbol, timeframe, data }: ChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  
  // TradingView Lightweight Charts集成
  // 多时间粒度切换
  // 技术指标叠加
  // 交互式操作
}
```

**特性保持**：
- **专业图表**：TradingView Lightweight Charts 5.0.8
- **多时间粒度**：完整支持所有时间粒度
- **技术指标**：完整的技术指标套件
- **性能优化**：大数据量的流畅渲染

#### 5.1.4 AI分析组件 (`AIAnalysis.tsx`)
```typescript
interface AIAnalysisProps {
  symbol: string
  mode: 'sequential' | 'parallel'
}

// Mantine UI重构后的AI分析界面
function AIAnalysis({ symbol, mode }: AIAnalysisProps) {
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>AI分析结果</Title>
        <SegmentedControl
          data={[
            { label: '并行分析', value: 'parallel' },
            { label: '顺序分析', value: 'sequential' }
          ]}
          value={mode}
        />
      </Group>
      
      <ScrollArea h={400}>
        <Stack gap="sm">
          {/* 流式分析结果展示 */}
          <Alert icon={<IconBrain />}>
            AI分析正在进行中...
          </Alert>
          
          {/* 结构化预测结果 */}
          {predictionResult && (
            <Paper withBorder p="md">
              <Text fw={500}>概率预测</Text>
              <Progress value={predictionProbability * 100} />
            </Paper>
          )}
        </Stack>
      </ScrollArea>
    </Stack>
  )
}
```

**v3.0.1重构亮点**：
- **现代组件**：Stack/Group/ScrollArea/Paper布局
- **状态管理**：SegmentedControl模式选择
- **流式展示**：Alert组件显示分析进度
- **预测可视化**：Progress组件显示概率值
- **响应式设计**：完美适配移动端

### 5.2 Mantine UI设计系统 (v3.0.1重构)

#### 5.2.1 主题与配置系统
```typescript
// MantineProvider配置
import { MantineProvider, createTheme } from '@mantine/core'

const theme = createTheme({
  primaryColor: 'blue',
  fontFamily: 'Inter, sans-serif',
  defaultRadius: 'md',
  colors: {
    // 自定义品牌色彩
    stockGreen: '#00d084',
    stockRed: '#ff3b69',
  },
  components: {
    Button: {
      styles: {
        root: {
          fontWeight: 600,
        },
      },
    },
    Paper: {
      defaultProps: {
        shadow: 'sm',
        withBorder: true,
      },
    },
  },
})

// 自动色彩方案支持
function App() {
  const [colorScheme, setColorScheme] = useLocalStorage<ColorScheme>({
    key: 'mantine-color-scheme',
    defaultValue: 'light',
    getInitialValueInEffect: true,
  })

  const toggleColorScheme = () => 
    setColorScheme(colorScheme === 'dark' ? 'light' : 'dark')
}
```

#### 5.2.2 核心设计组件
| Mantine组件    | 用途     | 替代的原生组件       | 优势                    |
| -------------- | -------- | -------------------- | ----------------------- |
| **Container**  | 页面容器 | div.container        | 响应式宽度，自动padding |
| **Stack**      | 垂直布局 | div + flex-direction | 简化间距，响应式gap     |
| **Group**      | 水平布局 | div + flex           | 对齐和分布控制          |
| **Paper**      | 卡片容器 | Card/div.card        | 统一阴影和边框样式      |
| **Grid**       | 网格布局 | div.grid             | 12列网格系统            |
| **ScrollArea** | 滚动区域 | div.overflow-auto    | 自定义滚动条，触摸优化  |

### 5.3 状态管理与数据流

#### 5.3.1 React Hooks增强模式
```typescript
// 类型安全的自定义Hooks
const useStockData = (symbol: string, timeframe: TimeFrame) => {
  const [data, setData] = useState<ValidatedStockData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidationResult>()

  // 数据获取与验证
  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.getStockData(symbol, timeframe)
      setValidationResult(response.validation)
      setData(response.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [symbol, timeframe])

  return { data, loading, error, validationResult, refetch: fetchData }
}

// AI分析状态管理（支持流式数据）
const useAIAnalysis = (symbol: string, mode: AnalysisMode) => {
  const [analysisState, setAnalysisState] = useState<AnalysisState>({
    status: 'idle',
    progress: 0,
    agents: {},
    results: {},
    prediction: null,
  })

  // 流式数据处理
  useEventSource(`/ai/analyze-${mode}`, {
    onMessage: (event) => {
      const data = JSON.parse(event.data)
      setAnalysisState(prev => ({ ...prev, ...data }))
    },
  })

  return analysisState
}
```

#### 5.3.2 数据流架构
```
用户交互 → 组件状态更新 → API调用 → 数据验证 → UI更新
    ↓           ↓            ↓        ↓         ↓
  搜索输入    Mantine状态   HTTP请求  ValidationResult  组件重渲染
     ↓            ↓            ↓         ↓            ↓
  Autocomplete → useDebounce  FastAPI  分层验证      实时反馈
```

### 5.4 性能与优化策略

#### 5.4.1 前端性能优化
- **组件懒加载**：动态import大型组件
- **代码分割**：Vite自动代码分割
- **虚拟化长列表**：大数据量的搜索结果
- **图片优化**：图表和图标资源优化
- **缓存策略**：浏览器缓存和API响应缓存

#### 5.4.2 用户体验优化
- **加载状态**：Mantine Loader组件
- **错误处理**：统一的错误展示
- **无障碍支持**：完整的ARIA标签
- **响应式设计**：移动端完美适配

## 6. 数据库设计 (v3.0.1优化)

### 6.1 核心表结构（基于实际数据库）

#### 6.1.1 股票代码映射表 (`stock_symbols`)
```sql
CREATE TABLE stock_symbols (
    fullsymbol VARCHAR(20) PRIMARY KEY,         -- 完整代码，主键
    symbol VARCHAR(10) NOT NULL,               -- 简化代码
    name VARCHAR(255) NOT NULL,                -- 英文名称
    -- 价格相关字段
    price DECIMAL(10, 4),                      -- 最新价
    price_change DECIMAL(10, 4),              -- 涨跌额
    price_change_percent DECIMAL(10, 4),      -- 涨跌幅
    open DECIMAL(10, 4),                       -- 开盘价
    high DECIMAL(10, 4),                       -- 最高价
    low DECIMAL(10, 4),                        -- 最低价
    pre_close DECIMAL(10, 4),                  -- 昨收价
    -- 市场数据字段
    market_value BIGINT,                       -- 总市值
    pe_ratio DECIMAL(10, 4),                  -- 市盈率
    volume BIGINT,                             -- 成交量
    turnover BIGINT,                           -- 成交额
    amplitude DECIMAL(10, 4),                 -- 振幅
    turnover_rate DECIMAL(10, 4),             -- 换手率
    -- 时间戳字段
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 性能优化索引
CREATE INDEX idx_stock_symbols_symbol ON stock_symbols(symbol);


```

#### 6.1.2 股票价格表 (`stock_prices_daily/weekly`)
```sql
-- 日线数据表
CREATE TABLE stock_prices_daily (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10, 4) NOT NULL,
    high DECIMAL(10, 4) NOT NULL,
    low DECIMAL(10, 4) NOT NULL,
    close DECIMAL(10, 4) NOT NULL,
    volume BIGINT,                             -- 成交量
    turnover BIGINT,                           -- 交易额
    amplitude DECIMAL(10, 4),                 -- 振幅
    price_change_percent DECIMAL(10, 4),      -- 涨跌幅
    price_change DECIMAL(10, 4),              -- 涨跌额
    turnover_rate DECIMAL(10, 4),             -- 换手率
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    PRIMARY KEY (ticker, date)
);

-- 周线数据表
CREATE TABLE stock_prices_weekly (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,                       -- 周结束日期
    open DECIMAL(10, 4) NOT NULL,
    high DECIMAL(10, 4) NOT NULL,
    low DECIMAL(10, 4) NOT NULL,
    close DECIMAL(10, 4) NOT NULL,
    volume BIGINT,                             -- 成交量
    turnover BIGINT,                           -- 交易额
    amplitude DECIMAL(10, 4),                 -- 振幅
    price_change_percent DECIMAL(10, 4),      -- 涨跌幅
    price_change DECIMAL(10, 4),              -- 涨跌额
    turnover_rate DECIMAL(10, 4),             -- 换手率
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    PRIMARY KEY (ticker, date)
);

-- 实际索引结构
CREATE INDEX idx_daily_date ON stock_prices_daily(date);
CREATE INDEX idx_daily_ticker ON stock_prices_daily(ticker);
CREATE INDEX idx_daily_ticker_date ON stock_prices_daily(ticker, date);
CREATE INDEX idx_weekly_date ON stock_prices_weekly(date);
CREATE INDEX idx_weekly_ticker ON stock_prices_weekly(ticker);
CREATE INDEX idx_weekly_ticker_date ON stock_prices_weekly(ticker, date);


```

#### 6.1.3 美股名称表 (`us_stocks_name`)
```sql
CREATE TABLE us_stocks_name (
    symbol VARCHAR PRIMARY KEY,                 -- 股票代码，主键
    name VARCHAR(255) NOT NULL,               -- 英文名称
    cname VARCHAR(255),                        -- 中文名称
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 实际索引结构
CREATE INDEX idx_us_stocks_name_name ON us_stocks_name(name);
CREATE INDEX idx_us_stocks_name_cname ON us_stocks_name(cname);
CREATE INDEX idx_us_stocks_name_composite ON us_stocks_name(symbol, name, cname);


```

#### 6.1.4 股票预测结果表 (`stock_predictions`)
```sql
CREATE TABLE stock_predictions (
    ticker VARCHAR(10) NOT NULL,               -- 股票代码
    market_aware_date DATE NOT NULL,          -- 市场感知日期（分析基准日期）
    target_date DATE NOT NULL,                 -- 预测目标日期
    trading_days_count BIGINT NOT NULL,       -- 预测交易日数量
    prediction_probability DECIMAL(5, 4) NOT NULL, -- 预测概率值(0.0000-1.0000)
    direction VARCHAR(4) NOT NULL,             -- 预测方向(UP/DOWN)
    confidence_level VARCHAR(6) NOT NULL,      -- 置信度(HIGH/MEDIUM/LOW)
    reasoning TEXT,                            -- 预测推理说明
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, market_aware_date)
);

-- 实际索引结构
CREATE INDEX idx_stock_predictions_ticker ON stock_predictions(ticker);
CREATE INDEX idx_stock_predictions_market_date ON stock_predictions(market_aware_date);
CREATE INDEX idx_stock_predictions_target_date ON stock_predictions(target_date);
CREATE INDEX idx_stock_predictions_direction ON stock_predictions(direction);
CREATE INDEX idx_stock_predictions_confidence ON stock_predictions(confidence_level);
CREATE INDEX idx_stock_predictions_ticker_direction ON stock_predictions(ticker, direction);
CREATE INDEX idx_stock_predictions_date_range ON stock_predictions(market_aware_date, target_date);

-- 唯一约束
CREATE UNIQUE INDEX uk_prediction_ticker_date ON stock_predictions(ticker, market_aware_date);


```

**功能说明**：
- 存储AI分析的结构化概率预测结果
- 复合主键确保每只股票每天只有一个预测记录
- 包含预测概率、方向、置信度和详细推理过程
- 多维度索引支持各种查询和分析需求

### 6.2 缓存策略与数据管理

**注意**: 新闻数据已移除数据库持久化，仅使用Redis缓存，确保时效性和分析相关性。
```python
# 缓存键命名规范和TTL策略
CACHE_KEYS = {
    'stock_data': 'stock_data:{symbol}:{period}:{date_range}',        # 股票数据
    'stock_news': 'stock_news:{symbol}',                              # 新闻数据
    'search_results': 'search:{query_hash}',                         # 搜索结果
    'realtime_quotes': 'quotes:{symbol}',                            # 实时行情
    'ai_analysis': 'ai_analysis:{task_id}',                          # AI分析结果
    'validation_cache': 'validation:{symbol}:{period}',              # 数据验证缓存
}

# TTL策略（基于交易时间）
TTL_STRATEGY = {
    'trading_hours': {
        'realtime_data': 300,      # 5分钟
        'daily_data': 900,        # 15分钟
        'news_data': 1800,        # 30分钟
    },
    'non_trading_hours': {
        'realtime_data': 3600,     # 1小时
        'daily_data': 14400,       # 4小时
        'news_data': 7200,        # 2小时
    }
}
```

#### 6.2.2 数据验证与清洗机制
```python
class DataValidation:
    """数据验证和自动修复系统"""
    
    def validate_ohlcv(self, data: pd.DataFrame) -> ValidationResult:
        """OHLCV数据验证"""
        # 1. 完整性检查
        # 2. 逻辑关系验证 (L <= O <= H, L <= C <= H)
        # 3. 异常值检测 (5%容忍度)
        # 4. 自动修复机制
        
    def validate_trading_day(self, date: datetime) -> bool:
        """交易日验证"""
        # 1. 检查是否为NYSE交易日
        # 2. 处理时区转换
        # 3. 假日检查
        
    def clean_duplicate_data(self, symbol: str, period: str) -> int:
        """重复数据清理"""
        # 1. 检测重复记录
        # 2. 保留最新数据
        # 3. 返回清理记录数
```

### 6.3 性能优化策略

#### 6.3.1 查询性能优化
- **复合主键**：`(ticker, date)` 提升时间范围查询性能
- **覆盖索引**：包含常用查询字段，减少回表操作
- **分区表**：按时间分区，提升大数据量查询性能
- **连接池**：SQLAlchemy连接池优化

#### 6.3.2 缓存性能优化
- **Redis Pipeline**：批量操作减少网络往返
- **缓存预热**：热门数据预加载
- **智能失效**：基于市场状态和数据更新时间的失效策略
- **内存优化**：数据压缩和序列化优化

## 7. 现代化架构模式 (v3.0.1增强)

### 7.1 现代化依赖注入系统 (`dependencies.py`)
```python
from typing import Annotated, AsyncGenerator
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

# 现代化类型别名 - 支持同步和异步
DatabaseDep = Annotated[Session, Depends(get_database)]
AsyncDatabaseDep = Annotated[AsyncSession, Depends(get_async_database)]
CacheDep = Annotated[redis.Redis, Depends(get_redis)]
AsyncCacheDep = Annotated[redis.Redis, Depends(get_async_redis)]
ConfigDep = Annotated[Settings, Depends(get_settings)]

# AI模型专用依赖
TechnicalAnalysisModelDep = Annotated[GenerativeModel, Depends(get_technical_model)]
SynthesisModelDep = Annotated[GenerativeModel, Depends(get_synthesis_model)]

# 使用示例 - 完整类型安全
async def get_stock_data(
    symbol: str,
    db: AsyncDatabaseDep,
    cache: AsyncCacheDep,
    config: ConfigDep,
    tech_model: TechnicalAnalysisModelDep
) -> ValidatedStockData:
    # 异步数据库操作 + 缓存 + AI模型集成
    pass
```

### 7.2 分层异常处理架构 (`exceptions.py`)
```python
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel

# 错误代码枚举
class ErrorCode(Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DATA_SERVICE_ERROR = "DATA_SERVICE_ERROR"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    CACHE_ERROR = "CACHE_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"

# 统一错误响应格式
class ErrorResponse(BaseModel):
    success: bool = False
    error_code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = datetime.utcnow()

# 分层异常类设计
class StockAIvoException(Exception):
    """基础异常类"""
    def __init__(self, message: str, error_code: ErrorCode, details: Optional[Dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

class ValidationException(StockAIvoException):
    """数据验证异常"""
    def __init__(self, message: str, validation_result: ValidationResult):
        super().__init__(message, ErrorCode.VALIDATION_ERROR, {
            "validation_result": validation_result.dict()
        })

class DataServiceException(StockAIvoException):
    """数据服务异常"""
    def __init__(self, message: str, source: str):
        super().__init__(message, ErrorCode.DATA_SERVICE_ERROR, {"source": source})

class AIServiceException(StockAIvoException):
    """AI服务异常"""
    def __init__(self, message: str, agent_name: str, model: str):
        super().__init__(message, ErrorCode.AI_SERVICE_ERROR, {
            "agent": agent_name,
            "model": model
        })

# 全局异常处理器
@app.exception_handler(StockAIvoException)
async def handle_stockaivo_exception(request: Request, exc: StockAIvoException):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=str(exc),
            details=exc.details
        ).dict()
    )
```

### 7.3 智能中间件系统 (`middleware.py`)
```python
from time import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 请求日志中间件
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time()
        response = await call_next(request)
        process_time = time() - start_time

        logger.info(
            f"{request.method} {request.url} - {response.status_code} - {process_time:.3f}s"
        )
        
        # 结构化日志记录
        await log_request_metrics({
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "process_time": process_time,
            "user_agent": request.headers.get("user-agent"),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return response

# 性能监控中间件
class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time()
        response = await call_next(request)
        process_time = time() - start_time

        # 慢请求检测和告警
        if process_time > 2.0:  # 超过2秒的请求
            await alert_slow_request(request, process_time)
        
        # 性能指标收集
        await collect_performance_metrics({
            "endpoint": request.url.path,
            "method": request.method,
            "response_time": process_time,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return response

# 缓存中间件
class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 为GET请求启用缓存
        if request.method == "GET":
            cache_key = f"cache:{request.url}"
            cached_response = await redis_client.get(cache_key)
            
            if cached_response:
                return Response(
                    content=cached_response,
                    media_type="application/json"
                )
        
        response = await call_next(request)
        
        # 缓存GET请求响应
        if request.method == "GET" and response.status_code == 200:
            await redis_client.setex(
                cache_key, 
                300,  # 5分钟TTL
                response.body
            )
        
        return response
```

### 7.4 AI模型配置系统 (`ai_config.py`)
```python
from dataclasses import dataclass
from typing import Dict, Optional
from google.generativeai import GenerativeModel

@dataclass
class AIModelConfig:
    """AI模型配置类"""
    default_model: str = "gemini-2.5-flash"
    technical_analysis_model: str = "gemini-2.5-pro"
    synthesis_model: str = "gemini-2.5-pro"
    news_analysis_model: str = "gemini-2.5-flash"
    prediction_model: str = "gemini-2.5-pro"
    
    # 模型参数配置
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    
    # 专用配置映射
    agent_model_mapping: Dict[str, str] = None
    
    def __post_init__(self):
        self.agent_model_mapping = {
            "technical_analysis": self.technical_analysis_model,
            "fundamental_analysis": self.default_model,
            "news_sentiment": self.news_analysis_model,
            "synthesis": self.synthesis_model,
            "prediction": self.prediction_model,
        }

class AIModelManager:
    """AI模型管理器"""
    
    def __init__(self, config: AIModelConfig):
        self.config = config
        self._models: Dict[str, GenerativeModel] = {}
    
    async def get_model(self, agent_name: str) -> GenerativeModel:
        """获取指定Agent的专用模型"""
        model_name = self.config.agent_model_mapping.get(agent_name, self.config.default_model)
        
        if model_name not in self._models:
            self._models[model_name] = GenerativeModel(model_name)
        
        return self._models[model_name]
    
    async def generate_structured_output(self, agent_name: str, prompt: str, schema: Dict) -> Dict:
        """生成结构化输出"""
        model = await self.get_model(agent_name)
        
        # 使用Pydantic模型进行结构化输出
        response = await model.generate_content_async(prompt)
        
        # 解析和验证结构化输出
        return self._parse_structured_response(response, schema)
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
python_version = "3.13"
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
FROM python:3.13.7-alpine
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
EXPOSE 3227
CMD ["uv", "run", "start"]

# 前端Dockerfile
FROM node:24.8.0-alpine
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

**文档版本**: v3.0.1
**最后更新**: 2025年9月18日
**维护者**: StockAIvo开发团队

---

## 版本更新说明

### v3.0.1 主要更新内容 (2025年9月)

#### 🎨 前端UI架构重构
- **UI框架迁移**: 从shadcn/ui + TailwindCSS完全迁移至Mantine UI 8.3.1
- **现代化组件**: 使用Container/Stack/Group/Grid替代传统div布局
- **设计系统**: 统一的Mantine主题变量和CSS-in-JS样式系统
- **图标更新**: lucide-react → @tabler/icons-react
- **主题支持**: 内置明暗主题自动切换功能

#### 🤖 AI分析系统增强
- **结构化预测Agent**: 基于多维分析生成概率化股价预测
- **智能数据验证**: ValidationResult类 + 价格边界修复 + 分层验证策略
- **执行依赖控制**: 综合分析仅在技术分析成功时执行
- **类型安全异常处理**: 防止Exception对象调用.items()方法
- **Agent名称规范化**: 统一agent_name参数传递

#### 📊 数据管理优化
- **实时行情字段**: stock_symbols表增加实时行情数据支持
- **数据验证字段**: 价格表增加验证状态和详情字段
- **美股名称表**: 新增us_stocks_name表，支持中英文搜索
- **智能缓存策略**: 基于交易时间的动态TTL管理
- **性能监控**: 缓存统计和健康检查端点

#### 🛠️ 架构现代化
- **异步支持**: 数据库和缓存操作全面支持异步
- **AI模型专用化**: 按Agent类型配置专用Gemini模型
- **中间件增强**: 智能缓存、性能监控、结构化日志
- **异常处理升级**: 分层异常类和统一错误响应格式
- **依赖注入增强**: 支持同步/异步数据库操作和AI模型依赖
