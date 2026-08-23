from bs4 import BeautifulSoup
import requests
import psycopg2
import time
import os
import urllib.parse

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ပိုမိုစစ်မှန်သော Browser တစ်ခုကဲ့သို့ ဟန်ဆောင်ရန် Headers များကို မြှင့်တင်ထားခြင်း
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

def send_telegram_message(telegram_id, message):
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is missing in environment!")
        return None
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message,
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def fetch_job_description(url, platform):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return "Description could not be fetched."
        
        soup = BeautifulSoup(res.text, "html.parser")
        desc = ""
        
        if platform == "Seek":
            desc_elem = soup.find("div", {"data-automation": "jobAdDetails"})
            if desc_elem: desc = desc_elem.get_text(separator="\n", strip=True)
        
        if not desc:
            desc = soup.get_text(separator="\n", strip=True)[:3000]
            
        return desc
    except Exception as e:
        print(f"Error fetching job details from {url}: {e}")
        return "Detailed description fetch failed."

def scrape_seek(keyword, location):
    formatted_kw = keyword.replace(" ", "-").lower()
    formatted_loc = location.replace(" ", "-").lower()
    url = f"https://www.seek.co.nz/{formatted_kw}-jobs/in-{formatted_loc}"
    print(f"🌐 Scraping URL: {url}")
    try:
        # Seek က Bot တွေကို ချက်ချင်းမသိအောင် Session တစ်ခုအသုံးပြုခြင်း
        session = requests.Session()
        res = session.get(url, headers=HEADERS, timeout=15)
        print(f"🌐 Seek Response Status: {res.status_code}")
        
        if res.status_code != 200: 
            print(f"⚠️ Blocked or page unavailable. Status: {res.status_code}")
            return []
        
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        articles = soup.find_all('article')
        print(f"📦 Found {len(articles)} article cards on Seek page.")
        
        for card in articles[:2]:
            title_elem = card.find('a', {'data-automation': 'jobTitle'}) or card.find('a', {'data-type': 'job-title'}) or card.find('a')
            company_elem = card.find('a', {'data-automation': 'jobCompany'}) or card.find('a', {'data-type': 'company-name'})
            if title_elem and title_elem.text:
                title = title_elem.text.strip()
                href = title_elem.get('href', '')
                link = "https://www.seek.co.nz" + href.split('?')[0] if href.startswith('/') else href
                company = company_elem.text.strip() if company_elem else "Direct Employer"
                
                print(f"🔗 Found Job -> Title: {title} | Company: {company}")
                full_desc = fetch_job_description(link, "Seek")
                jobs.append({
                    "platform": "Seek", "title": title, "company": company, "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"Seek scrape error: {e}")
        return []

def evaluate_job_match(user_cv, job_description):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
        prompt = f"""
        You are an expert New Zealand IT career coach and professional recruiter. 
        Carefully analyze the candidate's CV against the full Job Description below.

        Candidate CV:
        {user_cv}

        Full Job Description:
        {job_description}

        Provide your detailed analysis strictly in the following readable plain text format:
        MATCH_SCORE: [Provide an accurate percentage score from 0 to 100 based on skill relevance]
        KEY_MATCHES: [List 3-4 specific matching skills found in both CV and Job Description]
        COVER_LETTER: [Write a comprehensive, highly professional, tailored cover letter for this specific New Zealand job opening]
        """
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        res = requests.post(url, json=payload, timeout=30)
        
        if res.status_code == 200:
            data = res.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as parse_err:
                return "MATCH_SCORE: 50\nKEY_MATCHES: General Skills\nCOVER_LETTER: Generated analysis structure was unexpected."
        else:
            return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Unable to generate due to API connection issue."
    except Exception as e:
        return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Unable to generate due to exception."

def run_worker_loop():
    print("🚀 Robust Multi-Platform Job Scout Bot Started...")
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
                loc = location if location else "Whanganui"

                print(f"🔍 Scraping jobs for keyword: '{keywords}' in location: '{loc}'...")
                all_jobs = scrape_seek(keywords, loc)
                print(f"✅ Total scraped jobs to process: {len(all_jobs)}")

                for job in all_jobs:
                    analysis = evaluate_job_match(user_cv, job['description']) if user_cv else "MATCH_SCORE: 0\nKEY_MATCHES: N/A\nCOVER_LETTER: Please save your CV profile first."
                    
                    message = (
                        f"[{job['platform']}] New Job Match!\n\n"
                        f"Position: {job['title']}\n"
                        f"Company: {job['company']}\n\n"
                        f"Analysis & Cover Letter:\n{analysis}\n\n"
                        f"Apply Here: {job['url']}"
                    )
                    
                    telegram_res = send_telegram_message(telegram_id, message)
                    print(f"🤖 Telegram status for {telegram_id}: {telegram_res}")
                    time.sleep(3)

        except Exception as e:
            print(f"❌ Error in worker cycle: {e}")

        print("💤 Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600)

if __name__ == "__main__":
    run_worker_loop()