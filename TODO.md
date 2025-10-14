# 批量结构化预测异步调用系统 TODO

> 创建日期：2025-10-12 | 状态：进行中 | 优先级：🔴 HIGH

## 🎯 核心目标

实现一个智能的批量异步调用系统，向 `/ai/predict-structured` 接口批量发送股票结构化预测请求，同时严格遵守各类数据源和API的请求频率限制。

## 📋 背景与约束

### 现有限流机制（已实现）
- ✅ **新闻数据（TickerTick）**: 10次/分钟，429错误重试延迟65秒
- ✅ **AI服务（LLM）**: 指数退避重试（1-60秒）
- ⚠️ **其他数据源（AKShare）**: 未发现显式限流，需添加保护

### 关键约束
1. **新闻数据获取间隔**: 最低 6秒/次（10次/分钟）
2. **AI预测接口调用**: 需考虑LLM调用频率和并发数
3. **数据源保护**: 防止短时间大量请求导致IP被屏蔽
4. **错误恢复**: 支持断点续传和失败重试

## 🆕 当前任务清单（2025-10-14 更新）

> 以下任务已拆解至 1-2 日粒度，可直接在 TODO 中领取。所有任务默认延续 FastAPI 鉴权/中间件约定，并需使用中文注释与日志。

- [ ] **Task A：抽象结构化预测核心服务**（Owner：待定）
  - 目标：将 `stockaivo/routers/ai.py` 中 `/ai/predict-structured` 的单票流程下沉为 `stockaivo/ai/structured_prediction_service.py` 可复用协程。
  - 要点：保留 GraphState 初始化、Agent 并行执行、可选持久化；暴露 `async run_structured_prediction(request: StructuredPredictionRequest, db: Session | None)`；返回值直接映射 `StructuredPredictionResponse`。
  - 参考文件：`stockaivo/routers/ai.py`, `stockaivo/ai/agents.py`, `stockaivo/ai/orchestrator.py`
  - 交付物：核心服务模块 + 单元测试（打桩 LLM 调用即可）。

- [ ] **Task B：实现批量结构化预测 API**（依赖：Task A）
  - 目标：新增 `POST /ai/predict-structured/batch`，接收 `tickers`、`end_date`、`save_to_db`、`max_concurrency` 等参数，一次请求处理多只股票并等待全部完成。
  - 要点：
    - 在路由内创建 `asyncio.Semaphore` 控制并发，依次调用 Task A 服务函数。
    - 响应包含每只股票的 `success`、`error`、`latency`、`retries` 等字段，并在完成后输出汇总日志。
    - 保持与现有鉴权/中间件一致，并更新 `/ai` 模块的 OpenAPI。
    - 失败列表落盘或返回 payload，便于 CLI/前端重试。
  - 参考文件：`stockaivo/routers/ai.py`, `stockaivo/schemas.py`
  - 交付物：新路由 + 请求/响应模型 + 集成测试（可 mock 结构化预测服务）。

- [ ] **Task C：结构化预测 Redis 待持久化机制**（依赖：Task A）
  - 目标：为结构化预测结果建立 Redis `PENDING_SAVE` 结构，复用 `get_pending_data_keys` 调度链路，支持批量入库。
  - 要点：在 `cache_manager.py` 扩展 `CacheType` 或新增 JSON 写入 API（命名建议 `prediction:pending:{ticker}`）；在 `database_writer.py`/`persist_pending_data` 增加消费逻辑，将结构化预测写入 `StockPrediction`；避免与行情缓存混用。
  - 参考文件：`stockaivo/cache_manager.py`, `stockaivo/database_writer.py`, `stockaivo/models.py`
  - 交付物：Redis 追加/去重函数 + DB 写入流程 + 日志。

- [ ] **Task D：限流与并发控制组件**（依赖：Task B）
  - 目标：实现多源限流与退避模块，串联批量接口中的新闻数据、AKShare、LLM 调用，防止击穿数据源。
  - 要点：
    - 在 `stockaivo/batch_prediction` 或 `stockaivo/utils` 新建 `rate_limiter.py`，支持令牌桶/滑动窗口配置。
    - 提供 `async with limiter.guard("ai_predict")`/`await limiter.acquire("tickertick")` 等调用方式，记录命中日志与退避策略。
    - 内置默认配置示例：
      ```python
      RATE_LIMITS = {
          "tickertick": {"requests": 10, "window": 60},
          "akshare": {"requests": 20, "window": 60},
          "ai_predict": {"requests": 5, "window": 60},
      }
      ```
    - 支持注入抖动延迟、错误重试（最多3次）与全局并发上限监控。
  - 参考文件：`stockaivo/data_service.py`（现有限流背景逻辑参考），`TODO.md` 本段。
  - 交付物：限流模块 + 单元测试（模拟 429 退避）。

- [ ] **Task E：测试与文档更新**（依赖：Task B、Task C、Task D）
  - 目标：补齐批量预测相关文档、自动化测试与 TODO 回填。
  - 要点：
    - 新增 PyTest 用例覆盖成功/失败/限流场景，可通过打桩模拟外部数据源。
    - 更新 `docs/operations/batch-prediction-guide.md` 与 README 示例，补充批量接口、限流配置、Redis 持久化说明。
    - 如实现 CLI/批处理脚本，追加使用章节或示例命令。
    - 同步 TODO 状态与任务归档，确保 CI 通过。
  - 参考文件：`tests/`, `docs/operations/`, `README.md`
  - 交付物：测试脚本 + 文档截图或示例 + TODO 状态勾选。

## 📦 里程碑交付物

- [ ] 结构化预测核心服务模块与单元测试（Task A）
- [ ] 批量结构化预测 API 与集成测试（Task B）
- [ ] Redis 待持久化通道与数据库写入流程（Task C）
- [ ] 限流/退避组件与监控日志（Task D）
- [ ] 更新后的文档、示例脚本（如 CLI）与 CI 报告（Task E）

## 🔭 后续可选工作

- [ ] **CLI 批量执行工具**：基于 Task B API 实现命令行入口（示例命令见 Task E），支持读取 `symbols.txt`、失败重试等。
- [ ] **请求队列扩展**：若需离线大批量处理，可在 Redis/数据库中实现优先级队列与断点续传，再由 APScheduler 消费。
- [ ] **实时监控与仪表盘**：在 `/cache-stats` 基础上扩展 API 或 Prometheus 指标，展示成功率、耗时、限流命中次数。
- [ ] **结果导出模板**：可选支持 JSON/CSV 批量导出与执行报告生成，满足运营或报表需求。

## 📚 数据字典来源更新

symbols 已由 `well-known US stocks.xlsx` 一次性导入数据库表 `well_known_stock_symbols`，导入流程与维护策略详见 `docs/operations/well-known-stock-import.md`，任务归档参考 `docs/task-history/2025-10-well-known-stock-import.md`。

## 🎓 技术决策记录

### 为什么选择异步架构？
- 充分利用IO等待时间（网络请求）
- 提升整体吞吐量（预计提升3-5倍）
- 更好的资源利用率

### 为什么需要多级限流？
- **数据源保护**: 避免IP被封禁
- **成本控制**: LLM调用有费用
- **稳定性**: 避免后端服务过载

### 推荐的并发配置
- **保守模式**: 并发=2, AI间隔=15秒
- **平衡模式**: 并发=3, AI间隔=12秒（推荐）
- **激进模式**: 并发=5, AI间隔=8秒

## 📚 延后任务参考

- 新闻情感分析缓存优化：`docs/task-history/2025-10-news-sentiment-cache-deferred.md`

---

**下一步行动**: 优先认领 Task A（抽象结构化预测核心服务），完成后即可解锁批量接口开发。
