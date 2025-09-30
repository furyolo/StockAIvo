"""
StockAIvo - 智能美股数据与分析平台

这是一个集成了AI分析功能的股票数据平台，提供：
- 美股数据获取和存储
- 技术分析和基本面分析
- AI驱动的投资建议
- 实时数据流和缓存管理
"""

# 在所有模块导入之前配置UTC日志，确保时区一致性
from stockaivo.logging_config import configure_utc_logging
configure_utc_logging()

__version__ = "1.0.0"
__author__ = "StockAIvo Team"
