"""
测试 LLM 模型配置默认值与代理覆盖逻辑
"""

from stockaivo.ai.llm_service import LLMService


def test_llm_service_uses_new_default_and_agent_override_models(monkeypatch):
    """验证默认模型与代理专用模型覆盖值"""
    monkeypatch.setenv("OPENAI_API_BASE", "http://example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("AI_TECHNICAL_ANALYSIS_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("AI_SYNTHESIS_MODEL", "gemini-3.1-pro-preview")

    service = LLMService()

    assert service.get_model_name_for_agent() == "gemini-3-flash-preview"
    assert service.get_model_name_for_agent("technical_analysis_agent") == "gemini-3.1-pro-preview"
    assert service.get_model_name_for_agent("synthesis_agent") == "gemini-3.1-pro-preview"
