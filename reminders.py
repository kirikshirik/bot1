# utils/reminders.py
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.utils.markdown import escape_md

from utils.storage import DataStorage
from keyboards.inline import get_end_downtime_keyboard

# --- Константы для напоминаний ---
GROUP_REMINDER_DELAY_MINUTES = 30  # Через сколько минут напомнить группе о непринятой заявке
INITIATOR_REMINDER_DELAY_HOURS = 2 # Через сколько часов напомнить инициатору о незакрытой заявке

async def check_pending_requests_for_reminders(bot: Bot, storage: DataStorage):
    """
    Проверяет все активные заявки и отправляет напоминания, если они "зависли".
    Эта функция будет вызываться планировщиком каждые несколько минут.
    """
    logging.info("[REMINDER_CHECK] Запуск проверки заявок для напоминаний...")
    now = datetime.now()
    # Копируем ключи, чтобы избежать ошибок при изменении словаря во время итерации
    request_ids = list(storage.pending_requests.keys())
    
    reminders_sent_count = 0

    for request_id in request_ids:
        request_data = storage.pending_requests.get(request_id)
        if not request_data:
            continue

        status = request_data.get("status")
        
        try:
            # --- 1. Напоминание для группы о НЕПРИНЯТОЙ заявке ---
            if status == "pending_acceptance":
                creation_time = datetime.fromisoformat(request_data.get("creation_time", now.isoformat()))
                age = now - creation_time
                
                if age > timedelta(minutes=GROUP_REMINDER_DELAY_MINUTES) and request_data.get("reminders_sent_group", 0) == 0:
                    group_id = request_data["responsible_group_id"]
                    original_msg_id = request_data["group_notification_message_id"]
                    reminder_text = "⚠️ **Напоминание:** Эта заявка не принята в работу уже более 30 минут!"
                    
                    await bot.send_message(
                        chat_id=group_id,
                        text=reminder_text,
                        reply_to_message_id=original_msg_id,
                        parse_mode="Markdown"
                    )
                    request_data["reminders_sent_group"] = 1
                    reminders_sent_count += 1
                    logging.info(f"[REMINDER] Отправлено напоминание группе {group_id} по заявке {request_id}")

            # --- 2. Напоминание для инициатора о НЕЗАКРЫТОЙ заявке ---
            elif status == "pending_initiator_closure":
                group_completion_time_iso = request_data.get("group_completion_time")
                if not group_completion_time_iso: continue
                
                group_completion_time = datetime.fromisoformat(group_completion_time_iso)
                age_since_completion = now - group_completion_time

                if age_since_completion > timedelta(hours=INITIATOR_REMINDER_DELAY_HOURS) and request_data.get("reminders_sent_initiator", 0) == 0:
                    initiator_chat_id = request_data["initiating_user_chat_id"]
                    reminder_text = (f"⚠️ **Напоминание:**\n\n"
                                     f"Работа по вашей заявке на линии "
                                     f"**{escape_md(request_data.get('ls_name', ''))}** "
                                     f"была завершена ответственной группой более {INITIATOR_REMINDER_DELAY_HOURS} часов назад. "
                                     f"Пожалуйста, закройте запись о простое, нажав на одну из кнопок ниже.")
                    
                    await bot.send_message(
                        chat_id=initiator_chat_id,
                        text=reminder_text,
                        reply_markup=get_end_downtime_keyboard(),
                        parse_mode="Markdown"
                    )
                    request_data["reminders_sent_initiator"] = 1
                    reminders_sent_count += 1
                    logging.info(f"[REMINDER] Отправлено напоминание инициатору {initiator_chat_id} по заявке {request_id}")

        except Exception as e:
            logging.error(f"[REMINDER_CHECK] Ошибка при обработке заявки {request_id}: {e}")

    if reminders_sent_count > 0:
        logging.info(f"[REMINDER_CHECK] Проверка завершена. Отправлено напоминаний: {reminders_sent_count}.")