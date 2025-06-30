# handlers/downtime_handlers.py
import logging
from datetime import datetime
import json
import asyncio

from aiogram import Dispatcher, types, Bot
from aiogram.types import ContentType
from aiogram.dispatcher import FSMContext
from pytz import timezone

from fsm import DowntimeForm
from utils.storage import DataStorage
from config import (PRODUCTION_SITES, LINES_SECTIONS, DOWNTIME_REASONS, SCHEDULER_TIMEZONE)
from keyboards import inline
from utils.reports import calculate_shift_times
from g_sheets.api import append_downtime_record, get_next_sequence_number

# --- Начало и навигация в FSM ---

async def start_downtime_entry(message: types.Message, state: FSMContext):
    """Начинает процесс ввода данных о простое."""
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    
    logging.info(f"User {message.from_user.id} начал ввод простоя.")
    await state.finish()
    if not storage.responsible_groups:
        logging.warning("Список ответственных групп пуст. Попытка перезагрузки...")
        await storage.load_responsible_groups()
        if not storage.responsible_groups:
             await message.answer("⚠️ Список ответственных групп не загружен. Выбор группы будет пропущен.")
    
    await DowntimeForm.choosing_site.set()
    await message.answer("Выберите производственную площадку:", reply_markup=inline.get_sites_keyboard())

async def back_to_sites(cb: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору площадки."""
    await DowntimeForm.choosing_site.set()
    await cb.message.edit_text("Выберите производственную площадку:", reply_markup=inline.get_sites_keyboard())
    await cb.answer()

async def back_to_lines(cb: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору линии."""
    async with state.proxy() as data:
        site_key = data.get('site_key')
    await DowntimeForm.choosing_line_section.set()
    await cb.message.edit_text(
        f"Площадка: {PRODUCTION_SITES[site_key]}.\nВыберите линию/секцию:",
        reply_markup=inline.get_lines_sections_keyboard(site_key)
    )
    await cb.answer()

# --- Шаги FSM ---

async def process_site_choice(cb: types.CallbackQuery, state: FSMContext):
    site_key = cb.data.split('_')[1]
    site_name = PRODUCTION_SITES[site_key]
    await state.update_data(site_key=site_key, site_name=site_name)
    await DowntimeForm.next()
    await cb.message.edit_text(
        f"Площадка: {site_name}.\nВыберите линию/секцию:",
        reply_markup=inline.get_lines_sections_keyboard(site_key)
    )
    await cb.answer()

async def process_line_section_choice(cb: types.CallbackQuery, state: FSMContext):
    ls_key = cb.data.split('_')[1]
    async with state.proxy() as data:
        site_key = data['site_key']
        data['ls_key'] = ls_key
        data['ls_name'] = LINES_SECTIONS[site_key][ls_key]
    await DowntimeForm.next()
    await cb.message.edit_text(
        f"Линия/секция: {data['ls_name']}.\nВыберите направление простоя:",
        reply_markup=inline.get_downtime_reasons_keyboard()
    )
    await cb.answer()

async def process_reason_choice(cb: types.CallbackQuery, state: FSMContext):
    reason_key = cb.data.split('_', 1)[1]
    reason_name = DOWNTIME_REASONS[reason_key]
    await state.update_data(reason_key=reason_key, reason_name=reason_name)
    await DowntimeForm.next()
    await cb.message.edit_text(f"Направление: {reason_name}.\nВведите описание причины или отправьте фото с описанием.")
    await cb.answer()

async def process_description(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    tz = timezone(SCHEDULER_TIMEZONE)
    async with state.proxy() as data:
        data['description'] = message.text
        data['downtime_start_time'] = datetime.now(tz)
        data['photo_file_id'] = "" # Указываем, что фото нет
        # Добавляем линию в словарь активных простоев для отчета о статусе
        storage.active_downtimes[(data['site_name'], data['ls_name'])] = data.get('reason_name', 'Простой')
        logging.info(f"Добавлен активный простой для {data['site_name']}/{data['ls_name']}")
    await DowntimeForm.choosing_responsible_group.set()
    await message.reply("Описание принято.\nВыберите ответственную группу:", reply_markup=inline.get_responsible_groups_keyboard(storage))

async def process_initial_photo(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    tz = timezone(SCHEDULER_TIMEZONE)
    
    photo_file_id = message.photo[-1].file_id
    description = message.caption or "Фото без описания"

    async with state.proxy() as data:
        data['description'] = description
        data['photo_file_id'] = photo_file_id
        data['downtime_start_time'] = datetime.now(tz)
        storage.active_downtimes[(data['site_name'], data['ls_name'])] = data.get('reason_name', 'Простой')
        logging.info(f"Добавлен активный простой c фото для {data['site_name']}/{data['ls_name']}")

    await DowntimeForm.choosing_responsible_group.set()
    await message.reply("Фото и описание приняты.\nВыберите ответственную группу:", reply_markup=inline.get_responsible_groups_keyboard(storage))

async def skip_description(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    tz = timezone(SCHEDULER_TIMEZONE)
    async with state.proxy() as data:
        data['description'] = "Без описания"
        data['downtime_start_time'] = datetime.now(tz)
        data['photo_file_id'] = "" # Указываем, что фото нет
        storage.active_downtimes[(data['site_name'], data['ls_name'])] = data.get('reason_name', 'Простой')
        logging.info(f"Добавлен активный простой для {data['site_name']}/{data['ls_name']}")
    await DowntimeForm.choosing_responsible_group.set()
    await message.reply("Описание пропущено.\nВыберите ответственную группу:", reply_markup=inline.get_responsible_groups_keyboard(storage))

# --- Логика работы с группами ---

async def process_group_choice(cb: types.CallbackQuery, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    bot = cb.bot
    
    group_key = cb.data.split('group_', 1)[1]
    group_name = storage.responsible_groups.get(group_key)
    user = cb.from_user

    if not group_name:
        await cb.message.edit_text("Ошибка: группа не найдена. Попробуйте снова.")
        return

    tz = timezone(SCHEDULER_TIMEZONE)
    async with state.proxy() as data:
        data['responsible_group_name'] = group_name
        if 'downtime_start_time' not in data:
            data['downtime_start_time'] = datetime.now(tz)
    
    fsm_data = await state.get_data()
    group_id = storage.group_ids.get(group_name)

    if not group_id:
        logging.warning(f"ID для группы '{group_name}' не найден. Простой будет зафиксирован без уведомления.")
        await DowntimeForm.waiting_for_downtime_end.set()
        await cb.message.edit_text(f"Группа: {group_name} (ID не найден).\nНажмите, когда простой завершится:",
                                   reply_markup=inline.get_end_downtime_keyboard())
        return

    request_id = f"dt_{user.id}_{int(datetime.now().timestamp())}"
    start_time_obj = fsm_data.get('downtime_start_time')
    start_time_str = start_time_obj.strftime('%H:%M:%S %d.%m.%Y') if start_time_obj else "Неизвестно"

    notif_text = (f"🔔 **Новый простой (ID: {request_id})**\n\n"
                  f"Площадка: {fsm_data.get('site_name', 'Н/Д')}\n"
                  f"Линия/Секция: {fsm_data.get('ls_name', 'Н/Д')}\n"
                  f"Направление: {fsm_data.get('reason_name', 'Н/Д')}\n"
                  f"Описание: {fsm_data.get('description', 'Н/Д')}\n"
                  f"Начало: {start_time_str}\n"
                  f"Заявитель: {user.full_name}")
    
    photo_id = fsm_data.get("photo_file_id")

    try:
        # Отправляем уведомление с фото, если оно есть
        if photo_id:
            msg_to_group = await bot.send_photo(group_id, photo=photo_id, caption=notif_text, parse_mode='Markdown', reply_markup=inline.get_accept_downtime_keyboard(request_id))
        else:
            msg_to_group = await bot.send_message(group_id, notif_text, parse_mode='Markdown', reply_markup=inline.get_accept_downtime_keyboard(request_id))
        
        # Сохраняем заявку для отслеживания и напоминаний
        storage.pending_requests[request_id] = {
            "request_id": request_id,
            "creation_time": datetime.now().isoformat(),
            "status": "pending_acceptance",
            "reminders_sent_group": 0,
            "reminders_sent_initiator": 0,
            "initiating_user_id": user.id,
            "initiating_user_chat_id": cb.message.chat.id,
            "responsible_group_name": group_name,
            "responsible_group_id": group_id,
            "downtime_fsm_data_json": json.dumps(fsm_data, default=str),
            "group_notification_message_id": msg_to_group.message_id,
            "group_notification_text": notif_text,
            "ls_name": fsm_data.get('ls_name', '')
        }
        
        await DowntimeForm.waiting_for_group_acceptance.set()
        await cb.message.edit_text(f"Группа: {group_name}.\nЗаявка отправлена, ожидайте принятия.")
        
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление в группу {group_id}: {e}")
        await cb.message.edit_text("❌ Ошибка отправки уведомления в группу. Проверьте ID и права бота.", reply_markup=inline.get_group_send_fail_keyboard())

async def skip_group_choice(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(responsible_group_name="Не указана")
    await DowntimeForm.waiting_for_downtime_end.set()
    await cb.message.edit_text("Выбор группы пропущен.\nНажмите, когда простой завершится:",
                               reply_markup=inline.get_end_downtime_keyboard())

# --- Завершение и сохранение простоя ---

async def end_downtime_with_comment(cb: types.CallbackQuery, state: FSMContext):
    await DowntimeForm.entering_additional_comment.set()
    await cb.message.edit_text("Введите дополнительный комментарий (например, что было сделано для устранения):")
    await cb.answer()

async def process_additional_comment(message: types.Message, state: FSMContext):
    await state.update_data(additional_comment_initiator=message.text)
    await save_downtime_record(message, state)

async def end_downtime_no_comment(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(additional_comment_initiator="Без доп. комментария")
    await save_downtime_record(cb, state)

async def save_downtime_record(update: types.Update, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    bot = Bot.get_current()
    
    if isinstance(update, types.CallbackQuery):
        user = update.from_user
        chat_id = update.message.chat.id
        try:
            await bot.edit_message_reply_markup(chat_id, update.message.message_id, reply_markup=None)
        except Exception: 
            pass
    else:
        user = update.from_user
        chat_id = update.chat.id
        
    async with state.proxy() as data:
        request_id_to_clear = data.get('request_id')
        next_seq_num = get_next_sequence_number(storage.downtime_ws)
        start_time_val = data.get('downtime_start_time')
        start_time = datetime.fromisoformat(start_time_val) if isinstance(start_time_val, str) else start_time_val

        if not start_time:
            await bot.send_message(chat_id, "❌ Критическая ошибка: Время начала простоя не найдено.")
            await state.finish()
            return
        
        tz = timezone(SCHEDULER_TIMEZONE)
        end_time = datetime.now(tz)
        duration_minutes = max(1, int((end_time - start_time).total_seconds() / 60))
        shift_start_str, shift_end_str = calculate_shift_times(start_time)
        
        record_data = {
            "Порядковый номер заявки": next_seq_num, "Timestamp_записи": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
            "ID_пользователя_Telegram": user.id, "Username_Telegram": user.username or "N/A",
            "Имя_пользователя_Telegram": user.full_name, "Площадка": data.get('site_name', 'Н/Д'),
            "Линия_Секция": data.get('ls_name', 'Н/Д'), "Направление_простоя": data.get('reason_name', 'Н/Д'),
            "Причина_простоя_описание": data.get('description', 'Н/Д'), "Время_простоя_минут": duration_minutes,
            "Начало_смены_простоя": shift_start_str, "Конец_смены_простоя": shift_end_str,
            "Ответственная_группа": data.get('responsible_group_name', 'Не указана'),
            "Кто_принял_заявку_ID": data.get('accepted_by_user_id', ''), "Кто_принял_заявку_Имя": data.get('accepted_by_user_name', ''),
            "Время_принятия_заявки": data.get('acceptance_time', ''), "Кто_завершил_работу_в_группе_ID": data.get('group_completed_by_id', ''),
            "Кто_завершил_работу_в_группе_Имя": data.get('group_completed_by_name', ''), "Время_завершения_работы_группой": data.get('group_completion_time', ''),
            "Дополнительный_комментарий_инициатора": data.get('additional_comment_initiator', 'Без доп. комментария'),
            "ID_Фото": data.get('photo_file_id', '')
        }

    if append_downtime_record(storage.downtime_ws, record_data):
        try:
            line_key = (record_data['Площадка'], record_data['Линия_Секция'])
            if line_key in storage.active_downtimes:
                del storage.active_downtimes[line_key]
                logging.info(f"Удален активный простой для {line_key[0]}/{line_key[1]}")
            if request_id_to_clear and request_id_to_clear in storage.pending_requests:
                del storage.pending_requests[request_id_to_clear]
                logging.info(f"Заявка {request_id_to_clear} успешно закрыта и удалена из отслеживания.")
        except KeyError:
            pass

        await storage.refresh_downtime_cache(bot)
        
        summary_lines = [f"✅ **Заявка №{next_seq_num} успешно сохранена!**\n"]
        summary_lines.append(f"**Площадка:** {record_data['Площадка']}")
        summary_lines.append(f"**Линия/Секция:** {record_data['Линия_Секция']}")
        summary_lines.append(f"**Направление:** {record_data['Направление_простоя']}")
        summary_lines.append(f"**Описание:** {record_data['Причина_простоя_описание']}")
        summary_lines.append(f"**Время простоя:** {record_data['Время_простоя_минут']} мин.\n")
        
        if record_data.get('Ответственная_группа') and record_data['Ответственная_группа'] != 'Не указана':
            summary_lines.append(f"**Ответственная группа:** {record_data['Ответственная_группа']}")
        
        final_comment = record_data.get('Дополнительный_комментарий_инициатора')
        if final_comment and 'Без доп. комментария' not in final_comment:
            summary_lines.append(f"**Финальный комментарий:** {final_comment}")

        summary_caption = "\n".join(summary_lines)
        
        photo_id = record_data.get("ID_Фото")
        if photo_id:
            await bot.send_photo(chat_id, photo=photo_id, caption=summary_caption, parse_mode='Markdown')
        else:
            await bot.send_message(chat_id, summary_caption, parse_mode='Markdown')
    else:
        await bot.send_message(chat_id, "❌ Ошибка сохранения в Google Sheets.")
    
    await state.finish()

# --- Регистрация хендлеров ---
def register_downtime_handlers(dp: Dispatcher):
    dp.register_message_handler(start_downtime_entry, text="📊 Внести запись о Простое", state="*")
    
    dp.register_callback_query_handler(back_to_sites, text="back_to_sites", state=DowntimeForm.choosing_line_section)
    dp.register_callback_query_handler(back_to_lines, text="back_to_lines_sections", state=DowntimeForm.choosing_downtime_reason)

    dp.register_callback_query_handler(process_site_choice, lambda c: c.data.startswith('site_'), state=DowntimeForm.choosing_site)
    dp.register_callback_query_handler(process_line_section_choice, lambda c: c.data.startswith('ls_'), state=DowntimeForm.choosing_line_section)
    dp.register_callback_query_handler(process_reason_choice, lambda c: c.data.startswith('reason_'), state=DowntimeForm.choosing_downtime_reason)
    
    # Регистрация обработчиков для шага ввода описания (текст, фото или пропуск)
    dp.register_message_handler(skip_description, commands=['skip'], state=DowntimeForm.entering_description)
    dp.register_message_handler(process_description, state=DowntimeForm.entering_description, content_types=[ContentType.TEXT])
    dp.register_message_handler(process_initial_photo, state=DowntimeForm.entering_description, content_types=[ContentType.PHOTO])

    dp.register_callback_query_handler(process_group_choice, lambda c: c.data.startswith('group_'), state=DowntimeForm.choosing_responsible_group)
    dp.register_callback_query_handler(skip_group_choice, text="skip_group_selection", state=DowntimeForm.choosing_responsible_group)

    dp.register_callback_query_handler(end_downtime_with_comment, text="end_downtime_with_comment", state=DowntimeForm.waiting_for_downtime_end)
    dp.register_callback_query_handler(end_downtime_no_comment, text="end_downtime_without_comment", state=DowntimeForm.waiting_for_downtime_end)
    
    # На шаге доп. комментария принимаем только текст
    dp.register_message_handler(process_additional_comment, state=DowntimeForm.entering_additional_comment, content_types=[ContentType.TEXT])