import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg
from aiogram import Router
from aiogram.filters import Command

import os
from dotenv import load_dotenv

load_dotenv()

# Настройки
TOKEN = os.getenv("API_TOKEN")

if not TOKEN:
    raise ValueError("No enviroment variable")

DB_CONFIG = {
    'user': 'crea_writer',
    'password': '123qweASD@',
    'database': 'crea',
    'host': 'localhost',
    'port':'5432',
}

logging.basicConfig(level=logging.INFO)

# Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключаем маршрутизатор
router = Router()

# Определяем состояния
class MailingState(StatesGroup):
    waiting_for_text = State()
    waiting_for_image_decision = State()
    waiting_for_image = State()
    waiting_for_confirmation = State()

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)

# Команда /start
@router.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    conn = await get_db_connection()
    try:
        await conn.execute(
            "INSERT INTO public.users (user_id, role) VALUES ($1, 'user') ON CONFLICT (user_id) DO NOTHING",
            user_id
        )
    finally:
        await conn.close()
    await message.reply("Поздравляю! Теперь ты точно будешь в курсе всего происходящего.")

# Команда /start_mail для админов
@router.message(Command("start_mail"))
async def start_mail_command(message: types.Message, state: FSMContext):
    role = "user"
    user_id = message.from_user.id
    conn = await get_db_connection()
    try:
        role = await conn.fetchval("SELECT role FROM public.users WHERE user_id = $1", user_id)
        if role != 'admin':
            await message.reply("У вас нет прав на выполнение этой команды.")
            return
        await state.set_state(MailingState.waiting_for_text)
        await message.reply("Введите текст для рассылки:")
    finally:
        await conn.close()
    

# Получение текста рассылки
@router.message(MailingState.waiting_for_text)
async def receive_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(MailingState.waiting_for_image_decision)
    await message.reply("Хотите добавить изображение? (да/нет)")

# Решение об изображении
@router.message(F.text.lower().in_(['да', 'нет']), MailingState.waiting_for_image_decision)
async def image_decision(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        await state.set_state(MailingState.waiting_for_image)
        await message.reply("Отправьте изображение для рассылки.")
    else:
        await state.set_state(MailingState.waiting_for_confirmation)
        await message.reply("Подтвердите отправку рассылки. Напишите 'да' или 'нет'.")

# Получение изображения
@router.message(F.content_type == "photo", MailingState.waiting_for_image)
async def receive_image(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(photo=photo.file_id)
    await state.set_state(MailingState.waiting_for_confirmation)
    await message.reply("Подтвердите отправку рассылки. Напишите 'да' или 'нет'.")

# Подтверждение рассылки
@router.message(F.text.lower().in_(['да', 'нет']), MailingState.waiting_for_confirmation)
async def confirm_mailing(message: types.Message, state: FSMContext):
    if message.text.lower() == 'да':
        data = await state.get_data()
        text = data.get('text')
        photo_id = data.get('photo')

        conn = await get_db_connection()
        try:
            users = await conn.fetch("SELECT user_id FROM public.users WHERE role = 'user'")
        finally:
            await conn.close()
        for user in users:
            try:
                if photo_id:
                    await bot.send_photo(chat_id=user['user_id'], photo=photo_id, caption=text)
                else:
                    await bot.send_message(chat_id=user['user_id'], text=text)
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
        await message.reply("Рассылка завершена.")
    else:
        await message.reply("Рассылка отменена.")
    await state.clear()

# Запуск бота
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
