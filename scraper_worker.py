import sqlite3
import time
import requests

DB_NAME = "nz_job_saas.db"
# သင်၏ Telegram Bot Token ကို ဤနေရာတွင် ထည့်ပါ
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

def send_telegram_message(telegram_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")

def scrape_jobs_for_keywords(keywords, location):
    # ဤနေရာတွင် Job Scraper Logic (ဥပမာ - Seek, TradeMe ကဲ့သို့သောဆိုက်များမှ ရှာဖွေခြင်း) ကို ထည့်သွင်းနိုင်ပါသည်။
    # လောလောဆယ်အတွက် Mock Job Data တစ်ခု ထည့်သွင်းထားပါသည်။
    mock_jobs = [
        f"🔍 *New Job Found!* \nPosition: {keywords}\nLocation: {location}\nCompany: NZ Tech Solutions\nLink: https://example.com/job1",
        f"🔍 *New Job Found!* \nPosition: {keywords}\nLocation: {location}\nCompany: Kiwi Digital\nLink: https://example.com/job2"
    ]
    return mock_jobs

def run_worker():
    print("Background Job Scraper Worker started...")
    while True:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Subscription active ဖြစ်နေသော User များကို ထုတ်ယူခြင်း
        cursor.execute("SELECT telegram_id, job_keywords, location FROM users WHERE subscription_status = 'active'")
        active_users = cursor.fetchall()
        conn.close()

        for user in active_users:
            telegram_id, keywords, location = user
            print(f"Scraping jobs for Telegram ID: {telegram_id} ({keywords} in {location})")
            
            # အလုပ်ခေါ်စာများ ရှာဖွေခြင်း
            jobs = scrape_jobs_for_keywords(keywords, location)
            
            for job in jobs:
                # User ထံသို့ Telegram မှတဆင့် ပို့ဆောင်ခြင်း
                send_telegram_message(telegram_id, job)
                time.sleep(1)

        # ကြီးမားသော ကြားကာလ (ဥပမာ - ၁ နာရီတစ်ကြိမ်) ဖြင့် ထပ်ခါတလဲလဲ စစ်ဆေးရန်
        print("Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600) 

if __name__ == "__main__":
    run_worker()