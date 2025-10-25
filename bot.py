"""
Улучшённый бонус-бот (python-telegram-bot v21.x)
- JSON-хранилище в data/
- подтверждение покупок
- админ-панель с кнопками
- безопасное экранирование MarkdownV2
- логирование в bot.log
"""

import os
import json
import random
import logging
from typing import Optional, Dict, Any, List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------------
# SETTINGS (replace TOKEN)
# -------------------------
TOKEN = "8404250282:AAE1imGNWceA3NggkT2Q_lSnsK16qs-vokk"  # <-- ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН
ADMINS = [1176944561, 1284015566]  # список админов
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
LOG_FILE = "bot.log"

# товары (name, price)
BONUS_ITEMS: List[Tuple[str, int]] = [
    ("🥤 Напитки", 100),
    ("🍟 Гарниры", 100),
    ("🔥 Горячие блюда", 330),
    ("🥓 Закуски", 300),
    ("🍳 Завтраки", 200),
    ("🍝 Паста", 250),
    ("🍕 Пицца", 250),
    ("🍣 Роллы", 300),
    ("🥗 Салаты", 220),
    ("🥩 Стейки", 360),
    ("🍲 Супы", 200),
]
ITEMS_PER_PAGE = 5

# -------------------------
# LOGGING
# -------------------------
logger = logging.getLogger("bonus_bot")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(ch)

# -------------------------
# HELPERS: file storage, escape
# -------------------------
def ensure_data_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    for path in (USERS_FILE, CODES_FILE):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)


def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path: str, data: Dict[str, Any]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def md_escape(s: str) -> str:
    """
    Экранирование для MarkdownV2
    """
    if s is None:
        return ""
    to_escape = r'\_*[]()~`>#+-=|{}.!'
    res = ""
    for ch in str(s):
        if ch in to_escape:
            res += "\\" + ch
        else:
            res += ch
    return res


# balance functions
def get_balance(uid: int) -> int:
    users = load_json(USERS_FILE)
    return int(users.get(str(uid), 0))


def add_balance(uid: int, amount: int):
    users = load_json(USERS_FILE)
    users[str(uid)] = users.get(str(uid), 0) + int(amount)
    save_json(USERS_FILE, users)
    logger.info("Add balance: user=%s amount=%s new=%s", uid, amount, users[str(uid)])


def spend_balance(uid: int, amount: int) -> bool:
    users = load_json(USERS_FILE)
    cur = int(users.get(str(uid), 0))
    if cur >= amount:
        users[str(uid)] = cur - int(amount)
        save_json(USERS_FILE, users)
        logger.info("Spend: user=%s amount=%s left=%s", uid, amount, users[str(uid)])
        return True
    return False


# codes functions
def create_code(code: str, amount: int):
    codes = load_json(CODES_FILE)
    codes[code] = int(amount)
    save_json(CODES_FILE, codes)
    logger.info("Create code: %s -> %s", code, amount)


def pop_code(code: str) -> Optional[int]:
    codes = load_json(CODES_FILE)
    if code in codes:
        val = codes.pop(code)
        save_json(CODES_FILE, codes)
        logger.info("Use code: %s -> %s", code, val)
        return int(val)
    return None


def gen_code(length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(alphabet, k=length))


# -------------------------
# UI: keyboards
# -------------------------
def main_menu_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("Мой баланс 💰", callback_data="show_balance")],
        [InlineKeyboardButton("Ввести код ➡️", callback_data="enter_code")],
        [InlineKeyboardButton("Бонусное меню 🎁", callback_data="bonus_page_0")],
        [InlineKeyboardButton("Админ-панель 🛠", callback_data="open_admin")],
    ]
    return InlineKeyboardMarkup(kb)


def bonus_page_kb(page: int = 0) -> InlineKeyboardMarkup:
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    kb = []
    for idx, (name, price) in enumerate(BONUS_ITEMS[start:end], start):
        kb.append([InlineKeyboardButton(f"{name} — {price}", callback_data=f"want_buy_{idx}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"bonus_page_{page-1}"))
    if end < len(BONUS_ITEMS):
        nav.append(InlineKeyboardButton("▶️ Далее", callback_data=f"bonus_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🏠 Главное меню", callback_data="go_main")])
    return InlineKeyboardMarkup(kb)


def buy_confirm_kb(item_idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Да", callback_data=f"confirm_buy_{item_idx}"),
             InlineKeyboardButton("❌ Нет", callback_data="cancel_buy")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="go_main")]
        ]
    )


def admin_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Создать код вручную", callback_data="admin_create_manual")],
        [InlineKeyboardButton("🎲 Сгенерировать код", callback_data="admin_generate")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="admin_list_users")],
        [InlineKeyboardButton("➕ Начислить пользователю", callback_data="admin_grant_user")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏠 Назад", callback_data="go_main")],
    ]
    return InlineKeyboardMarkup(kb)


# -------------------------
# HANDLERS
# -------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Это бонусный бот. Выбери действие:",
        reply_markup=main_menu_kb()
    )


async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    uid = q.from_user.id
    data = q.data or ""

    # безопасный ответ на callback (может быть старым)
    try:
        await q.answer()
    except Exception:
        pass

    # MAIN
    if data == "go_main":
        try:
            await q.edit_message_text("🏠 Главное меню", reply_markup=main_menu_kb())
        except Exception:
            await q.message.reply_text("🏠 Главное меню", reply_markup=main_menu_kb())
        return

    if data == "show_balance":
        bal = get_balance(uid)
        text = f"💰 Баланс: *{md_escape(str(bal))}*"
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu_kb())
        except Exception:
            await q.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu_kb())
        return

    if data == "enter_code":
        context.user_data["await_code"] = True
        try:
            await q.edit_message_text("✏️ Пришли код (например: ABC123) — он будет списан и добавлен к балансу.")
        except Exception:
            await q.message.reply_text("✏️ Пришли код (например: ABC123) — он будет списан и добавлен к балансу.")
        return

    # BONUS paging
    if data.startswith("bonus_page_"):
        try:
            page = int(data.split("_")[2])
        except (IndexError, ValueError):
            page = 0
        try:
            await q.edit_message_text("🎁 Бонусное меню — выберите товар:", reply_markup=bonus_page_kb(page))
        except Exception:
            await q.message.reply_text("🎁 Бонусное меню — выберите товар:", reply_markup=bonus_page_kb(page))
        return

    # want to buy -> confirm
    if data.startswith("want_buy_"):
        try:
            idx = int(data.split("_")[2])
        except (IndexError, ValueError):
            await q.answer("Ошибка", show_alert=True)
            return
        name, price = BONUS_ITEMS[idx]
        msg = f"Вы хотите купить *{md_escape(name)}* за *{price}* бонусов?"
        try:
            await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=buy_confirm_kb(idx))
        except Exception:
            await q.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=buy_confirm_kb(idx))
        return

    # confirm purchase
    if data.startswith("confirm_buy_"):
        try:
            idx = int(data.split("_")[2])
            name, price = BONUS_ITEMS[idx]
        except (IndexError, ValueError):
            await q.answer("Ошибка", show_alert=True)
            return
        if spend_balance(uid, price):
            text = f"✅ Куплено: *{md_escape(name)}* за *{price}* бонусов.\n💰 Остаток: *{md_escape(str(get_balance(uid)))}*"
            try:
                await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu_kb())
            except Exception:
                await q.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_menu_kb())
        else:
            bal = get_balance(uid)
            text = f"🚫 Недостаточно бонусов (требуется: {price}, есть: {bal})"
            try:
                await q.edit_message_text(text, reply_markup=main_menu_kb())
            except Exception:
                await q.message.reply_text(text, reply_markup=main_menu_kb())
        return

    if data == "cancel_buy":
        try:
            await q.edit_message_text("Покупка отменена.", reply_markup=main_menu_kb())
        except Exception:
            await q.message.reply_text("Покупка отменена.", reply_markup=main_menu_kb())
        return

    # ADMIN OPEN
    if data == "open_admin":
        if uid not in ADMINS:
            try:
                await q.edit_message_text("🚫 У вас нет доступа к админ-панели.")
            except Exception:
                await q.message.reply_text("🚫 У вас нет доступа к админ-панели.")
            return
        try:
            await q.edit_message_text("🛠 Админ-панель:", reply_markup=admin_kb())
        except Exception:
            await q.message.reply_text("🛠 Админ-панель:", reply_markup=admin_kb())
        return

    # ADMIN: create manual
    if data == "admin_create_manual":
        if uid not in ADMINS:
            await q.answer("Нет доступа", show_alert=True)
            return
        context.user_data["admin_create_manual"] = True
        try:
            await q.edit_message_text("Отправьте код и сумму через пробел: CODE 250")
        except Exception:
            await q.message.reply_text("Отправьте код и сумму через пробел: CODE 250")
        return

    # ADMIN: generate random
    if data == "admin_generate":
        if uid not in ADMINS:
            await q.answer("Нет доступа", show_alert=True)
            return
        context.user_data["admin_gen_amount"] = True
        try:
            await q.edit_message_text("Отправьте сумму для случайного кода (например: 250)")
        except Exception:
            await q.message.reply_text("Отправьте сумму для случайного кода (например: 250)")
        return

    # ADMIN: list users
    if data == "admin_list_users":
        if uid not in ADMINS:
            await q.answer("Нет доступа", show_alert=True)
            return
        users = load_json(USERS_FILE)
        if not users:
            try:
                await q.edit_message_text("Пока нет пользователей.")
            except Exception:
                await q.message.reply_text("Пока нет пользователей.")
            return
        lines = [f"🆔 {md_escape(k)} — {md_escape(str(v))}" for k, v in users.items()]
        msg = "👥 Пользователи:\n\n" + "\n".join(lines[:200])
        try:
            await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            await q.message.reply_text(msg)
        return

    # ADMIN: grant to user
    if data == "admin_grant_user":
        if uid not in ADMINS:
            await q.answer("Нет доступа", show_alert=True)
            return
        context.user_data["admin_grant_user"] = True
        try:
            await q.edit_message_text("Напишите: user_id amount  (например: 123456789 250)")
        except Exception:
            await q.message.reply_text("Напишите: user_id amount  (например: 123456789 250)")
        return

    # ADMIN: broadcast
    if data == "admin_broadcast":
        if uid not in ADMINS:
            await q.answer("Нет доступа", show_alert=True)
            return
        context.user_data["admin_broadcast"] = True
        try:
            await q.edit_message_text("Отправьте текст рассылки (будет отправлен всем пользователям).")
        except Exception:
            await q.message.reply_text("Отправьте текст рассылки (будет отправлен всем пользователям).")
        return

    # fallback: unknown
    await q.answer()


async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    uid = msg.from_user.id
    text = msg.text.strip()

    # Admin: manual create code flow
    if context.user_data.get("admin_create_manual"):
        context.user_data.pop("admin_create_manual", None)
        if uid not in ADMINS:
            await msg.reply_text("🚫 Нет доступа.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await msg.reply_text("Неверный формат. Пример: MYCODE 250")
            return
        code, amt = parts[0], int(parts[1])
        create_code(code, amt)
        await msg.reply_text(f"✅ Код {md_escape(code)} создан на {amt} бонусов.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Admin: gen random code flow
    if context.user_data.get("admin_gen_amount"):
        context.user_data.pop("admin_gen_amount", None)
        if uid not in ADMINS:
            await msg.reply_text("🚫 Нет доступа.")
            return
        if not text.isdigit():
            await msg.reply_text("Нужно число. Пример: 250")
            return
        amt = int(text)
        code = gen_code()
        create_code(code, amt)
        await msg.reply_text(f"🎲 Сгенерирован код {md_escape(code)} на {amt} бонусов.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Admin: grant user flow
    if context.user_data.get("admin_grant_user"):
        context.user_data.pop("admin_grant_user", None)
        if uid not in ADMINS:
            await msg.reply_text("🚫 Нет доступа.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await msg.reply_text("Формат: user_id amount  (например: 123456789 250)")
            return
        user_id, amt = int(parts[0]), int(parts[1])
        add_balance(user_id, amt)
        await msg.reply_text(f"✅ Пользователю {user_id} начислено {amt} бонусов.")
        return

    # Admin: broadcast
    if context.user_data.get("admin_broadcast"):
        context.user_data.pop("admin_broadcast", None)
        if uid not in ADMINS:
            await msg.reply_text("🚫 Нет доступа.")
            return
        users = load_json(USERS_FILE)
        count = 0
        text_to_send = text
        for user_id in list(users.keys()):
            try:
                await context.bot.send_message(int(user_id), text_to_send)
                count += 1
            except Exception as e:
                logger.warning("Broadcast failed to %s: %s", user_id, e)
        await msg.reply_text(f"✅ Рассылка отправлена {count} пользователям.")
        return

    # Redeem code flow
    if context.user_data.get("await_code"):
        context.user_data.pop("await_code", None)
        code = text
        val = pop_code(code)
        if val is not None:
            add_balance(uid, val)
            await msg.reply_text(f"✅ Код принят! Вам начислено {val} бонусов. Баланс: {get_balance(uid)}",
                                 reply_markup=main_menu_kb())
        else:
            await msg.reply_text("❌ Код недействителен или уже использован.", reply_markup=main_menu_kb())
        return

    # /start shortcut
    if text == "/start":
        await cmd_start(update, context)
        return

    # admin text commands (quick)
    if text.startswith("/gen ") and uid in ADMINS:
        parts = text.split()
        if len(parts) == 3 and parts[2].isdigit():
            create_code(parts[1], int(parts[2]))
            await msg.reply_text(f"✅ Код {md_escape(parts[1])} создан на {parts[2]} бонусов.", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await msg.reply_text("❌ Формат: /gen CODE AMOUNT")
        return

    if text.startswith("/gen_auto ") and uid in ADMINS:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            code = gen_code()
            create_code(code, int(parts[1]))
            await msg.reply_text(f"🎲 Случайный код {md_escape(code)} создан на {parts[1]} бонусов.", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await msg.reply_text("❌ Формат: /gen_auto AMOUNT")
        return

    if text == "/users" and uid in ADMINS:
        users = load_json(USERS_FILE)
        if not users:
            await msg.reply_text("Пользователей нет.")
            return
        lines = [f"🆔 {md_escape(k)} — {md_escape(str(v))}" for k, v in users.items()]
        await msg.reply_text("👥 Пользователи:\n" + "\n".join(lines[:200]), parse_mode=ParseMode.MARKDOWN_V2)
        return

    # default reply
    await msg.reply_text("ℹ️ Используй кнопки меню или /start чтобы открыть главное меню.")


# -------------------------
# BOOT
# -------------------------
def main():
    ensure_data_files()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))

    logger.info("Starting bot...")
    app.run_polling()


if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        logger.error("TOKEN is not set. Put your bot token into the TOKEN variable before running.")
        print("ERROR: Set your bot token in the script (TOKEN variable).")
    else:
        main()