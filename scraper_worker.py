from bs4 import BeautifulSoup
import requests
import psycopg2
import time
import os

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

def send_telegram_message(telegram_id, message):
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN is missing!")
        return None
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message,
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            print(f"❌ Telegram Error Response: {response.text}")
        return response.json()
    except Exception as e:
        print(f"❌ Exception in send_telegram_message: {e}")
        return None

def fetch_job_description(url, platform):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return "Description could not be fetched."
        
        soup = BeautifulSoup(res.text, "html.parser")
        desc = ""
        
        if platform == "Trade Me":
            desc_elem = soup.find("div", class_="o-card")
            if desc_elem: desc = desc_elem.get_text(separator="\n", strip=True)
        elif platform == "Indeed":
            desc_elem = soup.find("div", id="jobDescriptionText")
            if desc_elem: desc = desc_elem.get_text(separator="\n", strip=True)
        elif platform == "LinkedIn":
            desc_elem = soup.find("div", class_="show-more-less-html__markup")
            if desc_elem: desc = desc_elem.get_text(separator="\n", strip=True)
            
        if not desc:
            desc = soup.get_text(separator="\n", strip=True)
            
        return desc[:1200]  # API ပေါ့ပါးမြန်ဆန်စေရန် စာသားအရှည်ကို သင့်တော်ရုံ ကန့်သတ်ထားသည်
    except Exception as e:
        return "Detailed description fetch failed."

def scrape_jobs_for_keyword(keyword, location):
    all_jobs = []
    
    # 1. Trade Me
    try:
        url = f"https://www.trademe.co.nz/a/jobs/search?search_string={keyword}&region={location}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.find_all('tg-card')[:2] or soup.find_all('div', class_='o-card')[:2]:
                title_elem = card.find('a')
                if title_elem:
                    title = title_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://www.trademe.co.nz" + href if href.startswith('/') else href
                    full_desc = fetch_job_description(link, "Trade Me")
                    all_jobs.append({"platform": "Trade Me", "title": title, "company": "Trade Me Employer", "url": link, "description": full_desc})
    except Exception as e:
        print(f"Trade Me error: {e}")

    # 2. Indeed
    try:
        url = f"https://nz.indeed.com/jobs?q={keyword}&l={location}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.find_all('div', class_='job_seen_beacon')[:2]:
                title_elem = card.find('span', id=lambda x: x and x.startswith('jobTitle')) or card.find('a', class_='jcs-JobTitle')
                company_elem = card.find('span', class_='companyName')
                if title_elem:
                    title = title_elem.text.strip()
                    link = "https://nz.indeed.com" + title_elem.get('href', '') if title_elem.name == 'a' else ""
                    company = company_elem.text.strip() if company_elem else "Indeed Employer"
                    full_desc = fetch_job_description(link, "Indeed") if link else "No link"
                    all_jobs.append({"platform": "Indeed", "title": title, "company": company, "url": link, "description": full_desc})
    except Exception as e:
        print(f"Indeed error: {e}")

    return all_jobs

def evaluate_job_match(user_cv, job_description):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GOOGLE_API_KEY}"
        prompt = f"""
        You are an expert New Zealand IT career coach and professional recruiter. 
        Analyze the candidate's CV against the Job Description below.

        Candidate CV:
        {user_cv}

        Job Description:
        {job_description}

        Provide your response strictly in this format:
        MATCH_SCORE: [Percentage score from 0 to 100, e.g., 85%]
        KEY_MATCHES: [List 3 specific matching skills]
        COVER_LETTER: [Write a concise, professional cover letter tailored for this job]
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=45)
        
        if res.status_code == 200:
            data = res.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return "MATCH_SCORE: 50\nKEY_MATCHES: General\nCOVER_LETTER: Parsing error."
        else:
            print(f"❌ Gemini API Error: {res.status_code}")
            return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: API failed."
    except Exception as e:
        print(f"❌ Exception in evaluation: {e}")
        return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Timeout or error."

def run_worker_loop():
    print("🚀 Optimized Job Scout Bot Started & Running...")
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, job_keywords, location, user_cv FROM users")
            active_users = cursor.fetchall()
            cursor.close()
            conn.close()

            print(f"👥 Found {len(active_users)} user(s) to process.")

            for user in active_users:
                telegram_id, keywords, location, user_cv = user
                if not keywords: continue
                loc = location if location else "Auckland"

                print(f"🔍 Checking jobs for keyword: '{keywords}' in '{loc}'...")
                jobs = scrape_jobs_for_keyword(keywords, loc)
                print(f"✅ Found {len(jobs)} job postings.")

                for job in jobs:
                    # Database တွင် ဤအလုပ်လင့်ခ်ကို ယခင်က ပို့ပြီးသားဟုတ်မဟုတ် စစ်ဆေးရန် (Optional table cache check)
                    # ယခုလက်ရှိအတွက် AI Evaluation ကို တိုက်ရိုက်လုပ်ဆောင်သည်
                    cv_text = str(user_cv) if user_cv else "General CV"
                    analysis = evaluate_job_match(cv_text, job['description'])
                    
                    message = (
                        f"🔥 [{job['platform']}] New Job Match!\n\n"
                        f"📌 Position: {job['title']}\n"
                        f"🏢 Company: {job['company']}\n\n"
                        f"{analysis}\n\n"
                        f"🔗 Apply Here: {job['url']}"
                    )
                    
                    send_telegram_message(telegram_id, message)
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error in worker cycle: {e}")

        print("💤 Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600)

if __name__ == "__main__":
    run_worker_loop()