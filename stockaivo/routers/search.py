"""
StockAIvo - 股票搜索API路由
提供股票名称模糊搜索的RESTful接口
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..search_service import search_stocks_with_pagination, get_stock_suggestions
from ..schemas import SearchResponse, SearchResult, ErrorResponse

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/search",
    tags=["股票搜索"],
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    }
)


def validate_search_query(query: str) -> str:
    """验证和标准化搜索查询词"""
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索查询词不能为空"
        )
    
    query = query.strip()
    if len(query) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索查询词长度至少为1个字符"
        )
    
    if len(query) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索查询词长度不能超过100个字符"
        )
    
    return query


def validate_pagination_params(limit: int, offset: int) -> tuple[int, int]:
    """验证分页参数"""
    if limit < 1:
        limit = 10
    elif limit > 50:
        limit = 50
    
    if offset < 0:
        offset = 0
    
    return limit, offset


@router.get("/stocks", response_model=SearchResponse)
async def search_stocks(
    q: str = Query(..., description="搜索查询词", min_length=1, max_length=100),
    limit: int = Query(10, description="返回结果数量限制", ge=1, le=50),
    offset: int = Query(0, description="分页偏移量", ge=0),
    use_cache: bool = Query(True, description="是否使用缓存")
):
    """
    搜索股票
    
    根据公司名称（英文或中文）模糊搜索股票，支持实时搜索和分页。
    
    Args:
        q: 搜索查询词，支持英文和中文公司名称
        limit: 返回结果数量限制，默认10，最大50
        offset: 分页偏移量，默认0
        use_cache: 是否使用缓存，默认True
        
    Returns:
        SearchResponse: 包含搜索结果的响应
    """
    try:
        # 验证查询参数
        query = validate_search_query(q)
        limit, offset = validate_pagination_params(limit, offset)
        
        logger.info(f"股票搜索请求: query='{query}', limit={limit}, offset={offset}, use_cache={use_cache}")
        
        # 调用搜索服务
        search_result = search_stocks_with_pagination(
            query=query,
            page=(offset // limit) + 1,
            page_size=limit,
            use_cache=use_cache
        )
        
        # 转换为SearchResult对象
        search_results = [
            SearchResult(
                symbol=result['symbol'],
                name=result['name'],
                cname=result['cname'],
                relevance_score=result['relevance_score']
            )
            for result in search_result['results']
        ]
        
        # 构建响应
        response = SearchResponse(
            query=query,
            total_count=search_result['total_count'],
            results=search_results,
            has_more=search_result['has_more'],
            timestamp=datetime.now()
        )
        
        logger.info(f"搜索完成: query='{query}', 总数={search_result['total_count']}, 返回={len(search_results)}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"股票搜索失败: query='{q}', error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )


@router.get("/stocks/suggestions")
async def get_search_suggestions(
    q: str = Query(..., description="搜索查询词", min_length=1, max_length=100),
    limit: int = Query(5, description="建议数量限制", ge=1, le=10)
):
    """
    获取搜索建议
    
    快速返回最相关的搜索建议，用于自动完成功能。
    
    Args:
        q: 搜索查询词
        limit: 建议数量限制，默认5，最大10
        
    Returns:
        List[SearchResult]: 搜索建议列表
    """
    try:
        # 验证查询参数
        query = validate_search_query(q)
        
        if limit < 1:
            limit = 5
        elif limit > 10:
            limit = 10
        
        logger.info(f"搜索建议请求: query='{query}', limit={limit}")
        
        # 调用搜索建议服务
        suggestions = get_stock_suggestions(query, limit)
        
        # 转换为SearchResult对象
        search_results = [
            SearchResult(
                symbol=result['symbol'],
                name=result['name'],
                cname=result['cname'],
                relevance_score=result['relevance_score']
            )
            for result in suggestions
        ]
        
        logger.info(f"搜索建议完成: query='{query}', 返回={len(search_results)}")
        return search_results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取搜索建议失败: query='{q}', error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取搜索建议失败: {str(e)}"
        )


@router.get("/health")
async def search_health_check():
    """
    搜索服务健康检查
    
    Returns:
        dict: 健康状态信息
    """
    try:
        # 简单的健康检查，可以扩展为检查数据库连接、缓存状态等
        return {
            "status": "healthy",
            "service": "search",
            "timestamp": datetime.now().isoformat(),
            "message": "搜索服务运行正常"
        }
    except Exception as e:
        logger.error(f"搜索服务健康检查失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索服务健康检查失败: {str(e)}"
        )
