from typing import Dict
from stockaivo.ai.llm_service import llm_service
from langchain_core.tools import tool


@tool
async def llm_tool(input_dict: Dict) -> str:
    """
    使用LLM服务执行分析。
    接收一个包含'prompt'键的字典，返回LLM的分析结果。
    """
    prompt = input_dict.get("prompt")
    if not prompt:
        return "Error: 'prompt' key is missing in the input dictionary."
    
    result = await llm_service.invoke(prompt)
    return result