"""
LLM Service - 大语言模型服务封装
提供与外部LLM API的统一接口
"""

import os
import httpx
import requests
import json
from typing import Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)


class LLMService:
    """
    大语言模型服务类
    封装对外部LLM API的调用。
    优先使用OpenAI兼容的API，如果环境变量未设置，则回退到Google Gemini。
    """

    def __init__(self):
        """初始化LLM服务"""
        self.mode = None
        self.openai_api_base = os.getenv("OPENAI_API_BASE")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

        if self.openai_api_base and self.openai_api_key:
            self.mode = "openai"
            self.openai_model_name = os.getenv("OPENAI_MODEL_NAME")
            if not self.openai_model_name:
                raise ValueError("OPENAI_MODEL_NAME 环境变量必须在 .env 文件中设置")
            self.client = httpx.AsyncClient(
                base_url=self.openai_api_base,
                headers={"Authorization": f"Bearer {self.openai_api_key}"},
                http2=False,
                timeout=httpx.Timeout(60.0, connect=10.0)
            )
            logger.info(f"LLM服务已配置为使用OpenAI兼容API (模型: {self.openai_model_name})。")
        elif self.gemini_api_key:
            self.mode = "gemini"
            self.gemini_model_name = os.getenv("GEMINI_MODEL_NAME")
            if not self.gemini_model_name:
                raise ValueError("GEMINI_MODEL_NAME 环境变量必须在 .env 文件中设置")
            genai.configure(api_key=self.gemini_api_key)  # type: ignore
            self.model = genai.GenerativeModel(self.gemini_model_name)  # type: ignore
            logger.info(f"LLM服务已配置为使用Google Gemini API (模型: {self.gemini_model_name})。")
        else:
            raise ValueError("必须配置OpenAI或Gemini的API密钥环境变量")

    async def invoke(self, prompt: str) -> str:
        """
        调用LLM并返回文本响应。

        Args:
            prompt: 发送给LLM的提示词。

        Returns:
            LLM的文本响应。
        """
        if self.mode == "openai":
            return await self._invoke_openai(prompt)
        elif self.mode == "gemini":
            return await self._invoke_gemini(prompt)
        else:
            return "LLM服务未正确配置"

    async def invoke_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        调用LLM并返回流式文本响应。

        Args:
            prompt: 发送给LLM的提示词。

        Yields:
            LLM的流式文本响应片段。
        """
        if self.mode == "openai":
            # 尝试真正的流式请求
            async for chunk in self._invoke_openai_stream(prompt):
                yield chunk
        elif self.mode == "gemini":
            # Gemini暂不支持流式，回退到一次性返回
            result = await self._invoke_gemini(prompt)
            # 模拟流式返回，按句子分割
            import asyncio
            sentences = result.split('。')
            for sentence in sentences:
                if sentence.strip():
                    yield sentence + '。'
                    await asyncio.sleep(0.2)  # 模拟流式延迟
        else:
            yield "LLM服务未正确配置"

    async def _invoke_openai(self, prompt: str) -> str:
        # 先尝试使用 requests 库（同步）
        try:
            request_data = {
                "model": self.openai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 6000
            }
            logger.info(f"Sending request to OpenAI API using requests: model={self.openai_model_name}, prompt_length={len(prompt)}")

            # 使用 requests 库进行同步请求
            import asyncio
            response = await asyncio.to_thread(
                requests.post,
                f"{self.openai_api_base}/chat/completions",
                json=request_data,
                headers={"Authorization": f"Bearer {self.openai_api_key}"},
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()

            content = data['choices'][0]['message']['content']
            logger.info(f"Received response from OpenAI API: content_length={len(content)}")
            return content

        except requests.exceptions.HTTPError as e:
            logger.error(f"调用OpenAI兼容API时发生HTTP错误 (requests): {e.response.status_code} - {e.response.text}")
            # 如果 requests 失败，回退到 httpx
            return await self._invoke_openai_httpx(prompt)
        except Exception as e:
            logger.error(f"调用OpenAI兼容API时发生错误 (requests): {type(e).__name__}: {e}")
            # 如果 requests 失败，回退到 httpx
            return await self._invoke_openai_httpx(prompt)

    async def _invoke_openai_httpx(self, prompt: str) -> str:
        try:
            request_data = {
                "model": self.openai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 6000
            }
            logger.info(f"Sending request to OpenAI API using httpx: model={self.openai_model_name}, prompt_length={len(prompt)}")

            response = await self.client.post("/chat/completions", json=request_data, timeout=60.0)
            response.raise_for_status()
            data = response.json()

            content = data['choices'][0]['message']['content']
            logger.info(f"Received response from OpenAI API: content_length={len(content)}")
            return content
        except httpx.HTTPStatusError as e:
            logger.error(f"调用OpenAI兼容API时发生HTTP错误: {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}: {e.response.text}"
        except httpx.RequestError as e:
            logger.error(f"调用OpenAI兼容API时发生请求错误: {e}")
            return f"Request Error: {str(e)}"
        except Exception as e:
            logger.error(f"调用OpenAI兼容API时发生未知错误: {type(e).__name__}: {e}")
            return f"Error calling OpenAI-compatible API: {type(e).__name__}: {str(e)}"

    async def _invoke_gemini(self, prompt: str) -> str:
        try:
            response = await self.model.generate_content_async(prompt)
            if response.candidates and response.candidates[0].content.parts:
                return response.candidates[0].content.parts[0].text
            else:
                logger.warning(f"LLM for prompt '{prompt[:50]}...' returned no content.")
                if response.prompt_feedback.block_reason:
                     return f"Blocked for {response.prompt_feedback.block_reason_message}"
                return "LLM did not return any content."
        except Exception as e:
            logger.error(f"调用LLM时发生意外错误: {e}")
            return f"Error calling LLM: {str(e)}"

    async def _invoke_openai_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        流式调用OpenAI兼容API，如果失败则回退到非流式并模拟流式输出
        """
        # 首先尝试使用requests进行流式请求（与非流式请求保持一致）
        try:
            request_data = {
                "model": self.openai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 6000,
                "stream": True
            }
            logger.info(f"Sending streaming request to OpenAI API: model={self.openai_model_name}, prompt_length={len(prompt)}")

            # 使用requests进行流式请求
            import asyncio
            import requests

            def stream_request():
                response = requests.post(
                    f"{self.openai_api_base}/chat/completions",
                    json=request_data,
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    timeout=60.0,
                    stream=True
                )
                response.raise_for_status()
                return response

            response = await asyncio.to_thread(stream_request)
            logger.info(f"Streaming response status: {response.status_code}")

            # 处理流式响应，确保正确的UTF-8编码
            for line_bytes in response.iter_lines():
                if line_bytes:
                    # 手动解码为UTF-8字符串
                    try:
                        line = line_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        # 如果UTF-8解码失败，尝试其他编码
                        try:
                            line = line_bytes.decode('latin-1')
                        except UnicodeDecodeError:
                            continue  # 跳过无法解码的行

                    if line.startswith("data: "):
                        data_str = line[6:]  # 移除 "data: " 前缀

                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content = delta["content"]
                                    if content:
                                        yield content
                        except json.JSONDecodeError:
                            # 跳过无法解析的行
                            continue

        except requests.exceptions.HTTPError as e:
            logger.error(f"流式调用HTTP错误 (requests): {e.response.status_code} - {e.response.text}")
            logger.warning(f"流式调用失败，回退到非流式调用: {e}")
            # 回退到非流式调用并模拟流式输出
            async for chunk in self._fallback_to_simulated_stream(prompt):
                yield chunk
        except Exception as e:
            logger.error(f"流式调用错误 (requests): {type(e).__name__}: {e}")
            logger.warning(f"流式调用失败，回退到非流式调用: {e}")
            # 回退到非流式调用并模拟流式输出
            async for chunk in self._fallback_to_simulated_stream(prompt):
                yield chunk

    async def _fallback_to_simulated_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        回退到非流式调用并模拟流式输出
        """
        try:
            result = await self._invoke_openai(prompt)
            # 模拟流式输出：按句子分割
            import asyncio
            sentences = result.split('。')
            for sentence in sentences:
                if sentence.strip():
                    yield sentence + '。'
                    await asyncio.sleep(0.1)  # 模拟流式延迟
        except Exception as fallback_error:
            logger.error(f"非流式回退也失败: {fallback_error}")
            yield f"Error: {str(fallback_error)}"

# 单例模式
llm_service = LLMService()