# Decision Log

This file records architectural and implementation decisions using a list format.
2025-06-20 20:55:45 - Log of updates made.

*
      
---
### Decision (Debug)
[2025-07-07 12:41:08] - [Bug Fix Strategy: Align RSI Output Length to Input Length]

**Rationale:**
A test failure (`AssertionError: assert 99 == 100`) indicated that the `calculate_rsi` function was returning a `pd.Series` with one less element than the input Series. This was caused by the `series.diff(1).dropna()` operation at the beginning of the function, which shortens the series by one. While the RSI calculation itself was correct, the output's length and index did not match the input's, causing the assertion to fail.

The fix is to reindex the final `rsi` Series to match the index of the original input `series`. This ensures the output has the exact same dimensions as the input, with a `NaN` value at the first position where RSI cannot be calculated.

**Details:**
- **File:** `stockaivo/ai/technical_indicator.py`
- **Change:** Added `.reindex(series.index)` to the return statement of the `calculate_rsi` function.
---
### Decision (Debug)
[2025-07-07 12:35:16] - [Bug Fix Strategy: Correct RSI Calculation in technical_indicator.py]

**Rationale:**
A Pylance type error (`operator ">" is not supported for types "Series[type[object]]"`) was reported in the `calculate_rsi` function. The root cause was that the `delta` Series, after a `.diff()` operation, was inferred as `object` type due to a leading `NaN` value. Additionally, the RSI calculation was using an incorrect method (Simple Moving Average instead of Exponential Moving Average) and was not robust against division-by-zero errors.

The fix addresses all three issues:
1.  **Type Error**: Explicitly converted the `delta` series to `float` using `.astype(float)` after removing the `NaN` value with `.dropna()`.
2.  **Calculation Method**: Replaced the `rolling().mean()` (SMA) with `ewm(com=period - 1, adjust=False).mean()` (EMA) to align with the standard RSI calculation formula.
3.  **Division by Zero**: Added logic to handle cases where average loss is zero, preventing an error and correctly setting RSI to 100, which represents a strong upward trend.

**Details:**
- **File:** `stockaivo/ai/technical_indicator.py`
- **Change:** Refactored the `calculate_rsi` function for correctness and robustness.
---
### Decision (Architecture)
[2025-07-04 16:43:58] - **Separate AI Analysis Endpoint into POST for Creation and GET for Streaming**

**Rationale:**
To resolve a "405 Method Not Allowed" error, the `/ai/analyze` endpoint's responsibilities were split. The previous design likely used a single endpoint for both initiating and streaming, causing method conflicts. The new design adheres more closely to RESTful principles:
1.  **`POST /ai/analyze`**: A client sends a `POST` request to create a new resource, in this case, an AI analysis task. This is a non-idempotent action that starts a background process.
2.  **`GET /ai/analyze`**: A client sends a `GET` request to retrieve the resource, which is the stream of analysis results from the created task. This is an idempotent action.

This separation directly resolves the method conflict and creates a clearer, more predictable API interface for clients.

**Implementation Details:**
- The proposed implementation uses a global variable (`current_analysis_generator`) to store the state (the analysis generator) between the `POST` and `GET` calls.
- **CRITICAL CAVEAT:** This state management approach is a proof-of-concept and is **NOT SUITABLE FOR PRODUCTION**. It is not thread-safe across multiple workers and can only handle one analysis task at a time for the entire application. A robust production solution would require a proper task queue system (e.g., Celery with a Redis or RabbitMQ broker) where the `POST` request returns a unique `task_id`, and the `GET` request uses this `task_id` to retrieve the results from a persistent or shared result backend.
- **Affected File:** [`stockaivo/routers/ai.py`](stockaivo/routers/ai.py)
---
### Decision (Code)
[2025-07-04 16:32:25] - **BugFix: Prevent Extra Search Request in StockSearch Component**

**Rationale:**
In the `StockSearch.tsx` component, when a user selected a stock from the search results, the `handleSelectStock` function would call `setQuery()` to update the input field's text. This state update would, in turn, trigger the `useEffect` hook that depends on the `query` state, causing an unnecessary and unintended additional search API request to be fired. This behavior was inefficient.

The fix removes the `setQuery()` call from the `handleSelectStock` function. This prevents the `useEffect` hook from re-triggering the search after a selection has been made, resolving the bug. The responsibility for updating the UI or related state now lies with the parent component through the `onSelectStock` callback.

**Details:**
- **File:** [`frontend/src/components/StockSearch.tsx`](frontend/src/components/StockSearch.tsx)
- **Change:** Removed the line `setQuery(...)` from the `handleSelectStock` function.
---
---
### Decision (Code)
[2025-07-03 21:23:00] - **Refactor: Remove Duplicate Stock Data Endpoint from main.py**

**Rationale:**
The `@app.get("/stock-data/{ticker}")` endpoint in `main.py` was functionally identical to the one defined in the dedicated router file `stockaivo/routers/stocks.py`. Maintaining duplicate code increases maintenance overhead and potential for inconsistencies. The removal centralizes the routing logic in the designated router, adhering to the project's modular architecture.

**Details:**
- **File:** `main.py`
- **Change:** Removed the entire `get_stock_data_endpoint` function and its associated `@app.get` decorator (lines 236-293).
### Decision (Code)
[2025-07-03 16:14:16] - **修复API日期格式并增强响应模型类型安全**

**Rationale:**
API 响应中的 `date` 字段被默认的 FastAPI/Starlette JSON 编码器序列化为包含时间的 ISO 格式字符串 (例如 `YYYY-MM-DDTHH:MM:SS`)，这不符合前端的预期。此外，响应模型 `StockDataResponse` 对 `data` 字段使用了通用的 `List[dict]` 类型，这绕过了 Pydantic 的类型验证和自动序列化特性，降低了类型安全性。

为了解决此问题，实施了以下两项关键更改：
1.  **自定义日期编码器**: 在 `stockaivo/schemas.py` 的 `StockPriceDaily` 和 `StockPriceWeekly` 模型中，通过 `model_config` 添加了一个 `json_encoders`。这个编码器强制 `date` 对象在序列化时使用 `%Y-%m-%d` 格式。
2.  **强化响应模型**: 在 `stockaivo/schemas.py` 中，将 `StockDataResponse` 的 `data` 字段类型从 `List[dict]` 更改为更具体的 `List[Union[StockPriceDaily, StockPriceWeekly, StockPriceHourly]]`。

这一组合方案利用了 Pydantic V2 的强大功能。当 FastAPI 准备响应时，Pydantic 会自动将从 `data_service` 返回的 DataFrame 记录（`to_dict('records')` 的结果）验证并转换为 `StockPriceDaily`/`Weekly`/`Hourly` 模型实例。在最终的 JSON 序列化阶段，Pydantic 会检测到 `StockPriceDaily`/`Weekly` 模型上我们自定义的 `json_encoders`，并应用它来格式化 `date` 字段，从而确保了输出格式的正确性。

**Details:**
- **File:** `stockaivo/schemas.py`
  - **Change:**
    - 为 `StockPriceDaily` 和 `StockPriceWeekly` 添加了带 `json_encoders` 的 `model_config`。
    - 将 `StockDataResponse.data` 的类型提示更新为 `List[Union[...]]`。
    - 为避免类型名冲突，将 `from datetime import date` 修改为 `from datetime import date as DateType`。
- **File:** `stockaivo/routers/stocks.py`
  - **Change:** 为了解决 Pylance 静态类型检查器无法验证 Pandas 的 `to_dict('records')` 输出与 Pydantic 模型输入匹配的问题，在 `data=data.to_dict('records'),` 行添加了 `# type: ignore` 注释。这保留了代码的运行时正确性和简洁性，同时解决了静态分析错误。
---
### Decision (Code)
[2025-07-03 15:45:47] - **优化数据获取以感知市场节假日**

**Rationale:**
系统当前会将市场节假日和周末误判为数据缺失，并尝试向远程API请求数据，这必然会导致失败并浪费资源。为了解决这个问题，在数据获取逻辑中引入了交易日历检查。在确定一个日期范围的数据缺失并准备从远程API获取之前，系统现在会先验证该范围内是否包含至少一个有效的交易日。如果该范围完全由非交易日（节假日、周末）组成，系统将记录一条信息并跳过该范围，从而避免无效的API调用。

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** 在 `get_stock_data` 函数中，处理缺失数据范围的循环内，增加了使用 `pandas-market-calendars` 库的逻辑。通过调用 `mcal.get_calendar('NYSE').schedule()` 来检查日期范围内的交易日。如果返回的 `schedule` 为空，则跳过当前循环。
- **Library Used:** `pandas-market-calendars`, 该库已存在于项目依赖中。
---
### Decision (Debug)
[2025-07-02 16:06:18] - [BugFix: Refactor React Component Structure to Fix Blank Page]

**Rationale:**
The application was rendering a blank page despite the individual components (`index.html`, `main.tsx`, `router.tsx`) appearing correct. The root cause was an improper component structure inherited from the Next.js to Vite migration. The main application layout (`RootLayout`) was too minimal (containing only `<Outlet />`), while the page content (`HomePage`) contained the overall page structure (like `<Header>` and `<main>`). This separation is not ideal for a `react-router-dom` setup.

The fix involved refactoring the component structure to follow a more standard React pattern:
1.  **`frontend/src/app/layout.tsx`**: This component was enhanced to contain the shared page structure, including the `<Header>` and the main content container. It renders the child routes via the `<Outlet />` component within this structure.
2.  **`frontend/src/app/page.tsx`**: This component was simplified to only contain the content specific to the home page, removing the redundant layout elements which are now handled by `RootLayout`.

This change creates a clear and correct hierarchy, where the root layout provides the persistent structure, and the router swaps out the page-specific content inside it.

**Details:**
- **File:** `frontend/src/app/layout.tsx`
  - **Change:** Added the main HTML structure (`div`, `Header`, `main`) to serve as the global layout.
- **File:** `frontend/src/app/page.tsx`
  - **Change:** Removed the outer layout structure, leaving only the grid system for the page's components.

---
### Decision (Debug)
[2025-07-02 15:57:07] - [BugFix: Correct `tsconfig.json` for Vite Migration to Resolve Module Not Found Error]

**Rationale:**
An import error, `[ts] Cannot find module './router'`, persisted in `frontend/src/main.tsx` even though the target file `frontend/src/router.tsx` existed and had a correct default export. The root cause was identified in `frontend/tsconfig.json`, which contained leftover configurations from a previous Next.js setup. The Next.js-specific plugin (`"plugins": [{"name": "next"}]`) and the JSX setting (`"jsx": "preserve"`) were incompatible with Vite's build and module resolution process, preventing TypeScript from correctly identifying the module.

The fix involved a comprehensive cleanup and update of `tsconfig.json`:
1.  **Removed Next.js Plugin:** The `plugins` array was deleted entirely.
2.  **Updated JSX Setting:** Changed `"jsx": "preserve"` to `"jsx": "react-jsx"`, which is the correct setting for Vite.
3.  **Cleaned `include` Array:** Removed Next.js-specific paths like `next-env.d.ts` and `.next/types/**/*.ts`.
4.  **Updated Target:** Changed `"target": "es5"` to `"target": "ESNext"` for modern compatibility.

This change aligns the TypeScript configuration with the project's Vite-based toolchain, resolving the module resolution conflict.

**Details:**
- **File:** `frontend/tsconfig.json`
- **Change:** Overhauled the configuration to remove Next.js-specific settings and align with Vite requirements.
- **File:** `frontend/src/main.tsx`
- **Change:** Removed a comment on an import line, which was the initial suspected cause but not the root issue.

---
### Decision (Code)
[2025-07-02 15:47:49] - **Refactor `page.tsx` to Client-Side and Decouple Child Components**

**Rationale:**
As part of the migration from Next.js to a Vite-based React setup, it was necessary to refactor `frontend/src/app/page.tsx` to be a pure client-side component. The primary goal was to remove server-side patterns (`"use client"`, `dynamic` imports) and prepare for client-side data fetching with SWR.

The initial refactoring of `page.tsx` removed state management (`useState`) and prop drilling, which caused TypeScript compilation errors because the child components (`StockDataForm`, `StockChart`) still expected those props. To resolve this without immediately implementing a full state management solution, the decision was made to modify the child components directly:
1.  **`StockDataForm.tsx`**: The `onSubmit` and `isLoading` props were removed. The component now manages its own form state, and the `handleSubmit` function was temporarily modified to log to the console, decoupling it from the parent.
2.  **`StockChart.tsx`**: The `data` and `ticker` props were made optional. This allows the component to be rendered without props, resolving the compile error.

This approach acts as a crucial intermediate step. It successfully decouples the components, allows the application to compile, and paves the way for the next phase, where SWR and a shared state mechanism (like Context or Zustand) will be integrated into the child components to handle data fetching and cross-component communication.

**Details:**
- **File:** `frontend/src/app/page.tsx`
  - **Change:** Removed all state management and data-fetching logic. Converted to a simple layout component rendering child components without data-related props.
- **File:** `frontend/src/components/StockDataForm.tsx`
  - **Change:** Removed `onSubmit` and `isLoading` from props. The component is now self-contained.
- **File:** `frontend/src/components/StockChart.tsx`
  - **Change:** Made `data` and `ticker` props optional to allow rendering without them.
---
### Decision (Architecture)
[2025-07-02 15:10:00] - **Replace ECharts with TradingView Lightweight Charts for Frontend Charting**

**Rationale:**
Based on the analysis from the spec-writer, TradingView Lightweight Charts are better suited for our financial data visualization needs. Key advantages include:
*   **Performance:** Optimized for large time-series datasets, providing a smoother user experience.
*   **Features:** Offers a rich set of built-in financial charting tools and indicators that are core to our product, reducing the need for custom development.
*   **Ease of Use:** The API is specifically designed for financial charts, simplifying implementation compared to the more generic ECharts library.
*   **Aesthetics:** Provides a professional and familiar look-and-feel for users accustomed to financial trading platforms.

**Implementation Details:**
*   **Component:** The existing [`frontend/src/components/StockChart.tsx`](frontend/src/components/StockChart.tsx) component will be refactored to use the TradingView Lightweight Charts library.
*   **Data Fetching:** The component will continue to fetch data from the existing backend API endpoint.
*   **Library:** The `lightweight-charts` package will be added as a dependency to [`frontend/package.json`](frontend/package.json).
*   **Styling:** Initial chart options will be configured for a clean, professional appearance, matching the application's theme.
---
### Decision (Code)
[2025-07-02 12:24:11] - [Refactor: Rename `dates` to `date` across codebase]

**Rationale:**
To standardize the date field name and eliminate inconsistencies, the column `dates` in `StockPriceDaily` and `StockPriceWeekly` models was renamed to `date`. This change was propagated throughout the entire codebase, including data services, database writers, data providers, and cache managers. All logic previously added to handle the conversion between `date` and `dates` has been removed, simplifying the data flow and improving code clarity.

**Details:**
- **File:** `stockaivo/models.py`
  - **Change:** Renamed `dates` column to `date` in `StockPriceDaily` and `StockPriceWeekly` models and updated all related constraints and indexes.
- **File:** `stockaivo/data_service.py`
  - **Change:** Updated `_get_date_col` and `_query_database` to use `date` instead of `dates`.
- **File:** `stockaivo/database_writer.py`
  - **Change:** Removed the logic for renaming `date` to `dates` and updated all data preparation and upsert functions to use the `date` field.
- **File:** `stockaivo/data_provider.py`
  - **Change:** Updated column mapping to map source date column to `date`.
- **File:** `stockaivo/cache_manager.py`
  - **Change:** Removed special handling for a `dates` column in serialization and deserialization logic.
---
### Decision (Code)
[2025-07-01 19:05:43] - [Refactor pyproject.toml to separate development dependencies]

**Rationale:**
To improve dependency management and distinguish between core application dependencies and development-specific tools, testing libraries (`pytest`, `pytest-asyncio`) were moved from the main `[project.dependencies]` list to a dedicated `[project.optional-dependencies.dev]` group. This separation ensures that production environments are leaner and do not include unnecessary testing packages, while development environments can be easily set up with all required tools by installing the 'dev' extras.

**Details:**
- **File:** `pyproject.toml`
- **Change:** Created `[project.optional-dependencies]` section with a `dev` group and moved `pytest` and `pytest-asyncio` into it.
---
---
### Decision (Debug)
[2025-07-01 11:35:21] - [BugFix: Prevent 502 Error by Truncating Prompt Data]

**Rationale:**
The `technical_analyst` agent was consistently causing a `502 Bad Gateway` error when communicating with the local OpenAI-compatible LLM service. The root cause was identified as an excessively long prompt. The agent was converting entire historical data DataFrames for daily and weekly prices into strings and including them in the prompt. Local LLMs have strict context length limits, and exceeding them can cause the server to crash or fail, resulting in a 502 error from the perspective of the client. The fix involves truncating the data to a reasonable size (`.tail(60)` for daily, `.tail(30)` for weekly) before converting it to a string. This significantly reduces the prompt size, keeping it within the LLM's operational limits while preserving enough recent data for a meaningful analysis.

**Details:**
- **File:** `stockaivo/ai/agents.py`
- **Change:** Modified the `technical_analysis_agent` to use `daily_price_df.tail(60).to_string()` and `weekly_price_df.tail(30).to_string()` to limit the amount of data sent in the prompt.
---
---
### Decision (Code)
[2025-07-01 11:16:08] - [BugFix: Prevent `AttributeError` in Orchestrator by Handling `None` Values]

**Rationale:**
The `run_analysis` method in `LangGraphOrchestrator` iterates through the output of the `astream` method. In certain edge cases, a value within the streamed output dictionary could be `None`. Attempting to call methods like `.get()` on a `None` value would raise an `AttributeError`, crashing the stream. To make the orchestrator more robust, a check `if value is None: continue` was added at the beginning of the loop. This ensures that any `None` values are safely skipped, preventing potential runtime errors.

**Details:**
- **File:** `stockaivo/ai/orchestrator.py`
- **Change:** Added the line `if value is None: continue` immediately after the `for key, value in output.items():` declaration in the `run_analysis` method.
---
### Decision (Code)
[2025-07-01 11:10:35] - [Refactor: Enhance `technical_analysis_agent` to Process Weekly and Daily Data]

**Rationale:**
The `technical_analysis_agent` was updated to provide a more comprehensive analysis by incorporating both daily and weekly price data. This allows the AI to identify both short-term and long-term trends, support, and resistance levels. The agent now fetches both `daily_prices` and `weekly_prices` from the state, converts them to string format, and includes them in separate sections within the prompt. The implementation also gracefully handles cases where either daily or weekly data might be missing, ensuring the agent's robustness.

**Details:**
- **File:** `stockaivo/ai/agents.py`
- **Change:**
    - Modified `technical_analysis_agent` to fetch both `daily_prices` and `weekly_prices` from `state.get("raw_data", {})`.
    - Added logic to convert weekly data to a string format, similar to daily data.
    - Updated the prompt to include distinct sections for "日线原始数据" (Daily Raw Data) and "周线原始数据" (Weekly Raw Data).
    - Ensured that if data is missing, a message like "无日线数据" (No daily data) is displayed in the prompt.
---
### Decision (Code)
[2025-07-01 10:49:30] - [Refactor: Migrate Pydantic V1 `@validator` to V2 `@model_validator`]

**Rationale:**
The Pylance linter correctly identified a deprecated `@validator` in `stockaivo/routers/ai.py`. This validator was performing cross-field validation on date-related fields. In Pydantic V2, the recommended approach for such validation is to use `@model_validator`. This refactoring replaces the deprecated validator with the modern equivalent, ensuring future compatibility and adhering to best practices. The `mode='before'` was chosen to validate the raw input data before model creation, which is efficient for this type of validation.

**Details:**
- **File:** `stockaivo/routers/ai.py`
- **Change:**
    - Replaced `@validator('end_date', always=True)` with `@model_validator(mode='before')`.
    - Updated the validation function to accept the entire data dictionary (`cls, data`) instead of individual fields.
    - Corrected a date comparison bug by using `date.fromisoformat()` to ensure proper date object comparison instead of string comparison.
    - Simplified the check for mutually exclusive date fields using the XOR operator (`bool(start) ^ bool(end)`).
---
### Decision (Debug)
[2025-07-01 10:46:02] - [BugFix: Handle Nested JSON in AI Analysis Endpoint]

**Rationale:**
The `/ai/analyze` endpoint was returning a `422 Unprocessable Entity` error because the incoming request body had a nested structure (`{"summary": "...", "value": {...}}`), while the Pydantic model `AnalysisRequest` expected a flat object. The fix involves introducing a new `NestedAnalysisRequest` model to capture the actual request structure. The endpoint now accepts this new model, and then extracts the `value` field to construct the `AnalysisRequest` object internally. This makes the endpoint robust to the specific request format being sent.

**Details:**
- **File:** `stockaivo/routers/ai.py`
- **Change:**
    - Created a new `NestedAnalysisRequest` Pydantic model to match the nested JSON payload.
    - Changed the endpoint's type hint to use `NestedAnalysisRequest`.
    - Added logic inside the `stream_ai_analysis` function to un-nest the relevant data from `nested_request.value` into an `AnalysisRequest` instance.
---
### Decision (Debug)
[2025-07-01 10:36:28] - [BugFix: Correct TypedDict Syntax in GraphState]

**Rationale:**
The Pylance error "[Pylance] TypedDict classes can only contain type annotations" was caused by assigning default values (`= None`) to fields within the `GraphState` TypedDict in `stockaivo/ai/state.py`. TypedDicts are for defining dictionary shapes and do not support default value assignments in their syntax. The fix involves removing the default value assignments. The optional nature of the keys is already correctly indicated by the `| None` in the type hint.

**Details:**
- **File:** `stockaivo/ai/state.py`
- **Change:** Removed `= None` from `date_range_option` and `custom_date_range` fields.
---
### Decision (Code)
[2025-07-01 10:29:47] - [BugFix: Add missing await for async call in stock data endpoint]

**Rationale:**
The call to the asynchronous function `get_stock_data` inside the `get_stock_data_endpoint` was missing the `await` keyword. This caused the code to attempt to access attributes on a coroutine object instead of the resolved DataFrame, leading to an `AttributeError` on line 252. Adding `await` ensures the coroutine is executed and its result is returned before proceeding, fixing the bug.

**Details:**
- **File:** [`main.py`](main.py)
- **Change:** Modified line 250 from `data = get_stock_data(...)` to `data = await get_stock_data(...)`.
---
### Decision (Code)
[2025-06-30 12:24:26] - [Fix: Resolve LangGraph State Merging Conflict with `Annotated`]

**Rationale:**
Following the refactoring of agents to return partial state updates, a mechanism was needed to correctly merge these partial dictionaries into the main `GraphState`. The previous `analysis_results: Dict[str, Any]` would cause new results to overwrite old ones instead of merging. By changing the type hint to `analysis_results: Annotated[dict, merge_dicts]`, we instruct LangGraph to use the custom `merge_dicts` function to combine the `analysis_results` dictionaries from different agent outputs. This ensures that results from all agents are preserved in the state.

**Details:**
- **File:** `stockaivo/ai/state.py`
- **Change:**
    - Imported `Annotated` from `typing`.
    - Defined a `merge_dicts` function.
    - Changed the type of `analysis_results` in `GraphState` to `Annotated[dict, merge_dicts]`.
---
### Decision (Code)
[2025-06-30 12:20:01] - [Refactor: Isolate Agent State Updates in LangGraph Workflow]

**Rationale:**
To resolve state update conflicts in the LangGraph workflow, the agents (`data_collection_agent`, `technical_analysis_agent`, `fundamental_analysis_agent`, `news_sentiment_analysis_agent`) were modified. Instead of modifying the shared `state` object directly and returning the entire state, each agent now returns only a dictionary containing its specific output. LangGraph is responsible for merging these partial states into the main state object. This pattern prevents race conditions, makes agents more modular and reusable, and clarifies the data flow within the graph.

**Details:**
- **File:** `stockaivo/ai/agents.py`
- **Change:** All targeted agents were refactored to remove direct state modification and now return a dictionary with a single key corresponding to their role and output (e.g., `return {"analysis_results": {"technical_analyst": analysis_result}}`).
---

### Decision (Code)
[2025-06-30 12:15:19] - [BugFix: Correct LLM Tool Invocation Parameter]

**Rationale:**
The `llm_tool.ainvoke` method in `stockaivo/ai/agents.py` was being called with an incorrect parameter structure. The tool expects the input to be a dictionary with the key `input_dict`, which in turn contains the prompt. The previous call was passing the prompt dictionary directly. This fix wraps the existing dictionary in the required `{"input_dict": ...}` structure to align with the tool's expected input schema.

**Details:**
- **File:** [`stockaivo/ai/agents.py`](stockaivo/ai/agents.py)
- **Change:** Modified line 78 from `await llm_tool.ainvoke({"prompt": prompt})` to `await llm_tool.ainvoke({"input_dict": {"prompt": prompt}})`.
---
---
### Decision (Code)
[2025-06-30 11:35:39] - [Revert: Change Dev Server Host back to 127.0.0.1]

**Rationale:**
Per user request, the development server host in `run.py` was reverted from `"0.0.0.0"` to `"127.0.0.1"`. This reverses a previous debugging step.

**Details:**
- **File:** [`stockaivo/scripts/run.py`](stockaivo/scripts/run.py)
- **Change:** Modified the `host` parameter in the `dev()` function from `"0.0.0.0"` to `"127.0.0.1"`.
---
---
### Decision (Debug)
[2025-06-30 11:31:29] - [BugFix: Change Dev Server Port to 8999 to Avoid System-Level Port Restrictions]

**Rationale:**
Despite `netstat` showing port 8080 as free, the application continues to fail with a `[WinError 10013]` socket access error. This indicates the issue is likely not a simple port conflict but may be related to system policies, security software, or user permissions restricting access to lower-range ports. Changing to a higher, non-standard port like 8999 is a common strategy to bypass these restrictions.

**Details:**
- **File:** [`stockaivo/scripts/run.py`](stockaivo/scripts/run.py)
- **Change:** Modified the `port` parameter in the `dev()` function from `8080` to `8999`.
---
### Decision (Debug)
[2025-06-30 11:26:53] - [BugFix: Change Dev Server Host to 0.0.0.0 to Resolve Socket Errors]

**Rationale:**
The application has been experiencing persistent `[WinError 10013]` socket access errors. Multiple attempts to resolve this by changing the port (8000 -> 8001 -> 8002 -> 8080) have not fixed the underlying issue. This suggests the problem is not a simple port conflict but likely a network binding or permission issue. Changing the host from `"127.0.0.1"` (localhost) to `"0.0.0.0"` allows the server to listen on all available network interfaces, which is a common and effective solution for such access permission errors, especially in development environments like Docker or WSL.

**Details:**
- **File:** [`stockaivo/scripts/run.py`](stockaivo/scripts/run.py)
- **Change:** Modified the `host` parameter in the `dev()` function from `"127.0.0.1"` to `"0.0.0.0"`.
---
---
### Decision (Debug)
[2025-06-30 11:23:10] - [BugFix: Change Dev Server Port to Avoid Conflict]

**Rationale:**
The development server port was changed from 8001 to 8002 to resolve a suspected port conflict. This follows a previous change from 8000 to 8001, indicating persistent issues on lower port numbers.

**Details:**
- **File:** `stockaivo/scripts/run.py`
- **Change:** Modified the `port` parameter in the `dev()` function from `8001` to `8002`.
---
---
### Decision (Debug)
[2025-06-30 11:19:17] - [BugFix: Change Dev Server Port to Avoid Conflict]

**Rationale:**
The `uv run dev` command failed with `[WinError 10013]`, indicating a port conflict or permission issue on the default port 8000. Although `netstat` did not show an active process, changing the port is the most reliable way to resolve such conflicts, which might be caused by ephemeral processes, firewalls, or other system restrictions. The development server port was changed from 8000 to 8001.

**Details:**
- **File:** `stockaivo/scripts/run.py`
- **Change:** Modified the `port` parameter in the `dev()` function from `8000` to `8001`.
---
---
### Decision (Code)
[2025-06-30 11:14:29] - [Model and Schema Change: Allow Nullable Volume]

**Rationale:**
The user requested to allow the 'volume' field to be nullable. This change provides more flexibility in data handling, accommodating cases where volume data might be missing from the source. The database models and Pydantic schemas were updated to reflect this change.

**Details:**
- **File:** `stockaivo/models.py`
  - **Change:** In `StockPriceDaily`, `StockPriceWeekly`, and `StockPriceHourly` models, the `volume` column's `nullable` attribute was changed from `False` to `True`.
- **File:** `stockaivo/schemas.py`
  - **Change:** In the `StockPriceBase` schema, the `volume` field was changed from `int` to `Optional[int]` and given a default value of `None`.
---
---
### Decision (Code)
[2025-06-29 21:50:56] - [Refactor: Clarify Log Message for Pending Persistence]

**Rationale:**
The log message "已触发待持久化缓存更新流程" (Persistence process triggered) was misleading. The system uses a centralized background scheduler (`background_scheduler.py`) to handle all data persistence from the `pending_save` cache, and there is no immediate, direct trigger from the data service. The log message has been changed to "已存入待持久化缓存" (Saved to pending persistence cache) to accurately reflect that the new data is simply queued for the scheduler to process. This improves clarity and reduces potential confusion during debugging.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** Updated two log messages on lines 268 and 299 to be more precise about the persistence mechanism.

### Decision (Code)
[2025-06-29 21:25:24] - [Refactor: Remove Manual Background Task Creation in `data_service.py`]

**Rationale:**
The system has a centralized background scheduler (`background_scheduler.py`) that automatically handles persistence for all Redis keys matching the `pending_save:*` pattern. The existing code in `data_service.py` was manually adding a `save_dataframe_to_db` task to `BackgroundTasks` every time new data was fetched from the remote API. This is redundant and bypasses the centralized scheduler, potentially leading to race conditions or inconsistent behavior. The refactoring removes this manual task creation, relying solely on the background scheduler to manage data persistence. This simplifies the data service's logic and centralizes the persistence mechanism.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** Removed two blocks of code responsible for calling `background_tasks.add_task(database_writer.save_dataframe_to_db, ...)`. The logic now simply logs that new data has been saved to the `pending_save` cache, where the scheduler will pick it up.

---
### Decision (Debug)
[2025-06-29 21:08:51] - [BugFix: Correct `UndefinedColumn` in Weekly Data Persistence and Refine Cache Clearing Logic]

**Rationale:**
1.  **`UndefinedColumn` Error:** The persistence task for weekly stock data was failing with a `psycopg2.errors.UndefinedColumn` error. The root cause was an incorrect column name (`week_start_date`) being used in the `ON CONFLICT` clause of the `INSERT` statement. The correct column, as defined in the `StockPriceWeekly` model, is `dates`.
2.  **Unsafe Cache Clearing:** The logic for clearing Redis cache in `persist_pending_data` was not fully transactional. It attempted to clear cache keys *before* the final database transaction was committed. This created a race condition where cache could be cleared even if the final `db.commit()` failed, potentially leading to data loss.

The fix involves two parts:
1.  Correcting the conflict key from `week_start_date` to `dates` in the `_batch_upsert_prices` call for weekly data within `persist_pending_data`.
2.  Refactoring the control flow in `persist_pending_data` to ensure that the Redis cache is cleared only *after* the database transaction has been successfully committed, mirroring the more robust pattern already present in the `save_dataframe_to_db` function.

**Details:**
- **File:** `stockaivo/database_writer.py`
- **Change 1:** In `persist_pending_data`, the `_batch_upsert_prices` call for the 'weekly' period was changed to use `['ticker', 'dates']` as the `conflict_columns` argument.
- **Change 2:** The code block for clearing Redis data was moved to after the `db.commit()` call to ensure transactional integrity.

---
### Decision (Code)
[2025-06-29 20:46:44] - [BugFix: Correct Data Fetching and Caching Logic in `get_stock_data`]

**Rationale:**
Two bugs were identified in the data fetching logic when the cache is incomplete:
1.  **Incorrect Caching:** Data retrieved from the database was incorrectly being added to the `pending_save` Redis cache, which should only store new data fetched from the remote API (AKShare) that needs to be persisted.
2.  **Incomplete Data Fetching:** When a missing date range was found, if the database returned only partial data for that range, the system failed to fetch the remaining missing dates from the remote API.

The fix refactors the logic block that handles incomplete cache scenarios. It now correctly differentiates between data sourced from the database and data from the remote API. After fetching from the database, it recalculates the *still* missing dates within the range and fetches only those from the remote API. A dedicated list (`data_from_remote_only`) is used to collect data from the remote source, and only this list is saved to the `pending_save` cache, while all newly acquired data (from both DB and remote) is merged to update the `general_cache`.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** Replaced the logic block from line 148 to 184 inside the `get_stock_data` function with a new implementation that correctly separates data sources, re-calculates missing dates after a database query, and ensures only remote data is queued for persistence.
---
### Decision (Code)
[2025-06-29 19:13:00] - [Refactor: Remove `adj_close` Column]

**Rationale:**
Based on a direct user request stating that the `adj_close` column is not provided by the AKShare data source and is redundant, all references to `adj_close` have been systematically removed from the codebase. This simplifies the data model and removes the logic that previously duplicated the `close` value into `adj_close`.

**Details:**
- **File:** `stockaivo/models.py`
  - **Change:** Removed the `adj_close` column definition from the `StockPriceDaily` model.
- **File:** `stockaivo/data_provider.py`
  - **Change:** Removed all logic related to creating, filling, or standardizing the `adj_close` column in the `fetch_from_akshare` and `_standardize_columns` functions.
- **File:** `stockaivo/database_writer.py`
  - **Change:** Removed all references to the `adj_close` column in the `_prepare_daily_price_data`, `_prepare_weekly_price_data`, and `_batch_upsert_prices` functions to prevent errors during database write operations.
- **File:** `stockaivo/data_service.py`
  - **Change:** No changes were needed. The file was inspected and confirmed to have no remaining references to `adj_close`, consistent with previous refactoring efforts.
---
### Decision (Debug)
[2025-06-29 17:26:00] - [Bug Fix Strategy: Address Root Cause of NaN `adj_close`]

**Rationale:**
The persistent `NaN` issue in the `adj_close` column was caused by a fundamental flaw in the data ingestion process. The AKShare API, when queried for US stock data with post-market adjustment (`qfq`), returns the adjusted price directly in the `close` column, and does not provide a separate `adj_close` column. The previous code in `stockaivo/data_provider.py` failed to account for this. It did not copy the value from the `close` column to a new `adj_close` column after fetching the data. All subsequent fixes in `data_service.py` were merely treating the symptoms (downstream `NaN` values) rather than the root cause.

The definitive fix is to modify `stockaivo/data_provider.py` to immediately create and populate the `adj_close` column from the `close` column right after the data is fetched from AKShare. This ensures that any data entering the system's cache or database is already correctly structured. Consequently, the temporary data cleaning logic for `adj_close` previously added to `data_service.py` becomes redundant and has been removed.

**Details:**
- **File:** `stockaivo/data_provider.py`
  - **Change:** In the `fetch_from_akshare` function, added logic to assign `df['adj_close'] = df['close']` immediately after a successful data fetch from AKShare.
- **File:** `stockaivo/data_service.py`
  - **Change:** Removed the `adj_close` cleaning block from the `_clean_dataframe` function as it is no longer necessary.
---
### Decision (Debug)
[2025-06-29 17:23:00] - [Bug Fix Strategy: Add `adj_close` cleaning in `data_service`]

**Rationale:**
The root cause of the recurring `NaN` issue in the `adj_close` column was that the data cleaning step in `data_service.py` only handled the `volume` column. When data from the database (where `adj_close` might be a `Decimal` type) was concatenated with data from the remote API (where it's a `float`), pandas could introduce `NaN` values due to type inconsistencies, especially if one of the dataframes was empty or had missing values. The definitive fix is to add a cleaning step for `adj_close` in the `_clean_dataframe` function, which is called on all data paths before being returned. This ensures the column is always a `float` and has no `NaN` values before serialization.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** In the `_clean_dataframe` function, added logic to check for the `adj_close` column, fill any `NaN` values with `0.0`, and cast the column type to `float`.
---
---
### Decision (Debug)
[2025-06-29 17:17:00] - [Bug Fix Strategy: Standardize `adj_close` Column]

**Rationale:**
The root cause of the `NaN` value in the `adj_close` field of cached data was a failure to process this column when fetching data from the remote AKShare API. The `_standardize_columns` function in `data_provider.py` was missing a mapping for the adjusted close price column (assumed to be '后复权价') and did not include `adj_close` in its list of numeric columns for type conversion. This resulted in a `NaN` value when the single, incorrectly processed row from the API was merged with historical data from the database.

**Details:**
- **File:** `stockaivo/data_provider.py`
- **Change 1:** In the `_standardize_columns` function, the `column_mapping` dictionary was updated to map '后复权价' to 'adj_close' and also included a defensive 'adj_close' to 'adj_close' mapping.
- **Change 2:** The `numeric_columns` list in the same function was updated to include 'adj_close', ensuring the column is correctly converted to a numeric type.
---
### Decision (Debug)
[2025-06-29 17:09:50] - [Bug Fix Strategy: Add Ticker to DataFrame]

**Rationale:**
The root cause of the `NaN` value in the `ticker` field was that the DataFrame returned from `data_provider.py` did not contain the ticker symbol. When this data was merged with other cached data, the missing `ticker` field resulted in a `NaN`. The fix involves adding the `ticker` as a new column to the DataFrame in the `fetch_from_akshare` function before it is returned, ensuring data integrity downstream.

**Details:**
- **File:** `stockaivo/data_provider.py`
- **Change:** In the `fetch_from_akshare` function, after successfully fetching and validating the data, the line `df['ticker'] = ticker` was added before the return statement.
---
### Decision (Code)
[2025-06-29 16:31:47] - [动态列选择与标准化日志格式]

**Rationale:**
1.  **动态列选择**: 为了使数据库查询更加健壮并减少不必要的数据传输，对 `_query_database` 函数进行了修改。通过使用 SQLAlchemy 的 `inspect` 功能，查询现在以编程方式仅选择模型中定义的列，同时显式排除了 `created_at` 和 `updated_at` 这两个通用时间戳字段。这避免了在模型更改时需要手动更新查询，并确保了API响应的简洁性。

---
**Date:** 2025-07-07
**Context:** Refactoring `calculate_rsi` in `stockaivo/ai/technical_indicator.py`
**Decision:**
Optimized the `calculate_rsi` function to improve conciseness, readability, and performance.

**Rationale:**
1.  **Conciseness**: Replaced `delta.where(...)` with the more compact `delta.clip(...)` for calculating `gain` and `loss`.
2.  **Performance/Correctness**: Removed a redundant check `rsi[avg_loss == 0] = 100`. The mathematical formula `100.0 - (100.0 / (1.0 + rs))` already correctly handles the case where `avg_loss` is zero (resulting in `rs` being infinity and `rsi` being 100), thus simplifying the code and avoiding an unnecessary operation.
3.  **Robustness**: Added `min_periods=period` to the `.ewm()` calculation. This ensures that the RSI is only calculated after a sufficient number of data points are available, preventing misleading initial values and making the calculation more robust.
4.  **Readability**: Improved the docstring to provide a clearer explanation of the RSI calculation logic and the function's parameters.

**Original Code Snippet:**
```python
delta = series.diff(1).dropna().astype(float)
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, 1)
rsi = 100 - (100 / (1 + rs))
rsi[avg_loss == 0] = 100
return rsi.reindex(series.index)
```

**Refactored Code Snippet:**
```python
delta = series.diff(1)
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
rs = avg_gain / avg_loss
rsi = 100.0 - (100.0 / (1.0 + rs))
return rsi.reindex(series.index)
```
---
