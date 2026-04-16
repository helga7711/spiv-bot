import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
THREAD_ID = int(os.getenv("THREAD_ID", "2"))
EXCEL_FILE = os.getenv("EXCEL_FILE", "ANIMA_Gantt__1_.xlsx")

TEAM_HANDLES = {
    "Mary":        os.getenv("TG_MARY",        "mariiyasoroka"),
    "Serge":       os.getenv("TG_SERGE",       "yamroz"),
    "Olha":        os.getenv("TG_OLHA",        "Olha_Yesvandzhyia"),
    "Oleksandra":  os.getenv("TG_OLEKSANDRA",  "OleksandraI"),
    "AnastasiyaK": os.getenv("TG_ANASTASIYAK", "Anastasiia_Kharasik"),
    "Дизайнер":    None,  # немає в чаті — Оля пересилає вручну
    "NastyaD":     os.getenv("TG_NASTYA_D",    "DmitrenkoA"),
}
