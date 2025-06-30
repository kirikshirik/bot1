# keyboards/reply.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    """Создает главную клавиатуру внизу экрана."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    
    # --- НОВЫЙ ПОРЯДОК КНОПОК ---
    
    # Кнопка, доступная всем
    kb.add(KeyboardButton(text="📊 Внести запись о Простое"))
    
    # Кнопки только для администраторов
    if is_admin:
        kb.add(KeyboardButton(text="🗓️ Внести прошедший простой"))
        kb.add(KeyboardButton(text="📄 Отчет за текущую смену"))
        kb.add(KeyboardButton(text="📄 Отчет за предыдущую смену"))
        kb.add(KeyboardButton(text="🔄 Статус линий"))
        kb.add(KeyboardButton(text="⚙️ Управление ролями"))
        
    return kb