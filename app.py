from flask import Flask, render_template, request, jsonify, redirect
from scheduler import start_scheduler
import os
import stripe
import requests
import psycopg2
import threading
import datetime
from scraper_worker import run_worker_loop

app = Flask(__name__)

# Stripe & Telegram API Key Configuration
stripe.api_key = os.environ.get("STRIPE_API_KEY", "sk_test_51U4dsARsY9pyx48SiKwb9uf48pewo7OVhBijGippD1q5RufnbXL9g1Jci1Okqq36q1LjQpEV3HvvNHlYzQgapdKK004uvCslZH")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_1hF3Jy80A9x1dANaNJdlmlSoAu5eWjOK")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8746508324:AAG2tZBW8U5ZKqzwci20W2b3SPwRs1MARI4")
PRIVATE_CHANNEL_ID = "-1004349902452"

# Supabase PostgreSQL Connection URL ကို Render Environment Variable မှ ရယူခြင်း
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id TEXT UNIQUE,
                job_keywords TEXT,
                location TEXT,
                user_cv TEXT,
                subscription_status TEXT DEFAULT 'inactive',
                subscription_expires_at TIMESTAMP WITH TIME ZONE
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ PostgreSQL Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/users', methods=['POST'])
def save_user():
    telegram_id = request.form.get('telegram_id')
    job_keywords = request.form.get('job_keywords')
    location = request.form.get('location')
    cv_file = request.files.get('cv_file')

    cv_text = ""
    if cv_file:
        raw_bytes = cv_file.read()
        cv_text = raw_bytes.decode('utf-8', errors='ignore')
        cv_text = cv_text.replace('\x00', '')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, job_keywords, location, user_cv, subscription_status)
            VALUES (%s, %s, %s, %s, 'inactive')
            ON CONFLICT (telegram_id) DO UPDATE SET
            job_keywords = EXCLUDED.job_keywords,
            location = EXCLUDED.location,
            user_cv = EXCLUDED.user_cv
        ''', (telegram_id, job_keywords, location, cv_text))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Profile saved successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.get_json(silent=True) or request.form
    telegram_id = data.get('telegram_id') if data else None

    if not telegram_id:
        return jsonify({'error': 'Telegram ID is missing'}), 400

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'nzd',
                    'product_data': {
                        'name': 'NZ Job Scout Pro Subscription',
                    },
                    'unit_amount': 1500, # 15 NZD
                    'recurring': {'interval': 'month'},
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.host_url + 'success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url,
            metadata={'telegram_id': telegram_id}
        )
        return jsonify({'checkout_url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        metadata_dict = session.get('metadata', {}) if hasattr(session, 'get') else getattr(session, 'metadata', {})
        telegram_id = metadata_dict.get('telegram_id') if isinstance(metadata_dict, dict) else getattr(metadata_dict, 'telegram_id', None)

        if telegram_id:
            try:
                # သက်တမ်း ၃၀ ရက် သတ်မှတ်ခြင်း
                expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'active',
                        subscription_expires_at = %s
                    WHERE telegram_id = %s
                ''', (expires_at, str(telegram_id)))
                conn.commit()
                cursor.close()
                conn.close()
                print(f"Subscription activated for Telegram ID: {telegram_id}")

                # Admin သို့ Notification ပို့ခြင်း
                ADMIN_TELEGRAM_CHAT_ID = "7072824431"
                admin_msg = f"🔔 *New Pro Subscriber!*\n• *Telegram ID:* `{telegram_id}`\n• *Status:* Active ✅"
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": ADMIN_TELEGRAM_CHAT_ID,
                    "text": admin_msg,
                    "parse_mode": "Markdown"
                })

                # Private Channel အတွက် တစ်ကြိမ်သုံး Invite Link ထုတ်ယူခြင်း
                invite_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createChatInviteLink"
                invite_payload = {
                    "chat_id": PRIVATE_CHANNEL_ID,
                    "member_limit": 1,
                    "expire_date": int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)).timestamp())
                }
                invite_res = requests.post(invite_url, json=invite_payload).json()
                
                channel_invite_link = ""
                if invite_res.get("ok"):
                    channel_invite_link = invite_res["result"]["invite_link"]

                # User သို့ Welcome မက်ဆေ့ချ်နှင့် Invite Link ပို့ခြင်း
                message = (
                    "🎉 ကျေးဇူးတင်ပါတယ်! Your NZ Job Scout Pro subscription is now active.\n\n"
                    "အောက်ပါ သီးသန့်လင့်ခ်ကိုနှိပ်၍ ကျွန်ုပ်တို့၏ Paid Telegram Channel ထဲသို့ ဝင်ရောက်နိုင်ပါပြီ - \n\n"
                    f"🔗 {channel_invite_link}\n\n"
                    "တရားဝင် Job အချက်အလက်များကို ဆက်လက်ပေးပို့သွားပါမည်။"
                )
                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload_data = {
                    "chat_id": telegram_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
                res = requests.post(telegram_url, json=payload_data)
                print(f"Telegram Notification Response: {res.status_code}")

            except Exception as e:
                print(f"Database error or Telegram notification error: {e}")

    return jsonify({'status': 'success'}), 200

def start_background_worker():
    worker_thread = threading.Thread(target=run_worker_loop, daemon=True)
    worker_thread.start()

if __name__ == '__main__':
    init_db()
    start_scheduler()
    start_background_worker()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)