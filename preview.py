"""
SPIV Bot Preview
Запуск: python3 preview.py
"""

import pandas as pd
from datetime import date, timedelta
from html import escape
import re

EXCEL_FILE = "ANIMA_Gantt__1_.xlsx"
PROJECT_END = date(2026, 6, 11)
BOT_START = date(2026, 3, 30)

# Зустрічі для яких НЕ надсилаємо окремих нагадувань (тільки в дайджесті)
# Без жодних нагадувань (тільки в дайджесті тижня)
NO_REMINDER_MEETINGS = {
    "Синхронізація по дослідженнях (внутрішня зустріч)",
    "Воркшоп: внутрішній синтез (внутрішня зустріч)",
}

# Тільки нагадування в день зустрічі (без за 2 дні та за 1 день)
DAY_ONLY_REMINDER_MEETINGS = {
    "Брифування Комунікація",
    "Брифування Дизайн",
}

TEAM_HANDLES = {
    "Mary":        "mariiyasoroka",
    "Serge":       "yamroz",
    "Olha":        "Olha_Yesvandzhyia",
    "Oleksandra":  "OleksandraI",
    "AnastasiyaK": "Anastasiia_Kharasik",
    "Dima":        "DimaErlikh",
    "NastyaD":     "DmitrenkoA",
}

MONTHS_UA = {
    1:"січня",2:"лютого",3:"березня",4:"квітня",
    5:"травня",6:"червня",7:"липня",8:"серпня",
    9:"вересня",10:"жовтня",11:"листопада",12:"грудня"
}

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
    # Тільки зустрічі починаючи з 30.03
    df = df[df["Start Date"].dt.date >= BOT_START].copy()
    return df

def tags_from_owners(owners_str):
    if not isinstance(owners_str, str) or not owners_str.strip():
        return []
    parts = re.split(r'[/,]', owners_str)
    result = []
    for p in parts:
        p = p.strip()
        handle = TEAM_HANDLES.get(p)
        result.append(f"@{handle}" if handle else p) if p else None
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

def build_digest(tasks_df, meetings_df, week_num, week_start, week_end):
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

    wl = weeks_left(week_start)
    lines = []
    lines.append(f'📋 ANIMA | Тиждень {week_num} ({fmt_short(week_start)} – {fmt_short(week_end)})  |  залишилось {wl} тижнів')
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")

    if not meetings.empty:
        lines.append("")
        lines.append("🗓 ЗУСТРІЧІ:")
        lines.append("")
        internal = meetings[meetings["Type"] == "Внутрішня"]
        external = meetings[meetings["Type"] == "Зовнішня"]

        if not internal.empty:
            lines.append("🏠 Внутрішні:")
            for _, r in internal.iterrows():
                tags_str = " ".join(tags_from_owners(r["Owner"]))
                lines.append(f"📍 {h(r['Activities'])}")
                if tags_str: lines.append(f"👤 {tags_str}")
                lines.append(f"📅 {fmt_long(r['Start Date'])}")
                lines.append("")

        if not external.empty:
            lines.append("🤝 Зовнішні:")
            for _, r in external.iterrows():
                tags_str = " ".join(tags_from_owners(r["Owner"]))
                lines.append(f"📍 {h(r['Activities'])}")
                if tags_str: lines.append(f"👤 {tags_str}")
                lines.append(f"📅 {fmt_long(r['Start Date'])} о 15:00")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━")

    if not tasks.empty:
        lines.append("")
        lines.append("✅ ЗАДАЧІ:")
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
            lines.append(f"👤 {t if t else owner}")
            for r in rows:
                deadline = f"до {fmt_short(r['End Date'])}" if pd.notna(r["End Date"]) else ""
                notes = f"  {h(r['Notes'])}" if pd.notna(r.get("Notes")) else ""
                lines.append(f"→ {h(r['Activities'])}")
                lines.append(f"   📅 {deadline}{notes}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    if week_num >= 11:
        lines.append("Проєкт ANIMA · SPIV studio")
        lines.append("")
        lines.append("🎉 Ми це зробили!")
        lines.append("Вітаю вас, моя реально-фізична команда SPIV 🙌")
        lines.append("")
        lines.append("Був радий служити вам,")
        lines.append("ваш Spiv Anima Bot 🤖")
        lines.append("")
        lines.append("Самознищення через 3... 2... 1... 💥")
    else:
        lines.append("Проєкт ANIMA · SPIV studio")
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
        label = f"У п'ятницю нагадуємо: зустріч у понеділок!"
    owner_tags = tags_from_owners(meeting_row["Owner"])
    tags_str = " ".join(owner_tags)
    meet_type = "🏠 Внутрішня" if meeting_row["Type"] == "Внутрішня" else "🤝 Зовнішня"
    hints = get_hints(str(meeting_row["Activities"]))

    time_str = " о 15:00" if meeting_row["Type"] == "Зовнішня" else ""
    lines = [f"⚠️ {label}", "",
        f"📍 {h(meeting_row['Activities'])}",
        f"{meet_type}",
        f"📅 {fmt_long(meeting_row['Start Date'])}{time_str}",
    ]
    if tags_str: lines.append(f"👤 {tags_str}")
    if hints:
        lines.append("")
        lines.append("🎯 Що підготувати:")
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


def main():
    tasks_df = load_tasks()
    meetings_df = load_meetings()

    all_events = []

    # Дайджести від 30.03
    week_num = 2
    d = BOT_START
    end = date(2026, 6, 8)
    while d <= end:
        week_end = d + timedelta(days=6)
        all_events.append({
            "send_at": f"Пн {d.strftime('%d.%m')} о 09:00",
            "sort_key": (d, 0),
            "type": "ДАЙДЖЕСТ",
            "week_num": week_num, "week_start": d, "week_end": week_end,
        })
        week_num += 1
        d += timedelta(weeks=1)

    # Нагадування — пропускаємо зустрічі з NO_REMINDER_MEETINGS
    for _, row in meetings_df.iterrows():
        activity = str(row["Activities"]).strip()
        if activity.strip() in NO_REMINDER_MEETINGS:
            continue
        meet_date = row["Start Date"].date()
        for days_before, hour in [(2, 10), (1, 10), (0, 9)]:
            # Брифування — тільки в день зустрічі
            if activity.strip() in DAY_ONLY_REMINDER_MEETINGS and days_before > 0:
                continue
            send_date = meet_date - timedelta(days=days_before)
            if send_date < BOT_START:
                continue
            # Якщо нагадування на вихідні — переносимо на п'ятницю
            if send_date.weekday() == 5:  # субота
                send_date = send_date - timedelta(days=1)
            elif send_date.weekday() == 6:  # неділя
                send_date = send_date - timedelta(days=2)
            # Якщо нагадування в понеділок (день дайджесту) — пропускаємо
            if send_date.weekday() == 0:
                continue
            labels = {2: "за 2 дні", 1: "за 1 день", 0: "в день зустрічі"}
            real_days_before = (meet_date - send_date).days
            all_events.append({
                "send_at": f"{send_date.strftime('%d.%m')} о {hour:02d}:00",
                "sort_key": (send_date, hour),
                "type": f"НАГАДУВАННЯ ({labels[days_before]})",
                "row": row, "days_before": real_days_before,
            })

    # Прощальне повідомлення — після останньої зустрічі 11.06
    all_events.append({
        "send_at": "11.06 о 15:05",
        "sort_key": (date(2026, 6, 11), 15),
        "type": "ПРОЩАННЯ",
        "row": None, "days_before": None,
    })

    all_events.sort(key=lambda x: x["sort_key"])

    sep = "=" * 60
    for ev in all_events:
        print(sep)
        print(f"📅 ВІДПРАВКА: {ev['send_at']}  |  {ev['type']}")
        print(sep)
        if ev["type"] == "ДАЙДЖЕСТ":
            msg = build_digest(tasks_df, meetings_df, ev["week_num"], ev["week_start"], ev["week_end"])
        elif ev["type"] == "ПРОЩАННЯ":
            msg = "🎉 Ми це зробили!\nВітаю вас, моя реально-фізична команда SPIV 🙌\n\nБув радий служити вам,\nваш Spiv Anima Bot 🤖\n\nСамознищення через 3... 2... 1... 💥"
        else:
            msg = build_reminder(ev["row"], ev["days_before"])
        print(re.sub(r'<[^>]+>', '', msg))
        print()

if __name__ == "__main__":
    main()
