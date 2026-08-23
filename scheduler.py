import os
import datetime
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client

# Supabase and Telegram Config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") # ဥပမာ - @your_channel_username သို့မဟုတ် -100xxxxxxx

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_subscriptions_task():
    print("Running subscription expiry check task...")
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot token not configured.")
        return

    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        # 1. Check for expired users (Kick out plan)
        response = supabase.table("users").select("*").eq("status", "active").execute()
        users = response.data

        for user in users:
            expires_at_str = user.get("subscription_expires_at")
            if not expires_at_str:
                continue
            
            expires_at = datetime.datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            telegram_id = user.get("telegram_id")

            # အကယ်၍ သက်တမ်းကုန်သွားပြီဆိုလျှင်
            if expires_at < now:
                print(f"Subscription expired for user Telegram ID: {telegram_id}")
                
                # Update status to expired in database
                supabase.table("users").update({"status": "expired"}).eq("telegram_id", telegram_id).execute()

                # Send expiration message to user
                msg = (
                    "❌ *Subscription Expired*\n\n"
                    "သင်၏ NZ Job Scout Subscription သက်တမ်း ကုန်ဆုံးသွားပြီ ဖြစ်ပါသည်။ "
                    "ထို့ကြောင့် Paid Channel မှ အလိုအလျောက် ဖယ်ရှားလိုက်ပါပြီ။\n\n"
                    "ဆက်လက်အသုံးပြုလိုပါက Website သို့ဝင်၍ သက်တမ်းပြန်တိုးနိုင်ပါသည်။"
                )
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": telegram_id,
                    "text": msg,
                    "parse_mode": "Markdown"
                })

                # Kick out from Telegram Channel/Group (if channel ID is provided)
                if TELEGRAM_CHANNEL_ID:
                    # Ban user
                    ban_res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/banChatMember", json={
                        "chat_id": TELEGRAM_CHANNEL_ID,
                        "user_id": telegram_id
                    })
                    # Unban immediately so they can rejoin via new link later if they renew
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/unbanChatMember", json={
                        "chat_id": TELEGRAM_CHANNEL_ID,
                        "user_id": telegram_id
                    })
                    print(f"Kicked user {telegram_id} from channel {TELEGRAM_CHANNEL_ID}")

            # 2. Check for 3-day reminder
            elif (expires_at - now) <= datetime.timedelta(days=3) and not user.get("reminder_sent"):
                print(f"Sending 3-day reminder to user: {telegram_id}")
                reminder_msg = (
                    "⚠️ *Subscription Renewal Reminder*\n\n"
                    "မင်္ဂလာပါ! သင်၏ NZ Job Scout Subscription သက်တမ်း **၃ ရက်အတွင်း** ကုန်ဆုံးတော့မည် ဖြစ်ပါသည်။ "
                    "ဆက်လက်အသုံးပြုနိုင်ရန် ကျေးဇူးပြု၍ သက်တမ်းတိုးပေးပါရန် မေတ္တာရပ်ခံအပ်ပါသည်။"
                )
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": telegram_id,
                    "text": reminder_msg,
                    "parse_mode": "Markdown"
                })
                # Mark reminder as sent to avoid spamming
                supabase.table("users").update({"reminder_sent": True}).eq("telegram_id", telegram_id).execute()

    except Exception as e:
        print(f"Error in subscription check task: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    # နေ့စဉ် တစ်ကြိမ် (သို့မဟုတ် လိုအပ်သလို အချိန်ပိုင်းခြား၍) စစ်ဆေးရန်
    scheduler.add_job(check_subscriptions_task, 'interval', hours=24)
    scheduler.start()
    print("Background scheduler started successfully.")