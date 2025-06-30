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