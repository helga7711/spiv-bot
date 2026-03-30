"""
SPIV Bot — Configuration
========================
Fill in your values below before deploying.
"""

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
# Get your token from @BotFather on Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "8362393784:AAFP7yiKcqQFJfkmvUnNTVQ8dcad1pLJRs4")

# The group chat ID where the bot will post
# To find it: add @userinfobot to your group, it will show the chat ID
CHAT_ID = os.getenv("CHAT_ID", "-1003776784870")

# ID гілки (topic) в форум-групі куди постити повідомлення
THREAD_ID = int(os.getenv("THREAD_ID", "2"))

# ── Team Telegram Handles ─────────────────────────────────────────────────────
# Map the names from the Excel file → Telegram username (without @)
TEAM_HANDLES = {
    "Mary":        os.getenv("TG_MARY",        "mariiyasoroka"),
    "Serge":       os.getenv("TG_SERGE",       "yamroz"),
    "Olha":        os.getenv("TG_OLHA",        "Olha_Yesvandzhyia"),
    "AnastasiyaK": os.getenv("TG_ANASTASIYAK", "Anastasiia_Kharasik"),
    "Dima":        os.getenv("TG_DIMA",        "DimaErlikh"),
    "NastyaD":     os.getenv("TG_NASTYA_D",    "DmitrenkoA"),
}

# ── Excel File Path ───────────────────────────────────────────────────────────
# Path to the Gantt Excel file (relative to bot.py or absolute)
EXCEL_FILE = os.getenv("EXCEL_FILE", "ANIMA_Gantt__1_.xlsx")
