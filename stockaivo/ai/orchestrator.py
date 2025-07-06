"""
AI Analysis Orchestrator using LangGraph

This file builds and runs the multi-agent workflow for stock analysis.
"""

from langgraph.graph import StateGraph, END
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
from typing import AsyncGenerator, cast
import json

class LangGraphOrchestrator:
    """
    Orchestrates the multi-agent stock analysis workflow using LangGraph.
    """
    def __init__(self):
        self.app = self._create_workflow()

    def _create_workflow(self):
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

    async def run_analysis(self, ticker: str, date_range_option: str | None = None, custom_date_range: dict | None = None) -> AsyncGenerator[str, None]:
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
async def run_ai_analysis(ticker: str, date_range_option: str | None = None, custom_date_range: dict | None = None) -> AsyncGenerator[str, None]:
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
    def __init__(self):
        pass

    async def run_analysis_stream(self, ticker: str, date_range_option: str | None = None, custom_date_range: dict | None = None) -> AsyncGenerator[str, None]:
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
        state = cast(GraphState, await data_collection_agent(initial_state))

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
        has_news_data = any(key in raw_data for key in ['news', 'sentiment'])

        # 2. 技术分析阶段（流式）
        print("\n---Phase 2: Technical Analysis (Streaming)---")
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

        def is_valid_analysis_result(result) -> bool:
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
                "output": "技术分析未返回有效结果，可能是网络连接问题或API服务异常。请稍后重试。",
                "streaming": False,
                "error": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        # 3. 基本面分析阶段（流式，如果有数据）
        if has_fundamental_data:
            print("\n---Phase 3: Fundamental Analysis (Streaming)---")
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
        else:
            print("\n---Skipping Fundamental Analysis (no data)---")

        # 4. 新闻情感分析阶段（流式，如果有数据）
        if has_news_data:
            print("\n---Phase 4: News Sentiment Analysis (Streaming)---")
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
        else:
            print("\n---Skipping News Sentiment Analysis (no data)---")

        # 5. 综合分析阶段（流式）- 检查是否有足够的分析结果
        analysis_results = state.get("analysis_results", {})
        technical_result = analysis_results.get("technical_analyst")
        fundamental_result = analysis_results.get("fundamental_analyst")
        news_result = analysis_results.get("news_sentiment_analyst")

        # 检查是否至少有一个有效的分析结果
        has_valid_analysis = any([
            is_valid_analysis_result(technical_result),
            is_valid_analysis_result(fundamental_result),
            is_valid_analysis_result(news_result)
        ])

        if not has_valid_analysis:
            print("\n---No valid analysis results available, skipping synthesis---")
            error_data = {
                "agent": "system",
                "output": "所有分析阶段都未返回有效结果，无法进行综合分析。请检查数据源或稍后重试。",
                "streaming": False,
                "error": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            return

        print("\n---Phase 5: Synthesis (Streaming)---")
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


# 流式orchestrator实例
streaming_orchestrator = StreamingLangGraphOrchestrator()

# 流式分析主函数
async def run_ai_analysis_stream(ticker: str, date_range_option: str | None = None, custom_date_range: dict | None = None) -> AsyncGenerator[str, None]:
    """
    运行流式AI分析工作流并产生结果
    """
    async for chunk in streaming_orchestrator.run_analysis_stream(ticker, date_range_option, custom_date_range):
        yield chunk

# Example usage for testing
async def main():
    """Main async function to test the orchestrator."""
    async for chunk in run_ai_analysis("AAPL"):
        print(chunk)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())