"""
AI分析路由器 - 提供AI投资决策分析的API端点
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from enum import Enum
from datetime import date, timedelta

from stockaivo.ai.orchestrator import run_ai_analysis, run_ai_analysis_stream

# 导入现代化异常处理模块
from ..exceptions import AIServiceException, ValidationException, create_error_response

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/ai", tags=["AI分析"])

# 移除全局状态管理，改为直接流式响应


class DateRangeOptions(str, Enum):
    """预设的日期范围选项"""
    # 日线数据选项
    PAST_30_DAYS = "past_30_days"
    PAST_60_DAYS = "past_60_days"
    PAST_90_DAYS = "past_90_days"
    PAST_180_DAYS = "past_180_days"
    PAST_1_YEAR = "past_1_year"

    # 周线数据选项
    PAST_8_WEEKS = "past_8_weeks"
    PAST_16_WEEKS = "past_16_weeks"
    PAST_24_WEEKS = "past_24_weeks"
    PAST_52_WEEKS = "past_52_weeks"


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
async def analyze_stock_stream(nested_request: NestedAnalysisRequest):
    """
    启动AI投资分析并流式返回结果。

    这是一个简化的单一端点，直接返回流式分析结果，
    无需额外的GET请求。
    """
    try:
        request = nested_request.value
        logger.info(f"收到AI分析请求: {request.ticker}, 日期选项: {request.date_range_option}, 自定义范围: {request.start_date}-{request.end_date}")

        custom_date_range = None
        if request.start_date and request.end_date:
            custom_date_range = {
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat()
            }

        # 直接创建并返回流式响应
        analysis_generator = run_ai_analysis_stream(
            ticker=request.ticker,
            date_range_option=request.date_range_option.value if request.date_range_option else None,
            custom_date_range=custom_date_range
        )

        async def stream_wrapper():
            """包装生成器以处理错误和清理"""
            try:
                async for event in analysis_generator:
                    yield event
            except asyncio.CancelledError:
                logger.warning("客户端断开了连接，AI分析流已取消。")
                # 客户端断开连接时不需要发送错误事件
            except Exception as e:
                logger.error(f"AI分析过程中发生错误: {e}")
                # 使用统一的错误响应格式
                error_response = create_error_response(
                    message=f"AI分析过程中发生错误: {str(e)}",
                    status_code=500
                )
                error_event = f"data: {error_response}\n\n"
                yield error_event
            finally:
                logger.info("AI分析流结束。")

        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

    except ValueError as e:
        logger.error(f"AI分析请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"启动AI分析失败: {e}")
        raise AIServiceException(f"启动AI分析失败: {str(e)}")