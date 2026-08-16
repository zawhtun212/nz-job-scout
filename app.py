from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import stripe

app = Flask(__name__)

# Stripe API Key Configuration
stripe.api_key = os.environ.get("STRIPE_API_KEY", "your_stripe_secret_key")
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

    # CV ဖိုင်ပါလာပါက စာသားများကို ဖတ်ရှုခြင်း သို့မဟုတ် သိမ်းဆည်းခြင်း
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
    data = request.get_json()
    telegram_id = data.get('telegram_id')

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'nzd',
                    'product_data': {
                        'name': 'NZ Job Scout Pro Subscription',
                    },
                    'unit_amount': 1500, # 15.00 NZD
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)