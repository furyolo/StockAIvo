"""
测试JSON响应清理功能
"""
import pytest
from stockaivo.ai.llm_service import LLMService


class TestJSONCleaning:
    """测试LLM服务的JSON清理功能"""

    @pytest.fixture
    def llm_service(self):
        """创建LLM服务实例"""
        return LLMService()

    def test_clean_json_with_markdown_wrapper(self, llm_service):
        """测试清理带markdown代码块的JSON"""
        # 模拟LLM返回的带markdown包裹的JSON
        raw_response = '''```json
{
  "prediction_probability": 0.70,
  "direction": "UP",
  "reasoning": "测试内容"
}
```'''

        expected_cleaned = '''{
  "prediction_probability": 0.70,
  "direction": "UP",
  "reasoning": "测试内容"
}'''

        cleaned = llm_service._clean_json_response(raw_response)
        assert cleaned == expected_cleaned

    def test_clean_json_with_json_prefix(self, llm_service):
        """测试清理带```json前缀的JSON"""
        raw_response = '''```json
{"key": "value"}
```'''

        expected_cleaned = '{"key": "value"}'

        cleaned = llm_service._clean_json_response(raw_response)
        assert cleaned == expected_cleaned

    def test_clean_json_with_generic_code_block(self, llm_service):
        """测试清理带通用代码块的JSON"""
        raw_response = '''```
{"key": "value"}
```'''

        expected_cleaned = '{"key": "value"}'

        cleaned = llm_service._clean_json_response(raw_response)
        assert cleaned == expected_cleaned

    def test_clean_json_already_clean(self, llm_service):
        """测试处理已经干净的JSON"""
        raw_response = '{"key": "value"}'

        cleaned = llm_service._clean_json_response(raw_response)
        assert cleaned == raw_response

    def test_clean_json_with_whitespace(self, llm_service):
        """测试清理带前后空白的JSON"""
        raw_response = '''

{"key": "value"}

        '''

        expected_cleaned = '{"key": "value"}'

        cleaned = llm_service._clean_json_response(raw_response)
        assert cleaned == expected_cleaned

    def test_clean_json_multiline_content(self, llm_service):
        """测试清理多行JSON内容"""
        raw_response = '''```json
{
  "prediction_probability": 0.65,
  "direction": "DOWN",
  "reasoning": "基于技术面分析，SMCI展现出强烈的短期看涨信号。\\n\\n我们将概率设定为0.70"
}
```'''

        cleaned = llm_service._clean_json_response(raw_response)

        # 验证清理后的内容可以被json.loads解析
        import json
        parsed = json.loads(cleaned)
        assert parsed["prediction_probability"] == 0.65
        assert parsed["direction"] == "DOWN"
        assert "基于技术面分析" in parsed["reasoning"]
