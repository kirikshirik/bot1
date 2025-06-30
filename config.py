# config.py
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла (опционально, для локальной разработки)
load_dotenv()

# --- Основные настройки ---
# Рекомендуется хранить токен в переменных окружения для безопасности
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8080782592:AAEfvF60b5LccOMLDNHnVbN2lSNhvRjyly0")
BOT_VERSION = "8.1_With_Seq_Num"

# --- Настройки Google Sheets ---
GOOGLE_SHEET_ID = "1lD4lvJGQDia9zPVThUMR4Zh2_mjQF07FWH-5YTeDMIU"
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = "service_account.json"
DOWNTIME_WORKSHEET_NAME = "Простои"
RESPONSIBLE_GROUPS_WORKSHEET_NAME = "Группы"
USER_ROLES_WORKSHEET_NAME = "Пользователи_Роли"

# --- Настройки отчетов и уведомлений ---
# ID чатов/групп для отправки отчетов (в виде списка строк)
REPORTS_CHAT_IDS = ["483262851", "323628998"]
SCHEDULER_TIMEZONE = "Europe/Moscow"
TOP_N_REASONS_FOR_SUMMARY = 3

# --- Кэш ---
CACHE_REFRESH_INTERVAL_SECONDS = 300  # 5 минут
CACHE_MAX_AGE_SECONDS = 900           # 15 минут

# --- Роли пользователей ---
ADMIN_ROLE = "Администратор"
EMPLOYEE_ROLE = "Сотрудник"

# --- Бизнес-данные (словари для клавиатур и логики) ---
PRODUCTION_SITES = {
    "omet": "ОМЕТ", "gambini2": "Гамбини-2", "gambini3": "Гамбини-3",
    "mts2": "МТС-2", "mts4": "МТС-4",
}
LINES_SECTIONS = {
    "omet": {"omet1": "ОМЕТ1", "omet2": "ОМЕТ2", "omet3": "ОМЕТ3", "omet4": "ОМЕТ4", "omet5": "ОМЕТ5", "sdf": "СДФ"},
    "gambini2": {"raskat": "раскат", "tisnenie": "тиснение", "namotchik": "намотчик", "bunker": "бункер", "rezka": "резка", "gilza": "гильза", "uno": "уно", "fbs": "фбс", "printer": "принтер"},
    "gambini3": {"raskat": "раскат", "tisnenie": "тиснение", "namotchik": "намотчик", "ambalazh": "амбалаж", "bunker": "бункер", "rezka": "резка", "gilza": "гильza", "uno": "уно", "fbs": "фбс", "infinity": "инфинити", "printer": "принter"},
    "mts2": {"raskat": "Раскат", "tisnenie": "Тиснение", "folder": "фолдер", "ambalazh": "амбалаж", "rezka": "резка", "tekna": "текна", "keyspaker": "кейспакер", "printer": "принтер"},
    "mts4": {"raskat": "Раскат", "tisnenie": "Тиснение", "folder": "фолдер", "ambalazh": "амбалаж", "rezka": "резка", "keyspaker": "кейспакер", "printer": "принтер"}
}
DOWNTIME_REASONS = {
    "perevod": "перевод", "mehanika": "механика", "kip": "кип", "obryv": "обрыв",
    "net_osnovy": "нет основы", "net_operatora": "нет оператора", "obed": "обед",
    "zamena": "замена", "net_plana": "нет плана", "phd": "пхд", "net_vozduha": "нет воздуха"
}

# --- Заголовки таблиц (должны соответствовать таблице) ---
SHEET_HEADERS = [
    "Порядковый номер заявки",
    "Timestamp_записи", "ID_пользователя_Telegram", "Username_Telegram",
    "Имя_пользователя_Telegram", "Площадка", "Линия_Секция",
    "Направление_простоя", "Причина_простоя_описание", "Время_простоя_минут",
    "Начало_смены_простоя", "Конец_смены_простоя",
    "Ответственная_группа",
    "Кто_принял_заявку_ID", "Кто_принял_заявку_Имя", "Время_принятия_заявки",
    "Кто_завершил_работу_в_группе_ID", "Кто_завершил_работу_в_группе_Имя", "Время_завершения_работы_группой",
    "Дополнительный_комментарий_инициатора",
    "ID_Фото"
]
GROUP_NAME_COLUMN = "Название группы"
GROUP_ID_COLUMN = "ID группы"
USER_ID_COLUMN = "ID_пользователя_Telegram"
USER_ROLE_COLUMN = "Роль"