### **项目文档：StockAIvo \- 智能美股数据与分析平台后端**

#### **1\. 项目概述**

StockAIvo 是一个面向美国股票市场的智能数据与分析后端服务。项目旨在通过现代化的技术栈，为前端应用或研究人员提供稳定、高效的股票数据接口，并利用大型语言模型（LLM）和多 Agent 协同系统，提供深度的、多视角的投资决策辅助。

* **项目名称:** StockAIvo  
* **核心目标:**  
  1. 提供按需、多时间粒度（日、周、小时）的美国股票数据。  
  2. 实现智能数据缓存与持久化机制，优化数据获取效率与成本。  
  3. 构建一个多 Agent 协同的 AI 系统，为投资决策提供智能化分析和建议。  
* **技术栈:**  
  * **Web 框架:** FastAPI  
  * **数据库:** PostgreSQL  
  * **缓存:** Redis  
  * **ORM:** SQLAlchemy  
  * **数据源:** AKShare  
  * **核心语言:** Python
  * **项目依赖与运行:** 使用 uv 进行高速的依赖管理和脚本运行，替代传统的 pip 和 venv

#### **2\. 开发环境与执行规范**

* **依赖管理:** 项目的所有 Python 依赖均在 `pyproject.toml` 文件中进行声明。  
  * **环境初始化:** 首次克隆或设置项目后，开发者应在项目根目录运行以下命令来创建虚拟环境并安装所有依赖：
      ```shell
    uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/simple
	``` 
  * **核心执行命令:** **重要注意事项：** 根据项目规范，所有 Python 程序（包括Web服务、数据处理脚本等）都**必须**通过 `uv run` 命令启动。这确保了所有代码都在由 `uv` 管理的、包含正确依赖的虚拟环境中执行。  
  * **启动 FastAPI 服务示例:**  
      ```shell
    # 在开发环境中启动，并开启热重载
uv run uvicorn main:app --reload
	``` 
  * **推荐实践:** 为了方便开发，建议在 `pyproject.toml` 文件中配置快捷脚本。
        ```Ini, TOML
   [tool.uv.scripts]
dev = "uvicorn main:app --reload"
start = "uvicorn main:app --host 0.0.0.0 --port 3227"
	``` 
  配置后，即可使用简化的命令启动服务：
        ```shell
# 启动开发服务器
uv run dev
	``` 

#### **3\. 系统架构**

系统主要由以下几个部分组成：

1. **API 层 (FastAPI):** 作为系统的入口，负责处理来自客户端（前端应用、分析脚本等）的 HTTP 请求。它解析请求参数，调用下层服务，并以 JSON 格式返回结果。  
2. **业务逻辑层:** 包含数据处理、AI 分析等核心功能。  
   * **数据服务模块:** 负责股票数据的获取、缓存和存储。  
   * **AI Agent 模块:** 负责协调多个 AI Agent 完成复杂的分析任务。  
3. **数据存储层:**  
   * **PostgreSQL:** 作为主数据库，用于永久存储结构化的股票数据（如公司信息、日/周/小时 K线数据等）。  
   * **Redis:** 作为高速缓存，临时存储从远程 API（AKShare）获取的、尚未入库的数据，同时也可用于缓存热点数据，降低数据库压力。  
4. **外部服务:**  
   * **AKShare:** 主要的第三方美股数据源。  
   * **大型语言模型 (LLM) API:** 为 AI Agent 提供自然语言处理和分析能力（例如 OpenAI GPT 系列, Google Gemini 等）。

#### **4\. 核心功能与任务拆解**

##### **功能一：智能数据获取与持久化**

**目标:** 建立一个高效、智能的数据管道，采用“缓存优先策略 (Cache-First Strategy)”来平衡实时性、成本和数据一致性。数据获取遵循 **1. Redis 缓存 -> 2. PostgreSQL 数据库 -> 3. 远程 API (AKShare)** 的读取顺序。

**任务拆解:**

* **1.1 数据库模式设计 (PostgreSQL & SQLAlchemy)**  
  * \[ \] 设计 stocks 表，用于存储股票基本信息（代码 ticker, 公司名称 company\_name, 上市交易所 exchange 等）。  
  * \[ \] 设计 stock\_prices\_daily 表，存储日 K 线数据（ticker, date, open, high, low, close, volume）。  
  * \[ \] 设计 stock\_prices\_weekly 表，存储周 K 线数据。  
  * \[ \] 设计 stock\_prices\_hourly 表，存储小时 K 线数据。  
  * \[ \] 使用 SQLAlchemy 创建对应的 ORM 模型。  
* **1.2 数据源封装 (AKShare)**  
  * \[ \] 创建一个 data\_provider.py 模块。  
  * \[ \] 参考 D:\\Coding\\stockai 项目，封装一个函数 fetch\_from\_akshare(ticker, period)，用于从 AKShare 获取指定股票、指定周期的数据。  
  * \[ \] 做好异常处理，例如网络错误、无数据返回等情况。  
* **1.3 Redis 缓存逻辑实现**  
  * \[ \] 配置 Redis 连接。  
  * \[ \] 实现一个函数 save\_to\_redis(ticker, data)，将从 AKShare 获取的数据以特定键（例如 pending\_save:{ticker}）存入 Redis。数据结构建议使用 Hash 或 String (JSON序列化)。  
  * \[ \] 实现一个函数 get\_from\_redis()，用于检查并获取所有待入库的数据。  
* **1.4 数据查询主逻辑**  
  * \[ \] 实现核心函数 get\_stock\_data(ticker, period)。  
  * \[ \] **逻辑流程 (缓存优先策略):**
    1. **查询 Redis 缓存:** 首先根据 `ticker` 和 `period` 查询 Redis 缓存。如果命中，则直接返回数据。
    2. **查询 PostgreSQL 数据库:** 如果缓存未命中，则查询 PostgreSQL 数据库。如果命中，返回数据并回填至缓存。
    3. **查询远程 API:** 如果数据库仍未命中，则从远程 API (AKShare) 获取数据。
    4. **数据更新与返回:** 从 API 获取的新数据将返回给用户，并异步写入数据库和缓存以备将来使用。
* **1.5 异步数据持久化**  
  * \[ \] **后端部分:** 创建一个特殊的 API 端点，例如 GET /check-pending-data。前端可以在用户空闲时轮询这个接口。该接口会检查 Redis 中是否有待入库的数据，如果有，则返回 {"pending": true}。  
  * \[ \] **前端交互逻辑 (需要与前端协同):**  
    * 前端应用检测到用户空闲（如无鼠标键盘操作超过 N 秒）。  
    * 调用 GET /check-pending-data 接口。  
    * 如果返回 {"pending": true}，则弹窗提示：“检测到新的股票数据，系统将在10秒后自动保存。您可以\[立即保存\]或\[取消\]。”  
  * \[ \] **后端处理用户选择:**  
    * 创建 POST /persist-data 接口。当前端用户点击“立即保存”或倒计时结束时，调用此接口。该接口负责将 Redis 中的所有待处理数据取出，并批量写入 PostgreSQL，成功后从 Redis 删除。  
    * 如果用户点击“取消”，前端停止本次操作，等待下一次空闲时机。后端无需做任何事。

##### ---

**功能二：股票数据 API**

**目标:** 基于 FastAPI，提供清晰、稳定、符合 RESTful 风格的数据查询接口。

**任务拆解:**

* **2.1 FastAPI 项目初始化**  
  * \[ \] 创建 FastAPI 应用实例。  
  * \[ \] 配置项目结构（例如 main.py, routers/, models/, services/）。  
  * \[ \] 整合 SQLAlchemy 和数据库连接配置。  
* **2.2 API 端点 (Endpoint) 设计与实现**  
  * \[ \] **获取日线数据:**  
    * **路径:** GET /stocks/{ticker}/daily  
    * **参数:** ticker (路径参数), start\_date (查询参数, 可选), end\_date (查询参数, 可选)。  
    * **实现:** 调用 get\_stock\_data(ticker, 'daily')，并根据日期参数筛选后返回。  
  * \[ \] **获取周线数据:**  
    * **路径:** GET /stocks/{ticker}/weekly  
    * **参数:** ticker (路径参数), start\_date (查询参数, 可选), end\_date (查询参数, 可选)。  
    * **实现:** 调用 get\_stock\_data(ticker, 'weekly')。  
  * \[ \] **获取小时线数据:**  
    * **路径:** GET /stocks/{ticker}/hourly  
    * **参数:** ticker (路径参数), start\_date (查询参数, 可选), end\_date (查询参数, 可选)。  
    * **实现:** 调用 get\_stock\_data(ticker, 'hourly')。  
* **2.3 数据序列化与响应**  
  * \[ \] 使用 Pydantic 模型定义清晰的请求体和响应体结构。  
  * \[ \] 确保所有端点在成功时返回 200 OK 和数据，在失败时（如股票代码不存在）返回合适的 HTTP 状态码（如 404 Not Found）和错误信息。

##### ---

**功能三：AI 投资决策辅助系统**

**目标:** 构建一个基于多 Agent 协同工作的 AI 分析引擎，提供全面的市场解读和投资建议。此功能参考 D:\\Coding\\A_Share_investment_Agent 项目的设计思想。

**任务拆解:**

* **3.1 Agent 角色定义**  
  * \[ \] **数据搜集 Agent (Data Collector Agent):** 负责根据分析请求，从数据库（功能一、二的产物）和网络（财经新闻、社交媒体情绪等）搜集必要信息。  
  * \[ \] **技术分析 Agent (Technical Analyst Agent):** 专注于分析股票的量价数据。输入 K 线数据，输出技术指标分析（如 MA, MACD, RSI, Bollinger Bands）、形态识别和趋势判断。例如，它可以计算 RSI=100−frac1001+RS，其中 RS 是平均上涨日收益与平均下跌日收益的比值。  
  * \[ \] **基本面分析 Agent (Fundamental Analyst Agent):** 负责分析公司的财务报表、行业地位、竞争优势等。输出公司的估值分析、盈利能力和成长性评估。  
  * \[ \] **新闻舆情 Agent (News & Sentiment Agent):** 负责抓取与该股票相关的最新新闻、公告和社交媒体讨论，并利用 LLM 分析市场情绪（正面、负面、中性）。  
  * \[ \] **决策合成 Agent (Master/Synthesizer Agent):** 作为总指挥，接收并整合以上所有 Agent 的分析报告，形成一份全面的、包含多角度观点和最终投资建议的综合报告。  
* **3.2 Agent 协同工作流实现**  
  * \[ \] 设计 Agent 之间的通信协议和数据格式。  
  * \[ \] 实现一个任务编排器 (Orchestrator)。当收到一个分析请求（例如 POST /ai/analyze/{ticker}）时，编排器会：  
    1. 启动 数据搜集 Agent。  
    2. 将搜集到的数据分发给 技术分析 Agent、基本面分析 Agent 和 新闻舆情 Agent，让它们并行工作。  
    3. 收集所有分析结果。  
    4. 将结果汇总后交给 决策合成 Agent。  
    5. 返回 决策合成 Agent 生成的最终报告。  
* **3.3 LLM 集成**  
  * \[ \] 创建一个 llm\_service.py 模块，用于封装对外部 LLM API 的调用。  
  * \[ \] 为每个需要分析能力的 Agent 设计专门的 Prompt（提示词）。例如，为 技术分析 Agent 设计的 Prompt 可能是：“你是一位资深的美股技术分析师。请分析以下 {ticker} 的日 K 线数据，并从趋势、动量和波动性三个角度给出你的看法。”  
* **3.4 API 接口**  
  * \[ \] 创建 POST /ai/analyze 接口。  
  * **请求体:** { "ticker": "AAPL", "analysis\_depth": "deep" }  
  * **响应体:** 返回一个结构化的 JSON，包含各个 Agent 的分析结果和最终的综合建议。由于分析可能耗时较长，可以考虑使用 WebSocket 或异步任务（如 Celery）返回结果。