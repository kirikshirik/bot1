# utils/storage.py
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from aiogram import Bot

import gspread
from g_sheets.api import get_gspread_client, get_worksheet, fetch_all_rows, load_user_roles, load_responsible_groups
from config import (ADMIN_ROLE, DOWNTIME_WORKSHEET_NAME, USER_ROLES_WORKSHEET_NAME, RESPONSIBLE_GROUPS_WORKSHEET_NAME, 
                    SHEET_HEADERS, CACHE_MAX_AGE_SECONDS)

class DataStorage:
    def __init__(self):
        self.gspread_client: Optional[gspread.Client] = get_gspread_client()
        self.downtime_ws: Optional[gspread.Worksheet] = None
        self.user_roles_ws: Optional[gspread.Worksheet] = None
        self.groups_ws: Optional[gspread.Worksheet] = None
        
        self.user_roles: Dict[str, str] = {}
        self.responsible_groups: Dict[str, str] = {}
        self.group_ids: Dict[str, int] = {}
        self.pending_requests: Dict[str, Dict[str, Any]] = {}

        self.downtime_cache: Dict[str, Any] = {"timestamp": None, "headers": None, "data_rows": None, "error": None}
        
        # <<<< ИСПРАВЛЕНИЕ: Добавлена недостающая строка >>>>
        self.active_downtimes: Dict[tuple, str] = {}

    def is_admin(self, user_id: str) -> bool:
        """Проверяет, является ли пользователь администратором."""
        return self.user_roles.get(str(user_id)) == ADMIN_ROLE

    async def initialize(self):
        """Инициализирует все соединения и загружает начальные данные."""
        logging.info("--- [STORAGE] Инициализация хранилища... ---")
        if not self.gspread_client:
            logging.critical("[STORAGE] gspread клиент не создан. Работа с таблицами невозможна.")
            return

        self.downtime_ws = get_worksheet(self.gspread_client, DOWNTIME_WORKSHEET_NAME, SHEET_HEADERS)
        self.user_roles_ws = get_worksheet(self.gspread_client, USER_ROLES_WORKSHEET_NAME)
        self.groups_ws = get_worksheet(self.gspread_client, RESPONSIBLE_GROUPS_WORKSHEET_NAME)

        await self.load_user_roles()
        await self.load_responsible_groups()
        await self.refresh_downtime_cache()
        logging.info("--- [STORAGE] Инициализация хранилища завершена. ---")

    async def load_user_roles(self):
        """Загружает или перезагружает роли пользователей."""
        if self.gspread_client:
            self.user_roles = load_user_roles(self.gspread_client)

    async def load_responsible_groups(self):
        """Загружает или перезагружает ответственные группы."""
        if self.gspread_client:
            self.responsible_groups, self.group_ids = load_responsible_groups(self.gspread_client)

    async def refresh_downtime_cache(self, bot: Optional[Bot] = None):
        """Обновляет кэш данных о простоях из Google Таблицы."""
        logging.info("Обновление кэша данных о простоях...")
        if not self.downtime_ws:
            self.downtime_cache["error"] = "Worksheet not available"
            logging.error("Лист простоев не доступен для обновления кэша.")
            return

        try:
            all_values = fetch_all_rows(self.downtime_ws)
            current_time = datetime.now()
            if all_values is not None:
                self.downtime_cache["headers"] = all_values[0] if all_values else []
                self.downtime_cache["data_rows"] = all_values[1:] if len(all_values) > 1 else []
                self.downtime_cache["timestamp"] = current_time
                self.downtime_cache["error"] = None
                logging.info(f"Кэш обновлен: {len(self.downtime_cache['data_rows'])} строк.")
            else:
                self.downtime_cache["error"] = "Failed to fetch data"
                logging.error("Не удалось получить данные для кэша (fetch_all_rows вернул None).")

        except gspread.exceptions.APIError as e:
            self.downtime_cache["error"] = f"API Error: {e.response.status_code}"
            logging.error(f"API ошибка при обновлении кэша: {e}")
            if e.response.status_code == 429 and bot:
                admin_ids = [uid for uid, role in self.user_roles.items() if role == ADMIN_ROLE]
                for admin_id in admin_ids:
                    try:
                        await bot.send_message(int(admin_id), "⚠️ Внимание: Достигнут лимит запросов к Google Sheets.")
                    except Exception as e_notify:
                        logging.error(f"Не удалось отправить уведомление админу {admin_id}: {e_notify}")
        except Exception as e:
            self.downtime_cache["error"] = f"Unexpected error: {str(e)}"
            logging.error(f"Неожиданная ошибка при обновлении кэша: {e}", exc_info=True)
            
    def is_cache_stale(self) -> bool:
        """Проверяет, не устарел ли кэш."""
        if not self.downtime_cache["timestamp"]:
            return True
        return (datetime.now() - self.downtime_cache["timestamp"]).total_seconds() > CACHE_MAX_AGE_SECONDS