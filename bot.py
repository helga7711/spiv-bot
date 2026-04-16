"""
SPIV Project Bot — ANIMA Project Telegram Notifier
"""

import asyncio
import logging
import re
import os
from datetime import date, timedelta
from html import escape

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BOT_TOKEN, CHAT_ID, THREAD_ID, TEAM_HANDLES, EXCEL_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROJECT_END = date(2026, 6, 11)
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

# Меми — 36 файлів, призначаємо по порядку нагадувань
MEMES_DIR = os.path.join(os.path.dirname(__file__), "memes")
MEME_FILES = sorted([
    os.path.join(MEMES_DIR, f)
    for f in os.listdir(MEMES_DIR)
    if f.startswith("meme_")
]) if os.path.exists(MEMES_DIR) else []


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
        if p == "Дизайнер":
            result.append("Дизайнер")
            continue
        handle = TEAM_HANDLES.get(p)
        result.append(f"@{handle}" if handle else p)
    return result

def tag_single(owner):
    if not isinstance(owner, str) or not owner.strip():
        return None
    if owner.strip() == "Дизайнер":
        return "Дизайнер"
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

def adjust_for_weekend(d):
    if d.weekday() == 5: return d - timedelta(days=1)
    if d.weekday() == 6: return d - timedelta(days=2)
    return d

def is_animation(filepath):
    return filepath.lower().endswith(('.gif', '.webp'))


# ─── Reminder schedule builder ────────────────────────────────────────────────

def build_reminder_schedule(meetings_df):
    """Повертає список нагадувань у хронологічному порядку."""
    reminders = []
    for _, row in meetings_df.iterrows():
        activity = str(row["Activities"]).strip()
        meet_type = str(row["Type"]).strip()
        if activity in NO_REMINDER_MEETINGS:
            continue
        meet_date = row["Start Date"].date()

        for days_before, hour in [(2, 10), (1, 10), (0, 10)]:
            if activity in DAY_ONLY_REMINDER_MEETINGS and days_before > 0:
                continue
            send_date = meet_date - timedelta(days=days_before)
            send_date = adjust_for_weekend(send_date)
            # Пт — тільки зовнішні (якщо нагадування не в день зустрічі)
            if send_date.weekday() == 4 and days_before > 0 and meet_type == "Внутрішня":
                continue
            # Пн — пропускаємо (є дайджест)
            if send_date.weekday() == 0:
                continue
            if send_date < BOT_START:
                continue
            real_days = (meet_date - send_date).days
            reminders.append({
                "send_date": send_date,
                "sort_key": (send_date, hour),
                "row": row,
                "real_days": real_days,
            })
    reminders.sort(key=lambda x: x["sort_key"])
    return reminders


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
    lines = [f'<b>📋 ANIMA | Тиждень {wn} ({fmt_short(week_start)} – {fmt_short(week_end)})</b>  |  залишилось {wl} тижнів']
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
                lines.append(f"📅 <code>{fmt_long(r['Start Date'])} о 15:00</code>")
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
    else:
        lines.append("<i>Проєкт ANIMA · SPIV studio</i>")
    return "\n".join(lines)


def build_reminder_text(row, real_days):
    activity = h(row["Activities"])
    meet_type = str(row["Type"]).strip()
    owner_tags = tags_from_owners(row["Owner"])
    tags_str = " ".join(owner_tags)
    time_str = " о 15:00" if meet_type == "Зовнішня" else ""
    date_str = fmt_long(row["Start Date"]) + time_str

    if real_days >= 2:
        text = (
            f"Є контакт 👀\n"
            f"<b>{activity}</b> вже {date_str}!\n\n"
            f"{tags_str} — час діставати нотатки зі стосу «колись розберуся» 📂"
        )
    elif real_days == 1:
        text = (
            f"Ану хто тут готується до <b>{activity}</b>? 👀\n"
            f"Завтра о {'15:00' if meet_type == 'Зовнішня' else '—'}, нагадую на всяк випадок\n\n"
            f"{tags_str} 💪"
        )
    else:
        text = (
            f"Доброго ранку, красені! ☀️\n"
            f"Сьогодні маємо <b>{activity}</b>{time_str}\n\n"
            f"{tags_str} поїхали! 🚀"
        )
    return text


# ─── Send helpers ─────────────────────────────────────────────────────────────

async def send_meme_reminder(bot, chat_id, thread_id, text, meme_path):
    """Відправляє мем + текст."""
    try:
        if is_animation(meme_path):
            await bot.send_animation(
                chat_id=chat_id,
                message_thread_id=thread_id,
                animation=open(meme_path, "rb"),
                caption=text,
                parse_mode="HTML"
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                message_thread_id=thread_id,
                photo=open(meme_path, "rb"),
                caption=text,
                parse_mode="HTML"
            )
    except Exception as e:
        log.error(f"Meme send failed: {e}")
        await bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text=text, parse_mode="HTML")


# ─── Scheduled Jobs ───────────────────────────────────────────────────────────

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

    # Будуємо повний розклад і знаходимо індекс сьогоднішніх нагадувань
    all_reminders = build_reminder_schedule(meetings_df)

    for i, rem in enumerate(all_reminders):
        if rem["send_date"] != today:
            continue
        meme_path = MEME_FILES[i % len(MEME_FILES)] if MEME_FILES else None
        text = build_reminder_text(rem["row"], rem["real_days"])
        if meme_path:
            await send_meme_reminder(bot, CHAT_ID, THREAD_ID, text, meme_path)
        else:
            await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=text, parse_mode="HTML")
        log.info(f"Reminder sent: {rem['row']['Activities']}")


async def send_farewell():
    bot = Bot(token=BOT_TOKEN)
    msg = (
        "🎉 <b>Ми це зробили!</b>\n"
        "Вітаю вас, моя реально-фізична команда SPIV 🙌\n\n"
        "Був радий служити вам,\n"
        "ваш Spiv Anima Bot 🤖\n\n"
        "Самознищення через 3... 2... 1... 💥"
    )
    await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=msg, parse_mode="HTML")
    log.info("Farewell sent")


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Генерую дайджест...")
    await send_weekly_digest()
    await update.message.reply_text("✅ Готово! Перевір чат групи.")

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Шукаю зустрічі на найближчі 7 днів...")
    bot = Bot(token=BOT_TOKEN)
    meetings_df = load_meetings()
    today = date.today()
    sent = 0
    all_reminders = build_reminder_schedule(meetings_df)
    for i, rem in enumerate(all_reminders):
        days = (rem["row"]["Start Date"].date() - today).days
        if 0 <= days <= 7:
            meme_path = MEME_FILES[i % len(MEME_FILES)] if MEME_FILES else None
            text = build_reminder_text(rem["row"], days)
            if meme_path:
                await send_meme_reminder(bot, CHAT_ID, THREAD_ID, text, meme_path)
            else:
                await bot.send_message(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=text, parse_mode="HTML")
            sent += 1
    if sent == 0:
        await update.message.reply_text("ℹ️ Зустрічей на найближчі 7 днів не знайдено.")
    else:
        await update.message.reply_text(f"✅ Відправлено {sent} нагадувань!")


async def cmd_extremetest19(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відправляє ВСІ повідомлення бота в особисті (не в гілку проєкту!)"""
    chat_id = update.effective_chat.id  # особисті повідомлення або чат звідки прийшла команда
    bot = Bot(token=BOT_TOKEN)

    await update.message.reply_text("🚀 Починаю надсилати всі повідомлення тут (не в групу)...\nЦе займе кілька хвилин.")

    tasks_df = load_tasks()
    meetings_df = load_meetings()
    all_reminders = build_reminder_schedule(meetings_df)

    # Дайджести
    d = BOT_START
    end = date(2026, 6, 8)
    week_num = FIRST_WEEK_NUM
    while d <= end:
        week_end = d + timedelta(days=6)
        msg = build_digest(tasks_df, meetings_df, d, week_end)
        await bot.send_message(chat_id=chat_id, text=f"📅 <b>ДАЙДЖЕСТ — Пн {d.strftime('%d.%m')} о 09:00</b>\n\n{msg}", parse_mode="HTML")
        await asyncio.sleep(0.5)
        d += timedelta(weeks=1)
        week_num += 1

    # Нагадування
    for i, rem in enumerate(all_reminders):
        meme_path = MEME_FILES[i % len(MEME_FILES)] if MEME_FILES else None
        text = f"📅 <b>НАГАДУВАННЯ — {rem['send_date'].strftime('%d.%m')} о 10:00</b>\n\n" + build_reminder_text(rem["row"], rem["real_days"])
        if meme_path:
            await send_meme_reminder(bot, chat_id, None, text, meme_path)
        else:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        await asyncio.sleep(0.5)

    # Прощання
    farewell = (
        "📅 <b>ПРОЩАННЯ — 11.06 о 15:05</b>\n\n"
        "🎉 <b>Ми це зробили!</b>\n"
        "Вітаю вас, моя реально-фізична команда SPIV 🙌\n\n"
        "Був радий служити вам,\nваш Spiv Anima Bot 🤖\n\nСамознищення через 3... 2... 1... 💥"
    )
    await bot.send_message(chat_id=chat_id, text=farewell, parse_mode="HTML")
    await update.message.reply_text("✅ Всі повідомлення надіслано!")


# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    # Дайджест — щопонеділка о 10:00 Київ
    scheduler.add_job(send_weekly_digest, "cron", day_of_week="mon", hour=10, minute=0)
    # Нагадування — щодня о 10:00 Київ (одне відправлення!)
    scheduler.add_job(send_meeting_reminders, "cron", hour=10, minute=5)
    # Прощання — 11.06.2026 о 15:05
    scheduler.add_job(send_farewell, "date", run_date="2026-06-11 15:05:00")
    scheduler.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("extremetest19", cmd_extremetest19))

    log.info("SPIV Bot started ✅")
    log.info("Команди: /test | /remind | /extremetest19")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
