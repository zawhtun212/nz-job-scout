from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import stripe
import requests

app = Flask(__name__)

# Stripe & Telegram API Key Configuration
stripe.api_key = os.environ.get("STRIPE_API_KEY", "sk_test_51U4dsARsY9pyx48SiKwb9uf48pewo7OVhBijGippD1q5RufnbXL9g1Jci1Okqq36q1LjQpEV3HvvNHlYzQgapdKK004uvCslZH")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_1hF3Jy80A9x1dANaNJdlmlSoAu5eWjOK")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8746508324:AAG2tZBW8U5ZKqzwci20W2b3SPwRs1MARI4")
DB_NAME = "nz_job_saas.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE,
            job_keywords TEXT,
            location TEXT,
            user_cv TEXT,
            subscription_status TEXT DEFAULT 'inactive'
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN user_cv TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

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
        cv_text = cv_file.read().decode('utf-8', errors='ignore')

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, job_keywords, location, user_cv, subscription_status)
            VALUES (?, ?, ?, ?, 'inactive')
            ON CONFLICT(telegram_id) DO UPDATE SET
            job_keywords=excluded.job_keywords,
            location=excluded.location,
            user_cv=excluded.user_cv
        ''', (telegram_id, job_keywords, location, cv_text))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Profile saved successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if request.is_json:
        data = request.get_json()
        telegram_id = data.get('telegram_id') if data else None
    else:
        telegram_id = request.form.get('telegram_id')

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
                    'unit_amount': 1500,
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
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        metadata_dict = session.get('metadata', {}) if hasattr(session, 'get') else getattr(session, 'metadata', {})
        telegram_id = metadata_dict.get('telegram_id') if isinstance(metadata_dict, dict) else getattr(metadata_dict, 'telegram_id', None)

        if telegram_id:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'active' 
                    WHERE telegram_id = ?
                ''', (telegram_id,))
                conn.commit()
                conn.close()
                print(f"Subscription activated for Telegram ID: {telegram_id}")

                # Telegram သို့ အောင်မြင်ကြောင်း မက်ဆေ့ခ်ျ ပို့ခြင်း
                message = "🎉 ကျေးဇူးတင်ပါတယ်! your NZ Job Scout Pro subscription is now active. တရားဝင် ဂျော့ခ်ျအချက်အလက်များကို ဆက်လက်ပေးပို့သွားပါမည်။"
                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload_data = {
                    "chat_id": telegram_id,
                    "text": message
                }
                res = requests.post(telegram_url, json=payload_data)
                print(f"Telegram Notification Response: {res.status_code}")

            except Exception as e:
                print(f"Database error or Telegram notification error: {e}")

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    init_db()
    app.run(debug=True)