#!/usr/bin/env python3
"""
SPIV Checklist Bot for Telegram
Usage: python spiv_bot.py YOUR_BOT_TOKEN
"""

import sys
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# ─── CHECKLISTS ───────────────────────────────────────────────────────────────

CHECKLISTS = {
    "prestart": {
        "title": "🚀 PRE-START CHECKLIST",
        "subtitle": "Перед стартом проєкту",
        "items": [
            "ТЗ погоджено з клієнтом",
            "Вхідна інформація про носії отримана",
            "Гант з дедлайнами закріплено в групі, дедлайни погоджено",
            "Внутрішні зустрічі заплановано",
            "Зустрічі з клієнтом заплановано до кінця проєкту",
            "Фінальний дедлайн закріплений у чаті",
            "Папка проєкту створена на Google Диску + Canva",
            "Перший платіж отриманий",
        ]
    },

    "zoom": {
        "title": "🎯 ZOOM-ФІЛЬТР Брейн-шторм",
        "subtitle": "Перед зустріччю",
        "items": [
            "Мета зуму сформульована",
            "Це можна вирішити в чаті? → якщо ні — заповни далі",
            "Відмітив хто конкретно потрібен на зумі",
            "Підготував 5 готових (дуже сирих) ідей до зуму",
            "Таймінг: 15 хвилин",
            "Таймінг: 30 хвилин",
        ]
    },
}

WEEKLY_MEMBERS = [
    "@Olha_Yesvandzhyia",
    "@mariiyasoroka",
    "@sophie_rekun",
    "@DmitrenkoA",
    "@DimaErlikh",
    "@Anastasiia_Kharasik",
    "@yamroz",
    "@OleksandraI",
]


HELP_TEXT = """
*SPIV Checklist Bot* 🎯

Команди:
/prestart — чек-лист старту проєкту
/weekly — щотижневий огляд
/zoom — фільтр перед брейн-штормом
/help — ця підказка
"""

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def build_keyboard(checklist_key: str, checked: set) -> InlineKeyboardMarkup:
    checklist = CHECKLISTS[checklist_key]
    buttons = []
    for i, item in enumerate(checklist["items"]):
        is_done = i in checked
        label = f"✅ {item}" if is_done else f"⬜ {item}"
        callback = f"{checklist_key}|{i}|{','.join(map(str, checked))}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])

    all_done = len(checked) == len(checklist["items"])
    if all_done:
        buttons.append([InlineKeyboardButton("🎉 Всі пункти виконані!", callback_data="done")])
    else:
        done_count = len(checked)
        total = len(checklist["items"])
        buttons.append([InlineKeyboardButton(
            f"Скинути ({done_count}/{total})",
            callback_data=f"reset|{checklist_key}"
        )])

    return InlineKeyboardMarkup(buttons)


def build_message(checklist_key: str) -> str:
    c = CHECKLISTS[checklist_key]
    return f"*{c['title']}*\n_{c['subtitle']}_"


# ─── HANDLERS ─────────────────────────────────────────────────────────────────

async def send_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    await update.message.reply_text(
        build_message(key),
        parse_mode="Markdown",
        reply_markup=build_keyboard(key, set())
    )


async def cmd_prestart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_checklist(update, context, "prestart")

async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 *WEEKLY CHECK* — розсилаю...", parse_mode="Markdown")
    for member in WEEKLY_MEMBERS:
        await update.message.reply_text(
            f"{member} знаєш задачі на цей тиждень? Дедлайни зрозумілі?\n\n👍 — все ок\n🆘 — є проблеми",
        )



async def cmd_zoom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_checklist(update, context, "zoom")



async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "done":
        return

    if data.startswith("reset|"):
        key = data.split("|")[1]
        await query.edit_message_text(
            build_message(key),
            parse_mode="Markdown",
            reply_markup=build_keyboard(key, set())
        )
        return

    parts = data.split("|")
    if len(parts) != 3:
        return

    checklist_key, item_idx_str, checked_str = parts
    item_idx = int(item_idx_str)
    checked = set(map(int, checked_str.split(","))) if checked_str else set()

    # Toggle
    if item_idx in checked:
        checked.discard(item_idx)
    else:
        checked.add(item_idx)

    await query.edit_message_text(
        build_message(checklist_key),
        parse_mode="Markdown",
        reply_markup=build_keyboard(checklist_key, checked)
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python spiv_bot.py YOUR_BOT_TOKEN")
        sys.exit(1)

    token = sys.argv[1]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("prestart", cmd_prestart))
    app.add_handler(CommandHandler("weekly", cmd_weekly))
    app.add_handler(CommandHandler("zoom", cmd_zoom))

    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ SPIV Bot запущений!")
    print("Команди: /prestart /weekly /zoom")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
