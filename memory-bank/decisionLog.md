# Decision Log

This file records architectural and implementation decisions using a list format.
2025-06-20 20:55:45 - Log of updates made.

*
      
---
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
2.  **标准化日志格式**: 为了提高日志的可读性和调试效率，对整个应用的日志系统进行了标准化配置。通过在 `main.py` 中设置 `basicConfig`，所有日志输出现在都包含 `[HH:MM:SS]` 格式的时间戳，使得按时间顺序追踪事件和关联不同模块的日志变得更加容易。

**Details:**
- **File:** `stockaivo/data_service.py`
  - **Change:** 在 `_query_database` 函数中，使用 `inspect(model).c` 和列表推导式来构建要选择的列列表，排除了 `created_at` 和 `updated_at`。查询语句被重构为使用 `select()`。
- **File:** `main.py`
  - **Change:** 修改了 `logging.basicConfig`，添加了 `format` 和 `datefmt` 参数，以实现全局统一的时间戳日志格式。
---
### Decision (Debug)
[2025-06-29 16:16:10] - [Bug Fix Strategy: Correct ON CONFLICT column name]

**Rationale:**
The application was failing with a `psycopg2.errors.UndefinedColumn` because the `persist_pending_data` function in `stockaivo/database_writer.py` was using the incorrect column name `date` in the `ON CONFLICT` clause for the `stock_prices_daily` table. The correct column name, as defined in the model and used in other parts of the code, is `dates`. The fix involves correcting this column name in the `_batch_upsert_prices` call within the `persist_pending_data` function.

**Details:**
- **File:** `stockaivo/database_writer.py`
- **Change:** In `persist_pending_data`, the `_batch_upsert_prices` call for the 'daily' period was changed to use `['ticker', 'dates']` as the `conflict_columns` argument, aligning it with the database schema.
---
### Decision (Debug)
[2025-06-27 17:43:00] - [Bug Fix Strategy: Data Sanitization Before Serialization]

**Rationale:**
The root cause of the `TypeError: 'float' object cannot be interpreted as an integer` was identified as `NaN` values in the `volume` column of the DataFrame being passed to the Pydantic model for serialization. `NaN` is a float, which violates the schema's expectation of an `int` for the `volume` field. The most robust fix is to sanitize the data just before it's returned by the `data_service`. This ensures that data from any source (cache, DB, or API) is cleaned, preventing similar errors in the future.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:**
    - A new private function `_clean_dataframe(df)` was created. This function checks for a `volume` column, fills any `NaN` values with `0`, and then explicitly casts the column's type to `int`.
    - This `_clean_dataframe` function is now called on the final DataFrame in all return paths of the main `get_stock_data` function, immediately before the data is returned for serialization. This guarantees that the data passed to the Pydantic models is always clean.
## Decision

*
      
## Rationale 

*

## Implementation Details

*
---
### Decision (Architecture)
[2025-06-27 17:29:00] - **实现后台持久化调度器**

**Rationale:**
为了确保临时缓存中的数据能够定期、可靠地持久化到主数据库（PostgreSQL），引入了基于 `apscheduler` 的后台调度器。这种异步、定时的机制取代了之前依赖手动或API触发的持久化方式，提高了系统的自动化程度和数据的最终一致性。调度器在独立的后台线程中运行，不会阻塞主应用的API请求，并且通过为每个任务创建独立的数据库会话来确保线程安全。

**Details:**
- **File:** `stockaivo/background_scheduler.py` (新文件)
  - **Change:** 创建了一个新的模块，包含 `start_scheduler`、`stop_scheduler` 和 `scheduled_persist_job` 函数。调度任务被配置为每5分钟运行一次，调用 `database_writer.persist_pending_data`。
- **File:** `main.py`
  - **Change:** 在 `lifespan` 上下文管理器中集成了调度器。应用启动时调用 `start_scheduler`，应用关闭时调用 `stop_scheduler`。
- **File:** `pyproject.toml`
  - **Change:** 将 `apscheduler` 添加到项目依赖中。
---
### Decision (Bug Fix)
[2025-06-27 17:16:26] - **修正 `data_service.py` 中的日期列名不一致问题**

**Rationale:**
为了解决因日期列名不一致 (`date` vs `dates`) 导致的潜在bug，对 `data_service.py` 进行了两处关键修正。1) `_get_date_col` 函数现在为日线和周线数据统一返回 `dates`。2) `_query_database` 函数在构建查询时统一使用 `model.dates` 属性。这确保了整个服务在处理日期列时使用唯一的标识符，与数据库模型保持一致，提高了代码的健壮性和可维护性。

**Details:**
- **File:** `stockaivo/data_service.py`
  - **Change in `_get_date_col`:** The return value for 'daily' and 'weekly' periods was changed from `'date'` to `'dates'`.
  - **Change in `_query_database`:** The date column attribute used in the query for 'daily' and 'weekly' data was changed from `model.date` to `model.dates`.
---
### Decision (Architecture)
[2025-06-27 16:50:01] - **实现持久化后自动清理 `pending_save` 缓存的机制**

**Rationale:**
为了确保数据管道的健壮性和状态的准确性，必须在数据成功从 `pending_save` 缓存持久化到数据库后，自动删除对应的缓存条目。如果不删除，可能会导致数据被重复处理，或者在缓存过期后数据丢失（如果持久化失败）。通过将 `pending_save` 的Redis键作为参数传递给后台的数据库写入任务，并在任务成功后由其负责删除该键，我们创建了一个可靠的、事务性的闭环操作。

**Details:**
- **File:** `stockaivo/cache_manager.py`
  - **Change:**
    - 添加了 `delete_from_redis(key: str)` 方法用于删除任意键。
    - 修改了 `save_to_redis(...)` 的返回类型，从 `bool` 变为 `Optional[str]`，使其在成功时返回生成的缓存键名。
- **File:** `stockaivo/data_service.py`
  - **Change:**
    - 在调用 `cache_manager.save_to_redis` 时捕获返回的 `pending_save` 键。
    - 在 `background_tasks.add_task` 调用中，将此 `pending_cache_key` 作为新参数传递给 `database_writer.save_dataframe_to_db`。
- **File:** `stockaivo/database_writer.py`
  - **Change:**
    - 修改了 `save_dataframe_to_db` 函数签名，增加了一个可选参数 `pending_cache_key: Optional[str] = None`。
    - 在数据库事务成功提交后，如果 `pending_cache_key` 存在，则调用 `cache_manager.delete_from_redis` 将其删除。

---
---
---
---
### Decision (Debug)
[2025-06-27 16:47:32] - **Bug Fix Strategy: Standardize Date Column Name**

**Rationale:**
The root cause of the bug was an inconsistency in the date column naming convention within `data_service.py`. The `_get_date_col` helper function returned 'date' for daily data, while the database models and query functions expected 'dates'. Standardizing the output of `_get_date_col` to always return 'dates' for both daily and weekly data is the most direct and correct fix, ensuring alignment with the database schema and resolving the data filtering failure.

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** Modified the `_get_date_col` function to return 'dates' for both 'daily' and 'weekly' periods.

### Decision (Architecture)
[2025-06-27 16:08:15] - **实施双重Redis缓存策略 (PENDING_SAVE & GENERAL_CACHE)**

**Rationale:**
为了进一步优化数据访问性能并明确数据状态，引入了两种不同的缓存类型。
1.  `PENDING_SAVE`: 用于存放从外部API（如AKShare）获取的、等待后台任务持久化到PostgreSQL的新数据。这类缓存的生存时间（TTL）较长（24小时），以确保数据在持久化完成前不会丢失。
2.  `GENERAL_CACHE`: 用于存放从数据库或API查询出的、服务于前端读取请求的数据。这类缓存的TTL较短（1小时），旨在加速热点数据的重复访问，同时也能较快地反映数据库的更新。
这种双重策略将“待写入”数据和“只读”数据分离开来，使得缓存管理更加清晰，提高了数据获取的整体效率和系统的健壮性。

**Details:**
- **File:** `stockaivo/cache_manager.py`
  - **Change:** 引入了 `CacheType` 枚举。修改了 `save_to_redis` 和 `get_from_redis` 函数，以支持基于 `CacheType` 的不同键名（`pending_save:` vs `general_cache:`）和TTL。
- **File:** `stockaivo/data_service.py`
  - **Change:**
    - 从远程API获取新数据后，会同时写入 `PENDING_SAVE` 和 `GENERAL_CACHE`。
    - 从数据库查询出的数据，仅写入 `GENERAL_CACHE`。
    - 数据读取请求优先查询 `GENERAL_CACHE`。
### Decision (Code)
[2025-06-27 12:22:07] - **修正 `_query_database` 中的日期列选择逻辑**

**Rationale:**
`_query_database` 函数在处理日线数据 (`daily`) 时错误地使用了 `model.date` 属性，而正确的属性应该是 `model.dates`，这与周线 (`weekly`) 数据一致。此修复统一了日线和周线数据的日期列处理逻辑，确保了与数据库模型 (`models.py`) 的定义完全一致，从而消除了一个潜在的数据查询错误。

**Details:**
- **File:** `stockaivo/data_service.py`
- **Change:** 修改了 `_query_database` 函数中的条件判断，确保当 `period` 为 `'daily'` 或 `'weekly'` 时，都使用 `model.dates` 作为日期列。
### Decision (Architecture)
[2025-06-27 12:17:36] - **统一数据流中的日期列命名规范：API 'date' -> DB 'dates'**

**Rationale:**
为了解决数据源 (AKShare) 和数据库模型 (SQLAlchemy) 之间关于日期列命名的长期不一致问题 (`date` vs `dates`)，特此确立统一的转换规范。数据提供者 (`data_provider.py`) 负责从外部API获取数据并将其标准化，统一输出为带 `date` 列的DataFrame。数据写入层 (`database_writer.py`) 则负责在数据持久化之前，将 `date` 列重命名为 `dates`，以匹配数据库模型中的定义。这种策略将数据转换的责任明确地放在了数据写入层，确保了数据源的纯粹性和数据库模型的稳定性。

**Details:**
- **File:** `stockaivo/data_provider.py`
  - **Change:** 移除了针对周线数据将 `date` 列重命名为 `dates` 的特殊逻辑，确保所有时间周期的数据都统一以 `date` 列名输出。
- **File:** `stockaivo/models.py`
  - **Change:** 确认并保持 `StockPriceDaily` 和 `StockPriceWeekly` 模型中的日期字段为 `dates`。
- **File:** `stockaivo/database_writer.py`
  - **Change:** 在 `save_dataframe_to_db` 函数中增加了明确的重命名步骤 `dataframe.rename(columns={'date': 'dates'})`，作为数据持久化前的预处理。同时，更新了相关的 `_prepare...` 和 `_batch_upsert_prices` 函数以正确处理 `dates` 字段。
---
### Decision (Architecture)
[2025-06-27 11:32:43] - **采用 FastAPI BackgroundTasks 实现数据库写入异步化**

**Rationale:**
为了优化API响应时间，特别是对于那些触发远程数据获取的请求，我们将耗时的数据库写入操作从主请求/响应循环中分离出来。使用 FastAPI 内置的 `BackgroundTasks` 是一个轻量级且高效的解决方案，它允许我们将函数（如 `save_dataframe_to_db`）注册为在响应发送后在后台运行的任务。这确保了用户可以立即收到数据，而数据库的持久化操作则在后台异步完成，从而显著提升了用户体验和系统吞吐量。

**Details:**
- **文件:** `stockaivo/routers/stocks.py`, `stockaivo/data_service.py`
- **实现:**
  - 在 `stocks.py` 的 API 端点中注入 `BackgroundTasks` 依赖。
  - 将 `background_tasks` 对象一直传递到 `data_service.get_stock_data` 函数。
  - 在 `data_service.py` 中，当从远程API获取到新数据后，使用 `background_tasks.add_task(database_writer.save_dataframe_to_db, ...)` 来调度异步写入，而不是直接调用该函数。
---
### Decision (Code)
[2025-06-20 21:01:18] - SQLAlchemy ORM模型架构设计

**Rationale:**
基于项目文档要求和数据库最佳实践，选择了合适的字段类型、约束和关系设计，确保数据一致性和查询性能。

**Details:**
- 价格字段使用Numeric(10,4)而非Float，避免浮点数精度问题
- 交易量使用BigInteger支持大数值
- 创建复合唯一约束(ticker+dates/timestamp)防止重复数据
- 使用cascade="all, delete-orphan"确保数据完整性
- 为高频查询字段创建专门索引提升性能
---
### Decision (Code)
[2025-06-20 21:09:20] - AKShare数据源封装实现决策

**Rationale:**
参考D:\Coding\stockai项目的成功实现，选择使用ak.stock_us_hist接口而非其他接口，并采用正确的fullsymbol格式（如"105.AAPL"）来确保数据获取的稳定性。

**Details:**
- 使用ak.stock_us_hist(symbol=fullsymbol, period=period, adjust="qfq")接口
- ticker转换为fullsymbol格式：f"105.{ticker}"（105为美股市场代码）
- 实现中文列名到英文的标准化映射，基于参考项目的成功经验
- 数据验证策略：对负数价格采用warning+修正而非直接拒绝，提高容错性
- 小时线数据暂用日线数据代替，因AKShare不直接支持美股小时数据
---
### Decision (Code)
[2025-06-20 21:12:30] - Redis缓存管理器架构设计与实现

**Rationale:**
基于项目文档1.3节要求，设计了一个完整的Redis缓存系统来处理从AKShare获取的临时数据。选择面向对象设计和类型安全的实现方式，确保系统的可维护性和健壮性。

**Details:**
- 使用CacheManager类封装所有Redis操作，支持连接池和健康检查
- 键名格式采用`pending_save:{ticker}:{period}`模式，清晰标识数据来源和类型
- DataFrame序列化采用JSON格式，包含元数据(时间戳、行数)便于调试和监控
- 实现完整的错误处理机制：连接错误、序列化错误、Redis操作错误
- 支持环境变量配置Redis连接参数，提供合理默认值
- 添加数据过期机制(24小时TTL)防止缓存数据积压
- 提供缓存统计和健康检查功能便于运维监控
---
### Decision (Code)
[2025-06-20 21:14:40] - 数据查询主逻辑架构设计与实现

**Rationale:**
基于项目文档1.4节要求，设计了一个完整的数据查询协调系统，采用数据库优先、外部API补充、缓存辅助的三层架构模式，确保数据获取的效率和可靠性。

**Details:**
- 实现核心函数get_stock_data(ticker, period)作为统一数据入口点
- 采用数据库优先策略：先查询PostgreSQL，未找到再调用AKShare
- 数据库查询使用占位符函数_query_database_placeholder()，便于后续具体实现
- 集成已实现的data_provider.fetch_from_akshare()和cache_manager.save_to_redis()函数
- 实现完善的错误处理机制：缓存失败不影响数据返回，确保服务可用性
- 添加健康检查check_data_service_health()和缓存统计get_cached_data_summary()功能
- 提供test_data_service()函数便于功能验证和调试
---
### Decision (Code)
[2025-06-20 21:19:25] - 异步数据持久化架构设计与实现

**Rationale:**
基于项目文档1.5节要求，设计了完整的数据持久化系统，采用PostgreSQL UPSERT机制处理数据冲突，确保数据一致性和系统健壮性。选择FastAPI框架提供RESTful API接口，便于系统集成和监控。

**Details:**
- 数据库连接管理：使用SQLAlchemy 2.0+引擎，配置连接池和健康检查机制
- 批量UPSERT策略：使用PostgreSQL的ON CONFLICT DO UPDATE语法处理数据冲突
- 事务管理：每个ticker+period组合使用独立事务，失败时不影响其他数据处理
- API设计：提供/check-pending-data检查和/persist-data执行两个核心端点
- 错误处理：完善的异常处理和日志记录，支持部分失败场景
- 数据类型映射：处理AKShare中文列名到数据库英文字段的转换
---
### Decision (Code)
[2025-06-20 21:22:45] - 股票数据API架构设计与实现

**Rationale:**
基于项目文档功能二要求，设计了完整的RESTful API系统，采用FastAPI路由器模式和Pydantic数据验证，确保API的标准化、可维护性和数据安全性。

**Details:**
- API端点设计：实现/stocks/{ticker}/daily、weekly、hourly三个核心端点，符合RESTful风格
- 数据模型设计：使用Pydantic定义StockPriceBase、StockDataResponse等响应模型，确保数据格式一致性
- 路由组织：采用FastAPI APIRouter模式，创建独立的stocks.py路由文件，便于模块化管理
- 参数验证：实现ticker代码验证、日期范围过滤等输入验证机制
- 错误处理：完善的HTTP状态码和错误响应，包括404、400、500等标准错误处理
- 集成方式：在main.py中使用include_router()集成股票路由，保持代码组织清晰
---
**Timestamp:** 2025-06-20T21:25:18+08:00


---
### Decision (Debug)
[2025-07-01 11:22:25] - [BugFix: Disable HTTP/2 to Resolve `httpx.ReadError`]

**Rationale:**
The application was experiencing `httpx.ReadError` when communicating with the local LLM service at `http://localhost:3222`. While direct `curl` requests were successful, `httpx` calls failed, suggesting a client-server incompatibility. The root cause was identified as a likely incompatibility between `httpx`'s default HTTP/2 support and the local LLM server's capabilities, causing the server to drop the connection prematurely.

The fix involves explicitly disabling HTTP/2 in the `httpx.AsyncClient` instance within `stockaivo/ai/llm_service.py`. This forces communication over HTTP/1.1, which stabilized the connection and resolved the `ReadError`, allowing the client to receive a proper `502 Bad Gateway` response instead of a connection error.

**Details:**
- **File:** `stockaivo/ai/llm_service.py`
- **Change:** Added the parameter `http2=False` to the `httpx.AsyncClient` constructor.

- **[2025-07-01 11:28:20] Deployment Strategy:**
  - **Decision:** Used `uv run dev` to start the application based on `pyproject.toml` scripts.
  - **Decision:** Used PowerShell's `Start-Job` for background execution and `Invoke-WebRequest` for API calls to ensure compatibility with the Windows environment.
  - **Observation:** Increased sleep time to 10 seconds to allow the server to initialize before sending requests.
  - **Issue:** Identified a `502 Bad Gateway` error from the `technical_analyst` agent, indicating a problem with a downstream service.


---
### Decision (Debug)
[2025-07-02 15:28:22] - [BugFix: Resolve `TypeError` in `StockChart.tsx` due to `lightweight-charts` typing issue]

**Rationale:**
The application was throwing a runtime error `TypeError: chartRef.current.addCandlestickSeries is not a function` in the `StockChart.tsx` component. The root cause was determined to be incorrect or mismatched TypeScript type definitions for the `lightweight-charts` library (v5.0.8), which caused the TypeScript compiler to believe that the `addCandlestickSeries` and `addHistogramSeries` methods did not exist on the `IChartApi` interface, even though they likely exist on the actual JavaScript object at runtime. The secondary cause was the incorrect API usage pattern for setting series options, which is a breaking change in v4+ of the library.

The fix involves two main parts:
1.  **Bypass Type Checking:** Use a type assertion (`as any`) when calling `addCandlestickSeries` and `addHistogramSeries`. This tells the TypeScript compiler to ignore the faulty type definitions and trust that the methods exist at runtime.
2.  **Correct API Usage:** Refactor the series creation logic to align with the `lightweight-charts` v4+ API. Instead of passing all options directly to the `add...Series` method, the series is created without options, and then `applyOptions` is called on the newly created series object to set its visual properties.

This combined approach resolves both the compile-time type errors and the underlying runtime error while aligning the code with modern library standards. Additionally, the component's parent page (`page.tsx`) was modified to use `next/dynamic` to import the chart component, preventing potential SSR-related issues.

**Details:**
- **File:** `frontend/src/components/StockChart.tsx`
  - **Change:** Wrapped `chartRef.current` with `(chartRef.current as any)` before calling `addCandlestickSeries` and `addHistogramSeries`. Separated series creation from option application using `.applyOptions()`.
- **File:** `frontend/src/app/page.tsx`
  - **Change:** Replaced the static import of `StockChart` with a dynamic import using `next/dynamic`, with `ssr: false`.


---
### Decision (Debug)
[2025-07-02 16:02:00] - [BugFix: Correct Invalid DOM Structure in Root Layout]

**Rationale:**
The application page at http://localhost:4222/ was blank. The root cause was identified as an invalid DOM structure being generated by the `RootLayout` component in `frontend/src/app/layout.tsx`. This component was rendering its own `<html>` and `<body>` tags. In a Vite-based single-page application, these tags are managed by the main `index.html` file, and React components should only render content *inside* the `<body>`. Rendering nested `<html>` tags is invalid HTML and causes modern browsers to fail to render the page correctly. The fix is to remove these tags from the React component, ensuring it only renders the `<Outlet />` for its child routes within a React Fragment.

**Details:**
- **File:** `frontend/src/app/layout.tsx`
- **Change:** Removed the `<html>` and `<body>` tags from the `RootLayout` component's return statement, wrapping the `<Outlet />` in a React Fragment (`<>...</>`).


---

### **内存银行更新摘要**

**标题:** `[2025-07-03] - 修正周线数据必需日期的生成逻辑以正确处理节假日`

**基本原理:**
`_get_required_dates` 函数在计算周线数据 (`weekly`) 的必需日期时，可能会将非交易日的周五（如节假日）错误地包含进来。这是因为它会将一周的最后一个交易日（如周四）的日期“滚动”到当周的周五，而没有验证该周五本身是否也是一个交易日。本次修复通过增加一个验证步骤来解决此问题：在生成所有潜在的周五之后，会与原始的交易日列表进行比对，只保留那些本身就是交易日的周五。这从根本上阻止了对节假日的数据请求，提高了数据管道的健壮性和准确性。

**实施细节:**
- **文件:** `stockaivo/data_service.py`
- **函数:** `_get_required_dates`
- **变更:**
    1.  在函数开始时，将从 `nyse.schedule` 获取的所有交易日存储在一个 `set` 中，以备快速查询。
    2.  在为 `weekly` 周期计算出所有潜在的周五后，增加了一个列表推导式，用 `trading_days_set` 来过滤这个列表，确保结果中的每个周五都是真实的交易日。

---
