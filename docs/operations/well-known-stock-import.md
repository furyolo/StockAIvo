# Well-known US Stocks 数据字典导入指引

本文档介绍如何将 `well-known US stocks.xlsx` 中的 `symbol`、`name` 数据导入到数据库的 `well_known_stock_symbols` 表中，以及常见问题与回滚方案。

## 前提条件
- 已完成数据库迁移，数据库中存在 `well_known_stock_symbols` 表（执行 `uv run database_migrations/create_well_known_stock_symbols.py`）。
- `.env` 中的 `DATABASE_URL` 指向可写的 PostgreSQL 实例。
- Excel 文件位于仓库根目录 `well-known US stocks.xlsx`，如需使用其他文件，可通过参数指定。

## 导入步骤
1. **干跑检查（推荐）**
   ```bash
   uv run python -m stockaivo.scripts.import_well_known_symbols --dry-run
   ```
   - 仅解析 Excel 并打印前 10 条数据，不对数据库做任何写入。

2. **实际导入**
   ```bash
   uv run python -m stockaivo.scripts.import_well_known_symbols
   ```
   - 默认读取仓库根目录的 Excel。
   - 若需指定路径：
     ```bash
     uv run python -m stockaivo.scripts.import_well_known_symbols --excel-path path/to/file.xlsx
     ```

3. **结果验证**
   - 查看脚本输出的“成功插入/更新数量”。
   - 可在 psql 中执行 `SELECT * FROM well_known_stock_symbols LIMIT 10;` 验证入库结果。

## 常见问题
- **提示缺少 symbol/name 列**：确认 Excel 列名准确（不区分大小写），无多余空格。
- **数据库连接失败**：检查 `.env` 或当前 Shell 的数据库环境变量，确保网络可达与权限正确。
- **重复执行是否安全**：脚本采用 UPSERT 逻辑并保留已有名称，重复运行不会产生重复记录。
- **名称为空的处理**：Excel 中缺失的名称会以 `NULL` 存储，脚本在冲突更新时不会覆盖已有名称。

## 回滚方案
- 如需清空导入结果，可执行：
  ```sql
  DELETE FROM well_known_stock_symbols;
  ```
- 若仅需移除特定条目：
  ```sql
  DELETE FROM well_known_stock_symbols WHERE symbol = 'AAPL';
  ```
- 若需要重新建表，可重新运行 `cd backend && python database_migrations/create_well_known_stock_symbols.py`（脚本包含触发器创建逻辑）。

## 后续维护建议
- Excel 更新后重复执行导入即可同步变更。
- 若新增字段（如行业、别名），需先更新迁移脚本/模型，再重新导入。
