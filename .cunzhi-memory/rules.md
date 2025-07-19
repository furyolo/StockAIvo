# 开发规范和规则

- 修复了周线数据默认日期范围计算中的周末处理逻辑错误。当当前日期是周末时，现在正确地从本周范围内查找最后一个交易日，而不是错误地查找上周的交易日。修复确保周末时使用本周五作为结束日期，而不是上周五。
- 删除了 stocks 表及其关联字段。移除了 Stock 模型类、所有价格表中的外键引用（ForeignKey('stocks.ticker')）、关系映射（relationship），以及 database_writer.py 中的 _prepare_stock_data 和 _upsert_stock_info 方法。现在价格表直接使用 ticker 字段作为主键，不再依赖 stocks 表。
