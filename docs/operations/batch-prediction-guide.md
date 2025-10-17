# 批量结构化预测操作指南

> 适用版本：2025-10-14 之后的批量预测改造

## 1. 功能概览

批量结构化预测 API 提供一次性为多只股票生成结构化预测结果的能力，核心流程包括：
- 由 `/ai/predict-structured/batch` 接收请求，基于 `StructuredPredictionBatchRequest` 参数校验。
- 使用 `asyncio.Semaphore` 与自研 `RateLimiter` 组件串联 Tickertick、AKShare 与 AI 调用速率，确保外部数据源安全。
- 每只股票调用 `stockaivo.ai.structured_prediction_service.run_structured_prediction` 获取预测结果，并可按需写入 PostgreSQL。
- 失败时按指数退避策略重试，最终输出每个 ticker 的成功状态、耗时、错误原因与重试次数。
- 预测结果和错误摘要会通过 `StructuredPredictionBatchResponse` 返回，同时写入结构化预测 Redis 待持久化队列。
- 新增 `execution_mode` 模式开关，可在完整预测（`full`）与仅数据采集（`data_collection_only`）之间切换。

## 2. 关键模块

| 模块         | 作用                                                         | 路径                                                                 |
| ------------ | ------------------------------------------------------------ | -------------------------------------------------------------------- |
| 路由入口     | 参数清洗、并发控制、重试调度                                 | `stockaivo/routers/ai.py`                                            |
| 核心预测服务 | 单只股票结构化预测协程                                       | `stockaivo/ai/structured_prediction_service.py`                      |
| 限流器       | 令牌桶 + 全局并发控制 + 指数退避                             | `stockaivo/utils/rate_limiter.py`                                    |
| Redis 管理   | 写入 `prediction:pending:{ticker}:{marketDate}:{targetDate}` | `stockaivo/cache_manager.py`                                         |
| 定时持久化   | 将 Redis 待持久化数据写入数据库                              | `stockaivo/database_writer.py` + `stockaivo/background_scheduler.py` |

## 3. 请求前准备

1. 确保 `.env` 中配置了以下关键项：
   - `OPENAI_API_BASE`、`OPENAI_API_KEY`：Agent 依赖的 LLM 服务。
   - `REDIS_URL`、`DATABASE_URL`：缓存与数据库连接。
   - 如需调整批量限流参数，请参考第 6 节环境变量。
2. 启动 FastAPI 应用（`uv run dev` 或 `docker-compose up`），确认 `/health` 返回 200。
3. Redis 需可写并允许创建 `prediction:pending:*` 键；PostgreSQL 需要存在 `stock_predictions` 相关表结构（随迁移自动创建）。

## 4. 请求与响应模型

### 4.1 请求体示例

```json
{
  "tickers": ["AAPL", "MSFT", "TSLA"],
  "end_date": "2025-01-10",
  "save_to_db": true,
  "max_concurrency": 3,
  "max_retries": 1,
  "retry_delay_seconds": 5.0,
  "execution_mode": "full"
}
```

字段说明：

| 字段                  | 类型        | 默认值 | 说明                                     |
| --------------------- | ----------- | ------ | ---------------------------------------- |
| `tickers`             | `List[str]` | 无     | 待处理股票列表，自动去重与裁剪空值       |
| `end_date`            | `date`      | `null` | 可选统一结束日期；为空时使用系统日期推算 |
| `save_to_db`          | `bool`      | `true` | 是否将结果持久化至 PostgreSQL            |
| `max_concurrency`     | `int`       | `3`    | 并发协程上限，取值 1-10，建议 1-5        |
| `max_retries`         | `int`       | `0`    | 单票失败后允许的最大重试次数（不含首次） |
| `retry_delay_seconds` | `float`     | `5.0`  | 重试前等待秒数，用作指数退避基础值       |
| `execution_mode`      | `str`       | `full` | 执行模式：`full` 运行完整预测；`data_collection_only` 仅采集日线/周线数据，跳过新闻与多智能体分析，且不会将结构化预测结果写入 Redis 待持久化队列或数据库 |

> `data_collection_only` 模式仅抓取日线/周线行情数据，不触发新闻情感、技术/基本面分析与最终预测生成；对应的结构化预测结果不会写入 Redis 待持久化队列或数据库。

### 4.2 响应体结构

```json
{
  "results": [
    {
      "ticker": "AAPL",
      "success": true,
      "latency_seconds": 1.42,
      "retries": 0,
      "response": { "success": true, "prediction_probability": 0.72, "direction": "UP", ... },
      "error": null,
      "execution_mode": "full"
    },
    {
      "ticker": "TSLA",
      "success": false,
      "latency_seconds": 3.18,
      "retries": 1,
      "response": null,
      "error": "LLM 服务不可用",
      "execution_mode": "full"
    }
  ],
  "summary": {
    "total": 2,
    "success": 1,
    "failed": 1,
    "duration_seconds": 3.44,
    "execution_mode_counts": {
      "full": 2
    }
  },
  "failed_tickers": ["TSLA"]
}
```

- `results`：逐票执行结果，包含耗时、重试次数与原始响应。
- `summary`：批量任务统计信息。
- `failed_tickers`：失败股票列表，可直接用于二次重试。
- `execution_mode`：标记该股票使用的执行模式，便于与失败列表、进度记录对应。
- `execution_mode_counts`：按模式统计的票数，当混合使用不同模式时可快速评估分布。
- `data_collection_summary`：仅在 `data_collection_only` 模式下出现，展示各数据集的记录条数。

**数据采集模式响应示例**（截取单项）：

```json
{
  "ticker": "AAPL",
  "success": true,
  "latency_seconds": 0.81,
  "retries": 0,
  "response": {
    "success": true,
    "direction": null,
    "prediction_probability": null,
    "execution_mode": "data_collection_only",
    "data_collection_summary": {
      "daily_prices": 120,
      "weekly_prices": 32
    },
    "reasoning": "数据采集模式已完成，采集 AAPL 的数据摘要：daily_prices: 120 条，weekly_prices: 32 条。"
  },
  "error": null,
  "execution_mode": "data_collection_only"
}
```

## 5. 使用示例

### 5.1 cURL

```bash
curl -X POST "http://127.0.0.1:8000/ai/predict-structured/batch" \
  -H "Content-Type: application/json" \
  -d '{
        "tickers": ["AAPL", "MSFT", "TSLA"],
        "save_to_db": false,
        "max_concurrency": 2,
        "max_retries": 1,
        "retry_delay_seconds": 4.0
      }'
```

### 5.2 CLI 或脚本建议

- 建议在外部脚本中按批次（例如 3-5 支股票）调用，并根据 `failed_tickers` 实现自动重试。
- 若需处理数百只股票，可考虑串联 APScheduler 队列或未来的 CLI 工具（见 TODO 中的后续任务）。

### 5.3 本地开发环境 CLI

如果只是在本地验证，可直接使用 `uv` 运行脚本；确保 FastAPI 服务已通过 `uv run dev` 启动（默认监听 `http://127.0.0.1:8000`）：

```bash
uv run python stockaivo/scripts/bulk_predict_from_db.py \
  --api-base-url http://127.0.0.1:8000 \
  --batch-size 10 \
  --max-concurrency 3 \
  --max-retries 1 \
  --dry-run
```

> 🧑‍💻 建议先使用 `--dry-run` 查看批次数量，再移除该参数执行真实请求。若希望脚本直接复用内部路由（无需 HTTP），可省略 `--api-base-url`，但要注意不要和同一进程的长时间批量任务冲突。

常见参数：

| 参数                     | 默认值                                           | 说明                                                                |
| ------------------------ | ------------------------------------------------ | ------------------------------------------------------------------- |
| `--api-base-url`         | 无                                               | 指定 FastAPI 服务地址，避免脚本与应用共用事件循环                   |
| `--batch-size`           | 20                                               | 可在本地调试时下调以缩短单批耗时                                    |
| `--output`               | `logs/batch_failures/bulk_predict_failures.json` | 失败列表输出路径，建议固定到可持久化目录，便于 diff 和归档          |
| `--execution-mode`       | `full`                                           | 执行模式：`full` 运行完整预测；`data_collection_only` 仅采集日线/周线数据，跳过新闻与预测阶段，结构化预测结果不会写入 Redis 待持久化队列或数据库 |
| `--limit`                | 无                                               | 仅取前 N 个 symbol，便于局部验证                                    |
| `--include-symbols-file` | 无                                               | 指定 manifest/JSON/CSV 清单后按文件内顺序执行，忽略数据库全量读取   |
| `--exclude-symbols-file` | 无                                               | 提供需跳过的股票清单，常用于暂时排除故障股票                        |
| `--progress-file`        | `logs/batch_progress/bulk_progress.json`        | 进度文件路径，记录已成功的股票，便于断点续跑                        |
| `--resume/--no-resume`   | `--resume`                                       | 是否根据进度文件跳过已完成股票，默认开启，可通过 `--no-resume` 关闭 |
| `--reset-progress`       | 关闭                                             | 运行前清空进度文件，适合重新跑批或验证                              |

### 5.4 Docker 生产环境 CLI

全量跑通 `well_known_stock_symbols` 表时，可直接在容器内调用新脚本 `stockaivo/scripts/bulk_predict_from_db.py`：

```bash
docker compose exec stockaivo-backend-1 \
  uv run python stockaivo/scripts/bulk_predict_from_db.py \
    --batch-size 20 \
    --max-concurrency 5 \
    --max-retries 1 \
    --output /logs/batch_failures/bulk_cli_failures.json
```

> ⚙️ 前置条件：
> - `stockaivo-backend-1` 容器正在运行且已完成 `.env` 配置；
> - Redis / PostgreSQL 均可写；`logs/` 已绑定为持久化卷（便于收集失败列表）。
> - 如果容器内尚未存在 `/logs/batch_failures/` 目录，请先执行 `mkdir -p /logs/batch_failures`。

命令参数说明：

| 参数                     | 默认值                                            | 说明                                                       |
| ------------------------ | ------------------------------------------------- | ---------------------------------------------------------- |
| `--batch-size`           | 20                                                | 每批处理的股票数量，可根据限流配置下调                     |
| `--max-concurrency`      | 5                                                 | 分发到 `/ai/predict-structured/batch` 的并发上限           |
| `--max-retries`          | 1                                                 | 单票失败后的重试次数（不含首次）                           |
| `--output`               | `/logs/batch_failures/bulk_predict_failures.json` | 失败列表输出路径，建议映射到宿主机便于重试；若使用示例命令将自动生成 `bulk_cli_failures.json` |
| `--dry-run`              | 关闭                                              | 开启后仅打印批次数量，不发起调用                           |
| `--api-base-url`         | 未设置                                            | 如需走 HTTP，可设为 `http://localhost:3224` 或反向代理地址 |
| `--execution-mode`       | `full`                                            | 执行模式：`full` 运行完整预测；`data_collection_only` 仅采集日线/周线数据，跳过新闻与预测阶段，结构化预测结果不会写入 Redis 待持久化队列或数据库 |
| `--include-symbols-file` | 无                                                | 指定容器内 manifest 或挂载清单，实现分批执行               |
| `--progress-file`        | `/logs/batch_progress/bulk_progress.json`        | 建议指向持久化卷，记录断点信息                             |
| `--resume/--no-resume`   | `--resume`                                        | 控制是否根据进度文件跳过已完成股票                         |
| `--reset-progress`       | 关闭                                              | 运行前清空进度文件；清空后若未限制范围，本轮将全量执行     |

执行完成后脚本会输出总成功/失败统计，若存在失败，将在 `--output` 指定路径生成 JSON，包含失败的 ticker、错误信息与批次索引，便于后续 `--dry-run` 验证或二次重试。

### 5.5 失败补跑脚本

批量预测完成后，如 `--output` 生成的 `bulk_predict_failures.json` 中仍有失败股票，可使用 `stockaivo/scripts/retry_failed_predictions.py` 自动补跑。该脚本会读取失败列表 JSON，按参数重新分批调用批量接口，并将最新失败结果写入新的文件，确保多轮重试具备可追溯性；若传入 `--progress-file`，补跑成功的股票也会同步写入进度文件，便于主脚本断点恢复。

```bash
uv run python stockaivo/scripts/retry_failed_predictions.py \
  --input logs/batch_failures/bulk_predict_failures.json \
  --output logs/batch_failures/bulk_predict_failures_retry.json \
  --batch-size 10 \
  --max-concurrency 3 \
  --max-retries 2 \
  --progress-file logs/batch_progress/bulk_progress.json \
  --api-base-url http://127.0.0.1:8000 \
  --run-context batch_004
```

参数说明：

| 参数                  | 默认值                                                 | 说明                                                                                                                                       |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `--input`             | `logs/batch_failures/bulk_predict_failures.json`       | 首次批量任务生成的失败列表路径，支持手动放入任意 JSON（需包含 `failures[].ticker` 或 `failed_tickers` 字段）；新格式将失败按 `runs` 聚合存储 |
| `--output`            | `logs/batch_failures/bulk_predict_failures_retry.json` | 补跑后的失败列表输出位置，可用于下一轮重试或审计                                                                                           |
| `--batch-size`        | `10`                                                   | 每批提交的股票数量，建议结合上一轮失败原因适当调小                                                                                         |
| `--max-concurrency`   | `3`                                                    | 补跑时的并发度，可在受限环境下调低避免触发限流                                                                                             |
| `--max-retries`       | `2`                                                    | 单票补跑的最大重试次数，默认比初次任务稍高                                                                                                 |
| `--retry-delay`       | `5.0`                                                  | 指数退避基础值，与批量接口参数一致                                                                                                         |
| `--save-to-db`        | `true`                                                 | 是否将补跑成功的结果写入数据库，可通过 `--no-save-to-db` 关闭                                                                              |
| `--end-date`          | `null`                                                 | 可选统一结束日期，如需覆盖请传入 `YYYY-MM-DD`                                                                                              |
| `--api-base-url`      | `null`                                                 | 指定 FastAPI 服务地址；未设置时脚本会复用应用内部路由                                                                                    |
| `--api-key`           | `null`                                                 | HTTP 调用时附加的 `Authorization` 头部                                                                                                     |
| `--limit`             | `null`                                                 | 仅补跑失败列表前 N 支股票，其余股票会原样保留在输出文件中，便于分批处理                                                                    |
| `--execution-mode`    | 自动检测（或 `full`）                                  | 若失败列表包含模式信息会自动继承，可手动指定 `full`/`data_collection_only` 强制以特定模式补跑                                              |
| `--run-context`       | `null`                                                 | 当失败文件中存在多个运行记录 (`runs[]`) 时，用于指定目标批次（通常为清单文件名，如 `batch_004`）；未指定时默认选取最新一条记录              |
| `--progress-file`     | `logs/batch_progress/bulk_progress.json`               | 指定进度文件，补跑成功会自动同步到该文件，后续主流程可据此跳过已成功股票                                                                   |
| `--resume/--no-resume`| `--resume`                                             | 控制是否根据进度文件跳过已成功股票，默认遵循进度；如需强制重跑可使用 `--no-resume`                                                         |
| `--reset-progress`    | 关闭                                                   | 运行前清空进度文件（仅在启用了 `--progress-file` 时生效），适合重新初始化补跑                                                              |

> 如未显式指定 `--run-context`，脚本会自动选取失败文件 `runs[]` 列表中的最新一条记录，并继承其中的 `execution_mode`；若失败文件仍为旧版（无 `runs` 字段），脚本将继续兼容原有结构。

> 建议补跑前先检查失败原因是否为限流或外部数据源故障。如多次补跑仍失败，可结合日志排查异常并考虑暂时移除问题股票。

> 📌 当使用 `--limit` 分批补跑时，脚本会自动将本轮成功的股票从输出 JSON 中移除，同时保留未处理与仍失败的股票，方便下一轮继续执行。

> 🔁 最佳实践：首轮补跑建议保持默认输出路径 `logs/batch_failures/bulk_predict_failures_retry.json`，下一轮可直接把该文件作为新的 `--input`，脚本会在此基础上继续补跑并写回同一路径。若希望“就地更新”原始 `bulk_predict_failures.json`，需要同时将 `--input` 与 `--output` 指向同一文件，执行前务必备份以便审计。

### 5.6 批次清单与断点续跑流程

> 自 2025-10-15 起，CLI 支持批次 manifest 生成与进度断点功能，可将 292 支股票拆分为多个小批次执行。

1. **生成批次清单**

   ```bash
   uv run python stockaivo/scripts/bulk_predict_from_db.py \
     --generate-manifests \
     --manifest-output-dir data/batch_manifests \
     --manifest-batch-size 30 \
     --manifest-shuffle \
     --manifest-concurrency 3
   ```

   - 默认会输出 `batch_001.json`、`batch_002.json`... 以及 `manifest_index.json`；
   - 每个清单包含 `batch_id`、`tickers`、`suggested_max_concurrency` 字段，可据此安排运行批次；
   - `--manifest-seed` 支持固定乱序顺序，便于团队之间复现批次划分。

   Manifest 相关参数补充：

   | 参数                     | 默认值                 | 说明                                                                           |
   | ------------------------ | ---------------------- | ------------------------------------------------------------------------------ |
   | `--manifest-output-dir`  | `data/batch_manifests` | 清单输出目录，建议纳入版本控制忽略列表；容器场景可指向 `/data/batch_manifests` |
   | `--manifest-batch-size`  | 30                     | 单个清单的股票量，可根据限流策略调整                                           |
   | `--manifest-concurrency` | 3                      | 推荐的最大并发值，将写入每个清单文件                                           |
   | `--manifest-prefix`      | `batch_`               | 清单文件名前缀（例如 `batch_001.json`）                                        |
   | `--manifest-shuffle`     | 关闭                   | 是否随机乱序股票列表，避免始终同一顺序                                         |
   | `--manifest-seed`        | 无                     | 与 `--manifest-shuffle` 配合使用，确保乱序可重现                               |

2. **选择清单执行**

   ```bash
   uv run python stockaivo/scripts/bulk_predict_from_db.py \
     --include-symbols-file data/batch_manifests/batch_001.json \
     --progress-file logs/batch_progress/bulk_progress.json \
     --execution-mode data_collection_only \
     --max-concurrency 3 \
     --max-retries 1
   ```

   - `--include-symbols-file` 会按清单顺序执行，绕过数据库全量读取；
   - `--exclude-symbols-file` 可用于跳过已知问题股票，支持 JSON/CSV/纯文本格式；
   - 可通过 `--execution-mode` 选择 `full` 或 `data_collection_only`；清单任务支持两种模式，执行结果将写入相应的失败/进度文件；
   - 进度默认写入 `logs/batch_progress/bulk_progress.json`，便于随时暂停并恢复剩余批次（文件会记录执行模式，切换模式时请配合 `--reset-progress` 或使用新文件）。

3. **断点续跑与重置**

   - `--resume/--no-resume` 控制是否根据进度文件自动跳过已完成股票（默认开启）；
   - `--reset-progress` 可在正式跑批前清空进度文件；清空后若未限制处理范围，会把当前批次选中的全部股票视为待执行；
   - 进度文件结构示例：

     ```json
    {
      "updated_at": "2025-10-15T01:23:45.678901",
      "processed_count": 120,
      "processed_tickers": ["AAPL", "MSFT", "..."],
      "execution_mode": "full"
    }
    ```
   - 进度文件会记录最近一次的执行模式，如需切换模式请先使用 `--reset-progress` 或清理该文件，避免跨模式跳过尚未执行的股票。

   - 当批次执行失败时，失败股票仍会写入 `--output` 指定的 JSON，可与 `retry_failed_predictions.py` 搭配补跑。

> 推荐流程：先使用 `--generate-manifests` 拆分批次 → 基于清单挨个跑批（搭配进度、排除清单）→ 若遇到失败则使用失败文件补跑或在下一批次前调整清单。

> ⚠️ 提醒：`--reset-progress` 仅清除历史记录，不会自动缩减本轮股票集合。若希望清空后只执行子集，请结合 `--include-symbols-file`、`--limit` 或手动裁剪清单。

## 6. 限流与重试配置

限流器通过 `stockaivo.dependencies.get_batch_prediction_rate_limiter` 懒加载，可用环境变量覆盖默认值：

| 环境变量                                | 默认值  | 说明                                     |
| --------------------------------------- | ------- | ---------------------------------------- |
| `BATCH_RATE_LIMITER_DISABLED`           | `false` | 置为 `true/1` 可完全关闭限流器（不推荐） |
| `AI_PREDICT_REQUESTS_PER_WINDOW`        | `5`     | AI 调用窗口内允许次数                    |
| `AI_PREDICT_WINDOW_SECONDS`             | `60.0`  | AI 调用时间窗口（秒）                    |
| `AI_PREDICT_JITTER_SECONDS`             | `0.5`   | AI 调用附加抖动                          |
| `TICKERTICK_REQUESTS_PER_WINDOW`        | `10`    | Tickertick 新闻接口窗口内次数            |
| `TICKERTICK_WINDOW_SECONDS`             | `60.0`  | Tickertick 时间窗口（秒）                |
| `TICKERTICK_JITTER_SECONDS`             | `1.0`   | Tickertick 抖动                          |
| `AKSHARE_REQUESTS_PER_WINDOW`           | `10`    | AKShare 调用窗口内次数                   |
| `AKSHARE_WINDOW_SECONDS`                | `60.0`  | AKShare 时间窗口（秒）                   |
| `AKSHARE_JITTER_SECONDS`                | `0.5`   | AKShare 抖动                             |
| `BATCH_RATE_LIMITER_DEFAULT_JITTER`     | `0.5`   | 默认抖动，应用于未单独配置的桶           |
| `BATCH_RATE_LIMITER_ERROR_BASE`         | `2.0`   | 重试退避基础间隔（秒）                   |
| `BATCH_RATE_LIMITER_ERROR_MAX`          | `45.0`  | 重试退避最大值（秒）                     |
| `BATCH_RATE_LIMITER_ERROR_JITTER`       | `1.0`   | 重试退避抖动                             |
| `BATCH_RATE_LIMITER_MAX_RETRIES`        | `3`     | 限流器内部允许的最大重试次数             |
| `BATCH_RATE_LIMITER_GLOBAL_CONCURRENCY` | `6`     | 全局并发上限，所有桶共享                 |

> 提示：API 请求中的 `max_retries` 会与限流器的 `max_retry_attempts` 取最小值；若需更多重试次数，应同步调大两侧配置。

## 7. Redis 持久化链路

1. 每次成功预测会调用 `CacheManager.enqueue_structured_prediction_pending`，写入键：
   `prediction:pending:{ticker}:{marketDate}:{targetDate}`。
2. APScheduler 任务 `persist_pending_data_job`（位于 `stockaivo/background_scheduler.py`）会定期执行 `database_writer.persist_pending_data`：
   - 读取并反序列化 Redis payload。
   - 调用 SQLAlchemy `merge` 写入 `StockPrediction` 表。
   - 成功后删除对应 Redis 键并记录日志。
3. 任务运行结果会返回处理数量、失败明细，建议结合日志或监控报警。

如需手动触发持久化，可在 FastAPI 应用上下文中调用 `persist_pending_data()` 或直接运行调度器脚本。

## 8. 故障排查

- **报错 "tickers 列表不能为空"**：检查请求是否传入有效股票代码，服务会自动去除重复与空白条目。
- **`LLM 服务不可用`**：LLM 超时或限流，可通过增大 `retry_delay_seconds`、降低 `max_concurrency` 或调低 AI 限流配置解决。
- **Redis 未写入待持久化数据**：确认 `save_to_db=true` 且 Redis 连接正常；检查日志中是否有 `prediction:pending` 相关警告。
- **PostgreSQL 事务失败**：查看 `logs/` 中的 `persist_pending_data` 日志明细，必要时手动清除问题 Redis 键再重试。
- **限流器日志警告**：出现 `RateLimitExceeded` 时，说明桶配置过小或批量并发过高，建议临时调低请求并发或调整环境变量。

## 9. 测试与验证

- `tests/test_structured_prediction_api.py`：覆盖批量 API 的成功、失败与退避流程。
- `tests/test_rate_limiter.py`：验证限流器的时间窗口、全局并发与退避上限。

执行 `uv run pytest tests/test_structured_prediction_api.py::test_batch_prediction_endpoint_success -q` 可快速检查回归。

## 10. 最佳实践

- 建议以 **平衡模式**（并发=3、AI 间隔≈12秒）作为生产初始值，逐步调优。
- 对于高优先级股票，可先小批量运行，观察 `summary.failed` 与日志，再放大批次。
- 搭配 `failed_tickers` 和 Redis 待持久化队列，可实现 CLI 或定时任务的断点重试流程。
- 更新限流配置后需重启服务以使缓存的 `RateLimiter` 生效（缓存通过 `lru_cache` 实现）。
