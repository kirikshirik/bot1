# filters/admin_filter.py
from aiogram.dispatcher.filters import BoundFilter
from aiogram.types import Message, CallbackQuery
from typing import Union
from utils.storage import DataStorage
from aiogram import Dispatcher

class AdminFilter(BoundFilter):
    key = 'is_admin'

    def __init__(self, is_admin: bool = True):
        self.is_admin = is_admin

    async def check(self, obj: Union[Message, CallbackQuery]) -> bool:
        """
        Проверяет, имеет ли пользователь права администратора.
        """
        # Получаем текущий диспетчер, чтобы из него достать хранилище
        dp = Dispatcher.get_current()
        if not dp:
            return False
            
        # Получаем объект хранилища, который мы добавили в main_bot.py
        storage: DataStorage = dp['storage']
        user_id = str(obj.from_user.id)
        
        # Сравниваем реальную роль пользователя с той, что требуется для хендлера
        return storage.is_admin(user_id) == self.is_admin