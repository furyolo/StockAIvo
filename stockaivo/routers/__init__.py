"""
StockAIvo - 路由模块
包含所有API路由定义
"""

from .stocks import router as stocks_router
from .ai import router as ai_router
from .search import router as search_router

__all__ = ["stocks_router", "ai_router", "search_router"]