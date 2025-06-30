# g_sheets/api.py
import logging
import gspread
from config import (GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
                    DOWNTIME_WORKSHEET_NAME, RESPONSIBLE_GROUPS_WORKSHEET_NAME,
                    USER_ROLES_WORKSHEET_NAME, SHEET_HEADERS, GROUP_NAME_COLUMN,
                    GROUP_ID_COLUMN, USER_ID_COLUMN, USER_ROLE_COLUMN)

def get_gspread_client():
    """Инициализирует и возвращает клиент gspread."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        gc = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_JSON_PATH, scopes=scope)
        return gc
    except Exception as e:
        logging.error(f"Критическая ошибка: Не удалось инициализировать gspread клиент: {e}")
        return None

def get_worksheet(gc: gspread.Client, worksheet_name: str, headers_list: list = None):
    """Получает или создает лист в Google Таблице."""
    if not gc:
        logging.error("gspread клиент не инициализирован.")
        return None
    try:
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logging.info(f"Лист '{worksheet_name}' не найден. Создаю новый...")
            cols = len(headers_list) + 5 if headers_list else 20
            rows = "100" if worksheet_name != DOWNTIME_WORKSHEET_NAME else "2000"
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=rows, cols=cols)
            if headers_list:
                worksheet.append_row(headers_list)
                logging.info(f"Добавлены заголовки {headers_list} в '{worksheet_name}'.")
        return worksheet
    except Exception as e:
        logging.error(f"Ошибка в get_worksheet для '{worksheet_name}': {e}")
        return None

def get_next_sequence_number(worksheet: gspread.Worksheet) -> int:
    """Определяет следующий порядковый номер в столбце A."""
    try:
        # Получаем все значения из первого столбца (A)
        col_a_values = worksheet.col_values(1)
        # Фильтруем только числовые значения, пропуская заголовок (первую строку)
        numeric_values = [int(v) for v in col_a_values[1:] if v and v.isdigit()]
        
        if not numeric_values:
            # Если чисел нет (только заголовок или пустой лист), начинаем с 1
            return 1
        else:
            # Иначе берем максимальное значение и прибавляем 1
            return max(numeric_values) + 1
            
    except Exception as e:
        logging.error(f"Не удалось определить следующий порядковый номер: {e}")
        # В случае любой ошибки, чтобы не останавливать работу, возвращаем 1
        # Можно заменить на более сложную логику, если требуется
        return 1

def append_downtime_record(gs_worksheet: gspread.Worksheet, data_dict: dict):
    """Добавляет запись о простое в Google Таблицу."""
    if not gs_worksheet:
        logging.error("Лист Простои не доступен для записи.")
        return False
    try:
        # Собираем строку в правильном порядке на основе заголовков из config.py
        row = [data_dict.get(h, "") for h in SHEET_HEADERS]
        gs_worksheet.append_row(row, value_input_option='USER_ENTERED')
        logging.info(f"Данные успешно добавлены в '{gs_worksheet.title}'.")
        return True
    except Exception as e:
        logging.error(f"Ошибка append_downtime_record: {e}")
        return False

def fetch_all_rows(gs_worksheet: gspread.Worksheet):
    """Получает все строки с листа для кэширования."""
    if not gs_worksheet:
        return None
    try:
        return gs_worksheet.get_all_values()
    except gspread.exceptions.APIError as e:
        logging.error(f"Google Sheets API error при получении данных: {e}")
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при получении данных с листа '{gs_worksheet.title}': {e}")
    return None

def load_responsible_groups(gc: gspread.Client):
    """Загружает словарь ответственных групп и их ID."""
    groups_ws = get_worksheet(gc, RESPONSIBLE_GROUPS_WORKSHEET_NAME, [GROUP_NAME_COLUMN, GROUP_ID_COLUMN])
    if not groups_ws:
        return {}, {}
    try:
        records = groups_ws.get_all_records()
        groups_by_name, ids_by_name = {}, {}
        for idx, record in enumerate(records):
            name = record.get(GROUP_NAME_COLUMN)
            group_id = str(record.get(GROUP_ID_COLUMN, "")).strip()
            if name and str(name).strip():
                name_str = str(name).strip()
                groups_by_name[f"grp_idx_{idx}"] = name_str
                if group_id:
                    try:
                        ids_by_name[name_str] = int(group_id)
                    except ValueError:
                        logging.error(f"Некорректный ID '{group_id}' для группы '{name_str}'.")
        logging.info(f"[GS] Загружено {len(groups_by_name)} ответственных групп.")
        return groups_by_name, ids_by_name
    except Exception as e:
        logging.error(f"Ошибка загрузки ответственных групп: {e}")
        return {}, {}

def load_user_roles(gc: gspread.Client):
    """Загружает словарь ролей пользователей."""
    roles_ws = get_worksheet(gc, USER_ROLES_WORKSHEET_NAME, [USER_ID_COLUMN, USER_ROLE_COLUMN])
    if not roles_ws:
        return {}
    try:
        records = roles_ws.get_all_records()
        roles = {}
        for record in records:
            user_id = str(record.get(USER_ID_COLUMN, "")).strip()
            role = str(record.get(USER_ROLE_COLUMN, "")).strip()
            if user_id and role:
                roles[user_id] = role
        logging.info(f"[GS] Загружено {len(roles)} ролей пользователей.")
        return roles
    except Exception as e:
        logging.error(f"Ошибка загрузки ролей: {e}")
        return {}