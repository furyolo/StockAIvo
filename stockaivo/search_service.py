"""
股票搜索服务模块

本模块实现股票名称的模糊搜索功能，支持从第一个字符开始的实时搜索。
包括数据库查询、结果排序、缓存集成和性能优化。
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, or_, func, case
from sqlalchemy.orm import Session

from .models import UsStocksName
from .database import get_db
from .cache_manager import save_search_results, get_search_results
from .schemas import SearchResult

# 配置日志
logger = logging.getLogger(__name__)


def calculate_relevance_score(query: str, symbol: str, name: str, cname: Optional[str] = None) -> float:
    """
    计算搜索结果的相关性评分

    Args:
        query: 搜索查询词
        symbol: 股票代码
        name: 英文公司名称
        cname: 中文公司名称（可选）

    Returns:
        float: 相关性评分 (0.0-1.0)
    """
    query_lower = query.lower().strip()
    symbol_lower = symbol.lower()
    name_lower = name.lower()
    cname_lower = cname.lower() if cname else ""

    # Symbol 精确匹配得分最高
    if query_lower == symbol_lower:
        return 1.0

    # Symbol 前缀匹配得分第二高
    if symbol_lower.startswith(query_lower):
        return 0.95

    # Name/Cname 精确匹配得分第三高
    if query_lower == name_lower or (cname and query_lower == cname_lower):
        return 0.9

    # Name/Cname 前缀匹配得分第四高
    if name_lower.startswith(query_lower) or (cname and cname_lower.startswith(query_lower)):
        return 0.8

    # Symbol 包含匹配
    if query_lower in symbol_lower:
        return 0.7

    # Name/Cname 包含匹配得分中等
    if query_lower in name_lower or (cname and query_lower in cname_lower):
        return 0.6

    # 单词边界匹配
    name_words = name_lower.split()
    cname_words = cname_lower.split() if cname else []

    for word in name_words + cname_words:
        if word.startswith(query_lower):
            return 0.5
        if query_lower in word:
            return 0.4

    # 默认最低分
    return 0.3


def search_stocks_by_name(
    query: str,
    limit: int = 10,
    offset: int = 0,
    use_cache: bool = True
) -> Tuple[List[Dict[str, Any]], int]:
    """
    根据公司名称模糊搜索股票
    
    Args:
        query: 搜索查询词
        limit: 返回结果数量限制
        offset: 分页偏移量
        use_cache: 是否使用缓存
        
    Returns:
        Tuple[List[Dict[str, Any]], int]: (搜索结果列表, 总结果数量)
    """
    if not query or not query.strip():
        logger.warning("搜索查询词为空")
        return [], 0
    
    query = query.strip()
    
    # 尝试从缓存获取结果
    if use_cache:
        cached_results = get_search_results(query, limit, offset)
        if cached_results is not None:
            logger.info(f"从缓存获取搜索结果: {query}, 数量: {len(cached_results)}")
            # 缓存中应该包含总数信息，这里简化处理
            return cached_results, len(cached_results)
    
    # 缓存未命中，查询数据库
    try:
        db = next(get_db())
        
        # 构建模糊搜索查询
        search_pattern = f"%{query}%"

        # 使用 ILIKE 进行不区分大小写的模糊匹配，包含 symbol 字段
        search_condition = or_(
            UsStocksName.symbol.ilike(search_pattern),
            UsStocksName.name.ilike(search_pattern),
            UsStocksName.cname.ilike(search_pattern)
        )
        
        # 构建排序逻辑：Symbol精确匹配 > Symbol前缀匹配 > Name/Cname精确匹配 > Name/Cname前缀匹配 > 包含匹配
        # 使用 CASE WHEN 进行数据库级别的排序
        order_score = case(
            # Symbol 精确匹配（最高优先级）
            (func.lower(UsStocksName.symbol) == query.lower(), 6),
            # Symbol 前缀匹配（第二优先级）
            (func.lower(UsStocksName.symbol).like(f"{query.lower()}%"), 5),
            # Name/Cname 精确匹配（第三优先级）
            (or_(
                func.lower(UsStocksName.name) == query.lower(),
                func.lower(UsStocksName.cname) == query.lower()
            ), 4),
            # Name/Cname 前缀匹配（第四优先级）
            (or_(
                func.lower(UsStocksName.name).like(f"{query.lower()}%"),
                func.lower(UsStocksName.cname).like(f"{query.lower()}%")
            ), 3),
            # 包含匹配（最低优先级）
            (search_condition, 2),
            else_=1
        )
        
        # 查询总数
        count_stmt = select(func.count(UsStocksName.symbol)).where(search_condition)
        total_count = db.execute(count_stmt).scalar() or 0
        
        # 查询结果
        stmt = (
            select(UsStocksName)
            .where(search_condition)
            .order_by(order_score.desc(), UsStocksName.symbol)
            .limit(limit)
            .offset(offset)
        )
        
        result = db.execute(stmt).scalars().all()
        
        # 转换为字典格式并计算相关性评分
        search_results = []
        for stock in result:
            relevance_score = calculate_relevance_score(query, stock.symbol, stock.name, stock.cname)
            search_results.append({
                'symbol': stock.symbol,
                'name': stock.name,
                'cname': stock.cname,
                'relevance_score': relevance_score
            })
        
        # 按相关性评分重新排序（数据库排序 + Python 精确排序）
        search_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        logger.info(f"数据库搜索完成: {query}, 总数: {total_count}, 返回: {len(search_results)}")
        
        # 保存到缓存
        if use_cache and search_results:
            try:
                save_search_results(query, search_results, limit, offset)
            except Exception as e:
                logger.warning(f"保存搜索结果到缓存失败: {e}")
        
        return search_results, total_count
        
    except Exception as e:
        logger.error(f"搜索股票时发生错误: {e}")
        return [], 0
    finally:
        if 'db' in locals():
            db.close()


def search_stocks_with_pagination(
    query: str,
    page: int = 1,
    page_size: int = 10,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    分页搜索股票
    
    Args:
        query: 搜索查询词
        page: 页码（从1开始）
        page_size: 每页大小
        use_cache: 是否使用缓存
        
    Returns:
        Dict[str, Any]: 包含搜索结果和分页信息的字典
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10
    
    offset = (page - 1) * page_size
    
    results, total_count = search_stocks_by_name(
        query=query,
        limit=page_size,
        offset=offset,
        use_cache=use_cache
    )
    
    total_pages = (total_count + page_size - 1) // page_size
    has_more = page < total_pages
    
    return {
        'query': query,
        'total_count': total_count,
        'results': results,
        'has_more': has_more,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    }


def get_stock_suggestions(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    获取股票搜索建议（快速搜索，仅返回最相关的结果）
    
    Args:
        query: 搜索查询词
        limit: 建议数量限制
        
    Returns:
        List[Dict[str, Any]]: 搜索建议列表
    """
    if not query or len(query.strip()) < 1:
        return []
    
    results, _ = search_stocks_by_name(
        query=query.strip(),
        limit=limit,
        offset=0,
        use_cache=True
    )
    
    # 只返回相关性评分较高的结果
    return [result for result in results if result['relevance_score'] >= 0.5]
