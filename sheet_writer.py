import gspread
from datetime import datetime
import logging

# --- Конфигурация (данные взяты из ваших файлов) ---
# ID вашей Google Таблицы из файла main_bot.py
GOOGLE_SHEET_ID = "1lD4lvJGQDia9zPVThUMR4Zh2_mjQF07FWH-5YTeDMIU" 
# Имя файла с ключами доступа
SERVICE_ACCOUNT_FILE = 'service_account.json'
# Имя листа, с которым работаем
DOWNTIME_WORKSHEET_NAME = "Простои" 

# Настройка логирования для отслеживания работы скрипта
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_next_sequence_number(worksheet):
    """
    Определяет следующий порядковый номер в столбце A.
    """
    try:
        # Получаем все значения из первого столбца (A)
        col_a_values = worksheet.col_values(1)
        
        # Фильтруем только числовые значения, пропуская заголовок
        numeric_values = [int(v) for v in col_a_values[1:] if v and v.isdigit()]
        
        if not numeric_values:
            # Если чисел нет (только заголовок или пустой лист), начинаем с 1
            return 1
        else:
            # Иначе берем максимальное значение и прибавляем 1
            return max(numeric_values) + 1
            
    except Exception as e:
        logging.error(f"Не удалось определить следующий порядковый номер: {e}")
        return None


def add_downtime_record(worksheet, downtime_data: list):
    """
    Добавляет новую запись о простое с автоматическим порядковым номером.
    """
    if not worksheet:
        logging.error("Лист для записи не доступен.")
        return

    # 1. Получаем следующий порядковый номер
    seq_num = get_next_sequence_number(worksheet)
    if seq_num is None:
        logging.error("Не удалось добавить запись, т.к. не был получен порядковый номер.")
        return

    # 2. Формируем полную строку для записи
    # Первым элементом ставим порядковый номер
    full_row_to_add = [seq_num] + downtime_data
    
    try:
        # 3. Добавляем строку в конец таблицы
        worksheet.append_row(full_row_to_add, value_input_option='USER_ENTERED')
        logging.info(f"Успешно добавлена запись с порядковым номером: {seq_num}")
    except Exception as e:
        logging.error(f"Ошибка при добавлении строки в Google Sheets: {e}")


# --- Основной блок для демонстрации работы ---
if __name__ == '__main__':
    try:
        # Авторизация в Google Sheets
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        # Открытие таблицы по ID и выбор нужного листа
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(DOWNTIME_WORKSHEET_NAME)
        logging.info(f"Успешное подключение к таблице '{spreadsheet.title}', листу '{worksheet.title}'.")

        # --- Пример использования ---
        # Представим, что эти данные пришли из вашего Telegram-бота
        example_downtime_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # Timestamp
            "7787270575",                                 # ID пользователя
            "test_user",                                  # Username
            "Тестовый Пользователь",                      # Имя пользователя
            "ОМЕТ",                                       # Площадка
            "ОМЕТ1",                                      # Линия/Секция
            "механика",                                   # Направление простоя
            "Тестовое описание для автоматической записи.", # Описание
            15,                                           # Время простоя, мин.
            # ... и другие ваши столбцы
        ]
        
        # Вызов функции для добавления записи
        add_downtime_record(worksheet, example_downtime_data)

    except FileNotFoundError:
        logging.error(f"Ошибка: Файл '{SERVICE_ACCOUNT_FILE}' не найден. Убедитесь, что он находится в той же папке, что и скрипт, или укажите полный путь.")
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error(f"Ошибка: Таблица с ID '{GOOGLE_SHEET_ID}' не найдена. Проверьте ID и права доступа у сервисного аккаунта.")
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка: {e}")