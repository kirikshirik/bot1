# handlers/admin_handlers.py
import logging
from datetime import datetime
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytz import timezone

# FSM
from fsm import AdminForm, PastDowntimeForm

# Filters, Storage, Config
from filters.admin_filter import AdminFilter
from utils.storage import DataStorage
from config import (
    USER_ID_COLUMN, USER_ROLE_COLUMN, SCHEDULER_TIMEZONE, 
    PRODUCTION_SITES, DOWNTIME_REASONS, LINES_SECTIONS
)

# Keyboards
from keyboards.inline import (
    get_admin_roles_keyboard,
    get_sites_keyboard,
    get_lines_sections_keyboard,
    get_downtime_reasons_keyboard,
    get_responsible_groups_keyboard
)

# Reports & G-Sheets API
from utils.reports import (
    get_downtime_report_for_period,
    get_shift_time_range,
    generate_line_status_report,
    calculate_shift_times
)
from g_sheets.api import get_worksheet, append_downtime_record, get_next_sequence_number

# --- Управление ролями ---
async def manage_roles_start(message: types.Message, state: FSMContext):
    await state.finish()
    await AdminForm.choosing_user_for_role.set()
    await message.answer("Введите Telegram ID пользователя, которому хотите назначить или изменить роль:")

async def process_user_for_role(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    user_input_id = message.text.strip()
    if not user_input_id.isdigit():
        await message.answer("Неверный формат ID. Введите только цифры.")
        return
    current_role = storage.user_roles.get(user_input_id, "Нет роли")
    await state.update_data(target_user_id=user_input_id, current_role=current_role)
    await AdminForm.next()
    await message.answer(f"Пользователь: `{user_input_id}`\nТекущая роль: **{current_role}**\n\nВыберите новую роль:", parse_mode='Markdown', reply_markup=get_admin_roles_keyboard())

async def process_role_choice(cb: types.CallbackQuery, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    new_role = cb.data.split('setrole_', 1)[1]
    user_data = await state.get_data()
    target_user_id = user_data.get('target_user_id')
    if not target_user_id or not storage.gspread_client:
        await cb.message.edit_text("❌ Ошибка: Не удалось получить ID пользователя. Попробуйте снова.")
        await state.finish()
        return
    try:
        roles_ws = get_worksheet(storage.gspread_client, storage.user_roles_ws.title, [USER_ID_COLUMN, USER_ROLE_COLUMN])
        cell = roles_ws.find(target_user_id, in_column=1)
        action_message = ""
        if new_role == "DELETE":
            if cell: roles_ws.delete_rows(cell.row)
            action_message = f"Роль для `{target_user_id}` удалена."
        else:
            if cell: roles_ws.update_cell(cell.row, 2, new_role)
            else: roles_ws.append_row([target_user_id, new_role])
            action_message = f"Роль для `{target_user_id}` установлена: **{new_role}**."
        await storage.load_user_roles()
        await cb.message.edit_text(action_message, parse_mode='Markdown')
        await cb.answer("Роль успешно обновлена.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении роли для {target_user_id}: {e}")
        await cb.message.edit_text("❌ Произошла непредвиденная ошибка при работе с Google Sheets.")
    await state.finish()

async def cancel_admin_input(cb: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await cb.message.edit_text("Действие отменено.")
    await cb.answer()

# --- Отчеты и статус ---
async def send_shift_report(message: types.Message, shift_type: str):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    await message.answer(f"⏳ Формирую отчет за { 'текущую' if shift_type == 'current' else 'предыдущую' } смену...")
    start_dt, end_dt = get_shift_time_range(shift_type)
    if not start_dt or not end_dt:
        await message.answer("Не удалось определить временные рамки смены.")
        return
    report_text = await get_downtime_report_for_period(start_dt, end_dt, storage)
    max_length = 4096
    if len(report_text) > max_length:
        for i in range(0, len(report_text), max_length):
            await message.answer(report_text[i:i+max_length], parse_mode='Markdown')
    else:
        await message.answer(report_text, parse_mode='Markdown')

async def send_line_status_now(message: types.Message):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    await message.answer("⏳ Формирую отчет о статусе линий...")
    report_text = await generate_line_status_report(storage)
    await message.answer(report_text, parse_mode='Markdown')

# --- Внесение прошедшего простоя ---
async def start_past_downtime(message: types.Message, state: FSMContext):
    await state.finish()
    await PastDowntimeForm.choosing_site.set()
    await message.answer("Выберите производственную площадку:", reply_markup=get_sites_keyboard())

async def past_downtime_site_chosen(cb: types.CallbackQuery, state: FSMContext):
    site_key = cb.data.split('_')[1]
    site_name = PRODUCTION_SITES[site_key]
    await state.update_data(site_key=site_key, site_name=site_name)
    await PastDowntimeForm.next()
    await cb.message.edit_text(
        f"Площадка: {site_name}.\nВыберите линию/секцию:",
        reply_markup=get_lines_sections_keyboard(site_key)
    )
    await cb.answer()

async def past_downtime_line_chosen(cb: types.CallbackQuery, state: FSMContext):
    ls_key = cb.data.split('_')[1]
    async with state.proxy() as data:
        site_key = data['site_key']
        data['ls_key'] = ls_key
        data['ls_name'] = LINES_SECTIONS[site_key][ls_key]
    await PastDowntimeForm.next()
    await cb.message.edit_text(
        f"Линия/секция: {data['ls_name']}.\nВыберите направление простоя:",
        reply_markup=get_downtime_reasons_keyboard()
    )
    await cb.answer()
    
async def past_downtime_reason_chosen(cb: types.CallbackQuery, state: FSMContext):
    reason_key = cb.data.split('_', 1)[1]
    reason_name = DOWNTIME_REASONS[reason_key]
    await state.update_data(reason_key=reason_key, reason_name=reason_name)
    await PastDowntimeForm.next()
    await cb.message.edit_text(f"Направление: {reason_name}.\n\nВведите **дату и время НАЧАЛА** простоя в формате\n`ДД.ММ.ГГГГ ЧЧ:ММ` (например, `27.06.2025 21:00`).")
    await cb.answer()

async def past_downtime_start_entered(message: types.Message, state: FSMContext):
    try:
        start_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        await state.update_data(start_time=start_time)
        await PastDowntimeForm.next()
        await message.answer("Время начала принято.\n\nТеперь введите **дату и время ОКОНЧАНИЯ** простоя в том же формате (`ДД.ММ.ГГГГ ЧЧ:ММ`).")
    except ValueError:
        await message.reply("❗️ **Неверный формат.**\nПожалуйста, введите дату и время точно в формате `ДД.ММ.ГГГГ ЧЧ:ММ`.")

async def past_downtime_end_entered(message: types.Message, state: FSMContext):
    try:
        end_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        async with state.proxy() as data:
            start_time = data.get('start_time')
            if end_time <= start_time:
                await message.reply("❗️ **Ошибка.**\nВремя окончания не может быть раньше или равно времени начала. Введите корректное время окончания.")
                return
            duration_minutes = max(1, int((end_time - start_time).total_seconds() / 60))
            data['end_time'] = end_time
            data['duration_minutes'] = duration_minutes
        await PastDowntimeForm.next()
        await message.answer(f"Время окончания принято. Расчетная длительность: **{duration_minutes} мин.**\n\nВведите описание причины простоя.")
    except ValueError:
        await message.reply("❗️ **Неверный формат.**\nПожалуйста, введите дату и время точно в формате `ДД.ММ.ГГГГ ЧЧ:ММ`.")

async def past_downtime_description_entered(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    await state.update_data(description=message.text)
    await PastDowntimeForm.next()
    await message.answer("Описание принято.\n\nВыберите ответственную группу:", reply_markup=get_responsible_groups_keyboard(storage))

async def past_downtime_group_chosen(cb: types.CallbackQuery, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    group_key = cb.data.split('group_', 1)[1]
    group_name = storage.responsible_groups.get(group_key, "Не указана")
    await state.update_data(responsible_group_name=group_name)
    await show_past_downtime_confirmation(cb.message, state)
    await cb.answer()

async def skip_past_downtime_group(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(responsible_group_name="Не указана")
    await show_past_downtime_confirmation(cb.message, state)
    await cb.answer()

async def show_past_downtime_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    start_time_str = data['start_time'].strftime('%d.%m.%Y %H:%M')
    end_time_str = data['end_time'].strftime('%d.%m.%Y %H:%M')
    text = [
        "**Проверьте и подтвердите данные:**\n",
        f"**Площадка:** {data['site_name']}", f"**Линия/Секция:** {data['ls_name']}",
        f"**Направление:** {data['reason_name']}", f"**Начало простоя:** {start_time_str}",
        f"**Окончание простоя:** {end_time_str}", f"**Длительность:** {data['duration_minutes']} мин.",
        f"**Описание:** {data['description']}", f"**Отв. группа:** {data['responsible_group_name']}\n",
        "Все верно?"
    ]
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Сохранить", callback_data="past_downtime_save"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_input")
    )
    await PastDowntimeForm.confirming_submission.set()
    await message.edit_text("\n".join(text), parse_mode="Markdown", reply_markup=kb)

async def save_past_downtime(cb: types.CallbackQuery, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    user = cb.from_user
    tz = timezone(SCHEDULER_TIMEZONE)

    async with state.proxy() as data:
        start_time = data.get('start_time')
        shift_start_str, shift_end_str = calculate_shift_times(start_time)
        next_seq_num = get_next_sequence_number(storage.downtime_ws)
        record_data = {
            "Порядковый номер заявки": next_seq_num,
            "Timestamp_записи": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
            "ID_пользователя_Telegram": user.id,
            "Username_Telegram": user.username or "N/A",
            "Имя_пользователя_Telegram": f"{user.full_name} (внесено адм.)",
            "Площадка": data.get('site_name', 'Н/Д'),
            "Линия_Секция": data.get('ls_name', 'Н/Д'),
            "Направление_простоя": data.get('reason_name', 'Н/Д'),
            "Причина_простоя_описание": data.get('description', 'Н/Д'),
            "Время_простоя_минут": data.get('duration_minutes', 0),
            "Начало_смены_простоя": shift_start_str, "Конец_смены_простоя": shift_end_str,
            "Ответственная_группа": data.get('responsible_group_name', 'Не указана'),
            "Кто_принял_заявку_ID": "", "Кто_принял_заявку_Имя": "", "Время_принятия_заявки": "",
            "Кто_завершил_работу_в_группе_ID": "", "Кто_завершил_работу_в_группе_Имя": "", "Время_завершения_работы_группой": "",
            "Дополнительный_комментарий_инициатора": f"Запись внесена вручную {start_time.strftime('%d.%m %H:%M')} - {data['end_time'].strftime('%d.%m %H:%M')}",
            "ID_Фото": ""
        }
    if append_downtime_record(storage.downtime_ws, record_data):
        await storage.refresh_downtime_cache(cb.bot)
        await cb.message.edit_text(f"✅ **Запись о прошедшем простое (№{next_seq_num}) успешно сохранена!**", parse_mode='Markdown')
    else:
        await cb.message.edit_text("❌ Ошибка сохранения в Google Sheets.")
    await state.finish()
    await cb.answer("Сохранено")

def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(manage_roles_start, AdminFilter(), text="⚙️ Управление ролями", state="*")
    dp.register_message_handler(process_user_for_role, state=AdminForm.choosing_user_for_role)
    dp.register_callback_query_handler(process_role_choice, lambda c: c.data.startswith('setrole_'), state=AdminForm.choosing_role_for_user)
    dp.register_callback_query_handler(cancel_admin_input, text="cancel_admin_role_input", state=AdminForm.all_states)
    dp.register_message_handler(lambda msg: send_shift_report(msg, 'current'), AdminFilter(), text="📄 Отчет за текущую смену", state="*")
    dp.register_message_handler(lambda msg: send_shift_report(msg, 'previous'), AdminFilter(), text="📄 Отчет за предыдущую смену", state="*")
    dp.register_message_handler(send_line_status_now, AdminFilter(), text="🔄 Статус линий", state="*")
    dp.register_message_handler(start_past_downtime, AdminFilter(), text="🗓️ Внести прошедший простой", state="*")
    dp.register_callback_query_handler(past_downtime_site_chosen, lambda c: c.data.startswith('site_'), state=PastDowntimeForm.choosing_site)
    dp.register_callback_query_handler(past_downtime_line_chosen, lambda c: c.data.startswith('ls_'), state=PastDowntimeForm.choosing_line_section)
    dp.register_callback_query_handler(past_downtime_reason_chosen, lambda c: c.data.startswith('reason_'), state=PastDowntimeForm.choosing_downtime_reason)
    dp.register_message_handler(past_downtime_start_entered, state=PastDowntimeForm.entering_downtime_start)
    dp.register_message_handler(past_downtime_end_entered, state=PastDowntimeForm.entering_downtime_end)
    dp.register_message_handler(past_downtime_description_entered, state=PastDowntimeForm.entering_description)
    dp.register_callback_query_handler(past_downtime_group_chosen, lambda c: c.data.startswith('group_'), state=PastDowntimeForm.choosing_responsible_group)
    dp.register_callback_query_handler(skip_past_downtime_group, text="skip_group_selection", state=PastDowntimeForm.choosing_responsible_group)
    dp.register_callback_query_handler(save_past_downtime, text="past_downtime_save", state=PastDowntimeForm.confirming_submission)
    dp.register_callback_query_handler(cancel_admin_input, text="cancel_input", state=[PastDowntimeForm.all_states, AdminForm.all_states])