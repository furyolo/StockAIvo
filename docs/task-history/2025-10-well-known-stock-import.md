# 任务归档：Well-known US Stocks 数据入库

## 基本信息
- **任务名称**：Well-known US Stocks 数据入库
- **完成日期**：2025-10-13（Asia/Shanghai）
- **负责人**：团队协作（通过 TODO.md 规划）
- **状态**：✅ 已完成

## 背景与目标
TODO.md 中新增任务要求将 `well-known US stocks.xlsx` 的 `symbol` / `name` 列一次性持久化，以供后续功能引用，避免重复解析 Excel。

## 实施内容
1. 新增 ORM 模型 `WellKnownStockSymbol` 与建表迁移脚本 `database_migrations/create_well_known_stock_symbols.py`，包含 `symbol` 主键、`name` 可空、`created_at/updated_at` 字段。
2. 开发导入脚本 `stockaivo/scripts/import_well_known_symbols.py`，支持干跑、路径参数和 UPSERT 幂等写入。
3. 编写测试 `tests/test_well_known_stock_symbols.py`，覆盖数据清洗、UPSERT SQL 生成以及干跑/实写流程。
4. 输出运维文档 `docs/operations/well-known-stock-import.md` 说明执行步骤、故障排查与回滚策略。

## 验收与验证
- `uv run pytest -k well_known_stock_symbols` 全部通过。
- 导入脚本支持重复执行无副作用，空名称字段会以 `NULL` 存储。
- 迁移脚本可独立运行，确保触发器与表结构一致。

## 后续建议
- 若 Excel 更新或新增列，先调整模型与迁移，再重跑导入。
- 若需将 `symbol` 用于搜索/联动，可在业务逻辑中直接查询 `well_known_stock_symbols` 表。
