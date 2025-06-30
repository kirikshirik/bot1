import gspread
import logging

# --- НАСТРОЙКИ ---

# ВАЖНО: Укажите ID вашей Google Таблицы здесь
# Его можно взять из адресной строки браузера:
# https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit
SPREADSHEET_ID = '1lD4lvJGQDia9zPVThUMR4Zh2_mjQF07FWH-5YTeDMIU'

# Название для нового листа
NEW_WORKSHEET_NAME = 'Простои (Новая структура)'

# Имя файла с ключами доступа (должен лежать в той же папке)
SERVICE_ACCOUNT_FILE = 'service_account.json'

# --- Заголовки из вашего скриншота ---
# Я внимательно переписал все заголовки в нужном порядке
HEADERS = [
    "Timestamp_записи",
    "ID_пользователя_Telegram",
    "Username_Telegram",
    "Имя_пользователя_Telegram",
    "Площадка",
    "Линия_Секция",
    "Направление_простоя",
    "Причина_простоя_описание",
    "ID_Фото",
    "Время_простоя_мин",
    "Начало_смены_простоя",
    "Конец_смены_простоя",
    "Ответственная_группа",
    "Кто_принял_заявку_ID",
    "Кто_принял_заявку_Имя",
    "Время_принятия_заявки",
    "Кто_завершил_работу_в_группе_ID",
    "Кто_завершил_работу_в_группе_Имя",
    "Время_завершения_работы_группой",
    "Дополнительный_комментарий",
    "ID_Заявки"
]

# Настройка логирования для вывода информации о работе
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def create_new_sheet_with_headers(spreadsheet_id, worksheet_name, headers, service_account_path):
    """
    Создает новый лист в указанной таблице и добавляет заголовки.
    """
    try:
        # Авторизация
        gc = gspread.service_account(filename=service_account_path)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        logging.info(f"Успешно подключился к таблице: '{spreadsheet.title}'")

        # Проверка, существует ли уже лист с таким именем
        try:
            spreadsheet.worksheet(worksheet_name)
            logging.warning(f"Лист с именем '{worksheet_name}' уже существует. Создание отменено.")
            print(f"❌ Лист '{worksheet_name}' уже существует. Выберите другое имя, если нужен новый лист.")
            return
        except gspread.exceptions.WorksheetNotFound:
            # Если лист не найден, создаем его
            logging.info(f"Создаю новый лист с именем '{worksheet_name}'...")
            new_worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, 
                rows=1000, 
                cols=len(headers) + 2
            )
            
            # Добавляем заголовки в первую строку
            new_worksheet.append_row(headers, value_input_option='USER_ENTERED')
            logging.info("Заголовки успешно добавлены.")
            
            # Формируем и выводим ссылку на новый лист
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={new_worksheet.id}"
            print(f"\n✅ Успешно создан новый лист '{worksheet_name}'")
            print(f"   Ссылка на новый лист: {sheet_url}")

    except FileNotFoundError:
        logging.error(f"Ошибка: Файл ключа '{service_account_path}' не найден.")
        print(f"❌ Ошибка: Убедитесь, что файл '{service_account_path}' находится в той же папке, что и скрипт.")
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error(f"Ошибка: Таблица с ID '{spreadsheet_id}' не найдена.")
        print(f"❌ Ошибка: Проверьте правильность SPREADSHEET_ID и права доступа у сервисного аккаунта.")
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка: {e}")

# --- Запуск скрипта ---
if __name__ == '__main__':
    create_new_sheet_with_headers(SPREADSHEET_ID, NEW_WORKSHEET_NAME, HEADERS, SERVICE_ACCOUNT_FILE)