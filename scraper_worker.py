from bs4 import BeautifulSoup
import google.generativeai as genai
import requests
import sqlite3
import time
import os

DB_NAME = "nz_job_saas.db"

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

def send_telegram_message(telegram_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": telegram_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")

# --- 1. SEEK SCRAPER ---
def scrape_seek(keyword, location):
    formatted_kw = keyword.replace(" ", "-")
    url = f"https://www.seek.co.nz/{formatted_kw}-jobs?where={location}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, "html.parser")
        jobs = []
        for card in soup.find_all("article", {"data-automation": "normalJob"})[:2]:
            title = card.find("a", {"data-automation": "jobTitle"})
            company = card.find("a", {"data-automation": "jobCompany"})
            if title:
                jobs.append({
                    "platform": "Seek",
                    "title": title.text,
                    "company": company.text if company else "Confidential",
                    "url": "https://www.seek.co.nz" + title.get("href", ""),
                    "description": title.text + " role in NZ."
                })
        return jobs
    except:
        return []

# --- 2. TRADE ME SCRAPER ---
def scrape_trademe(keyword, location):
    formatted_kw = keyword.replace(" ", "-")
    url = f"https://www.trademe.co.nz/a/jobs/{location.lower()}/{formatted_kw}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, "html.parser")
        jobs = []
        # Trade Me structure အလိုက် card များကို ရှာဖွေခြင်း
        cards = soup.find_all("tg-card", class_="tm-marketplace-card")[:2]
        for card in cards:
            title_elem = card.find("a")
            if title_elem:
                jobs.append({
                    "platform": "Trade Me",
                    "title": title_elem.text.strip(),
                    "company": "Trade Me Employer",
                    "url": "https://www.trademe.co.nz" + title_elem.get("href", ""),
                    "description": title_elem.text.strip() + " role."
                })
        return jobs
    except:
        return []

# --- 3. INDEED SCRAPER ---
def scrape_indeed(keyword, location):
    url = f"https://nz.indeed.com/jobs?q={keyword.replace(' ', '+')}&l={location.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, "html.parser")
        jobs = []
        for card in soup.find_all("div", class_="job_seen_beacon")[:2]:
            title = card.find("h2", class_="jobTitle")
            company = card.find("span", class_="companyName")
            link = card.find("a")
            if title:
                jobs.append({
                    "platform": "Indeed",
                    "title": title.text,
                    "company": company.text if company else "Confidential",
                    "url": "https://nz.indeed.com" + link.get("href", "") if link else "#",
                    "description": title.text + " position."
                })
        return jobs
    except:
        return []

# --- 4. LINKEDIN SCRAPER (Public Jobs API/Page) ---
def scrape_linkedin(keyword, location):
    url = f"https://www.linkedin.com/jobs/search?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, "html.parser")
        jobs = []
        for card in soup.find_all("div", class_="base-card")[:2]:
            title = card.find("h3", class_="base-search-card__title")
            company = card.find("h4", class_="base-search-card__subtitle")
            link = card.find("a", class_="base-card__full-link")
            if title:
                jobs.append({
                    "platform": "LinkedIn",
                    "title": title.text.strip(),
                    "company": company.text.strip() if company else "Confidential",
                    "url": link.get("href", "") if link else "#",
                    "description": title.text.strip() + " role."
                })
        return jobs
    except:
        return []

def evaluate_job_match(user_cv, job_description):
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        prompt = f"""
        You are an expert recruitment assistant in New Zealand. 
        Analyze the following Candidate CV and Job Description.
        
        Candidate CV:
        {user_cv}
        
        Job Description:
        {job_description}
        
        Provide your response strictly in the following format:
        MATCH_SCORE: [Integer between 0 to 100]
        KEY_MATCHES: [Short summary of why it matches]
        COVER_LETTER: [A professional, tailored cover letter for this specific job]
        """
        response = model.generate_content(prompt)
        return response.text
    except:
        return "MATCH_SCORE: 50\nKEY_MATCHES: Default\nCOVER_LETTER: N/A"

def run_worker():
    print("Multi-Platform Job Scraper & AI Matcher Started...")
    while True:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, job_keywords, location, user_cv FROM users WHERE subscription_status = 'active'")
        active_users = cursor.fetchall()
        conn.close()

        for user in active_users:
            telegram_id, keywords, location, user_cv = user
            if not keywords: continue
            loc = location if location else "New Zealand"

            # Platforms (၄) ခုစလုံးမှ တစ်ပြိုင်နက် ဆွဲထုတ်ခြင်း
            all_jobs = []
            all_jobs.extend(scrape_seek(keywords, loc))
            all_jobs.extend(scrape_trademe(keywords, loc))
            all_jobs.extend(scrape_indeed(keywords, loc))
            all_jobs.extend(scrape_linkedin(keywords, loc))

            for job in all_jobs:
                if user_cv:
                    analysis = evaluate_job_match(user_cv, job['description'])
                    message = (
                        f"🚨 *[{job['platform']}] New Matched Job!* \n\n"
                        f"*Position:* {job['title']}\n"
                        f"*Company:* {job['company']}\n"
                        f"[View Job Link]({job['url']})\n\n"
                        f"*AI Analysis & Cover Letter:*\n{analysis}"
                    )
                else:
                    message = (
                        f"🔍 *[{job['platform']}] New Job Found!* \n\n"
                        f"*Position:* {job['title']}\n"
                        f"*Company:* {job['company']}\n"
                        f"[View Job Link]({job['url']})"
                    )
                
                send_telegram_message(telegram_id, message)
                time.sleep(2)

        print("Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600)

if __name__ == "__main__":
    run_worker()