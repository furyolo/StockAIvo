from typing import Dict, Optional
from stockaivo.ai.llm_service import llm_service
from langchain_core.tools import tool


@tool
async def llm_tool(input_dict: Dict) -> str:
    """
    使用LLM服务执行分析。
    接收一个包含'prompt'键的字典，可选包含'agent_name'键，返回LLM的分析结果。
    """
    prompt = input_dict.get("prompt")
    if not prompt:
        return "Error: 'prompt' key is missing in the input dictionary."

    agent_name = input_dict.get("agent_name")
    result = await llm_service.invoke(prompt, agent_name)
    return result