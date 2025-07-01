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
)
from typing import AsyncGenerator
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
                # Yield a JSON string for each agent's output
                agent_name = key.replace('_agent', '')
                result_data = {
                    "agent": agent_name,
                    "output": value.get("analysis_results", {}).get(agent_name) or value.get("final_report")
                }
                if result_data["output"]: # Only yield if there is content
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

# Example usage for testing
async def main():
    """Main async function to test the orchestrator."""
    async for chunk in run_ai_analysis("AAPL"):
        print(chunk)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())