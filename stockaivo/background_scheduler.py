# file: stockaivo/background_scheduler.py

import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Dict, Any, Optional, cast
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.engine import Result, CursorResult
from stockaivo.database import get_db
from stockaivo.database_writer import persist_pending_data


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# 调整默认任务参数，允许短暂延迟并避免重复触发
scheduler = BackgroundScheduler(
    daemon=True,
    job_defaults={
        "coalesce": True,
        "misfire_grace_time": 300,
        "max_instances": 1,
    },
)

def scheduled_persist_job():
    """
    一个预定的作业，用于持久化挂起的数据。
    为每个作业运行创建一个新的数据库会话。
    支持股票价格数据的批量持久化。
    """
    logger.info("开始执行预定的数据持久化任务...")
    job_start_utc = datetime.now(timezone.utc)
    job_timer = perf_counter()
    db_session: Session | None = None
    result: Dict[str, Any] = {"success": False}

    try:
        db_session = next(get_db())
        logger.info("执行持久化任务")
        result = persist_pending_data(db_session)

        if result.get("success"):
            processed_count = result.get("processed_count", 0)
            failed_count = result.get("failed_count", 0)
            pending_count = result.get("pending_count", 0)
            logger.info(
                "预定任务完成 - 总处理: %s 条, 失败: %s 条, Redis 待处理键: %s",
                processed_count,
                failed_count,
                pending_count,
            )
        else:
            logger.error(f"预定任务执行失败: {result.get('message', '未知错误')}")

    except Exception as e:
        logger.error(f"在预定的持久化任务中发生错误: {e}", exc_info=True)
    finally:
        if db_session:
            db_session.close()

        duration = perf_counter() - job_timer
        if result.get("success"):
            logger.info(
                "持久化任务完成 - 处理: %s 条, 失败: %s 条, 耗时: %.2f 秒",
                result.get("processed_count", 0),
                result.get("failed_count", 0),
                duration,
            )





def start_scheduler():
    """
    启动后台调度器。
    """
    if not scheduler.running:
        # 添加数据持久化任务（每8分钟执行一次）
        scheduler.add_job(
            func=scheduled_persist_job,
            trigger="interval",
            minutes=8,
            id="persist_pending_data_job",
            replace_existing=True
        )

        scheduler.start()
        logger.info("后台调度器已启动:")
        logger.info("- 数据持久化任务: 每8分钟运行一次")
    else:
        logger.info("调度器已在运行。")

def stop_scheduler():
    """
    关闭后台调度器。
    """
    if scheduler.running:
        logger.info("正在关闭后台调度器...")
        scheduler.shutdown()
        logger.info("后台调度器已关闭。")
    else:
        logger.info("调度器未在运行。")


