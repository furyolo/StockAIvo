"""
LangGraph State Definition for StockAIvo

This file defines the shared state object that is passed between nodes in the
LangGraph workflow.
"""

from typing import Dict, Any, TypedDict, Annotated

def merge_dicts(left: dict, right: dict) -> dict:
    """Merges two dictionaries, overwriting left with right."""
    return {**left, **right}

class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        ticker: The stock ticker to analyze.
        raw_data: Raw data collected by the data collection agent.
        analysis_results: A dictionary to store the results from each agent.
        final_report: The final, synthesized report.
    """
    ticker: str
    date_range_option: str | None
    custom_date_range: dict | None
    raw_data: Annotated[dict, merge_dicts]
    analysis_results: Annotated[dict, merge_dicts]
    final_report: str