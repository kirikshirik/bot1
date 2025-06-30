# keyboards/inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.storage import DataStorage
from config import PRODUCTION_SITES, LINES_SECTIONS, DOWNTIME_REASONS, ADMIN_ROLE, EMPLOYEE_ROLE

def get_sites_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=f"🏭 {v}", callback_data=f"site_{k}") for k, v in PRODUCTION_SITES.items()]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_input"))
    return kb

def get_lines_sections_keyboard(site_key: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    if site_key in LINES_SECTIONS:
        buttons = [InlineKeyboardButton(text=f"➡️ {v}", callback_data=f"ls_{k}") for k, v in LINES_SECTIONS[site_key].items()]
        kb.add(*buttons)
    kb.add(InlineKeyboardButton(text="⬅️ Назад к площадкам", callback_data="back_to_sites"))
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_input"))
    return kb

def get_downtime_reasons_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=f"⚙️ {v}", callback_data=f"reason_{k}") for k, v in DOWNTIME_REASONS.items()]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton(text="⬅️ Назад к линиям/секциям", callback_data="back_to_lines_sections"))
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_input"))
    return kb

def get_responsible_groups_keyboard(storage: DataStorage) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    if storage.responsible_groups:
        buttons = [InlineKeyboardButton(text=f"👥 {v}", callback_data=f"group_{k}") for k, v in storage.responsible_groups.items()]
        kb.add(*buttons)
    kb.add(InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_group_selection"))
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_input"))
    return kb

def get_end_downtime_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(text="✅ Завершить (с доп. комментарием)", callback_data="end_downtime_with_comment"))
    kb.add(InlineKeyboardButton(text="✅ Завершить (без комментария)", callback_data="end_downtime_without_comment"))
    return kb

def get_accept_downtime_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup().add(InlineKeyboardButton("✅ Принять заявку", callback_data=f"accept_dt_{request_id}"))

def get_group_work_completion_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup().add(InlineKeyboardButton("✅ Завершить работу по заявке", callback_data=f"gw_simple_{request_id}"))
    
def get_group_send_fail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(text="➡️ Пропустить выбор группы", callback_data="skip_group_selection")
    )

def get_admin_roles_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton(text=f"👑 {ADMIN_ROLE}", callback_data=f"setrole_{ADMIN_ROLE}"))
    kb.add(InlineKeyboardButton(text=f"👤 {EMPLOYEE_ROLE}", callback_data=f"setrole_{EMPLOYEE_ROLE}"))
    kb.add(InlineKeyboardButton(text="🗑️ Удалить роль", callback_data=f"setrole_DELETE"))
    kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_admin_role_input"))
    return kb