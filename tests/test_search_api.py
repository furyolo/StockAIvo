"""
搜索API测试模块

测试搜索API端点的功能、参数验证和错误处理。
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

# 导入主应用
from main import app

# 创建测试客户端
client = TestClient(app)


class TestSearchStocksAPI:
    """测试股票搜索API端点"""

    @patch('stockaivo.routers.search.search_stocks_with_pagination')
    def test_search_stocks_success(self, mock_search):
        """测试成功的搜索请求"""
        # 模拟搜索结果
        mock_search.return_value = {
            'query': 'apple',
            'results': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'cname': '苹果公司', 'relevance_score': 1.0}
            ],
            'total_count': 1,
            'page': 1,
            'page_size': 10,
            'total_pages': 1,
            'has_more': False,
            'timestamp': '2025-07-02T12:00:00'
        }

        response = client.get("/search/stocks?q=apple")

        assert response.status_code == 200
        data = response.json()
        assert data['query'] == 'apple'
        assert len(data['results']) == 1
        assert data['results'][0]['symbol'] == 'AAPL'
        assert data['total_count'] == 1
        mock_search.assert_called_once_with(query='apple', page=1, page_size=10, use_cache=True)

    def test_search_stocks_with_pagination(self):
        """测试带分页参数的搜索"""
        with patch('stockaivo.routers.search.search_stocks_with_pagination') as mock_search:
            mock_search.return_value = {
                'query': 'tech',
                'results': [],
                'total_count': 0,
                'page': 2,
                'page_size': 5,
                'total_pages': 0,
                'has_more': False,
                'timestamp': '2025-07-02T12:00:00'
            }

            response = client.get("/search/stocks?q=tech&page=2&page_size=5")

            assert response.status_code == 200
            data = response.json()
            assert data['page'] == 2
            assert data['page_size'] == 5
            mock_search.assert_called_once_with(query='tech', page=2, page_size=5, use_cache=True)

    def test_search_stocks_missing_query(self):
        """测试缺少查询参数"""
        response = client.get("/search/stocks")

        assert response.status_code == 422  # Validation error

    def test_search_stocks_empty_query(self):
        """测试空查询参数"""
        response = client.get("/search/stocks?q=")

        assert response.status_code == 400
        data = response.json()
        assert "查询参数不能为空" in data['detail']

    def test_search_stocks_whitespace_query(self):
        """测试只包含空格的查询"""
        response = client.get("/search/stocks?q=   ")

        assert response.status_code == 400
        data = response.json()
        assert "查询参数不能为空" in data['detail']

    def test_search_stocks_invalid_page(self):
        """测试无效页码"""
        response = client.get("/search/stocks?q=apple&page=0")

        assert response.status_code == 400
        data = response.json()
        assert "页码必须大于0" in data['detail']

        response = client.get("/search/stocks?q=apple&page=-1")

        assert response.status_code == 400

    def test_search_stocks_invalid_page_size(self):
        """测试无效页面大小"""
        response = client.get("/search/stocks?q=apple&page_size=0")

        assert response.status_code == 400
        data = response.json()
        assert "页面大小必须在1-100之间" in data['detail']

        response = client.get("/search/stocks?q=apple&page_size=101")

        assert response.status_code == 400

    @patch('stockaivo.routers.search.search_stocks_with_pagination')
    def test_search_stocks_service_error(self, mock_search):
        """测试服务层错误"""
        mock_search.side_effect = Exception("Database connection failed")

        response = client.get("/search/stocks?q=apple")

        assert response.status_code == 500
        data = response.json()
        assert "搜索服务暂时不可用" in data['detail']

    def test_search_stocks_special_characters(self):
        """测试特殊字符查询"""
        with patch('stockaivo.routers.search.search_stocks_with_pagination') as mock_search:
            mock_search.return_value = {
                'query': 'AT&T',
                'results': [],
                'total_count': 0,
                'page': 1,
                'page_size': 10,
                'total_pages': 0,
                'has_more': False,
                'timestamp': '2025-07-02T12:00:00'
            }

            response = client.get("/search/stocks?q=AT%26T")  # URL encoded &

            assert response.status_code == 200
            data = response.json()
            assert data['query'] == 'AT&T'

    def test_search_stocks_unicode_characters(self):
        """测试Unicode字符查询"""
        with patch('stockaivo.routers.search.search_stocks_with_pagination') as mock_search:
            mock_search.return_value = {
                'query': '苹果',
                'results': [],
                'total_count': 0,
                'page': 1,
                'page_size': 10,
                'total_pages': 0,
                'has_more': False,
                'timestamp': '2025-07-02T12:00:00'
            }

            response = client.get("/search/stocks?q=苹果")

            assert response.status_code == 200
            data = response.json()
            assert data['query'] == '苹果'


class TestSearchSuggestionsAPI:
    """测试搜索建议API端点"""

    @patch('stockaivo.routers.search.get_stock_suggestions')
    def test_suggestions_success(self, mock_suggestions):
        """测试成功的建议请求"""
        mock_suggestions.return_value = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'cname': '苹果公司', 'relevance_score': 1.0},
            {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'cname': '微软公司', 'relevance_score': 0.8}
        ]

        response = client.get("/search/stocks/suggestions?q=app")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]['symbol'] == 'AAPL'
        assert data[1]['symbol'] == 'MSFT'
        mock_suggestions.assert_called_once_with(query='app', limit=5)

    def test_suggestions_with_limit(self):
        """测试带限制参数的建议"""
        with patch('stockaivo.routers.search.get_stock_suggestions') as mock_suggestions:
            mock_suggestions.return_value = []

            response = client.get("/search/stocks/suggestions?q=test&limit=3")

            assert response.status_code == 200
            mock_suggestions.assert_called_once_with(query='test', limit=3)

    def test_suggestions_missing_query(self):
        """测试缺少查询参数"""
        response = client.get("/search/stocks/suggestions")

        assert response.status_code == 422  # Validation error

    def test_suggestions_empty_query(self):
        """测试空查询参数"""
        response = client.get("/search/stocks/suggestions?q=")

        assert response.status_code == 400
        data = response.json()
        assert "查询参数不能为空" in data['detail']

    def test_suggestions_invalid_limit(self):
        """测试无效限制参数"""
        response = client.get("/search/stocks/suggestions?q=test&limit=0")

        assert response.status_code == 400
        data = response.json()
        assert "限制数量必须在1-20之间" in data['detail']

        response = client.get("/search/stocks/suggestions?q=test&limit=21")

        assert response.status_code == 400

    @patch('stockaivo.routers.search.get_stock_suggestions')
    def test_suggestions_service_error(self, mock_suggestions):
        """测试服务层错误"""
        mock_suggestions.side_effect = Exception("Service unavailable")

        response = client.get("/search/stocks/suggestions?q=test")

        assert response.status_code == 500
        data = response.json()
        assert "搜索建议服务暂时不可用" in data['detail']


class TestSearchHealthAPI:
    """测试搜索健康检查API端点"""

    @patch('stockaivo.routers.search.get_db')
    def test_health_check_success(self, mock_get_db):
        """测试健康检查成功"""
        # 模拟数据库连接成功
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.execute.return_value.scalar.return_value = 1

        response = client.get("/search/health")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'search'
        assert 'timestamp' in data
        assert 'database_connection' in data
        assert data['database_connection'] == 'ok'

    @patch('stockaivo.routers.search.get_db')
    def test_health_check_database_error(self, mock_get_db):
        """测试数据库连接错误"""
        mock_get_db.side_effect = Exception("Database connection failed")

        response = client.get("/search/health")

        assert response.status_code == 503
        data = response.json()
        assert data['status'] == 'unhealthy'
        assert data['database_connection'] == 'failed'


class TestSearchAPIPerformance:
    """性能测试"""

    @patch('stockaivo.routers.search.search_stocks_with_pagination')
    def test_response_time(self, mock_search):
        """测试响应时间"""
        import time
        
        mock_search.return_value = {
            'query': 'test',
            'results': [],
            'total_count': 0,
            'page': 1,
            'page_size': 10,
            'total_pages': 0,
            'has_more': False,
            'timestamp': '2025-07-02T12:00:00'
        }

        start_time = time.time()
        response = client.get("/search/stocks?q=test")
        end_time = time.time()

        assert response.status_code == 200
        # 响应时间应该在合理范围内（这里设置为1秒，实际可能需要调整）
        assert (end_time - start_time) < 1.0

    @patch('stockaivo.routers.search.search_stocks_with_pagination')
    def test_concurrent_requests(self, mock_search):
        """测试并发请求"""
        import threading
        import time

        mock_search.return_value = {
            'query': 'concurrent',
            'results': [],
            'total_count': 0,
            'page': 1,
            'page_size': 10,
            'total_pages': 0,
            'has_more': False,
            'timestamp': '2025-07-02T12:00:00'
        }

        def make_request():
            response = client.get("/search/stocks?q=concurrent")
            assert response.status_code == 200

        # 创建多个线程同时发送请求
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)

        start_time = time.time()
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
        end_time = time.time()

        # 所有请求应该在合理时间内完成
        assert (end_time - start_time) < 5.0


if __name__ == '__main__':
    pytest.main([__file__])
