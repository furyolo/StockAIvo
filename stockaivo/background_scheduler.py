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
    支持股票价格数据和新闻数据的批量持久化。
    """
    # 增强定时任务日志记录以监控新闻数据处理状态
    logger.info("开始执行预定的数据持久化任务（包括股票价格和新闻数据）...")
    db_session: Session | None = None
    try:
        db_session = next(get_db())
        logger.info(f"使用数据库会话 {db_session} 执行持久化任务。")
        result = persist_pending_data(db_session)

        # 详细记录处理结果
        if result.get('success'):
            processed_count = result.get('processed_count', 0)
            failed_count = result.get('failed_count', 0)
            details = result.get('details', [])

            # 统计不同类型数据的处理情况
            news_count = sum(1 for d in details if d.get('period') == 'news')
            price_count = len(details) - news_count

            logger.info(f"预定任务完成 - 总处理: {processed_count} 条, 失败: {failed_count} 条")
            logger.info(f"数据类型分布 - 新闻数据: {news_count} 批次, 价格数据: {price_count} 批次")
        else:
            logger.error(f"预定任务执行失败: {result.get('message', '未知错误')}")

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