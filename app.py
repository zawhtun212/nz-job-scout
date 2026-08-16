import sqlite3
import stripe
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
DB_NAME = "nz_job_saas.db"

# သင့်ရဲ့ Stripe Secret Key အမှန်ကို ထည့်ပါ
stripe.api_key = "sk_test_..." 

def init_db():
    conn = sqlite3.connect(DB_NAME)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT UNIQUE,
                job_keywords TEXT,
                location TEXT,
                subscription_status TEXT
            )
        """)
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/users", methods=["POST"])
def register_user():
    data = request.json
    try:
        conn = sqlite3.connect(DB_NAME)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO users (telegram_id, job_keywords, location, subscription_status)
                VALUES (?, ?, ?, ?)
            """, (data['telegram_id'], data['job_keywords'], data['location'], "pending"))
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        data = request.json
        telegram_id = data.get("telegram_id")

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'nzd',
                    'product_data': {
                        'name': 'NZ Job Scout Subscription',
                        'description': 'Monthly automated job alert service',
                    },
                    'unit_amount': 1500, # 15.00 NZD
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='http://127.0.0.1:5000/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://127.0.0.1:5000/',
            metadata={
                'telegram_id': telegram_id
            }
        )
        return jsonify({'checkout_url': checkout_session.url})
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    event = None
    try:
        event = request.json
    except Exception as e:
        return jsonify(success=False), 400

    # ငွေပေးချေမှု အောင်မြင်သောအခါ (checkout.session.completed)
    if event and event.get('type') == 'checkout.session.completed':
        session = event.get('data', {}).get('object', {})
        metadata = session.get('metadata', {})
        telegram_id = metadata.get('telegram_id')

        if telegram_id:
            conn = sqlite3.connect(DB_NAME)
            with conn:
                conn.execute("""
                    UPDATE users 
                    SET subscription_status = 'active' 
                    WHERE telegram_id = ?
                """, (telegram_id,))
            conn.close()

    return jsonify(success=True)

@app.route("/success")
def success():
    return "<h3>Payment successful! Your subscription is now active.</h3>"

if __name__ == "__main__":
    app.run(debug=True, port=5000)