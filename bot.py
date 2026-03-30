"""
SPIV Project Bot — ANIMA Project Telegram Notifier

Commands:
  /test   — надіслати дайджест задач на поточний тиждень прямо зараз
  /remind — надіслати нагадування про зустрічі на найближчі 7 днів
"""

import asyncio
import logging
import re
from datetime import date, timedelta
from html import escape

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BOT_TOKEN, CHAT_ID, THREAD_ID, TEAM_HANDLES, EXCEL_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_END = date(2026, 6, 1)
BOT_START = date(2026, 3, 30)
FIRST_WEEK_NUM = 2

NO_REMINDER_MEETINGS = {
    "Синхронізація по дослідженнях (внутрішня зустріч)",
    "Воркшоп: внутрішній синтез (внутрішня зустріч)",
}

DAY_ONLY_REMINDER_MEETINGS = {
    "Брифування Комунікація",
    "Брифування Дизайн",
}

MONTHS_UA = {
    1:"січня",2:"лютого",3:"березня",4:"квітня",
    5:"травня",6:"червня",7:"липня",8:"серпня",
    9:"вересня",10:"жовтня",11:"листопада",12:"грудня"
}


# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_tasks():
    df = pd.read_excel(EXCEL_FILE, sheet_name=0, header=0)
    df.columns = [
        "ID","Week","Category","Activities","Dependency",
        "Duration","Start Date","End Date","Completion","Type","Owner","Notes"
    ]
    df = df[
        df["ID"].notna() &
        df["Activities"].notna() &
        df["Owner"].notna() &
        (~df["Type"].isin(["Main Task", "Milestone"]))
    ].copy()
    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    df["End Date"] = pd.to_datetime(df["End Date"], errors="coerce")
    return df

def load_meetings():
    df = pd.read_excel(EXCEL_FILE, sheet_name=1, header=0)
    df.columns = ["Week","Section","Activities","Duration","Start Date","End Date","Type","Owner"]
    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    df = df[
        df["Week"].notna() &
        df["Type"].isin(["Внутрішня", "Зовнішня"]) &
        df["Activities"].notna() &
        df["Start Date"].notna()
    ].copy()
    df = df[df["Start Date"].dt.date >= BOT_START].copy()
    return df


# ─── Helpers ──────────────────────────────────────────────────────────────────

def tags_from_owners(owners_str):
    if not isinstance(owners_str, str) or not owners_str.strip():
        return []
    parts = re.split(r'[/,]', owners_str)
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        handle = TEAM_HANDLES.get(p)
        result.append(f"@{handle}" if handle else p)
    return result

def tag_single(owner):
    if not isinstance(owner, str) or not owner.strip():
        return None
    handle = TEAM_HANDLES.get(owner.strip())
    return f"@{handle}" if handle else owner.strip()

def h(text):
    if not text or (isinstance(text, float) and pd.isna(text)):
        return ""
    return escape(str(text))

def fmt_short(dt):
    if pd.isna(dt): return "—"
    d = dt.date() if hasattr(dt, 'date') else dt
    return f"{d.day:02d}.{d.month:02d}"

def fmt_long(dt):
    if pd.isna(dt): return "—"
    d = dt.date() if hasattr(dt, 'date') else dt
    return f"{d.day} {MONTHS_UA[d.month]}"

def weeks_left(from_date):
    return max(0, ((PROJECT_END - from_date).days + 6) // 7)

def week_num_for(d):
    delta = (d - BOT_START).days // 7
    return FIRST_WEEK_NUM + delta

def adjust_for_weekend(send_date):
    """Якщо нагадування на вихідні — переносимо на п'ятницю."""
    if send_date.weekday() == 5:
        return send_date - timedelta(days=1)
    elif send_date.weekday() == 6:
        return send_date - timedelta(days=2)
    return send_date


# ─── Message Builders ─────────────────────────────────────────────────────────

def build_digest(tasks_df, meetings_df, week_start, week_end):
    mask = (
        (tasks_df["Start Date"].dt.date <= week_end) &
        (tasks_df["End Date"].dt.date >= week_start) &
        (tasks_df["Completion"].fillna(0) < 1)
    )
    tasks = tasks_df[mask].copy()

    meet_mask = (
        (meetings_df["Start Date"].dt.date >= week_start) &
        (meetings_df["Start Date"].dt.date <= week_end)
    )
    meetings = meetings_df[meet_mask].copy()

    wn = week_num_for(week_start)
    wl = weeks_left(week_start)
    lines = []
    lines.append(f'<b>📋 ANIMA | Тиждень {wn} ({fmt_short(week_start)} – {fmt_short(week_end)})</b>  |  залишилось {wl} тижнів')
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")

    if not meetings.empty:
        lines.append("")
        lines.append("🗓 <b>ЗУСТРІЧІ:</b>")
        lines.append("")
        internal = meetings[meetings["Type"] == "Внутрішня"]
        external = meetings[meetings["Type"] == "Зовнішня"]

        if not internal.empty:
            lines.append("🏠 <b>Внутрішні:</b>")
            for _, r in internal.iterrows():
                tags_str = " ".join(tags_from_owners(r["Owner"]))
                lines.append(f"📍 {h(r['Activities'])}")
                if tags_str: lines.append(f"👤 {tags_str}")
                lines.append(f"📅 <code>{fmt_long(r['Start Date'])}</code>")
                lines.append("")

        if not external.empty:
            lines.append("🤝 <b>Зовнішні:</b>")
            for _, r in external.iterrows():
                tags_str = " ".join(tags_from_owners(r["Owner"]))
                lines.append(f"📍 {h(r['Activities'])}")
                if tags_str: lines.append(f"👤 {tags_str}")
                lines.append(f"📅 <code>{fmt_long(r['Start Date'])}</code>")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━")

    if not tasks.empty:
        lines.append("")
        lines.append("✅ <b>ЗАДАЧІ:</b>")
        lines.append("")
        by_owner = {}
        for _, r in tasks.iterrows():
            owner = str(r["Owner"]).strip()
            by_owner.setdefault(owner, []).append(r)

        first = True
        for owner, rows in by_owner.items():
            if not first: lines.append("")
            first = False
            t = tag_single(owner)
            lines.append(f"👤 <b>{t if t else owner}</b>")
            for r in rows:
                deadline = f"до {fmt_short(r['End Date'])}" if pd.notna(r["End Date"]) else ""
                notes = f"  <i>{h(r['Notes'])}</i>" if pd.notna(r.get("Notes")) else ""
                lines.append(f"→ {h(r['Activities'])}")
                lines.append(f"   📅 <code>{deadline}</code>{notes}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")

    if wl == 0:
        lines.append("<i>Проєкт ANIMA · SPIV studio</i>")
        lines.append("")
        lines.append("🎉 <b>Ми це зробили!</b>")
        lines.append("Вітаю вас, моя реально-фізична команда SPIV 🙌")
        lines.append("")
        lines.append("Був радий служити вам,")
        lines.append("ваш Spiv Anima Bot 🤖")
        lines.append("")
        lines.append("Самознищення через 3... 2... 1... 💥")
    else:
        lines.append("<i>Проєкт ANIMA · SPIV studio</i>")

    return "\n".join(lines)


def build_reminder(meeting_row, days_before):
    if days_before == 0:
        label = "Сьогодні зустріч!"
    elif days_before == 1:
        label = "Завтра зустріч!"
    elif days_before == 2:
        label = "Післязавтра зустріч!"
    elif days_before == 3:
        label = "Через 3 дні зустріч!"
    else:
        label = "У п'ятницю нагадуємо: зустріч у понеділок!"

    owner_tags = tags_from_owners(meeting_row["Owner"])
    tags_str = " ".join(owner_tags)
    meet_type = "🏠 Внутрішня" if meeting_row["Type"] == "Внутрішня" else "🤝 Зовнішня"
    hints = get_hints(str(meeting_row["Activities"]))

    lines = [
        f"⚠️ <b>{label}</b>", "",
        f"📍 <b>{h(meeting_row['Activities'])}</b>",
        f"{meet_type}",
        f"📅 <code>{fmt_long(meeting_row['Start Date'])}</code>",
    ]
    if tags_str: lines.append(f"👤 {tags_str}")
    if hints:
        lines.append("")
        lines.append("🎯 <b>Що підготувати:</b>")
        for hint in hints: lines.append(f"→ {hint}")
    lines.append("")
    if tags_str: lines.append(f"{tags_str} — не забудьте підготуватись! 🙏")
    return "\n".join(lines)


def get_hints(activity):
    a = activity.lower()
    hints = []
    if "кік-офф" in a or "брифінг" in a: hints += ["Матеріали клієнта / бриф", "Список питань для обговорення"]
    if "синхронізація" in a: hints += ["Статус по задачах від кожного", "Блокери та питання"]
    if "воркшоп" in a or "синтез" in a: hints += ["Результати досліджень", "Гіпотези та інсайти"]
    if "проміжна сесія" in a: hints += ["Презентаційні матеріали (до 10 слайдів)", "Q&A підготовка"]
    if "фінальна презентація" in a: hints += ["Фінальна версія deck (PDF + PPTX)", "Посилання для клієнта"]
    if "фірмового стилю" in a: hints += ["Варіанти дизайну готові до показу"]
    if "комунікації партнерам" in a: hints += ["Фінальна презентація комунікаційної платформи"]
    if "затвердження" in a: hints += ["Фінальна версія матеріалів для затвердження"]
    if "олександрою" in a: hints += ["Драфт презентації для продажів"]
    if "видача тз" in a: hints += ["Бриф та ТЗ для дизайнера"]
    if "чек" in a and "носіям" in a: hints += ["Перевірити всі носії на диску"]
    return hints


# ─── Scheduler Jobs ───────────────────────────────────────────────────────────

async def send_weekly_digest():
    bot = Bot(token=BOT_TOKEN)
    tasks_df = load_tasks()
    meetings_df = load_meetings()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    msg = build_digest(tasks_df, meetings_df, week_start, week_end)
    await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=msg, parse_mode="HTML")
    log.info("Weekly digest sent")


async def send_meeting_reminders():
    bot = Bot(token=BOT_TOKEN)
    meetings_df = load_meetings()
    today = date.today()

    for _, row in meetings_df.iterrows():
        activity = str(row["Activities"]).strip()
        if activity in NO_REMINDER_MEETINGS:
            continue
        meet_date = row["Start Date"].date()

        for days_before, hour in [(2, 10), (1, 10), (0, 9)]:
            if activity in DAY_ONLY_REMINDER_MEETINGS and days_before > 0:
                continue
            send_date = meet_date - timedelta(days=days_before)
            send_date = adjust_for_weekend(send_date)
            if send_date.weekday() == 0:  # понеділок — є дайджест
                continue
            if send_date != today:
                continue

            real_days_before = (meet_date - today).days
            msg = build_reminder(row, real_days_before)
            await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=msg, parse_mode="HTML")
            log.info(f"Reminder sent: {activity}")


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Генерую дайджест...")
    await send_weekly_digest()
    await update.message.reply_text("✅ Готово! Перевір чат групи.")

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Шукаю зустрічі на найближчі 7 днів...")
    bot = Bot(token=BOT_TOKEN)
    meetings_df = load_meetings()
    sent = 0
    today = date.today()
    for _, row in meetings_df.iterrows():
        activity = str(row["Activities"]).strip()
        if activity in NO_REMINDER_MEETINGS:
            continue
        meet_date = row["Start Date"].date()
        days_before = (meet_date - today).days
        if 0 <= days_before <= 7:
            msg = build_reminder(row, days_before)
            await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=msg, parse_mode="HTML")
            sent += 1
    if sent == 0:
        await update.message.reply_text("ℹ️ Зустрічей на найближчі 7 днів не знайдено.")
    else:
        await update.message.reply_text(f"✅ Відправлено {sent} нагадувань!")


# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(send_weekly_digest, "cron", day_of_week="mon", hour=9, minute=0)
    scheduler.add_job(send_meeting_reminders, "cron", hour=9, minute=5)
    scheduler.add_job(send_meeting_reminders, "cron", hour=10, minute=0)
    scheduler.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("remind", cmd_remind))

    log.info("SPIV Bot started ✅")
    log.info("Команди: /test — дайджест | /remind — нагадування")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
