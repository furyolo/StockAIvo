"""
搜索功能性能测试模块

测试搜索功能在不同负载下的性能表现。
"""

import pytest
import time
import statistics
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient

from main import app
from stockaivo.search_service import (
    calculate_relevance_score,
    search_stocks_by_name,
    search_stocks_with_pagination
)

client = TestClient(app)


class TestSearchPerformance:
    """搜索性能测试"""

    def test_relevance_score_performance(self):
        """测试相关性评分算法性能"""
        test_cases = [
            ("apple", "Apple Inc.", "苹果公司"),
            ("microsoft", "Microsoft Corporation", "微软公司"),
            ("google", "Alphabet Inc.", "谷歌公司"),
            ("tesla", "Tesla Inc.", "特斯拉公司"),
            ("amazon", "Amazon.com Inc.", "亚马逊公司"),
        ]

        # 测试单次执行时间
        start_time = time.time()
        for query, name, cname in test_cases:
            calculate_relevance_score(query, name, cname)
        end_time = time.time()

        single_execution_time = end_time - start_time
        assert single_execution_time < 0.01, f"单次执行时间过长: {single_execution_time:.4f}秒"

        # 测试批量执行时间
        iterations = 1000
        start_time = time.time()
        for _ in range(iterations):
            for query, name, cname in test_cases:
                calculate_relevance_score(query, name, cname)
        end_time = time.time()

        batch_execution_time = end_time - start_time
        avg_time_per_call = batch_execution_time / (iterations * len(test_cases))
        
        assert avg_time_per_call < 0.001, f"平均执行时间过长: {avg_time_per_call:.6f}秒"
        print(f"相关性评分性能: {iterations * len(test_cases)}次调用耗时 {batch_execution_time:.4f}秒")
        print(f"平均每次调用: {avg_time_per_call:.6f}秒")

    @patch('stockaivo.search_service.get_db')
    @patch('stockaivo.search_service.get_search_results')
    @patch('stockaivo.search_service.save_search_results')
    def test_search_function_performance(self, mock_save_cache, mock_get_cache, mock_get_db):
        """测试搜索函数性能"""
        # 模拟缓存未命中
        mock_get_cache.return_value = None

        # 模拟数据库查询
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        
        # 模拟大量搜索结果
        mock_stocks = [
            MagicMock(symbol=f"TEST{i:04d}", name=f"Test Company {i}", cname=f"测试公司{i}")
            for i in range(100)
        ]
        
        mock_db.execute.return_value.scalar.return_value = 100
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_stocks

        # 测试搜索性能
        start_time = time.time()
        results, total_count = search_stocks_by_name("test", limit=50, offset=0, use_cache=False)
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 1.0, f"搜索执行时间过长: {execution_time:.4f}秒"
        assert len(results) == 50
        assert total_count == 100

        print(f"搜索函数性能: 处理100条记录耗时 {execution_time:.4f}秒")

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_api_response_time(self, mock_search):
        """测试API响应时间"""
        # 模拟搜索结果
        mock_search.return_value = (
            [{'symbol': f'TEST{i}', 'name': f'Test {i}', 'cname': None, 'relevance_score': 0.8} 
             for i in range(10)],
            10
        )

        response_times = []
        
        # 测试多次请求的响应时间
        for _ in range(20):
            start_time = time.time()
            response = client.get("/search/stocks?q=test")
            end_time = time.time()
            
            assert response.status_code == 200
            response_times.append(end_time - start_time)

        avg_response_time = statistics.mean(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)

        assert avg_response_time < 0.5, f"平均响应时间过长: {avg_response_time:.4f}秒"
        assert max_response_time < 1.0, f"最大响应时间过长: {max_response_time:.4f}秒"

        print(f"API响应时间统计:")
        print(f"  平均: {avg_response_time:.4f}秒")
        print(f"  最小: {min_response_time:.4f}秒")
        print(f"  最大: {max_response_time:.4f}秒")

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_concurrent_api_requests(self, mock_search):
        """测试并发API请求性能"""
        # 模拟搜索结果
        mock_search.return_value = (
            [{'symbol': 'TEST', 'name': 'Test Company', 'cname': None, 'relevance_score': 0.8}],
            1
        )

        def make_request(query_id):
            start_time = time.time()
            response = client.get(f"/search/stocks?q=test{query_id}")
            end_time = time.time()
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time,
                'query_id': query_id
            }

        # 并发测试
        concurrent_requests = 10
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
            futures = [executor.submit(make_request, i) for i in range(concurrent_requests)]
            results = [future.result() for future in as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time

        # 验证所有请求都成功
        for result in results:
            assert result['status_code'] == 200

        # 计算性能指标
        response_times = [result['response_time'] for result in results]
        avg_response_time = statistics.mean(response_times)
        throughput = concurrent_requests / total_time

        assert avg_response_time < 1.0, f"并发请求平均响应时间过长: {avg_response_time:.4f}秒"
        assert throughput > 5, f"吞吐量过低: {throughput:.2f} 请求/秒"

        print(f"并发性能测试结果:")
        print(f"  并发请求数: {concurrent_requests}")
        print(f"  总耗时: {total_time:.4f}秒")
        print(f"  平均响应时间: {avg_response_time:.4f}秒")
        print(f"  吞吐量: {throughput:.2f} 请求/秒")

    @patch('stockaivo.search_service.get_search_results')
    @patch('stockaivo.search_service.save_search_results')
    def test_cache_performance(self, mock_save_cache, mock_get_cache):
        """测试缓存性能"""
        # 模拟缓存命中
        cached_results = [
            {'symbol': f'CACHE{i}', 'name': f'Cached Company {i}', 'cname': None, 'relevance_score': 0.9}
            for i in range(50)
        ]
        mock_get_cache.return_value = cached_results

        # 测试缓存命中性能
        cache_hit_times = []
        for _ in range(100):
            start_time = time.time()
            results, total_count = search_stocks_by_name("cached", limit=50, offset=0, use_cache=True)
            end_time = time.time()
            cache_hit_times.append(end_time - start_time)

        avg_cache_hit_time = statistics.mean(cache_hit_times)
        assert avg_cache_hit_time < 0.01, f"缓存命中时间过长: {avg_cache_hit_time:.6f}秒"

        print(f"缓存性能测试:")
        print(f"  平均缓存命中时间: {avg_cache_hit_time:.6f}秒")
        print(f"  缓存命中次数: {mock_get_cache.call_count}")

    def test_memory_usage_during_search(self):
        """测试搜索过程中的内存使用"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # 模拟大量搜索操作
        with patch('stockaivo.search_service.get_search_results') as mock_cache:
            mock_cache.return_value = None
            with patch('stockaivo.search_service.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_get_db.return_value = iter([mock_db])
                mock_db.execute.return_value.scalar.return_value = 0
                mock_db.execute.return_value.scalars.return_value.all.return_value = []

                # 执行多次搜索
                for i in range(100):
                    search_stocks_by_name(f"test{i}", limit=10, offset=0, use_cache=False)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # 内存增长应该在合理范围内
        assert memory_increase < 50, f"内存增长过多: {memory_increase:.2f}MB"

        print(f"内存使用测试:")
        print(f"  初始内存: {initial_memory:.2f}MB")
        print(f"  最终内存: {final_memory:.2f}MB")
        print(f"  内存增长: {memory_increase:.2f}MB")

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_large_result_set_performance(self, mock_search):
        """测试大结果集性能"""
        # 模拟大量搜索结果
        large_results = [
            {'symbol': f'LARGE{i:06d}', 'name': f'Large Company {i}', 'cname': f'大公司{i}', 'relevance_score': 0.7}
            for i in range(1000)
        ]
        mock_search.return_value = (large_results, 1000)

        start_time = time.time()
        result = search_stocks_with_pagination("large", page=1, page_size=100)
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 2.0, f"大结果集处理时间过长: {execution_time:.4f}秒"
        assert len(result['results']) == 100
        assert result['total_count'] == 1000

        print(f"大结果集性能: 处理1000条记录耗时 {execution_time:.4f}秒")


class TestSearchStressTest:
    """搜索压力测试"""

    @patch('stockaivo.search_service.search_stocks_by_name')
    def test_sustained_load(self, mock_search):
        """测试持续负载"""
        mock_search.return_value = (
            [{'symbol': 'STRESS', 'name': 'Stress Test', 'cname': None, 'relevance_score': 0.8}],
            1
        )

        # 持续发送请求
        duration = 10  # 秒
        request_count = 0
        start_time = time.time()
        
        while time.time() - start_time < duration:
            response = client.get("/search/stocks?q=stress")
            assert response.status_code == 200
            request_count += 1

        end_time = time.time()
        actual_duration = end_time - start_time
        requests_per_second = request_count / actual_duration

        assert requests_per_second > 10, f"持续负载性能不足: {requests_per_second:.2f} 请求/秒"

        print(f"持续负载测试:")
        print(f"  测试时长: {actual_duration:.2f}秒")
        print(f"  总请求数: {request_count}")
        print(f"  平均 QPS: {requests_per_second:.2f}")


if __name__ == '__main__':
    pytest.main([__file__, "-v", "-s"])
