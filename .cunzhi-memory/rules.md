# 开发规范和规则

- 修复了周线数据默认日期范围计算中的周末处理逻辑错误。当当前日期是周末时，现在正确地从本周范围内查找最后一个交易日，而不是错误地查找上周的交易日。修复确保周末时使用本周五作为结束日期，而不是上周五。
- 删除了 stocks 表及其关联字段。移除了 Stock 模型类、所有价格表中的外键引用（ForeignKey('stocks.ticker')）、关系映射（relationship），以及 database_writer.py 中的 _prepare_stock_data 和 _upsert_stock_info 方法。现在价格表直接使用 ticker 字段作为主键，不再依赖 stocks 表。
- 股票新闻数据获取功能设计：使用AKShare的stock_news_em()函数，通过us_stocks_name表的cname字段作为查询关键词，删除"公司"和"集团"等字样，仅保留最近3天数据，今日数据每次重新获取，历史数据可缓存。数据字段需要中英文映射，删除"文章来源"和"新闻链接"字段。
- stock_news表字段顺序为ticker、keyword、title、content、publish_time、created_at、updated_at，数据按发布时间逆序排列（最新在前）。不要生成总结性文档、测试脚本，不要编译或运行代码。
- 类型错误修复完成：stockaivo/ai/orchestrator.py 和 stockaivo/search_service.py 以及 stockaivo/database.py 的所有类型错误已修复。主要修复包括：添加完整类型导入、函数返回类型注解、SQLAlchemy 列类型转换、全局变量类型声明等。
- AI代理模型配置：默认模型为gemini-2.5-flash，technical_analysis_agent和synthesis_agent使用gemini-2.5-pro。模型配置通过环境变量管理，支持按代理名称选择特定模型。
- AI模型配置已重新设计：使用AI_前缀的统一命名约定，AI_DEFAULT_MODEL为全局默认，AI_TECHNICAL_ANALYSIS_MODEL和AI_SYNTHESIS_MODEL为特定代理覆盖，AI_OPENAI_FALLBACK_MODEL和AI_GEMINI_FALLBACK_MODEL为服务级回退模型。移除了旧的OPENAI_MODEL_NAME和GEMINI_MODEL_NAME依赖。
- AI模型配置已简化：只使用AI_DEFAULT_MODEL作为全局默认模型(gemini-2.5-flash)，AI_TECHNICAL_ANALYSIS_MODEL和AI_SYNTHESIS_MODEL等代理特定配置。如果代理特定配置为空，则使用全局默认模型。移除了复杂的服务级回退模型配置。
- 用户明确要求：不要生成总结性Markdown文档，不要生成测试脚本，不要编译，不要运行代码。用户会自己处理这些操作。
- 用户要求实现三个独立分析代理（技术分析、基本面分析、新闻情感分析）的并行执行，以提高性能。需要保持当前的流式用户体验，同时支持多个代理同时流式输出到前端。
