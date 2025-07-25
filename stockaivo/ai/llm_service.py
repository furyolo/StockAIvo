"""
LLM Service - 大语言模型服务封装
提供与外部LLM API的统一接口
"""

import os
import asyncio
import httpx
import json
import random
from typing import Dict, Any, Optional, AsyncGenerator
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

        # 加载AI模型配置
        self.ai_default_model = os.getenv("AI_DEFAULT_MODEL", "gemini-2.5-flash")

        # 代理特定模型配置
        self.agent_model_overrides = {
            "technical_analysis_agent": os.getenv("AI_TECHNICAL_ANALYSIS_MODEL"),
            "synthesis_agent": os.getenv("AI_SYNTHESIS_MODEL"),
            "fundamental_analysis_agent": os.getenv("AI_FUNDAMENTAL_ANALYSIS_MODEL"),
            "news_sentiment_analysis_agent": os.getenv("AI_NEWS_SENTIMENT_MODEL"),
            "data_collection_agent": os.getenv("AI_DATA_COLLECTION_MODEL"),
        }

        if self.openai_api_base and self.openai_api_key:
            self.mode = "openai"
            # 使用默认模型作为服务级别的基础模型
            self.openai_model_name = self.ai_default_model
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
            logger.info(f"LLM服务已配置为使用OpenAI兼容API (默认模型: {self.openai_model_name})。")
        elif self.gemini_api_key:
            self.mode = "gemini"
            # 使用默认模型作为服务级别的基础模型
            self.gemini_model_name = self.ai_default_model
            genai.configure(api_key=self.gemini_api_key)  # type: ignore
            self.model = genai.GenerativeModel(self.gemini_model_name)  # type: ignore
            logger.info(f"LLM服务已配置为使用Google Gemini API (默认模型: {self.gemini_model_name})。")
        else:
            raise ValueError("必须配置OpenAI或Gemini的API密钥环境变量")

    def get_model_name_for_agent(self, agent_name: Optional[str] = None) -> str:
        """
        获取指定代理的模型名称

        Args:
            agent_name: 代理名称，如果为None则使用默认模型

        Returns:
            模型名称
        """
        # 1. 首先检查代理特定的模型配置
        if agent_name and agent_name in self.agent_model_overrides:
            override_model = self.agent_model_overrides[agent_name]
            if override_model:  # 如果配置了非空值
                return override_model

        # 2. 使用默认模型
        return self.ai_default_model

    async def invoke(self, prompt: str, agent_name: Optional[str] = None) -> str:
        """
        调用LLM并返回文本响应。

        Args:
            prompt: 发送给LLM的提示词。
            agent_name: 代理名称，用于选择特定的模型。

        Returns:
            LLM的文本响应。
        """
        if self.mode == "openai":
            return await self._invoke_openai(prompt, agent_name)
        elif self.mode == "gemini":
            return await self._invoke_gemini(prompt, agent_name)
        else:
            return "LLM服务未正确配置"

    def _should_retry(self, status_code: int) -> bool:
        """
        判断是否应该重试请求

        Args:
            status_code: HTTP状态码

        Returns:
            是否应该重试
        """
        # 对于429 (Too Many Requests) 和 5xx 服务器错误进行重试
        return status_code == 429 or (500 <= status_code < 600)

    async def _calculate_retry_delay(self, attempt: int, base_delay: float = 1.0) -> float:
        """
        计算重试延迟时间（指数退避 + 随机抖动）

        Args:
            attempt: 当前重试次数 (从1开始)
            base_delay: 基础延迟时间（秒）

        Returns:
            延迟时间（秒）
        """
        # 指数退避: base_delay * (2 ^ (attempt - 1))
        exponential_delay = base_delay * (2 ** (attempt - 1))
        # 添加随机抖动，避免雷群效应
        jitter = random.uniform(0.1, 0.5) * exponential_delay
        total_delay = exponential_delay + jitter
        # 最大延迟不超过60秒
        return min(total_delay, 60.0)

    def _build_request_data(self, prompt: str, stream: bool = False, agent_name: Optional[str] = None) -> dict:
        """
        构建请求数据

        Args:
            prompt: 提示词
            stream: 是否为流式请求
            agent_name: 代理名称，用于选择特定的模型

        Returns:
            请求数据字典
        """
        model_name = self.get_model_name_for_agent(agent_name)
        request_data = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 9000
        }
        if stream:
            request_data["stream"] = True
        return request_data

    def _get_timeout_config(self, is_stream: bool = False) -> httpx.Timeout:
        """
        获取超时配置

        Args:
            is_stream: 是否为流式请求

        Returns:
            超时配置
        """
        if is_stream:
            return httpx.Timeout(
                timeout=180.0,  # 流式请求需要更长的超时时间
                connect=30.0,
                read=180.0,
                write=30.0
            )
        else:
            return httpx.Timeout(
                timeout=120.0,
                connect=30.0,
                read=120.0,
                write=30.0
            )

    def _log_request_error(self, e: httpx.RequestError, request_type: str = "请求") -> str:
        """
        记录请求错误日志并返回错误信息

        Args:
            e: 请求错误
            request_type: 请求类型（用于日志）

        Returns:
            错误信息字符串
        """
        import traceback
        logger.error(f"调用OpenAI兼容API时发生{request_type}错误 (httpx): {type(e).__name__}: {e}")
        logger.error(f"httpx 错误详细信息: {str(e)}")
        logger.error(f"httpx 错误堆栈: {traceback.format_exc()}")
        if hasattr(e, '__cause__') and e.__cause__:
            logger.error(f"httpx 错误根本原因: {type(e.__cause__).__name__}: {e.__cause__}")
        return f"Error calling OpenAI-compatible API: {type(e).__name__}: {e}"

    def _log_http_error(self, e: httpx.HTTPStatusError, request_type: str = "请求") -> str:
        """
        记录HTTP错误日志并返回错误信息

        Args:
            e: HTTP状态错误
            request_type: 请求类型（用于日志）

        Returns:
            错误信息字符串
        """
        error_text = ""
        try:
            error_text = e.response.text if hasattr(e.response, 'text') else str(e.response.content)
        except:
            error_text = "无法读取错误响应"
        logger.error(f"{request_type}HTTP错误 (httpx): {e.response.status_code} - {error_text}")
        return f"HTTP Error {e.response.status_code}: {error_text}"

    async def invoke_stream(self, prompt: str, agent_name: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        调用LLM并返回流式文本响应。

        Args:
            prompt: 发送给LLM的提示词。
            agent_name: 代理名称，用于选择特定的模型。

        Yields:
            LLM的流式文本响应片段。
        """
        if self.mode == "openai":
            # 尝试真正的流式请求
            async for chunk in self._invoke_openai_stream(prompt, agent_name):
                yield chunk
        elif self.mode == "gemini":
            # Gemini 支持真正的流式输出
            async for chunk in self._invoke_gemini_stream(prompt, agent_name):
                yield chunk
        else:
            yield "LLM服务未正确配置"

    async def _invoke_openai(self, prompt: str, agent_name: Optional[str] = None) -> str:
        """
        调用OpenAI兼容API（带重试机制）
        """
        max_retries = 3
        model_name = self.get_model_name_for_agent(agent_name)

        for attempt in range(1, max_retries + 1):
            try:
                request_data = self._build_request_data(prompt, stream=False, agent_name=agent_name)
                logger.info(f"Sending request to OpenAI API using httpx: model={model_name}, agent={agent_name}, prompt_length={len(prompt)}")

                response = await self.client.post(
                    "/chat/completions",
                    json=request_data,
                    timeout=self._get_timeout_config(is_stream=False)
                )
                response.raise_for_status()
                data = response.json()

                content = data['choices'][0]['message']['content']
                logger.info(f"Received response from OpenAI API: content_length={len(content)}")
                return content

            except httpx.HTTPStatusError as e:
                if self._should_retry(e.response.status_code) and attempt < max_retries:
                    delay = await self._calculate_retry_delay(attempt)
                    logger.warning(f"非流式请求失败 (状态码: {e.response.status_code})，{delay:.1f}秒后进行第{attempt + 1}次重试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    return self._log_http_error(e, "非流式调用")

            except httpx.RequestError as e:
                # 网络错误等，不进行重试
                return self._log_request_error(e, "非流式请求")

            except Exception as e:
                logger.error(f"调用OpenAI兼容API时发生未知错误 (httpx): {type(e).__name__}: {e}")
                return f"Error calling OpenAI-compatible API: {type(e).__name__}: {str(e)}"

        # 如果所有重试都失败了，返回错误信息
        return f"所有重试都失败了，请稍后再试"

    async def _invoke_gemini(self, prompt: str, agent_name: Optional[str] = None) -> str:
        try:
            model_name = self.get_model_name_for_agent(agent_name)
            # 如果需要使用不同的模型，创建新的模型实例
            if model_name != self.gemini_model_name:
                model = genai.GenerativeModel(model_name)  # type: ignore
                logger.info(f"Using specific model for agent {agent_name}: {model_name}")
            else:
                model = self.model

            response = await model.generate_content_async(prompt)
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

    async def _invoke_gemini_stream(self, prompt: str, agent_name: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        流式调用 Gemini API
        """
        try:
            model_name = self.get_model_name_for_agent(agent_name)
            # 如果需要使用不同的模型，创建新的模型实例
            if model_name != self.gemini_model_name:
                model = genai.GenerativeModel(model_name)  # type: ignore
                logger.info(f"Using specific model for streaming agent {agent_name}: {model_name}")
            else:
                model = self.model

            logger.info(f"Sending streaming request to Gemini API: model={model_name}, agent={agent_name}, prompt_length={len(prompt)}")

            # 使用 Gemini 的流式生成方法
            response_stream = await model.generate_content_async(
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

    async def _invoke_openai_stream(self, prompt: str, agent_name: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        流式调用OpenAI兼容API（带重试机制）
        """
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                async for chunk in self._invoke_openai_stream_single_attempt(prompt, agent_name):
                    yield chunk
                return  # 成功完成，退出重试循环

            except httpx.HTTPStatusError as e:
                if self._should_retry(e.response.status_code) and attempt < max_retries:
                    delay = await self._calculate_retry_delay(attempt)
                    logger.warning(f"流式请求失败 (状态码: {e.response.status_code})，{delay:.1f}秒后进行第{attempt + 1}次重试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 不需要重试或已达到最大重试次数，执行原有的回退逻辑
                    self._log_http_error(e, "流式调用")
                    logger.warning(f"httpx流式调用失败，回退到模拟流式: {type(e).__name__}: {e}")
                    # 回退到非流式调用并模拟流式输出
                    async for chunk in self._fallback_to_simulated_stream(prompt, agent_name):
                        yield chunk
                    return

            except httpx.RequestError as e:
                # 网络错误等，直接执行原有的回退逻辑
                logger.error(f"httpx 流式请求错误: {e}")
                logger.warning(f"httpx流式调用失败，回退到模拟流式: {type(e).__name__}: {e}")
                async for chunk in self._fallback_to_simulated_stream(prompt, agent_name):
                    yield chunk
                return

    async def _invoke_openai_stream_single_attempt(self, prompt: str, agent_name: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        单次流式调用OpenAI兼容API（不包含重试逻辑）
        """
        # 优先使用 httpx 的 client.stream 进行流式请求
        model_name = self.get_model_name_for_agent(agent_name)
        request_data = self._build_request_data(prompt, stream=True, agent_name=agent_name)
        logger.info(f"Sending streaming request to OpenAI API using httpx.stream: model={model_name}, agent={agent_name}, prompt_length={len(prompt)}")

        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=request_data,
            timeout=self._get_timeout_config(is_stream=True)
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

    async def _fallback_to_simulated_stream(self, prompt: str, agent_name: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        回退到非流式调用并模拟流式输出
        """
        try:
            result = await self._invoke_openai(prompt, agent_name)
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