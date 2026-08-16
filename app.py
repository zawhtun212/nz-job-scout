from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import stripe

app = Flask(__name__)

# Stripe API Key Configuration
stripe.api_key = os.environ.get("STRIPE_API_KEY", "your_stripe_secret_key")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_1hF3Jy80A9x1dANaNJdlmlSoAu5eWjOK")
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
        metadata = session.get('metadata', {})
        telegram_id = metadata.get('telegram_id')

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
            except Exception as e:
                print(f"Database error updating subscription: {e}")

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    init_db()
    app.run(debug=True)