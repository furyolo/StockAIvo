"""
实时行情API端点测试

测试新添加的实时行情API端点的功能
"""

import pytest
import httpx
import asyncio
from unittest.mock import patch, Mock
import pandas as pd
from fastapi.testclient import TestClient

# 导入FastAPI应用
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


class TestRealTimeQuotesAPI:
    """测试实时行情API端点"""

    def setup_method(self):
        """测试前的设置"""
        self.client = TestClient(app)
    
    def test_update_realtime_quotes_success(self):
        """测试手动更新实时行情数据成功"""
        mock_data = pd.DataFrame({
            'fullsymbol': ['106.AAPL', '106.MSFT'],
            'symbol': ['AAPL', 'MSFT'],
            'name': ['苹果', '微软'],
            'price': [150.25, 280.50],
            'created_at': [pd.Timestamp.now(), pd.Timestamp.now()],
            'updated_at': [pd.Timestamp.now(), pd.Timestamp.now()]
        })
        
        with patch('stockaivo.data_provider.fetch_realtime_quotes', return_value=mock_data), \
             patch('stockaivo.database_writer.save_realtime_quotes_to_db', return_value=True):
            
            response = self.client.post("/stocks/realtime-quotes/update")
            
            assert response.status_code == 200
            
            data = response.json()
            assert data['success'] is True
            assert data['message'] == '实时行情数据更新成功'
            assert data['updated_count'] == 2
            assert 'timestamp' in data
    
    def test_update_realtime_quotes_no_data(self):
        """测试手动更新时无数据的情况"""
        with patch('stockaivo.data_provider.fetch_realtime_quotes', return_value=None):
            response = self.client.post("/stocks/realtime-quotes/update")
            
            assert response.status_code == 404
            assert "未能获取到实时行情数据" in response.json()['detail']
    
    def test_update_realtime_quotes_db_error(self):
        """测试手动更新时数据库错误的情况"""
        mock_data = pd.DataFrame({
            'fullsymbol': ['106.AAPL'],
            'symbol': ['AAPL'],
            'name': ['苹果'],
            'price': [150.25],
            'created_at': [pd.Timestamp.now()],
            'updated_at': [pd.Timestamp.now()]
        })
        
        with patch('stockaivo.data_provider.fetch_realtime_quotes', return_value=mock_data), \
             patch('stockaivo.database_writer.save_realtime_quotes_to_db', return_value=False):
            
            response = self.client.post("/stocks/realtime-quotes/update")
            
            assert response.status_code == 500
            assert "更新实时行情数据到数据库失败" in response.json()['detail']


class TestAPIIntegration:
    """API集成测试"""

    def setup_method(self):
        """测试前的设置"""
        self.client = TestClient(app)

    def test_update_endpoint_integration(self):
        """测试更新端点的集成功能"""
        mock_data = pd.DataFrame({
            'fullsymbol': ['106.AAPL'],
            'symbol': ['AAPL'],
            'name': ['苹果'],
            'price': [150.25],
            'price_change': [2.50],
            'price_change_percent': [1.69],
            'open': [148.00],
            'high': [151.50],
            'low': [147.25],
            'pre_close': [147.75],
            'market_value': [2500000000000],
            'pe_ratio': [28.5],
            'volume': [45000000],
            'turnover': [6750000000],
            'amplitude': [2.88],
            'turnover_rate': [1.85],
            'created_at': [pd.Timestamp.now()],
            'updated_at': [pd.Timestamp.now()]
        })

        with patch('stockaivo.data_provider.fetch_realtime_quotes', return_value=mock_data), \
             patch('stockaivo.database_writer.save_realtime_quotes_to_db', return_value=True):

            response = self.client.post("/stocks/realtime-quotes/update")

            assert response.status_code == 200

            data = response.json()

            # 验证响应结构
            required_fields = ['success', 'message', 'updated_count', 'timestamp']
            for field in required_fields:
                assert field in data

            assert data['success'] is True
            assert data['updated_count'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
