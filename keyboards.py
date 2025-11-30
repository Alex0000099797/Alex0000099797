from aiogram.utils.keyboard import InlineKeyboardBuilder

def request_kb(req_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Ответить", callback_data=f"reply_{req_id}")
    kb.button(text="Бан", callback_data=f"ban_{req_id}")
    kb.button(text="Закрыть", callback_data=f"close_{req_id}")
    kb.adjust(2)
    return kb.as_markup()

def confirm_broadcast_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, разослать", callback_data="yes_broadcast")
    kb.button(text="Отмена", callback_data="no_broadcast")
    return kb.as_markup()
