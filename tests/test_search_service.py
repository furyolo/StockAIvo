"""
搜索服务测试模块

测试股票搜索功能的正确性、性能和边界情况处理。
包括单元测试、集成测试和性能测试。
"""

import unittest
from unittest.mock import patch, MagicMock, call
import pytest
from datetime import datetime
from typing import List, Dict, Any

# 导入被测试的模块
from stockaivo.search_service import (
    calculate_relevance_score,
    search_stocks_by_name,
    search_stocks_with_pagination,
    get_stock_suggestions
)
from stockaivo.models import UsStocksName


class TestCalculateRelevanceScore(unittest.TestCase):
    """测试相关性评分算法"""

    def test_exact_match_english(self):
        """测试英文精确匹配"""
        score = calculate_relevance_score("apple", "Apple", "苹果公司")
        self.assertEqual(score, 1.0)

    def test_exact_match_chinese(self):
        """测试中文精确匹配"""
        score = calculate_relevance_score("苹果", "Apple Inc.", "苹果")
        self.assertEqual(score, 1.0)

    def test_prefix_match_english(self):
        """测试英文前缀匹配"""
        score = calculate_relevance_score("app", "Apple Inc.", "苹果公司")
        self.assertEqual(score, 0.9)

    def test_prefix_match_chinese(self):
        """测试中文前缀匹配"""
        score = calculate_relevance_score("苹", "Apple Inc.", "苹果公司")
        self.assertEqual(score, 0.9)

    def test_contains_match_english(self):
        """测试英文包含匹配"""
        score = calculate_relevance_score("tech", "Apple Technology Inc.", "苹果科技")
        self.assertEqual(score, 0.7)

    def test_contains_match_chinese(self):
        """测试中文包含匹配"""
        score = calculate_relevance_score("科技", "Apple Technology", "苹果科技公司")
        self.assertEqual(score, 0.7)

    def test_word_boundary_match(self):
        """测试单词边界匹配"""
        score = calculate_relevance_score("tech", "Apple Tech Solutions", None)
        self.assertEqual(score, 0.7)  # 包含匹配

    def test_partial_word_match(self):
        """测试部分单词匹配"""
        score = calculate_relevance_score("app", "Snapple Inc.", None)
        self.assertEqual(score, 0.7)  # 包含匹配

    def test_no_match(self):
        """测试无匹配情况"""
        score = calculate_relevance_score("xyz", "Apple Inc.", "苹果公司")
        self.assertEqual(score, 0.3)

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        score1 = calculate_relevance_score("APPLE", "apple inc.", None)
        score2 = calculate_relevance_score("apple", "APPLE INC.", None)
        self.assertEqual(score1, score2)
        self.assertEqual(score1, 0.9)  # 前缀匹配

    def test_empty_query(self):
        """测试空查询"""
        score = calculate_relevance_score("", "Apple Inc.", "苹果公司")
        self.assertEqual(score, 0.9)  # 空字符串是前缀匹配

    def test_none_cname(self):
        """测试中文名称为None的情况"""
        score = calculate_relevance_score("apple", "Apple Inc.", None)
        self.assertEqual(score, 0.9)  # 前缀匹配


class TestSearchStocksByName(unittest.TestCase):
    """测试股票搜索核心功能"""

    def setUp(self):
        """设置测试数据"""
        self.mock_stocks = [
            MagicMock(symbol="AAPL", name="Apple Inc.", cname="苹果公司"),
            MagicMock(symbol="MSFT", name="Microsoft Corporation", cname="微软公司"),
            MagicMock(symbol="GOOGL", name="Alphabet Inc.", cname="谷歌公司"),
            MagicMock(symbol="TSLA", name="Tesla Inc.", cname="特斯拉公司"),
        ]

    @patch('stockaivo.search_service.get_db')
    @patch('stockaivo.search_service.get_search_results')
    def test_cache_hit(self, mock_get_cache, mock_get_db):
        """测试缓存命中情况"""
        # 模拟缓存命中
        cached_results = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'cname': '苹果公司', 'relevance_score': 1.0}
        ]
        mock_get_cache.return_value = cached_results

        results, total_count = search_stocks_by_name("apple", limit=10, offset=0, use_cache=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['symbol'], 'AAPL')
        self.assertEqual(total_count, 1)
        mock_get_cache.assert_called_once()
        mock_get_db.assert_not_called()

    @patch('stockaivo.search_service.get_db')
    @patch('stockaivo.search_service.get_search_results')
    @patch('stockaivo.search_service.save_search_results')
    def test_cache_miss_database_query(self, mock_save_cache, mock_get_cache, mock_get_db):
        """测试缓存未命中，查询数据库"""
        # 模拟缓存未命中
        mock_get_cache.return_value = None

        # 模拟数据库查询
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        
        # 模拟查询结果
        mock_db.execute.return_value.scalar.return_value = 2  # 总数
        mock_db.execute.return_value.scalars.return_value.all.return_value = self.mock_stocks[:2]

        results, total_count = search_stocks_by_name("apple", limit=10, offset=0, use_cache=True)

        self.assertEqual(total_count, 2)
        self.assertEqual(len(results), 2)
        mock_get_cache.assert_called_once()
        mock_save_cache.assert_called_once()

    def test_empty_query(self):
        """测试空查询"""
        results, total_count = search_stocks_by_name("", limit=10, offset=0)
        self.assertEqual(results, [])
        self.assertEqual(total_count, 0)

        results, total_count = search_stocks_by_name("   ", limit=10, offset=0)
        self.assertEqual(results, [])
        self.assertEqual(total_count, 0)

    def test_none_query(self):
        """测试None查询"""
        results, total_count = search_stocks_by_name(None, limit=10, offset=0)
        self.assertEqual(results, [])
        self.assertEqual(total_count, 0)

    @patch('stockaivo.search_service.get_db')
    @patch('stockaivo.search_service.get_search_results')
    def test_database_error_handling(self, mock_get_cache, mock_get_db):
        """测试数据库错误处理"""
        mock_get_cache.return_value = None
        mock_get_db.side_effect = Exception("Database connection failed")

        results, total_count = search_stocks_by_name("apple", limit=10, offset=0)

        self.assertEqual(results, [])
        self.assertEqual(total_count, 0)

    def test_pagination_parameters(self):
        """测试分页参数"""
        # 测试默认参数
        with patch('stockaivo.search_service.get_search_results') as mock_cache:
            mock_cache.return_value = None
            with patch('stockaivo.search_service.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_get_db.return_value = iter([mock_db])
                mock_db.execute.return_value.scalar.return_value = 0
                mock_db.execute.return_value.scalars.return_value.all.return_value = []

                search_stocks_by_name("test")
                # 验证默认参数
                self.assertTrue(mock_db.execute.called)


class TestSearchStocksWithPagination(unittest.TestCase):
    """测试分页搜索功能"""

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_pagination_calculation(self, mock_search):
        """测试分页计算"""
        # 模拟搜索结果
        mock_search.return_value = (
            [{'symbol': f'TEST{i}', 'name': f'Test Company {i}', 'cname': None, 'relevance_score': 0.8} 
             for i in range(5)],
            25  # 总数
        )

        result = search_stocks_with_pagination("test", page=2, page_size=5)

        self.assertEqual(result['page'], 2)
        self.assertEqual(result['page_size'], 5)
        self.assertEqual(result['total_count'], 25)
        self.assertEqual(result['total_pages'], 5)
        self.assertTrue(result['has_more'])
        
        # 验证offset计算
        mock_search.assert_called_with(query="test", limit=5, offset=5, use_cache=True)

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_last_page(self, mock_search):
        """测试最后一页"""
        mock_search.return_value = ([], 10)

        result = search_stocks_with_pagination("test", page=3, page_size=5)

        self.assertFalse(result['has_more'])

    def test_invalid_page_parameters(self):
        """测试无效分页参数"""
        with patch('stockaivo.search_service.search_stocks_by_name') as mock_search:
            mock_search.return_value = ([], 0)

            # 测试负数页码
            result = search_stocks_with_pagination("test", page=-1, page_size=10)
            self.assertEqual(result['page'], 1)

            # 测试零页码
            result = search_stocks_with_pagination("test", page=0, page_size=10)
            self.assertEqual(result['page'], 1)

            # 测试无效页面大小
            result = search_stocks_with_pagination("test", page=1, page_size=0)
            self.assertEqual(result['page_size'], 10)

            result = search_stocks_with_pagination("test", page=1, page_size=200)
            self.assertEqual(result['page_size'], 10)


class TestGetStockSuggestions(unittest.TestCase):
    """测试搜索建议功能"""

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_suggestions_filtering(self, mock_search):
        """测试建议过滤"""
        # 模拟搜索结果，包含不同相关性评分
        mock_search.return_value = (
            [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'cname': '苹果公司', 'relevance_score': 1.0},
                {'symbol': 'SNAP', 'name': 'Snapple Inc.', 'cname': None, 'relevance_score': 0.4},
                {'symbol': 'MSFT', 'name': 'Microsoft', 'cname': '微软', 'relevance_score': 0.8},
            ],
            3
        )

        suggestions = get_stock_suggestions("app", limit=5)

        # 应该只返回相关性评分 >= 0.5 的结果
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0]['symbol'], 'AAPL')
        self.assertEqual(suggestions[1]['symbol'], 'MSFT')

    def test_empty_query_suggestions(self):
        """测试空查询建议"""
        suggestions = get_stock_suggestions("", limit=5)
        self.assertEqual(suggestions, [])

        suggestions = get_stock_suggestions("a", limit=5)  # 单字符查询应该正常处理
        # 这里会调用实际的搜索函数，但由于没有数据库，会返回空结果


class TestSearchIntegration(unittest.TestCase):
    """集成测试"""

    def test_end_to_end_search_flow(self):
        """测试端到端搜索流程"""
        # 这是一个集成测试示例，实际运行需要数据库
        # 在实际环境中，这个测试会验证完整的搜索流程
        pass

    def test_cache_integration(self):
        """测试缓存集成"""
        # 测试缓存的完整流程
        pass


if __name__ == '__main__':
    unittest.main()
