"""
AI Analysis Orchestrator using LangGraph

This file builds and runs the multi-agent workflow for stock analysis.
"""

from langgraph.graph import StateGraph, END  # type: ignore
from stockaivo.ai.state import GraphState
from stockaivo.ai.agents import (
    data_collection_agent,
    technical_analysis_agent,
    fundamental_analysis_agent,
    news_sentiment_analysis_agent,
    synthesis_agent,
    technical_analysis_agent_stream,
    fundamental_analysis_agent_stream,
    news_sentiment_analysis_agent_stream,
    synthesis_agent_stream,
)
from typing import AsyncGenerator, Dict, Any, Optional
import json
import json
import logging

logger = logging.getLogger(__name__)

class LangGraphOrchestrator:
    """
    Orchestrates the multi-agent stock analysis workflow using LangGraph.
    """
    def __init__(self) -> None:
        self.app = self._create_workflow()

    def _create_workflow(self) -> Any:
        """
        Creates the LangGraph workflow by defining nodes and edges.
        """
        # 1. Instantiate the StateGraph with our custom state
        workflow = StateGraph(GraphState)

        # 2. Add nodes to the graph
        # Each node is an agent function we defined earlier.
        workflow.add_node("data_collector", data_collection_agent)
        workflow.add_node("technical_analyst", technical_analysis_agent)
        workflow.add_node("fundamental_analyst", fundamental_analysis_agent)
        workflow.add_node("news_sentiment_analyst", news_sentiment_analysis_agent)
        workflow.add_node("synthesis", synthesis_agent)

        # 3. Define the edges to control the flow
        # This sets up the sequence of operations.

        # Set the entry point of the graph
        workflow.set_entry_point("data_collector")

        # An edge from data collection to the three parallel analysis agents
        workflow.add_edge("data_collector", "technical_analyst")
        workflow.add_edge("data_collector", "fundamental_analyst")
        workflow.add_edge("data_collector", "news_sentiment_analyst")

        # After the parallel analyses are done, they all lead to the synthesis agent
        # Note: LangGraph automatically waits for all incoming edges to a node to complete
        # before running that node. This creates a "fan-in" or synchronization point.
        workflow.add_edge("technical_analyst", "synthesis")
        workflow.add_edge("fundamental_analyst", "synthesis")
        workflow.add_edge("news_sentiment_analyst", "synthesis")

        # The synthesis agent is the final step, so it connects to the END
        workflow.add_edge("synthesis", END)

        # 4. Compile the graph into a runnable application
        return workflow.compile()

    async def run_analysis(self, ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        """
        Runs the full AI analysis workflow for a given stock ticker
        and yields the output of each agent as a JSON string.
        """
        print(f"\n---Starting AI Analysis for {ticker}---")
        
        initial_state = {
            "ticker": ticker,
            "date_range_option": date_range_option,
            "custom_date_range": custom_date_range,
            "analysis_results": {},
            "final_report": ""
        }
        
        # Use astream for async iteration
        async for output in self.app.astream(initial_state):
            for key, value in output.items():
                if value is None: continue

                # Handle different types of outputs
                if key == "synthesis":
                    # For synthesis agent, output the final report
                    final_report = value.get("final_report")
                    if final_report:
                        result_data = {
                            "agent": "synthesis",
                            "output": final_report
                        }
                        yield f"data: {json.dumps(result_data)}\n\n"
                else:
                    # For other agents, output their analysis results
                    agent_name = key.replace('_agent', '')
                    analysis_results = value.get("analysis_results", {})
                    agent_output = analysis_results.get(agent_name)

                    # 只输出非空的分析结果
                    if agent_output is not None:
                        result_data = {
                            "agent": agent_name,
                            "output": agent_output
                        }
                        yield f"data: {json.dumps(result_data)}\n\n"
            
        print("\n---AI Analysis Complete---")

# Instantiate the orchestrator
orchestrator = LangGraphOrchestrator()

# Main async function to run the analysis and stream results
async def run_ai_analysis(ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
    """
    Runs the full AI analysis workflow for a given stock ticker
    and yields the output of each agent as a JSON string.
    """
    async for chunk in orchestrator.run_analysis(ticker, date_range_option, custom_date_range):
        yield chunk


# ==================== 流式版本的Orchestrator ====================

class StreamingLangGraphOrchestrator:
    """
    流式版本的多智能体股票分析工作流编排器
    """
    def __init__(self) -> None:
        pass

    async def run_analysis_stream(self, ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        """
        运行流式AI分析工作流
        """
        print(f"\n=== Starting Streaming AI Analysis for {ticker} ===")

        # 初始化状态
        initial_state: GraphState = {
            "ticker": ticker,
            "date_range_option": date_range_option,
            "custom_date_range": custom_date_range,
            "raw_data": {},
            "analysis_results": {},
            "final_report": ""
        }

        # 1. 数据收集阶段（非流式）
        print("\n---Phase 1: Data Collection---")
        data_collection_result = await data_collection_agent(initial_state)

        # 手动合并状态（在流式版本中需要手动处理状态合并）
        state = initial_state.copy()
        if "raw_data" in data_collection_result:
            state["raw_data"] = {**state.get("raw_data", {}), **data_collection_result["raw_data"]}
        if "analysis_results" in data_collection_result:
            state["analysis_results"] = {**state.get("analysis_results", {}), **data_collection_result["analysis_results"]}

        # 发送数据收集结果
        data_collector_result = state.get("analysis_results", {}).get("data_collector")
        if data_collector_result:
            result_data = {
                "agent": "data_collector",
                "output": data_collector_result
            }
            yield f"data: {json.dumps(result_data)}\n\n"

        # 检查是否有基本面数据和新闻数据
        raw_data = state.get("raw_data", {})
        has_fundamental_data = any(key in raw_data for key in ['financials', 'company_info', 'earnings'])
        has_news_data = 'news' in raw_data and raw_data['news']  # 更准确的新闻数据检查

        # 实现动态阶段编号以适应跳过的分析阶段
        current_phase = 2  # 从技术分析开始

        # 2. 技术分析阶段（流式）
        print(f"\n---Phase {current_phase}: Technical Analysis (Streaming)---")
        async for chunk in technical_analysis_agent_stream(state):
            analysis_results = chunk.get("analysis_results", {})
            technical_result = analysis_results.get("technical_analyst")
            if technical_result:
                # 更新状态
                state["analysis_results"]["technical_analyst"] = technical_result

                # 发送流式结果
                result_data = {
                    "agent": "technical_analyst",
                    "output": technical_result,
                    "streaming": True
                }
                yield f"data: {json.dumps(result_data)}\n\n"

        # 检查技术分析是否有有效结果
        final_technical_result = state.get("analysis_results", {}).get("technical_analyst")

        def is_valid_analysis_result(result: Any) -> bool:
            """检查分析结果是否有效（不是空或错误信息）"""
            if not result or not isinstance(result, str) or result.strip() == "":
                return False
            # 检查是否是错误信息
            error_indicators = [
                "Error calling",
                "HTTP Error",
                "Error:",
                "所有重试都失败了",
                "LLM服务未正确配置"
            ]
            return not any(indicator in result for indicator in error_indicators)

        if not is_valid_analysis_result(final_technical_result):
            print("\n---Technical Analysis returned invalid result, skipping remaining analysis---")
            error_data = {
                "agent": "system",
                "output": "技术分析未返回有效结果，跳过后续分析。",
                "error": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        current_phase += 1

        # 3. 基本面分析阶段（流式，如果有数据）
        if has_fundamental_data:
            print(f"\n---Phase {current_phase}: Fundamental Analysis (Streaming)---")
            async for chunk in fundamental_analysis_agent_stream(state):
                analysis_results = chunk.get("analysis_results", {})
                fundamental_result = analysis_results.get("fundamental_analyst")
                if fundamental_result:
                    # 更新状态
                    state["analysis_results"]["fundamental_analyst"] = fundamental_result

                    # 发送流式结果
                    result_data = {
                        "agent": "fundamental_analyst",
                        "output": fundamental_result,
                        "streaming": True
                    }
                    yield f"data: {json.dumps(result_data)}\n\n"
            current_phase += 1
        else:
            print(f"\n---Skipping Phase {current_phase}: Fundamental Analysis (No data available)---")
            skip_data = {
                "agent": "system",
                "output": "跳过基本面分析：无可用的财务数据。"
            }
            yield f"data: {json.dumps(skip_data)}\n\n"
            current_phase += 1

        # 4. 新闻情感分析阶段（流式，如果有数据）
        if has_news_data:
            print(f"\n---Phase {current_phase}: News Sentiment Analysis (Streaming)---")
            async for chunk in news_sentiment_analysis_agent_stream(state):
                analysis_results = chunk.get("analysis_results", {})
                news_result = analysis_results.get("news_sentiment_analyst")
                if news_result:
                    # 更新状态
                    state["analysis_results"]["news_sentiment_analyst"] = news_result

                    # 发送流式结果
                    result_data = {
                        "agent": "news_sentiment_analyst",
                        "output": news_result,
                        "streaming": True
                    }
                    yield f"data: {json.dumps(result_data)}\n\n"
            current_phase += 1
        else:
            print(f"\n---Skipping Phase {current_phase}: News Sentiment Analysis (No data available)---")
            skip_data = {
                "agent": "system",
                "output": "跳过新闻情感分析：无可用的新闻数据。"
            }
            yield f"data: {json.dumps(skip_data)}\n\n"
            current_phase += 1

        # 5. 综合分析阶段（流式）
        print(f"\n---Phase {current_phase}: Synthesis (Streaming)---")

        # 检查是否有有效的分析结果
        analysis_results = state.get("analysis_results", {})
        has_valid_analysis = any([
            is_valid_analysis_result(analysis_results.get("technical_analyst")),
            is_valid_analysis_result(analysis_results.get("fundamental_analyst")),
            is_valid_analysis_result(analysis_results.get("news_sentiment_analyst"))
        ])

        if not has_valid_analysis:
            error_data = {
                "agent": "system",
                "output": "所有分析阶段都未返回有效结果，无法进行综合分析。",
                "error": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # 执行综合分析
        async for chunk in synthesis_agent_stream(state):
            final_report = chunk.get("final_report")
            if final_report:
                result_data = {
                    "agent": "synthesis",
                    "output": final_report,
                    "streaming": True
                }
                yield f"data: {json.dumps(result_data)}\n\n"

        print("\n---Streaming AI Analysis Complete---")


# ==================== 并行流式版本的Orchestrator ====================

class ParallelStreamingOrchestrator:
    """
    并行流式版本的多智能体股票分析工作流编排器
    支持三个分析代理的真正并行执行和独立流式输出
    """
    def __init__(self) -> None:
        pass

    async def run_parallel_analysis_stream(self, ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        """
        运行并行流式AI分析工作流

        架构设计：
        1. 数据收集阶段（顺序执行）
        2. 三个分析代理并行执行，各自独立流式输出
        3. 综合分析阶段（等待所有分析完成后执行）
        """
        print(f"\n=== Starting Parallel Streaming AI Analysis for {ticker} ===")

        # 初始化状态
        initial_state: GraphState = {
            "ticker": ticker,
            "date_range_option": date_range_option,
            "custom_date_range": custom_date_range,
            "raw_data": {},
            "analysis_results": {},
            "final_report": ""
        }

        # 1. 数据收集阶段（非流式，必须先完成）
        print("\n---Phase 1: Data Collection---")
        try:
            data_collection_result = await data_collection_agent(initial_state)

            # 合并状态
            state = initial_state.copy()
            if "raw_data" in data_collection_result:
                state["raw_data"] = {**state.get("raw_data", {}), **data_collection_result["raw_data"]}
            if "analysis_results" in data_collection_result:
                state["analysis_results"] = {**state.get("analysis_results", {}), **data_collection_result["analysis_results"]}

            # 发送数据收集结果
            data_collector_result = state.get("analysis_results", {}).get("data_collector")
            if data_collector_result:
                result_data = {
                    "agent": "data_collector",
                    "output": data_collector_result,
                    "phase": "data_collection",
                    "streaming": False
                }
                yield f"data: {json.dumps(result_data)}\n\n"

        except Exception as e:
            logger.error(f"数据收集阶段失败: {e}")
            error_data = {
                "agent": "system",
                "output": f"数据收集失败: {str(e)}",
                "error": True,
                "phase": "data_collection"
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # 检查数据可用性
        raw_data = state.get("raw_data", {})
        has_fundamental_data = any(key in raw_data for key in ['financials', 'company_info', 'earnings'])
        has_news_data = 'news' in raw_data and raw_data['news']

        # 发送数据可用性信息给前端
        available_analyses = ['technical_analysis']  # 技术分析总是可用
        if has_fundamental_data:
            available_analyses.append('fundamental_analysis')
        if has_news_data:
            available_analyses.append('news_sentiment')

        availability_info = {
            "agent": "system",
            "output": f"数据检查完成，将执行以下分析: {', '.join(available_analyses)}",
            "phase": "data_collection",
            "available_analyses": available_analyses,
            "streaming": False
        }
        yield f"data: {json.dumps(availability_info)}\n\n"

        # 2. 并行分析阶段
        print("\n---Phase 2: Parallel Analysis (Technical, Fundamental, News Sentiment)---")

        # 创建并行任务列表
        parallel_tasks = []
        task_names = []

        # 技术分析（总是执行）
        parallel_tasks.append(self._run_technical_analysis_stream(state))
        task_names.append("technical_analysis")

        # 基本面分析（如果有数据）
        if has_fundamental_data:
            parallel_tasks.append(self._run_fundamental_analysis_stream(state))
            task_names.append("fundamental_analysis")

        # 新闻情感分析（如果有数据）
        if has_news_data:
            parallel_tasks.append(self._run_news_sentiment_stream(state))
            task_names.append("news_sentiment")

        # 并行执行所有分析任务并合并流式输出
        async for merged_result in self._merge_parallel_streams_v2(parallel_tasks, task_names, state):
            yield merged_result

        # 3. 综合分析阶段（等待所有分析完成）
        print("\n---Phase 3: Synthesis (waiting for all analyses to complete)---")

        # 检查是否有有效的分析结果
        analysis_results = state.get("analysis_results", {})
        has_valid_analysis = any([
            self._is_valid_analysis_result(analysis_results.get("technical_analyst")),
            self._is_valid_analysis_result(analysis_results.get("fundamental_analyst")),
            self._is_valid_analysis_result(analysis_results.get("news_sentiment_analyst"))
        ])

        if not has_valid_analysis:
            error_data = {
                "agent": "system",
                "output": "所有分析阶段都未返回有效结果，无法进行综合分析。",
                "error": True,
                "phase": "synthesis"
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # 执行综合分析
        async for chunk in synthesis_agent_stream(state):
            final_report = chunk.get("final_report")
            if final_report:
                result_data = {
                    "agent": "synthesis",
                    "output": final_report,
                    "streaming": True,
                    "phase": "synthesis"
                }
                yield f"data: {json.dumps(result_data)}\n\n"

        print("\n---Parallel Streaming AI Analysis Complete---")

    async def _run_technical_analysis_stream(self, state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
        """运行技术分析流式任务"""
        try:
            async for chunk in technical_analysis_agent_stream(state):
                analysis_results = chunk.get("analysis_results", {})
                technical_result = analysis_results.get("technical_analyst")
                if technical_result:
                    # 更新共享状态
                    state["analysis_results"]["technical_analyst"] = technical_result
                    yield {
                        "agent": "technical_analyst",
                        "output": technical_result,
                        "streaming": True,
                        "phase": "parallel_analysis",
                        "task_type": "technical_analysis"
                    }
        except Exception as e:
            logger.error(f"技术分析流式任务失败: {e}")
            yield {
                "agent": "technical_analyst",
                "output": f"技术分析失败: {str(e)}",
                "error": True,
                "phase": "parallel_analysis",
                "task_type": "technical_analysis"
            }

    async def _run_fundamental_analysis_stream(self, state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
        """运行基本面分析流式任务"""
        try:
            async for chunk in fundamental_analysis_agent_stream(state):
                analysis_results = chunk.get("analysis_results", {})
                fundamental_result = analysis_results.get("fundamental_analyst")
                if fundamental_result:
                    # 更新共享状态
                    state["analysis_results"]["fundamental_analyst"] = fundamental_result
                    yield {
                        "agent": "fundamental_analyst",
                        "output": fundamental_result,
                        "streaming": True,
                        "phase": "parallel_analysis",
                        "task_type": "fundamental_analysis"
                    }
        except Exception as e:
            logger.error(f"基本面分析流式任务失败: {e}")
            yield {
                "agent": "fundamental_analyst",
                "output": f"基本面分析失败: {str(e)}",
                "error": True,
                "phase": "parallel_analysis",
                "task_type": "fundamental_analysis"
            }

    async def _run_news_sentiment_stream(self, state: GraphState) -> AsyncGenerator[Dict[str, Any], None]:
        """运行新闻情感分析流式任务"""
        try:
            async for chunk in news_sentiment_analysis_agent_stream(state):
                analysis_results = chunk.get("analysis_results", {})
                news_result = analysis_results.get("news_sentiment_analyst")
                if news_result:
                    # 更新共享状态
                    state["analysis_results"]["news_sentiment_analyst"] = news_result
                    yield {
                        "agent": "news_sentiment_analyst",
                        "output": news_result,
                        "streaming": True,
                        "phase": "parallel_analysis",
                        "task_type": "news_sentiment"
                    }
        except Exception as e:
            logger.error(f"新闻情感分析流式任务失败: {e}")
            yield {
                "agent": "news_sentiment_analyst",
                "output": f"新闻情感分析失败: {str(e)}",
                "error": True,
                "phase": "parallel_analysis",
                "task_type": "news_sentiment"
            }

    async def _merge_parallel_streams(self, parallel_tasks: list, task_names: list, state: GraphState) -> AsyncGenerator[str, None]:
        """
        合并多个并行流式任务的输出

        使用更简单的方法：为每个任务创建独立的协程，使用队列来收集所有输出
        """
        import asyncio
        from asyncio import Queue

        # 创建一个队列来收集所有并行任务的输出
        output_queue: Queue = Queue()

        # 跟踪活跃任务数量
        active_tasks = len(parallel_tasks)

        async def task_runner(task_generator, task_name: str):
            """运行单个流式任务并将输出放入队列"""
            try:
                async for result in task_generator:
                    await output_queue.put(f"data: {json.dumps(result)}\n\n")
            except Exception as e:
                logger.error(f"并行任务 {task_name} 执行失败: {e}")
                error_result = {
                    "agent": task_name.replace("_", "_analyst") if not task_name.endswith("_analyst") else task_name,
                    "output": f"任务执行失败: {str(e)}",
                    "error": True,
                    "phase": "parallel_analysis"
                }
                await output_queue.put(f"data: {json.dumps(error_result)}\n\n")
            finally:
                # 任务完成，减少活跃任务计数
                nonlocal active_tasks
                active_tasks -= 1
                # 放入一个特殊标记表示任务完成
                await output_queue.put(None)

        # 启动所有并行任务
        tasks = []
        for i, task_generator in enumerate(parallel_tasks):
            task_name = task_names[i]
            task = asyncio.create_task(task_runner(task_generator, task_name))
            tasks.append(task)

        # 从队列中读取输出并转发
        completed_tasks = 0
        try:
            while completed_tasks < len(parallel_tasks):
                # 等待队列中的下一个输出
                output = await output_queue.get()

                if output is None:
                    # 收到任务完成标记
                    completed_tasks += 1
                    continue

                # 转发输出
                yield output

        except Exception as e:
            logger.error(f"并行流合并过程中发生错误: {e}")
            error_result = {
                "agent": "system",
                "output": f"并行处理失败: {str(e)}",
                "error": True,
                "phase": "parallel_analysis"
            }
            yield f"data: {json.dumps(error_result)}\n\n"
        finally:
            # 清理所有任务
            for task in tasks:
                if not task.done():
                    task.cancel()

            # 等待所有任务完成清理
            await asyncio.gather(*tasks, return_exceptions=True)

    def _is_valid_analysis_result(self, result: Any) -> bool:
        """检查分析结果是否有效（不是空或错误信息）"""
        if not result or not isinstance(result, str) or result.strip() == "":
            return False
        # 检查是否是错误信息
        error_indicators = [
            "Error calling",
            "HTTP Error",
            "Error:",
            "所有重试都失败了",
            "LLM服务未正确配置",
            "失败:"
        ]
        return not any(indicator in result for indicator in error_indicators)

    async def _merge_parallel_streams_v2(self, parallel_tasks: list, task_names: list, state: GraphState) -> AsyncGenerator[str, None]:
        """
        改进的并行流合并方法
        使用真正的并行执行：每个任务独立运行，实时转发输出
        """
        import asyncio
        from asyncio import Queue

        # 创建输出队列
        output_queue: Queue = Queue()
        active_tasks = len(parallel_tasks)

        async def stream_forwarder(task_generator, task_name: str):
            """转发单个流的输出到队列"""
            try:
                async for result in task_generator:
                    await output_queue.put(f"data: {json.dumps(result)}\n\n")
            except Exception as e:
                logger.error(f"并行任务 {task_name} 执行失败: {e}")
                error_result = {
                    "agent": task_name.replace("_", "_analyst") if not task_name.endswith("_analyst") else task_name,
                    "output": f"任务执行失败: {str(e)}",
                    "error": True,
                    "phase": "parallel_analysis"
                }
                await output_queue.put(f"data: {json.dumps(error_result)}\n\n")
            finally:
                nonlocal active_tasks
                active_tasks -= 1
                if active_tasks == 0:
                    await output_queue.put(None)  # 结束标记

        # 启动所有并行任务
        tasks = []
        for i, task_generator in enumerate(parallel_tasks):
            task_name = task_names[i]
            task = asyncio.create_task(stream_forwarder(task_generator, task_name))
            tasks.append(task)

        # 从队列中读取并转发输出
        try:
            while True:
                output = await output_queue.get()
                if output is None:  # 结束标记
                    break
                yield output
        except Exception as e:
            logger.error(f"并行流合并过程中发生错误: {e}")
            error_result = {
                "agent": "system",
                "output": f"并行处理失败: {str(e)}",
                "error": True,
                "phase": "parallel_analysis"
            }
            yield f"data: {json.dumps(error_result)}\n\n"
        finally:
            # 清理所有任务
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # run_analysis_stream 方法已移至 StreamingLangGraphOrchestrator 类中


# 流式orchestrator实例
streaming_orchestrator = StreamingLangGraphOrchestrator()

# 并行流式orchestrator实例
parallel_streaming_orchestrator = ParallelStreamingOrchestrator()

# 流式分析主函数
async def run_ai_analysis_stream(ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
    """
    运行流式AI分析工作流并产生结果
    """
    async for chunk in streaming_orchestrator.run_analysis_stream(ticker, date_range_option, custom_date_range):
        yield chunk

# 并行流式分析主函数
async def run_ai_analysis_parallel_stream(ticker: str, date_range_option: Optional[str] = None, custom_date_range: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
    """
    运行并行流式AI分析工作流并产生结果
    三个分析代理（技术分析、基本面分析、新闻情感分析）将并行执行
    """
    async for chunk in parallel_streaming_orchestrator.run_parallel_analysis_stream(ticker, date_range_option, custom_date_range):
        yield chunk

# Example usage for testing
async def main() -> None:
    """Main async function to test the orchestrator."""
    async for chunk in run_ai_analysis("AAPL"):
        print(chunk)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())