# fsm.py
from aiogram.dispatcher.filters.state import State, StatesGroup

class DowntimeForm(StatesGroup):
    choosing_site = State()
    choosing_line_section = State()
    choosing_downtime_reason = State()
    entering_description = State()
    choosing_responsible_group = State()
    waiting_for_group_acceptance = State()
    waiting_for_group_work_completion = State()
    waiting_for_downtime_end = State()
    entering_additional_comment = State()

class AdminForm(StatesGroup):
    choosing_user_for_role = State()
    choosing_role_for_user = State()

# Новая FSM для внесения прошедших простоев администратором
class PastDowntimeForm(StatesGroup):
    choosing_site = State()
    choosing_line_section = State()
    choosing_downtime_reason = State() # Добавлен выбор причины для консистентности
    entering_downtime_start = State() # Запрос времени начала
    entering_downtime_end = State() # Запрос времени окончания
    entering_description = State()
    choosing_responsible_group = State()
    confirming_submission = State() # Финальное подтверждение перед записью