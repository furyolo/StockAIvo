# file: stockaivo/background_scheduler.py

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from stockaivo.database import get_db
from stockaivo.database_writer import persist_pending_data

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(daemon=True)

def scheduled_persist_job():
    """
    一个预定的作业，用于持久化挂起的数据。
    为每个作业运行创建一个新的数据库会话。
    """
    logger.info("开始执行预定的数据持久化任务...")
    db_session: Session | None = None
    try:
        db_session = next(get_db())
        logger.info(f"使用数据库会话 {db_session} 执行持久化任务。")
        result = persist_pending_data(db_session)
        logger.info(f"预定任务完成. 结果: {result}")
    except Exception as e:
        logger.error(f"在预定的持久化任务中发生错误: {e}", exc_info=True)
    finally:
        if db_session:
            logger.info(f"关闭数据库会话 {db_session}。")
            db_session.close()

def start_scheduler():
    """
    启动后台调度器。
    """
    if not scheduler.running:
        scheduler.add_job(
            func=scheduled_persist_job,
            trigger="interval",
            minutes=5,
            id="persist_pending_data_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info("后台数据持久化调度器已启动，每5分钟运行一次。")
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