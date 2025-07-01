# 项目配置指南 (`.env`)

本文档提供了配置项目所需环境变量的详细说明。通过编辑项目根目录下的 `.env` 文件，您可以自定义数据库连接和所需的大语言模型 (LLM) 服务。

## 1. `.env` 文件简介

`.env` 文件用于存储敏感信息和特定于环境的配置，例如 API 密钥和数据库 URL。这允许我们将配置与代码分离，从而提高了安全性和灵活性。

项目启动时会加载此文件中的变量，并将其注入到应用程序的环境中。

**重要提示:** 请勿将 `.env` 文件提交到版本控制系统（如 Git）中，因为它可能包含敏感的凭据。通常应将 `.env` 添加到 `.gitignore` 文件中。

## 2. 数据库配置

应用程序使用 PostgreSQL 数据库。您需要在 `.env` 文件中提供数据库连接字符串。

### `DATABASE_URL`

此变量指定了用于连接到 PostgreSQL 数据库的完整 URL。

**格式:**
```
postgresql://<user>:<password>@<host>:<port>/<dbname>
```

**`.env` 示例:**
```env
DATABASE_URL="postgresql://postgres:123456@localhost:5432/stock"
```

## 3. 大语言模型 (LLM) 服务配置

本系统支持两种类型的 LLM 服务：**OpenAI 兼容 API** 和 **Google Gemini API**。系统会根据 `.env` 文件中的配置自动选择使用哪一个。

**选择逻辑:**
系统会优先检查是否存在 `OPENAI_API_BASE` 和 `OPENAI_API_KEY`。如果二者都已设置，则会使用 OpenAI 兼容 API。否则，它将回退到检查 `GEMINI_API_KEY` 并使用 Google Gemini API。

### 3.1. 使用 OpenAI 兼容 API

要使用任何与 OpenAI API 格式兼容的服务（例如本地模型、LM Studio、Ollama 等），请配置以下变量：

*   `OPENAI_API_BASE`: 服务的 URL 端点。
*   `OPENAI_API_KEY`: 您的 API 密钥（即使本地服务不需要，也需要填写一个非空值）。
*   `OPENAI_MODEL_NAME`: **（必需）** 您希望使用的具体模型名称。

**`.env` 配置示例:**
```env
# --- OpenAI 兼容 API 设置 ---
OPENAI_API_BASE="http://localhost:1234/v1"
OPENAI_API_KEY="sk-your-key-here"
OPENAI_MODEL_NAME="gpt-4"

# 注释掉或移除 Gemini 变量以确保使用 OpenAI
# GEMINI_API_KEY=
# GEMINI_MODEL_NAME=
```

### 3.2. 使用 Google Gemini API

要使用 Google Gemini，请配置以下变量：

*   `GEMINI_API_KEY`: 您的 Google AI Studio API 密钥。
*   `GEMINI_MODEL_NAME`: **（必需）** 您希望使用的具体 Gemini 模型名称（例如 `gemini-pro`）。

**`.env` 配置示例:**
```env
# --- Google Gemini API 设置 ---
GEMINI_API_KEY="your-google-api-key-here"
GEMINI_MODEL_NAME="gemini-1.5-pro-latest"

# 确保 OpenAI 变量为空或被注释掉
# OPENAI_API_BASE=
# OPENAI_API_KEY=
# OPENAI_MODEL_NAME=
```

**【关键】模型名称是必需的**

根据系统实现 ([`stockaivo/ai/llm_service.py:1`](stockaivo/ai/llm_service.py:1))，无论您选择哪种服务，都**必须**为该服务提供一个明确的 `MODEL_NAME`。如果选择了某个服务但未在 `.env` 文件中提供相应的模型名称（`OPENAI_MODEL_NAME` 或 `GEMINI_MODEL_NAME`），应用程序将无法启动并会抛出错误
## 4. 性能优化

### 问题描述
之前，在通过 API (`/stocks/{symbol}/daily`) 请求特定日期范围的股票数据时，系统会从 AKShare 拉取该股票的全部历史数据。随后，数据在内存中进行过滤，以筛选出符合 `start_date` 和 `end_date` 的部分。这种方法不仅下载了大量非必要的数据，还占用了过多的内存和计算资源，导致 API 响应缓慢。

### 解决方案
为了解决此问题，我们对数据请求流程进行了优化。现在，`start_date` 和 `end_date` 参数会从 API 层一直传递到数据提供层 (`data_provider.py`)。这样，我们可以在调用 AKShare 接口的源头就指定所需的数据时间范围，而不是在获取全部数据后再进行过滤。

### 影响
此项优化带来了显著的性能提升：
*   **减少数据下载量：** 只请求指定日期范围内的数据，大幅降低了网络流量。
*   **降低内存消耗：** 无需在内存中加载和处理全部历史数据，有效减少了应用的内存占用。
*   **提高 API 响应速度：** 由于处理的数据量减少，API 能够更快地响应用户请求，提升了系统整体性能和用户体验。

## 5. AI Agent 工作流程

本节详细介绍用于股票分析的 AI Agent 工作流程的架构和组件。该系统利用 `LangGraph` 框架来编排一系列专门的 Agent，每个 Agent 执行分析过程中的特定任务。

### 5.1. 核心架构

工作流程被构建为一个有向无环图 (DAG)，其中每个节点代表一个 Agent，每条边代表节点之间的数据流和依赖关系。这种模块化的方法使得系统易于扩展和维护。

该工作流程在 [`LangGraphOrchestrator`](stockaivo/ai/orchestrator.py:19) 类中定义和编译，它负责管理整个分析过程的执行。

### 5.2. DataCollectionAgent

`DataCollectionAgent` 是整个 AI 分析工作流程的入口点。它的主要职责是为指定的股票代码收集必要的基础数据。

#### 作用和功能

- **数据获取**: 此 Agent 负责从系统的数据层获取原始数据。具体来说，它会调用在 [`DataService`](stockaivo/data_service.py:74) 中定义的 `get_stock_data` 函数。
- **数据类型**: 它主要获取两种时间周期的数据：日线 (`daily`) 和周线 (`weekly`) 的价格和交易量数据。
- **工作流程起点**: 在 [`LangGraphOrchestrator`](stockaivo/ai/orchestrator.py:45) 中，`DataCollectionAgent` 被设置为图的入口点 (`entry_point`)。这意味着任何分析任务都始于此 Agent。

#### 与 DataService 的交互

`DataCollectionAgent` 与 [`DataService`](stockaivo/data_service.py:74) 紧密集成，以利用项目中先进的数据处理能力：

1.  **调用服务**: Agent 通过调用 `get_stock_data` 函数来请求数据，而不是直接访问外部 API 或数据库。
2.  **利用缓存**: [`DataService`](stockaivo/data_service.py:74) 实现了多级缓存策略（Redis 缓存优先）。这意味着 `DataCollectionAgent` 的数据请求首先会尝试从缓存中获取，如果缓存中不存在或数据不完整，`DataService` 会自动处理从数据库或外部数据源（如 AKShare）获取数据，并更新缓存。
3.  **数据持久化**: 通过 `DataService` 获取的数据会被自动安排进行后台持久化存储到 PostgreSQL 数据库中，确保了数据的可靠性和后续分析的一致性。

#### 在 LangGraphOrchestrator 中的集成

- **节点定义**: 在 [`_create_workflow`](stockaivo/ai/orchestrator.py:26) 方法中，`data_collection_agent` 函数被注册为一个名为 `"data_collector"` 的节点。
- **流程控制**: 在数据收集完成后，`LangGraphOrchestrator` 会将 `DataCollectionAgent` 的输出（即原始股价数据）并行传递给下游的多个分析 Agent，包括 `technical_analyst`、`fundamental_analyst` 和 `news_sentiment_analyst`。这种“扇出”（fan-out）模式允许不同类型的分析同时进行，提高了效率。