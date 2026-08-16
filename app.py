import os
import sqlite3
import stripe
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document

app = Flask(__name__)
DB_NAME = "nz_job_saas.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# API Keys များကို Environment Variables မှ ရယူခြင်း
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("Telegram_Bot_Token")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def init_db():
    conn = sqlite3.connect(DB_NAME)
    with conn:
        # Table အရင်ရှိမရှိ စစ်ဆေးခြင်း
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT UNIQUE,
                job_keywords TEXT,
                location TEXT,
                cv_text TEXT,
                subscription_status TEXT
            )
        """)
        
        # Column အဟောင်းများအတွက် Safe Migration (Render Error မတက်စေရန်)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'cv_text' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN cv_text TEXT")
        if 'subscription_status' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN subscription_status TEXT")
            
    conn.close()

init_db()

def extract_text_from_file(file_path, filename):
    text = ""
    try:
        if filename.endswith('.pdf'):
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        elif filename.endswith('.docx') or filename.endswith('.doc'):
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting text: {e}")
    return text

def send_telegram_message(telegram_id, message):
    if not TELEGRAM_BOT_TOKEN or not telegram_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/users", methods=["POST"])
def register_user():
    telegram_id = request.form.get('telegram_id')
    job_keywords = request.form.get('job_keywords')
    location = request.form.get('location')
    file = request.files.get('cv_file')

    if not file:
        return jsonify({"status": "error", "message": "No CV file uploaded"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # PDF သို့မဟုတ် Word ဖိုင်မှ စာသားများ ထုတ်ယူခြင်း
    cv_text = extract_text_from_file(file_path, filename)

    try:
        conn = sqlite3.connect(DB_NAME)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO users (telegram_id, job_keywords, location, cv_text, subscription_status)
                VALUES (?, ?, ?, ?, ?)
            """, (telegram_id, job_keywords, location, cv_text, "pending"))
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        data = request.json
        telegram_id = data.get("telegram_id")
        host_url = request.host_url.rstrip('/')

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
            success_url=f'{host_url}/success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{host_url}/',
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

            # ငွေပေးချေမှု အောင်မြင်ကြောင်း Telegram သို့ အသိပေးခြင်း
            send_telegram_message(telegram_id, "🎉 ငွေပေးချေမှု အောင်မြင်ပါပြီ! သင့်ရဲ့ NZ Job Scout subscription ယခု အလုပ်လုပ်နေပါပြီ။ Seek, Indeed, TradeMe နှင့် LinkedIn တို့မှ ကိုက်ညီသော အလုပ်များကို တင်ပေးပါမည်။")

    return jsonify(success=True)

@app.route("/success")
def success():
    return "<h3>Payment successful! Your subscription is now active. You can close this window.</h3>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


@app.route("/test-telegram/<telegram_id>")
def test_telegram(telegram_id):
    send_telegram_message(telegram_id, "🧪 ဒါက သင့်ဆီ တိုက်ရိုက်ပို့တဲ့ Test Message ပါ။ Telegram Bot အလုပ်လုပ်ကြောင်း အတည်ပြုချက်ပါ။")
    return f"Test message sent to {telegram_id}! Please check your Telegram."