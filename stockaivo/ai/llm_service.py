"""
LLM Service - 大语言模型服务封装
提供与外部LLM API的统一接口
"""

import os
import asyncio
import httpx
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
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}"
                },
                http2=False,
                timeout=httpx.Timeout(
                    timeout=120.0,  # 总超时时间
                    connect=30.0,   # 连接超时
                    read=120.0,     # 读取超时
                    write=30.0      # 写入超时
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0
                ),
                follow_redirects=True,
                trust_env=False  # 禁用环境变量代理设置
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
            # Gemini 支持真正的流式输出
            async for chunk in self._invoke_gemini_stream(prompt):
                yield chunk
        else:
            yield "LLM服务未正确配置"

    async def _invoke_openai(self, prompt: str) -> str:
        try:
            request_data = {
                "model": self.openai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 6000
            }
            logger.info(f"Sending request to OpenAI API using httpx: model={self.openai_model_name}, prompt_length={len(prompt)}")

            response = await self.client.post(
                "/chat/completions",
                json=request_data,
                timeout=httpx.Timeout(
                    timeout=120.0,
                    connect=30.0,
                    read=120.0,
                    write=30.0
                )
            )
            response.raise_for_status()
            data = response.json()

            content = data['choices'][0]['message']['content']
            logger.info(f"Received response from OpenAI API: content_length={len(content)}")
            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"调用OpenAI兼容API时发生HTTP错误 (httpx): {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}: {e.response.text}"
        except httpx.RequestError as e:
            # 详细记录 httpx 错误信息
            import traceback
            logger.error(f"调用OpenAI兼容API时发生请求错误 (httpx): {type(e).__name__}: {e}")
            logger.error(f"httpx 错误详细信息: {str(e)}")
            logger.error(f"httpx 错误堆栈: {traceback.format_exc()}")
            if hasattr(e, '__cause__') and e.__cause__:
                logger.error(f"httpx 错误根本原因: {type(e.__cause__).__name__}: {e.__cause__}")
            return f"Error calling OpenAI-compatible API: {type(e).__name__}: {e}"
        except Exception as e:
            logger.error(f"调用OpenAI兼容API时发生未知错误 (httpx): {type(e).__name__}: {e}")
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

    async def _invoke_gemini_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        流式调用 Gemini API
        """
        try:
            logger.info(f"Sending streaming request to Gemini API: prompt_length={len(prompt)}")

            # 使用 Gemini 的流式生成方法
            response_stream = await self.model.generate_content_async(
                prompt,
                stream=True
            )

            async for chunk in response_stream:
                if chunk.candidates and chunk.candidates[0].content.parts:
                    text = chunk.candidates[0].content.parts[0].text
                    if text:
                        yield text

        except Exception as e:
            logger.error(f"Gemini 流式调用错误: {type(e).__name__}: {e}")
            logger.warning(f"Gemini 流式调用失败，回退到模拟流式")
            # 回退到非流式调用并模拟流式输出
            try:
                result = await self._invoke_gemini(prompt)
                # 模拟流式返回，按句子分割
                sentences = result.split('。')
                for sentence in sentences:
                    if sentence.strip():
                        yield sentence + '。'
                        await asyncio.sleep(0.2)  # 模拟流式延迟
            except Exception as fallback_e:
                logger.error(f"Gemini 回退调用也失败: {fallback_e}")
                yield f"Error calling Gemini: {str(e)}"

    async def _invoke_openai_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        流式调用OpenAI兼容API
        """
        # 优先使用 httpx 的 client.stream 进行流式请求
        try:
            request_data = {
                "model": self.openai_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 6000,
                "stream": True
            }
            logger.info(f"Sending streaming request to OpenAI API using httpx.stream: model={self.openai_model_name}, prompt_length={len(prompt)}")

            async with self.client.stream(
                "POST",
                "/chat/completions",
                json=request_data,
                timeout=httpx.Timeout(
                    timeout=180.0,  # 流式请求需要更长的超时时间
                    connect=30.0,
                    read=180.0,
                    write=30.0
                )
            ) as response:
                logger.info(f"Streaming response status (httpx): {response.status_code}")

                # 检查响应状态码
                if response.status_code != 200:
                    error_text = ""
                    try:
                        error_text = await response.aread()
                        error_text = error_text.decode('utf-8') if isinstance(error_text, bytes) else str(error_text)
                    except Exception:
                        error_text = "无法读取错误响应"

                    logger.error(f"httpx 流式请求返回错误状态码: {response.status_code}")
                    logger.error(f"错误响应内容: {error_text}")
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response
                    )

                # 处理流式响应
                async for line_bytes in response.aiter_lines():
                    if line_bytes:
                        # 解码为UTF-8字符串
                        try:
                            line = line_bytes.decode('utf-8') if isinstance(line_bytes, bytes) else line_bytes
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

        except httpx.HTTPStatusError as e:
            error_text = ""
            try:
                error_text = e.response.text if hasattr(e.response, 'text') else str(e.response.content)
            except:
                error_text = "无法读取错误响应"
            logger.error(f"流式调用HTTP错误 (httpx): {e.response.status_code} - {error_text}")
            logger.warning(f"httpx流式调用失败，回退到模拟流式: {type(e).__name__}: {e}")
            # 回退到非流式调用并模拟流式输出
            async for chunk in self._fallback_to_simulated_stream(prompt):
                yield chunk
        except httpx.RequestError as e:
            # 详细记录 httpx 错误信息
            import traceback
            logger.error(f"流式调用请求错误 (httpx): {type(e).__name__}: {e}")
            logger.error(f"httpx 错误详细信息: {str(e)}")
            logger.error(f"httpx 错误堆栈: {traceback.format_exc()}")
            if hasattr(e, '__cause__') and e.__cause__:
                logger.error(f"httpx 错误根本原因: {type(e.__cause__).__name__}: {e.__cause__}")
            logger.warning(f"httpx流式调用失败，回退到模拟流式: {type(e).__name__}: {e}")
            # 回退到非流式调用并模拟流式输出
            async for chunk in self._fallback_to_simulated_stream(prompt):
                yield chunk
        except Exception as e:
            logger.error(f"流式调用未知错误 (httpx): {type(e).__name__}: {e}")
            logger.warning(f"httpx流式调用失败，回退到模拟流式: {type(e).__name__}: {e}")
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