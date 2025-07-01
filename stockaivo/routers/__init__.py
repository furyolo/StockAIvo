"""
StockAIvo - 路由模块
包含所有API路由定义
"""

from .stocks import router as stocks_router

__all__ = ["stocks_router"]