# handlers/other_handlers.py
import logging
from datetime import datetime
import json
from aiogram import Dispatcher, types, Bot
from aiogram.dispatcher import FSMContext
from utils.storage import DataStorage
from config import EMPLOYEE_ROLE, BOT_VERSION
from keyboards.reply import get_main_keyboard
from keyboards.inline import get_end_downtime_keyboard, get_group_work_completion_keyboard
from fsm import DowntimeForm

async def send_welcome(message: types.Message, state: FSMContext):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    await state.finish()
    user_id = str(message.from_user.id)
    if user_id not in storage.user_roles:
        logging.info(f"Новый пользователь {user_id}. Авто-регистрация.")
        try:
            if storage.user_roles_ws:
                storage.user_roles_ws.append_row([user_id, EMPLOYEE_ROLE])
                await storage.load_user_roles()
            else:
                logging.error("Лист ролей не доступен для авто-регистрации.")
        except Exception as e:
            logging.error(f"Ошибка авто-регистрации пользователя {user_id}: {e}")
    is_admin_user = storage.is_admin(user_id)
    await message.reply(f"Привет, {message.from_user.full_name}!\nЯ бот для сбора данных (Версия: {BOT_VERSION}).", reply_markup=get_main_keyboard(is_admin_user))

async def cancel_handler(cb: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await cb.answer("Нет активных действий для отмены.")
        return
    await state.finish()
    await cb.message.edit_text("Ввод отменен.")
    await cb.answer()

async def handle_accept_downtime(cb: types.CallbackQuery):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    bot = cb.bot
    request_id = cb.data.split("accept_dt_", 1)[1]
    user = cb.from_user
    
    request = storage.pending_requests.get(request_id)
    if not request:
        await cb.answer("Эта заявка уже обработана или недействительна.", show_alert=True)
        return

    request['status'] = 'work_in_progress'
    request['accepted_by_user_id'] = user.id
    request['accepted_by_user_name'] = user.full_name
    request['acceptance_time_iso'] = datetime.now().isoformat()
    
    updated_text = request['group_notification_text'] + f"\n\n✅ **Принята в работу:** {user.full_name}"

    try:
        # <<<< НАЧАЛО ИСПРАВЛЕННОГО БЛОКА >>>>
        # Проверяем, было ли исходное сообщение с фото
        if cb.message.photo:
            await bot.edit_message_caption(
                caption=updated_text,
                chat_id=request["responsible_group_id"],
                message_id=request["group_notification_message_id"],
                parse_mode='Markdown',
                reply_markup=get_group_work_completion_keyboard(request_id)
            )
        else:
            await bot.edit_message_text(
                text=updated_text,
                chat_id=request["responsible_group_id"],
                message_id=request["group_notification_message_id"],
                parse_mode='Markdown',
                reply_markup=get_group_work_completion_keyboard(request_id)
            )
        # <<<< КОНЕЦ ИСПРАВЛЕННОГО БЛОКА >>>>
    except Exception as e:
        logging.error(f"Ошибка обновления сообщения в группе {request['responsible_group_id']}: {e}")
    
    initiator_chat_id = request["initiating_user_chat_id"]
    try:
        await bot.send_message(
            initiator_chat_id,
            f"✅ Ваша заявка принята группой '{request['responsible_group_name']}'.\nПринял(а): {user.full_name}."
        )
    except Exception as e:
        logging.error(f"Не удалось уведомить инициатора {request['initiating_user_id']}: {e}")

    await cb.answer("Заявка принята!")

async def handle_group_work_complete(cb: types.CallbackQuery):
    dp = Dispatcher.get_current()
    storage: DataStorage = dp['storage']
    bot = cb.bot
    request_id = cb.data.split("gw_simple_", 1)[1]
    user = cb.from_user

    request = storage.pending_requests.get(request_id)
    if not request:
        await cb.answer("Эта заявка уже обработана или недействительна.", show_alert=True)
        return
        
    request['status'] = 'pending_initiator_closure'
    request['group_completion_time'] = datetime.now().isoformat()
    
    initiator_id = request['initiating_user_id']
    initiator_chat_id = request['initiating_user_chat_id']
    fsm_context = FSMContext(storage=dp.storage, chat=initiator_chat_id, user=initiator_id)
    
    try:
        fsm_data = json.loads(request["downtime_fsm_data_json"])
        await fsm_context.set_data(fsm_data)
        
        async with fsm_context.proxy() as data:
            data['request_id'] = request.get('request_id')
            data['accepted_by_user_id'] = request.get('accepted_by_user_id')
            data['accepted_by_user_name'] = request.get('accepted_by_user_name')
            data['acceptance_time'] = datetime.fromisoformat(request['acceptance_time_iso']).strftime("%Y-%m-%d %H:%M:%S")
            data['group_completed_by_id'] = user.id
            data['group_completed_by_name'] = user.full_name
            data['group_completion_time'] = datetime.fromisoformat(request['group_completion_time']).strftime("%Y-%m-%d %H:%M:%S")

        await fsm_context.set_state(DowntimeForm.waiting_for_downtime_end)
        await bot.send_message(initiator_chat_id, f"✅ Работы по вашей заявке со стороны группы '{request['responsible_group_name']}' завершены.", reply_markup=get_end_downtime_keyboard())
        
        final_text = request['group_notification_text'] + f"\n\n✅ **Принята:** {request.get('accepted_by_user_name', 'Н/Д')}" + f"\n🏁 **Работа завершена:** {user.full_name}"
        
        # <<<< НАЧАЛО ИСПРАВЛЕННОГО БЛОКА >>>>
        if cb.message.photo:
            await bot.edit_message_caption(
                caption=final_text, chat_id=cb.message.chat.id,
                message_id=cb.message.message_id, parse_mode='Markdown'
            )
        else:
            await bot.edit_message_text(
                text=final_text, chat_id=cb.message.chat.id,
                message_id=cb.message.message_id, parse_mode='Markdown'
            )
        # <<<< КОНЕЦ ИСПРАВЛЕННОГО БЛОКА >>>>

        await cb.answer("Работа завершена! Инициатор уведомлен.")
    except Exception as e:
        logging.error(f"Ошибка в handle_group_work_complete: {e}", exc_info=True)

def register_other_handlers(dp: Dispatcher):
    dp.register_message_handler(send_welcome, commands=['start', 'help'], state="*")
    dp.register_callback_query_handler(cancel_handler, text="cancel_input", state="*")
    dp.register_callback_query_handler(handle_accept_downtime, lambda c: c.data.startswith("accept_dt_"))
    dp.register_callback_query_handler(handle_group_work_complete, lambda c: c.data.startswith("gw_simple_"))