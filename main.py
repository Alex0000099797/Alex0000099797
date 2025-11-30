import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from config import BOT_TOKEN, ADMIN_IDS, WEBHOOK_URL, HOST, PORT
from db import create_tables, AsyncSessionLocal, User, Request
from keyboards import request_kb, confirm_broadcast_kb
from utils import check_flood

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())

class S(StatesGroup):
    reply = State()
    broadcast = State()

# === Пользовательские сообщения ===
@dp.message(F.from_user.id.not_in(ADMIN_IDS))
async def user_message(message: Message):
    if check_flood(message.from_user.id):
        return await message.answer("Слишком часто пишете, подождите минуту")

    async with AsyncSessionLocal() as s:
        user = await s.get(User, message.from_user.id)
        if not user:
            user = User(user_id=message.from_user.id, first_name=message.from_user.first_name or "")
            s.add(user)
        if user.is_banned:
            return await message.answer("Вы в бане")

        file_id = file_type = None
        if message.photo:
            file_id, file_type = message.photo[-1].file_id, "photo"
        elif message.video:
            file_id, file_type = message.video.file_id, "video"
        elif message.document:
            file_id, file_type = message.document.file_id, "document"

        req = Request(
            user_id=message.from_user.id,
            text=message.text or message.caption,
            file_id=file_id,
            file_type=file_type
        )
        s.add(req)
        await s.commit()
        await s.refresh(req)

        text = f"<b>Заявка #{req.id}</b>\nОт: <a href='tg://user?id={user.user_id}'>{message.from_user.full_name}</a>\n\n{message.text or message.caption or 'Медиа без текста'}"

        for aid in ADMIN_IDS:
            try:
                fwd = await message.forward(aid)
                await fwd.reply(text, reply_markup=request_kb(req.id))
            except:
                await bot.send_message(aid, text, reply_markup=request_kb(req.id))

        await message.answer(f"Заявка принята №{req.id}\nОтветим скоро")

# === Админка и кнопки ===
@dp.message(Command("panel"), F.from_user.id.in_(ADMIN_IDS))
async def panel(m: Message):
    async with AsyncSessionLocal() as s:
        new = (await s.execute("SELECT COUNT(*) FROM requests WHERE status='new'")).scalar()
        ban = (await s.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")).scalar()
    await m.answer(f"<b>Панель админа</b>\nНовых заявок: {new}\nЗабанено: {ban}\n\n/broadcast — рассылка")

@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(c: CallbackQuery, state: FSMContext):
    req_id = int(c.data.split("_")[1])
    await state.update_data(req_id=req_id)
    await state.set_state(S.reply)
    await c.message.edit_text(c.message.html_text + "\n\nНапишите ответ пользователю:")
    await c.answer()

@dp.message(S.reply, F.from_user.id.in_(ADMIN_IDS))
async def reply_send(m: Message, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as s:
        req = await s.get(Request, data["req_id"])
        if not req: return await m.answer("Заявка пропала")

        if m.photo:
            await bot.send_photo(req.user_id, m.photo[-1].file_id, caption=m.caption)
        elif m.video:
            await bot.send_video(req.user_id, m.video.file_id, caption=m.caption)
        elif m.document:
            await bot.send_document(req.user_id, m.document.file_id, caption=m.caption)
        else:
            await bot.send_message(req.user_id, m.text)

        req.status = "answered"
        req.admin_id = m.from_user.id
        await s.commit()

    await m.answer("Ответ отправлен!")
    await state.clear()

@dp.callback_query(F.data.startswith("ban_"))
async def ban(c: CallbackQuery):
    req_id = int(c.data.split("_")[1])
    async with AsyncSessionLocal() as s:
        req = await s.get(Request, req_id)
        if req:
            user = await s.get(User, req.user_id)
            user.is_banned = True
            req.status = "closed"
            await s.commit()
            await c.message.edit_text(c.message.html_text + "\n\nПользователь забанен")
    await c.answer()

@dp.callback_query(F.data.startswith("close_"))
async def close(c: CallbackQuery):
    req_id = int(c.data.split("_")[1])
    async with AsyncSessionLocal() as s:
        req = await s.get(Request, req_id)
        if req:
            req.status = "closed"
            await s.commit()
    await c.message.edit_reply_markup()
    await c.answer("Закрыто")

# === Рассылка ===
@dp.message(Command("broadcast"), F.from_user.id.in_(ADMIN_IDS))
async def b_start(m: Message, state: FSMContext):
    await m.answer("Перешлите/отправьте сообщение для рассылки")
    await state.set_state(S.broadcast)

@dp.message(S.broadcast, F.from_user.id.in_(ADMIN_IDS))
async def b_confirm(m: Message, state: FSMContext):
    await state.update_data(msg_id=m.message_id, chat_id=m.chat.id)
    await m.forward(m.chat.id)
    await m.answer("Разослать это всем?", reply_markup=confirm_broadcast_kb())

@dp.callback_query(F.data == "yes_broadcast")
async def b_go(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as s:
        users = (await s.execute("SELECT user_id FROM users WHERE is_banned=0")).scalars().all()

    ok = 0
    for uid in users:
        try:
            await bot.forward_message(uid, data["chat_id"], data["msg_id"])
            ok += 1
            await asyncio.sleep(0.04)
        except:
            pass

    await c.message.edit_text(f"Рассылка завершена. Доставлено: {ok}")
    await state.clear()

@dp.callback_query(F.data == "no_broadcast")
async def b_no(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отменено")
    await state.clear()

# === Запуск webhook ===
async def on_startup(_):
    await create_tables()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("Webhook установлен")

async def on_shutdown(_):
    await bot.delete_webhook()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    runner = web.AppRunner(app)
    asyncio.get_event_loop().run_until_complete(runner.setup())
    site = web.TCPSite(runner, HOST, PORT)
    asyncio.get_event_loop().run_until_complete(site.start())
    logging.info(f"Сервер запущен на {HOST}:{PORT}")
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    main()
