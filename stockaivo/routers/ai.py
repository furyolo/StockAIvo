"""
AI分析路由器 - 提供AI投资决策分析的API端点
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from enum import Enum
from datetime import date, timedelta

from stockaivo.ai.orchestrator import run_ai_analysis

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/ai", tags=["AI分析"])


class DateRangeOptions(str, Enum):
    """预设的日期范围选项"""
    PAST_30_DAYS = "past_30_days"
    PAST_60_DAYS = "past_60_days"
    PAST_90_DAYS = "past_90_days"
    PAST_8_WEEKS = "past_8_weeks"
    PAST_16_WEEKS = "past_16_weeks"
    PAST_24_WEEKS = "past_24_weeks"
    FULL_HISTORY = "full_history"


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    ticker: str = Field(..., description="股票代码，例如 'AAPL'")
    date_range_option: Optional[DateRangeOptions] = Field(None, description="选择一个预设的日期范围")
    start_date: Optional[date] = Field(None, description="自定义开始日期 (YYYY-MM-DD)")
    end_date: Optional[date] = Field(None, description="自定义结束日期 (YYYY-MM-DD)")

    @model_validator(mode='before')
    @classmethod
    def validate_date_range(cls, data):
        """验证日期范围的逻辑"""
        option = data.get('date_range_option')
        start = data.get('start_date')
        end = data.get('end_date')

        # 如果选择了预设选项，则不能使用自定义日期
        if option and (start or end):
            raise ValueError("当选择预set日期范围时，不能提供自定义的 start_date 或 end_date")

        # 如果提供了自定义日期，则必须同时提供开始和结束
        if bool(start) ^ bool(end):
            raise ValueError("必须同时提供 start_date 和 end_date")

        # 确保结束日期不晚于开始日期
        if start and end and date.fromisoformat(end) < date.fromisoformat(start):
            raise ValueError("end_date 不能早于 start_date")

        # 如果没有提供任何日期选项，则由 agent 处理默认值
        if not option and not start and not end:
            pass
            
        return data


class NestedAnalysisRequest(BaseModel):
    """用于处理来自前端的嵌套请求结构"""
    summary: str
    value: AnalysisRequest


@router.post("/analyze")
async def stream_ai_analysis(nested_request: NestedAnalysisRequest):
    """
    启动并流式传输AI投资分析结果。

    此端点将实时返回每个AI Agent的分析结果。
    您可以选择一个预
    设的日期范围，或提供一个自定义的日期范围。
    """
    try:
        request = nested_request.value
        logger.info(f"收到AI流式分析请求: {request.ticker}, 日期选项: {request.date_range_option}, 自定义范围: {request.start_date}-{request.end_date}")
        
        custom_date_range = None
        if request.start_date and request.end_date:
            custom_date_range = {
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat()
            }

        # 返回一个流式响应
        return StreamingResponse(
            run_ai_analysis(
                ticker=request.ticker,
                date_range_option=request.date_range_option.value if request.date_range_option else None,
                custom_date_range=custom_date_range
            ),
            media_type="text/event-stream"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"启动AI流式分析失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"启动AI流式分析失败: {str(e)}"
        )