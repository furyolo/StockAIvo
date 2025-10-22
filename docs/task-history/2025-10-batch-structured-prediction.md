# 任务归档：批量结构化预测异步调用系统

## 基本信息
- **任务名称**：批量结构化预测异步调用系统
- **完成日期**：2025-10-22（Asia/Shanghai）
- **负责人**：团队协作（基于 TODO.md 规划执行）
- **状态**：✅ 已完成

## 背景与目标
为 `/ai/predict-structured` 场景构建批量异步调用能力，确保在多数据源限流约束下仍可高效获取并持久化结构化预测结果。任务覆盖服务抽象、批量 API、Redis 中转、限流退避、文档与 CLI 工具，全链路打通批量预测闭环。

## 实施内容
1. **Task A：抽象核心服务**  
   将单票结构化预测逻辑下沉至 `stockaivo/ai/structured_prediction_service.py`，提供 `async run_structured_prediction(...)` 协程，并以 `tests/test_structured_prediction_service.py` 覆盖 LLM 打桩流程。
2. **Task B：批量结构化预测 API**  
   新增 `POST /ai/predict-structured/batch`，引入 `asyncio.Semaphore` 并发控制与统计汇总，响应返回每只股票的成功/失败详情；补充集成测试验证鉴权与限流路径。
3. **Task C：Redis 待持久化机制**  
   建立 `prediction:pending:{ticker}:{marketDate}:{targetDate}` 缓存键，完善去重与批量消费逻辑，并在 `StockPrediction` 模型落盘；新增对应单元测试。
4. **Task D：限流与并发控制组件**  
   在 `stockaivo/utils/rate_limiter.py` 实现多桶限流器，支持 Tickertick/AkShare/AI 频控、指数退避与全局并发约束；以 `tests/test_rate_limiter.py` 覆盖等待与退避行为。
5. **Task E：测试与文档更新**  
   扩充成功/失败/限流测试场景，更新 `docs/operations/batch-prediction-guide.md` 与 README，记录使用步骤、限流配置及 Redis 持久化说明。
6. **Task F：CLI 批量预测脚本**  
   提供 `stockaivo/scripts/bulk_predict_from_db.py`，按批读取 `well_known_stock_symbols`，调用批量接口执行预测，默认并发 5、失败输出 JSON/CSV，并补充脚本级单元测试与文档。
7. **Task G：批次清单与进度断点**  
   增加 manifest 恢复模式与 `execution_mode=data_collection_only`，支持数据采集跳过新闻及断点续跑，详见运维文档 5.6 节。

## 验收与验证
- `uv run pytest` 相关用例（结构化服务、限流器、批量 API、CLI）全部通过。
- 批量接口兼容现有 FastAPI 鉴权与中间件；日志包含耗时、退避、失败详情。
- Redis Pending 缓存与数据库批写一致，通过干跑与实写测试验证幂等性。
- 文档与 README 已同步更新示例命令、配置说明与故障排查。

## 成果物列表
- 核心服务：`stockaivo/ai/structured_prediction_service.py`
- 批量路由与模型：`stockaivo/routers/ai.py`, `stockaivo/schemas.py`
- 缓存与持久化：`stockaivo/cache_manager.py`, `stockaivo/database_writer.py`, `stockaivo/models.py`
- 限流组件：`stockaivo/utils/rate_limiter.py`
- CLI 脚本：`stockaivo/scripts/bulk_predict_from_db.py`
- 文档：`docs/operations/batch-prediction-guide.md`, `README.md`
- 测试：`tests/test_structured_prediction_service.py`, `tests/test_rate_limiter.py`, `tests/test_bulk_predict_from_db.py`

## 后续建议
- 持续监控限流命中率与退避日志，调整默认并发与速率配置。
- 评估将批量预测结果写入外部监控或告警系统，便于追踪失败分布。
- data-collection-only 模式可与定时任务结合，完善数据采集调度策略。
