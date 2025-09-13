"""
AI分析路由器 - 提供AI投资决策分析的API端点
"""

import logging
import asyncio
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional

from stockaivo.ai.orchestrator import run_ai_analysis, run_ai_analysis_stream, run_ai_analysis_parallel_stream
from stockaivo.exceptions import AIServiceException, ValidationException, create_error_response
from stockaivo.ai.agents import structured_prediction_agent, _is_llm_error_result
from stockaivo.ai.agents import data_collection_agent, technical_analysis_agent, fundamental_analysis_agent, news_sentiment_analysis_agent
from stockaivo.data_service import get_market_aware_current_date
from stockaivo.ai.state import GraphState
from stockaivo.models import StockPrediction
from stockaivo.dependencies import DatabaseDep

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/ai", tags=["AI分析"])

# 移除全局状态管理，改为直接流式响应


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    ticker: str = Field(..., description="股票代码，例如 'AAPL'")
    end_date: Optional[date] = Field(None, description="自定义结束日期 (YYYY-MM-DD)，开始日期由系统根据数据周期自动计算")


@router.post("/analyze-sequential")
async def analyze_stock_sequential(request: AnalysisRequest) -> StreamingResponse:
    """
    启动AI投资分析并顺序流式返回结果。

    分析代理将按顺序执行，提供逐步的分析过程展示。
    这是一个简化的单一端点，直接返回流式分析结果。
    """
    try:
        logger.info(f"收到AI顺序分析请求: {request.ticker}, 结束日期: {request.end_date}")

        custom_date_range = None
        if request.end_date:
            custom_date_range = {
                "end_date": request.end_date.isoformat()
            }

        # 直接创建并返回流式响应
        analysis_generator = run_ai_analysis_stream(
            ticker=request.ticker,
            custom_date_range=custom_date_range
        )

        async def stream_wrapper():
            """包装生成器以处理错误和清理"""
            try:
                async for event in analysis_generator:
                    yield event
            except asyncio.CancelledError:
                logger.warning("客户端断开了连接，AI顺序分析流已取消。")
                # 客户端断开连接时不需要发送错误事件
            except Exception as e:
                logger.error(f"AI顺序分析过程中发生错误: {e}")
                # 使用统一的错误响应格式
                error_response = create_error_response(
                    message=f"AI顺序分析过程中发生错误: {str(e)}",
                    status_code=500
                )
                error_event = f"data: {error_response}\n\n"
                yield error_event
            finally:
                logger.info("AI顺序分析流结束。")

        return StreamingResponse(stream_wrapper(), media_type="text/event-stream")

    except ValueError as e:
        logger.error(f"AI顺序分析请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"启动AI顺序分析失败: {e}")
        raise AIServiceException(f"启动AI顺序分析失败: {str(e)}")


@router.post("/analyze-parallel")
async def analyze_stock_parallel_stream(request: AnalysisRequest) -> StreamingResponse:
    """
    启动AI投资分析并行流式返回结果。

    三个分析代理（技术分析、基本面分析、新闻情感分析）将并行执行，
    提供更快的分析速度和更好的用户体验。
    """
    try:
        logger.info(f"收到AI并行分析请求: {request.ticker}, 结束日期: {request.end_date}")

        custom_date_range = None
        if request.end_date:
            custom_date_range = {
                "end_date": request.end_date.isoformat()
            }

        # 创建并行流式响应
        analysis_generator = run_ai_analysis_parallel_stream(
            ticker=request.ticker,
            custom_date_range=custom_date_range
        )

        async def parallel_stream_wrapper():
            """包装并行生成器以处理错误和清理"""
            try:
                async for event in analysis_generator:
                    yield event
            except asyncio.CancelledError:
                logger.warning("客户端断开了连接，AI并行分析流已取消。")
                # 客户端断开连接时不需要发送错误事件
            except Exception as e:
                logger.error(f"AI并行分析过程中发生错误: {e}")
                # 使用统一的错误响应格式
                error_response = create_error_response(
                    message=f"AI并行分析过程中发生错误: {str(e)}",
                    status_code=500
                )
                error_event = f"data: {error_response}\n\n"
                yield error_event
            finally:
                logger.info("AI并行分析流结束。")

        return StreamingResponse(parallel_stream_wrapper(), media_type="text/event-stream")

    except ValueError as e:
        logger.error(f"AI并行分析请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"启动AI并行分析失败: {e}")
        raise AIServiceException(f"启动AI并行分析失败: {str(e)}")


class StructuredPredictionRequest(BaseModel):
    """结构化预测请求模型"""
    ticker: str = Field(..., description="股票代码，例如 'AAPL'")
    end_date: Optional[date] = Field(None, description="自定义结束日期 (YYYY-MM-DD)，开始日期由系统根据数据周期自动计算")
    save_to_db: bool = Field(True, description="是否保存预测结果到数据库")


class StructuredPredictionResponse(BaseModel):
    """结构化预测响应模型"""
    success: bool = Field(..., description="预测是否成功")
    prediction_probability: Optional[float] = Field(None, description="预测概率值，范围0.0-1.0")
    direction: Optional[str] = Field(None, description="预测方向：UP或DOWN")
    confidence_level: Optional[str] = Field(None, description="置信度：HIGH、MEDIUM或LOW")
    reasoning: Optional[str] = Field(None, description="预测推理说明")
    ticker: str = Field(..., description="股票代码")
    timestamp: str = Field(..., description="预测生成时间")
    market_aware_date: Optional[str] = Field(None, description="市场感知日期")
    error: Optional[str] = Field(None, description="错误信息（如果失败）")


@router.post("/predict-structured", response_model=StructuredPredictionResponse)
async def analyze_stock_structured_prediction(request: StructuredPredictionRequest, db: DatabaseDep) -> StructuredPredictionResponse:
    """
    生成股票结构化预测。
    
    基于综合AI分析生成概率化的股价预测，包括：
    - 预测概率值（0.0-1.0）
    - 预测方向（UP/DOWN）
    - 置信度（HIGH/MEDIUM/LOW） 
    - 详细推理说明
    
    注意：需要技术分析成功执行才能生成预测结果。
    """
    
    try:
        logger.info(f"收到结构化预测请求: {request.ticker}, 结束日期: {request.end_date}")
        
        # 1. 构建完整的AI分析状态，集成多Agent并行分析流程
        # 包含数据收集、技术分析、基本面分析、新闻情感分析的完整工作流
        
        logger.info(f"开始构建分析状态为结构化预测做准备: {request.ticker}")
        
        # 初始化状态
        analysis_state = GraphState(
            ticker=request.ticker,
            custom_date_range=None,
            raw_data={},
            analysis_results={},
            final_report="",
            market_analysis=None
        )
        
        # 添加自定义日期范围
        if request.end_date:
            analysis_state["custom_date_range"] = {
                "end_date": request.end_date.isoformat()
            }
        
        # 2. 并行运行分析agents（优化性能）
        try:
            # 数据收集（必须先完成）
            data_result = await data_collection_agent(analysis_state)
            for key, value in data_result.items():
                if key in analysis_state:
                    analysis_state[key] = value  # type: ignore
            
            # 并行执行三个分析agents
            logger.info(f"开始并行执行分析agents: {request.ticker}")
            analysis_tasks = [
                technical_analysis_agent(analysis_state),  # 技术分析（必需）
                fundamental_analysis_agent(analysis_state),  # 基本面分析（可选）
                news_sentiment_analysis_agent(analysis_state)  # 新闻情感分析（可选）
            ]
            
            # 并行执行，允许部分失败
            analysis_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            
            # 处理技术分析结果（必需，必须成功）
            tech_result = analysis_results[0]
            if isinstance(tech_result, Exception):
                logger.error(f"技术分析失败: {tech_result}")
                raise AIServiceException(f"技术分析失败，无法生成结构化预测: {str(tech_result)}")
            
            # 应用技术分析结果 - 使用合并而不是替换
            if isinstance(tech_result, dict):
                for key, value in tech_result.items():
                    if key == 'analysis_results':
                        # 合并analysis_results，保留data_collector信息
                        current_analysis = analysis_state.get("analysis_results", {})
                        if isinstance(value, dict):
                            current_analysis.update(value)
                        analysis_state[key] = current_analysis  # type: ignore
                    elif key in analysis_state:
                        analysis_state[key] = value  # type: ignore
                
                # 检查技术分析是否真的成功了
                technical_analysis = analysis_state.get("analysis_results", {}).get("technical_analyst")
                if technical_analysis and not _is_llm_error_result(technical_analysis):
                    logger.info("技术分析完成")
                elif technical_analysis and _is_llm_error_result(technical_analysis):
                    logger.error(f"技术分析LLM调用失败: {technical_analysis}")
                else:
                    logger.error("技术分析未返回结果")
            
            # 验证技术分析是否成功
            technical_analysis = analysis_state.get("analysis_results", {}).get("technical_analyst")
            if not technical_analysis or _is_llm_error_result(technical_analysis):
                error_msg = f"技术分析失败，无法生成结构化预测: {technical_analysis}" if technical_analysis else "技术分析未返回有效结果，无法生成结构化预测"
                logger.error(error_msg)
                raise AIServiceException(error_msg)
            
            # 处理基本面分析结果（可选）
            fundamental_result = analysis_results[1]
            if isinstance(fundamental_result, Exception):
                logger.warning(f"基本面分析失败，继续执行: {fundamental_result}")
            else:
                # 确保结果是字典类型才调用items()
                if isinstance(fundamental_result, dict):
                    # 检查是否真的有基本面分析结果
                    fundamental_analysis = fundamental_result.get("analysis_results", {}).get("fundamental_analyst")
                    if fundamental_analysis is not None and not _is_llm_error_result(fundamental_analysis):
                        for key, value in fundamental_result.items():
                            if key == 'analysis_results':
                                # 合并analysis_results，保留已有信息
                                current_analysis = analysis_state.get("analysis_results", {})
                                if isinstance(value, dict):
                                    current_analysis.update(value)
                                analysis_state[key] = current_analysis  # type: ignore
                            elif key in analysis_state:
                                analysis_state[key] = value  # type: ignore
                        logger.info("基本面分析完成")
                    elif fundamental_analysis is not None and _is_llm_error_result(fundamental_analysis):
                        logger.warning(f"基本面分析LLM调用失败: {fundamental_analysis}")
                    else:
                        logger.info("基本面分析跳过")
                else:
                    logger.info("基本面分析跳过")
            
            # 处理新闻情感分析结果（可选）
            news_result = analysis_results[2]
            if isinstance(news_result, Exception):
                logger.warning(f"新闻情感分析失败，继续执行: {news_result}")
            else:
                # 确保结果是字典类型才调用items()
                if isinstance(news_result, dict):
                    # 检查是否真的有新闻情感分析结果
                    news_analysis = news_result.get("analysis_results", {}).get("news_sentiment_analyst")
                    if news_analysis is not None and not _is_llm_error_result(news_analysis):
                        for key, value in news_result.items():
                            if key == 'analysis_results':
                                # 合并analysis_results，保留已有信息
                                current_analysis = analysis_state.get("analysis_results", {})
                                if isinstance(value, dict):
                                    current_analysis.update(value)
                                analysis_state[key] = current_analysis  # type: ignore
                            elif key in analysis_state:
                                analysis_state[key] = value  # type: ignore
                        logger.info("新闻情感分析完成")
                    elif news_analysis is not None and _is_llm_error_result(news_analysis):
                        logger.warning(f"新闻情感分析LLM调用失败: {news_analysis}")
                    else:
                        logger.info("新闻情感分析跳过")
                else:
                    logger.info("新闻情感分析跳过")
            
            logger.info(f"并行分析完成: {request.ticker}")
                
        except Exception as e:
            logger.error(f"分析阶段失败: {e}")
            raise AIServiceException(f"分析阶段失败: {str(e)}")
        
        # 3. 运行结构化预测Agent
        logger.info(f"开始生成结构化预测: {request.ticker}")
        prediction_result = await structured_prediction_agent(analysis_state)
        
        # 4. 处理预测结果
        prediction_data = prediction_result.get("structured_prediction", {})
        
        if not prediction_data.get("success", False):
            # 预测失败
            error_msg = prediction_data.get("error", "结构化预测失败")
            logger.warning(f"结构化预测失败: {request.ticker}, 错误: {error_msg}")
            
            return StructuredPredictionResponse(
                success=False,
                prediction_probability=None,
                direction=None,
                confidence_level=None,
                reasoning=None,
                ticker=request.ticker,
                timestamp=prediction_data.get("timestamp", datetime.now().isoformat()),
                market_aware_date=None,
                error=error_msg
            )
        
        # 5. 预测成功，准备响应数据
        response_data = {
            "success": True,
            "prediction_probability": prediction_data.get("prediction_probability"),
            "direction": prediction_data.get("direction"),
            "confidence_level": prediction_data.get("confidence_level"),
            "reasoning": prediction_data.get("reasoning"),
            "ticker": request.ticker,
            "timestamp": prediction_data.get("timestamp")
        }
        
        # 6. 保存到数据库（如果请求）
        if request.save_to_db:
            try:
                # 从market_analysis获取正确的市场日期信息
                market_analysis = analysis_state.get("market_analysis")
                if market_analysis:
                    market_aware_date = market_analysis.market_aware_date
                    end_date = market_analysis.target_friday_date
                    trading_days = market_analysis.trading_days_count
                else:
                    # 如果没有获取到market_analysis，使用默认方法
                    market_aware_date = get_market_aware_current_date()
                    end_date = request.end_date or date.today()
                    trading_days = 5
                
                response_data["market_aware_date"] = market_aware_date.isoformat()
                
                # 创建StockPrediction实例
                prediction_record = StockPrediction(
                    ticker=request.ticker,
                    market_aware_date=market_aware_date,
                    target_date=end_date,
                    trading_days_count=trading_days,
                    prediction_probability=prediction_data.get("prediction_probability"),
                    direction=prediction_data.get("direction"),
                    confidence_level=prediction_data.get("confidence_level"),
                    reasoning=prediction_data.get("reasoning", "")
                )
                
                # 使用merge处理主键冲突（相同ticker和market_aware_date的记录）
                db.merge(prediction_record)
                db.commit()
                
                logger.info(f"成功保存结构化预测到数据库: {request.ticker}, 市场日期: {market_aware_date}, 目标日期: {end_date}")
                
            except Exception as db_error:
                logger.error(f"保存结构化预测到数据库失败: {db_error}")
                db.rollback()
                # 不影响API响应，只是记录错误
        
        logger.info(f"结构化预测成功: {request.ticker}, 方向={prediction_data.get('direction')}, 概率={prediction_data.get('prediction_probability'):.2f}")
        
        return StructuredPredictionResponse(**response_data)
        
    except ValueError as e:
        logger.error(f"结构化预测请求验证失败: {e}")
        raise ValidationException(f"请求参数验证失败: {str(e)}")
    except AIServiceException as e:
        # 重新抛出AI服务异常
        raise e
    except Exception as e:
        logger.error(f"结构化预测失败: {e}")
        raise AIServiceException(f"结构化预测失败: {str(e)}")