# main_bot.py
import logging
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from utils.storage import DataStorage
from filters.admin_filter import AdminFilter
from utils.reports import scheduled_line_status_report
from utils.reminders import check_pending_requests_for_reminders

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger(__name__)


# --- Планировщик задач (старый отчет по простоям) ---
# Новый отчет о статусе линий и напоминания вынесены в свои модули
async def scheduled_shift_report(bot: Bot, storage: DataStorage, shift_type: str, description: str):
    """
    Формирует и рассылает отчеты о простоях по окончании смены.
    """
    from utils.reports import get_shift_time_range, generate_admin_shift_summary
    logger.info(f"Запуск планового отчета для '{description}'")
    start_dt, end_dt = get_shift_time_range(shift_type)
    if not start_dt or not end_dt:
        logger.error(f"Не удалось определить рамки смены для отчета '{description}'")
        return

    # Отправка сводки администраторам
    admin_ids = [uid for uid, role in storage.user_roles.items() if storage.is_admin(uid)]
    if admin_ids:
        summary_text = await generate_admin_shift_summary(start_dt, end_dt, storage)
        for admin_id in admin_ids:
            try:
                await bot.send_message(int(admin_id), summary_text, parse_mode=types.ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Ошибка отправки сводки админу {admin_id}: {e}")

    # Отправка уведомления в общий чат
    if config.REPORTS_CHAT_IDS:
        report_period_str = f"c {start_dt.strftime('%H:%M %d.%m')} по {end_dt.strftime('%H:%M %d.%m')}"
        message_text = f"Сформирован отчет по простоям за {description.lower()} {report_period_str}"
        sheet_url = f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/"
        
        for chat_id in config.REPORTS_CHAT_IDS:
            try:
                await bot.send_message(int(chat_id), f"{message_text}\n\n[Открыть таблицу]({sheet_url})", parse_mode=types.ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Ошибка отправки отчета в чат {chat_id}: {e}")


# --- Жизненный цикл бота ---
async def on_startup(dp: Dispatcher):
    """
    Выполняется при запуске бота.
    """
    logger.warning("--- ЗАПУСК БОТА ---")
    bot = dp.bot
    
    storage: DataStorage = dp['storage']
    await storage.initialize()
    if not storage.gspread_client:
        logger.critical("Не удалось инициализировать gspread клиент. Бот может работать некорректно.")

    # Настройка и запуск планировщика
    scheduler = AsyncIOScheduler(timezone=config.SCHEDULER_TIMEZONE)
    
    # 1. Отчеты о простоях по сменам (в 08:05 и 20:05)
    scheduler.add_job(scheduled_shift_report, 'cron', hour=8, minute=5, args=[bot, storage, 'previous', "Ночная смена"])
    scheduler.add_job(scheduled_shift_report, 'cron', hour=20, minute=5, args=[bot, storage, 'previous', "Дневная смена"])
    
    # 2. Отчет о статусе линий за 5 минут до конца смены (в 07:55 и 19:55)
    scheduler.add_job(scheduled_line_status_report, 'cron', hour=7, minute=55, args=[bot, storage])
    scheduler.add_job(scheduled_line_status_report, 'cron', hour=19, minute=55, args=[bot, storage])
    
    # 3. Проверка "зависших" заявок для напоминаний (каждые 5 минут)
    scheduler.add_job(check_pending_requests_for_reminders, 'interval', minutes=5, args=[bot, storage])
    
    # 4. Технические задачи
    scheduler.add_job(storage.refresh_downtime_cache, 'interval', seconds=config.CACHE_REFRESH_INTERVAL_SECONDS, args=[bot])
    scheduler.add_job(storage.initialize, 'interval', hours=6)
    
    scheduler.start()
    dp['scheduler'] = scheduler
    logger.info("Планировщик задач запущен.")


async def on_shutdown(dp: Dispatcher):
    """
    Выполняется при остановке бота.
    """
    logger.warning("--- ОСТАНОВКА БОТА ---")
    scheduler = dp.get('scheduler')
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик остановлен.")
        
    await dp.storage.close()
    await dp.storage.wait_closed()
    session = await dp.bot.get_session()
    if session and not session.closed:
        await session.close()
    logger.info("Все ресурсы освобождены.")


def main():
    """
    Главная функция, собирающая и запускающая бота.
    """
    # Инициализация основных объектов
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    storage_fsm = MemoryStorage()
    dp = Dispatcher(bot, storage=storage_fsm)
    
    # Создание и передача хранилища данных через dp
    data_storage = DataStorage()
    dp['storage'] = data_storage
    
    # Регистрация фильтров
    dp.filters_factory.bind(AdminFilter)
    
    # Регистрация обработчиков
    logger.info("Регистрация обработчиков...")
    from handlers import admin_handlers
    from handlers import downtime_handlers
    from handlers import other_handlers

    admin_handlers.register_admin_handlers(dp)
    downtime_handlers.register_downtime_handlers(dp)
    other_handlers.register_other_handlers(dp)
    
    # Запуск
    executor.start_polling(
        dispatcher=dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
    )

if __name__ == '__main__':
    main()