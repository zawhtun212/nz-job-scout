import os
import sqlite3
import stripe
import requests
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document

app = Flask(__name__)
DB_NAME = "nz_job_saas.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("Telegram_Bot_Token")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    with conn:
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

    # Extract text from PDF or Word
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