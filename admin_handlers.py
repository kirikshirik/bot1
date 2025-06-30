Здравствуйте\! Спасибо за скриншот, он очень помогает понять ситуацию.

Проблема не в том, что отчеты "не работают" в целом, а в том, что они **не находят записей**, которые соответствуют временным рамкам текущей и предыдущей смены. Ваш бот корректно определяет эти временные рамки, но при поиске в кэше данных из Google Таблиц ни одна из записей не проходит проверку на попадание в этот диапазон.

Из наших предыдущих логов мы знаем, что вы создавали записи (например, в 13:30). Такая запись должна была попасть в отчет за текущую смену (с 08:00 по 20:00). Раз этого не произошло, наиболее вероятная причина — **несоответствие формата даты**.

Скорее всего, Google Таблицы автоматически изменяют формат ячейки с датой, и код не может корректно прочитать это измененное значение.

### Решение: делаем код более устойчивым к форматам дат

Я внес изменения в два файла, чтобы сделать систему более надежной:

1.  **`reports.py`**: Обновлена логика чтения дат. Теперь код будет пытаться распознать несколько распространенных форматов, что делает его гораздо более устойчивым к автоформатированию Google.
2.  **`admin_handlers.py`**: Обнаружена и исправлена небольшая ошибка, связанная с часовым поясом при внесении "прошедшего простоя".

Пожалуйста, обновите эти два файла.

### 1\. Обновленный код для `reports.py`

Полностью замените содержимое файла `reports.py` на код ниже:

```python
# utils/reports.py
import logging
from datetime import datetime, timedelta, time
from collections import Counter, defaultdict
from pytz import timezone

from aiogram.utils.markdown import escape_md
from aiogram import Bot

from config import (SCHEDULER_TIMEZONE, TOP_N_REASONS_FOR_SUMMARY,
                    PRODUCTION_SITES, LINES_SECTIONS, ADMIN_ROLE)
from utils.storage import DataStorage

def get_shift_time_range(shift_type: str) -> (datetime, datetime):
    tz = timezone(SCHEDULER_TIMEZONE)
    now_local = datetime.now(tz)
    time_08_00 = time(8, 0)
    time_20_00 = time(20, 0)

    if time_08_00 <= now_local.time() < time_20_00:
        current_start = now_local.replace(hour=8, minute=0, second=0, microsecond=0)
        current_end = now_local.replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        if now_local.time() >= time_20_00:
            current_start = now_local.replace(hour=20, minute=0, second=0, microsecond=0)
            current_end = (now_local + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            current_start = (now_local - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
            current_end = now_local.replace(hour=8, minute=0, second=0, microsecond=0)

    if shift_type == 'current':
        return current_start, current_end
    elif shift_type == 'previous':
        if current_start.time() == time_08_00:
            prev_end = current_start
            prev_start = (current_start - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        else:
            prev_end = current_start
            prev_start = current_start.replace(hour=8, minute=0, second=0, microsecond=0)
        return prev_start, prev_end

    return None, None


def calculate_shift_times(record_datetime: datetime) -> (str, str):
    tz = timezone(SCHEDULER_TIMEZONE)
    record_datetime_aware = record_datetime.astimezone(tz) if record_datetime.tzinfo else tz.localize(record_datetime)
    record_date = record_datetime_aware.date()
    record_time = record_datetime_aware.time()
    time_08_00 = time(8, 0)
    time_20_00 = time(20, 0)

    if time_08_00 <= record_time < time_20_00:
        start_dt = tz.localize(datetime.combine(record_date, time_08_00))
        end_dt = tz.localize(datetime.combine(record_date, time_20_00))
    elif record_time >= time_20_00:
        start_dt = tz.localize(datetime.combine(record_date, time_20_00))
        end_dt = tz.localize(datetime.combine(record_date + timedelta(days=1), time_08_00))
    else:
        start_dt = tz.localize(datetime.combine(record_date - timedelta(days=1), time_20_00))
        end_dt = tz.localize(datetime.combine(record_date, time_08_00))

    return start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")

def _parse_datetime_from_sheet(dt_string: str) -> datetime | None:
    """Пытается распарсить строку с датой из таблицы, пробуя несколько форматов."""
    # Список возможных форматов, от наиболее вероятного к менее
    formats_to_try = [
        "%Y-%m-%d %H:%M:%S",  # Наш основной формат
        "%d.%m.%Y %H:%M:%S",  # Распространенный формат в РФ
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(dt_string, fmt)
        except ValueError:
            continue
    logging.warning(f"Не удалось распознать формат даты-времени: '{dt_string}'")
    return None

async def get_downtime_report_for_period(start_dt: datetime, end_dt: datetime, storage: DataStorage):
    cache_status = ""
    if storage.downtime_cache.get("error"):
        cache_status += f"\n\n⚠️ **Кэш-ошибка: {storage.downtime_cache['error']}.**"
    if storage.is_cache_stale():
        cache_status += f"\n\n⚠️ **Данные могут быть неактуальны (кэш устарел).**"

    headers = storage.downtime_cache.get("headers")
    data_rows = storage.downtime_cache.get("data_rows")

    if not headers or data_rows is None:
        return f"Нет данных о простоях для анализа.{cache_status}"

    try:
        required_cols = [
            "Timestamp_записи", "Площадка", "Линия_Секция", "Направление_простоя",
            "Время_простоя_минут", "Причина_простоя_описание", "Ответственная_группа",
            "Дополнительный_комментарий_инициатора"
        ]
        idx_map = {col: headers.index(col) for col in required_cols}
    except ValueError as e:
        logging.error(f"Отсутствует необходимый столбец в таблице: {e}")
        return f"Ошибка конфигурации отчета: столбец '{str(e).split()[0]}' не найден в таблице."

    downtimes_by_site = defaultdict(list)
    total_minutes = 0
    tz = timezone(SCHEDULER_TIMEZONE)

    for row in data_rows:
        try:
            if len(row) <= max(idx_map.values()): continue
            
            record_timestamp_str = row[idx_map["Timestamp_записи"]]
            if not record_timestamp_str: continue
            
            # Используем новую надежную функцию для парсинга
            record_dt = _parse_datetime_from_sheet(record_timestamp_str)
            if not record_dt: continue

            record_dt_aware = tz.localize(record_dt)

            if start_dt <= record_dt_aware < end_dt:
                site = escape_md(row[idx_map['Площадка']])
                duration = int(row[idx_map["Время_простоя_минут"]] or 0)
                total_minutes += duration
                description = escape_md(row[idx_map["Причина_простоя_описание"]])
                initiator_comment = escape_md(row[idx_map["Дополнительный_комментарий_инициатора"]])
                line_info = (f"⚙️ **{escape_md(row[idx_map['Линия_Секция']])}**: "
                             f"{escape_md(row[idx_map['Направление_простоя']])} ({duration} мин.)\n"
                             f"   📝 _{description}_\n"
                             f"   👥 {escape_md(row[idx_map['Ответственная_группа']])}")

                if initiator_comment and "Без доп. комментария" not in initiator_comment:
                    line_info += f"\n   🗣️ Комментарий инициатора: _{initiator_comment}_"
                downtimes_by_site[site].append(line_info)
        except (ValueError, IndexError) as e:
            logging.warning(f"Пропущена некорректная строка при создании отчета: {row}. Ошибка: {e}")
            continue

    if not downtimes_by_site:
        return f"Нет корректных записей за смену с {start_dt.strftime('%H:%M %d.%m')} по {end_dt.strftime('%H:%M %d.%m')}.{cache_status}"

    report_header = f"**📊 Отчет за смену с {start_dt.strftime('%H:%M %d.%m')} по {end_dt.strftime('%H:%M %d.%m')}**\n"
    report_lines = ["\n".join(lines) for site, lines in sorted(downtimes_by_site.items())]
    report_summary = f"\n\n**⏱️ Общее время простоя: {total_minutes} минут.**"
    return report_header + "\n\n".join(report_lines) + report_summary + cache_status


async def generate_admin_shift_summary(start_dt: datetime, end_dt: datetime, storage: DataStorage):
    headers = storage.downtime_cache.get("headers")
    data_rows = storage.downtime_cache.get("data_rows")

    if not headers or data_rows is None: return "Нет данных для сводки."

    try:
        idx_map = {col: headers.index(col) for col in ["Timestamp_записи", "Время_простоя_минут", "Направление_простоя"]}
    except ValueError as e: return f"Ошибка конфигурации сводки: столбец '{str(e).split()[0]}' не найден."
    
    total_minutes = 0
    reason_counts = Counter()
    tz = timezone(SCHEDULER_TIMEZONE)

    for row in data_rows:
        try:
            if len(row) <= max(idx_map.values()): continue
            record_timestamp_str = row[idx_map["Timestamp_записи"]]
            if not record_timestamp_str: continue
            
            record_dt = _parse_datetime_from_sheet(record_timestamp_str)
            if not record_dt: continue

            record_dt_aware = tz.localize(record_dt)

            if start_dt <= record_dt_aware < end_dt:
                duration = int(row[idx_map["Время_простоя_минут"]] or 0)
                reason = row[idx_map["Направление_простоя"]] or "Не указана"
                total_minutes += duration
                reason_counts[reason] += duration
        except (ValueError, IndexError) as e:
            logging.warning(f"Пропущена некорректная строка при создании сводки: {row}. Ошибка: {e}")
            continue

    if total_minutes == 0:
        return f"За смену ({start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}) простоев не зафиксировано."

    hours, minutes = divmod(total_minutes, 60)
    top_reasons_list = reason_counts.most_common(TOP_N_REASONS_FOR_SUMMARY)
    top_reasons = [f"- {escape_md(r)} ({m} мин.)" for r, m in top_reasons_list]
    summary = (f"**Сводка за смену ({start_dt.strftime('%H:%M %d.%m')})**\n\n"
               f"Общий простой: **{hours} ч {minutes} мин.**\n\n"
               f"**Топ-{len(top_reasons)} причины:**\n" + "\n".join(top_reasons))
    return summary


async def generate_line_status_report(storage: DataStorage):
    report_lines = ["**Статус линий на текущий момент:**"]
    for site_key, site_name in PRODUCTION_SITES.items():
        if site_key not in LINES_SECTIONS: continue
        report_lines.append(f"\n🏭 **{escape_md(site_name)}**")
        for line_key, line_name in LINES_SECTIONS[site_key].items():
            line_tuple = (site_name, line_name)
            if line_tuple in storage.active_downtimes:
                reason = storage.active_downtimes[line_tuple]
                report_lines.append(f"   🔴 {escape_md(line_name)}: **ПРОСТОЙ** ({escape_md(reason)})")
            else:
                report_lines.append(f"   🟢 {escape_md(line_name)}: Работает")
    return "\n".join(report_lines)


async def scheduled_line_status_report(bot: Bot, storage: DataStorage):
    logging.info("SCHEDULER: Запуск задачи на отправку отчета о статусе линий.")
    admin_ids = [uid for uid, role in storage.user_roles.items() if role == ADMIN_ROLE]
    if not admin_ids:
        logging.warning("SCHEDULER: Нет администраторов для отправки отчета о статусе линий.")
        return
    report_text = await generate_line_status_report(storage)
    for admin_id in admin_ids:
        try:
            await bot.send_message(int(admin_id), report_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"SCHEDULER: Не удалось отправить отчет о статусе линий админу {admin_id}: {e}")
    logging.info(f"SCHEDULER: Отчет о статусе линий отправлен {len(admin_ids)} администраторам.")
```

### 2\. Обновленный код для `admin_handlers.py`

Полностью замените содержимое файла `admin_handlers.py` на код ниже:

```python
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
    