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
        print(f"📱 Telegram API Status: {response.status_code}")
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
            desc = soup.get_text(separator="\n", strip=True)[:3000]
            
        return desc
    except Exception as e:
        return "Detailed description fetch failed."

def scrape_trademe(keyword, location):
    url = f"https://www.trademe.co.nz/a/jobs/search?search_string={keyword}&region={location}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('tg-card')[:2] or soup.find_all('div', class_='o-card')[:2]:
            title_elem = card.find('a')
            if title_elem:
                title = title_elem.text.strip()
                href = title_elem.get('href', '')
                link = "https://www.trademe.co.nz" + href if href.startswith('/') else href
                full_desc = fetch_job_description(link, "Trade Me")
                jobs.append({
                    "platform": "Trade Me", "title": title, "company": "Trade Me Employer", "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"Trade Me error: {e}")
        return []

def scrape_indeed(keyword, location):
    url = f"https://nz.indeed.com/jobs?q={keyword}&l={location}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('div', class_='job_seen_beacon')[:2]:
            title_elem = card.find('span', id=lambda x: x and x.startswith('jobTitle')) or card.find('a', class_='jcs-JobTitle')
            company_elem = card.find('span', class_='companyName')
            if title_elem:
                title = title_elem.text.strip()
                link = "https://nz.indeed.com" + title_elem.get('href', '') if title_elem.name == 'a' else ""
                company = company_elem.text.strip() if company_elem else "Indeed Employer"
                full_desc = fetch_job_description(link, "Indeed") if link else "No link"
                jobs.append({
                    "platform": "Indeed", "title": title, "company": company, "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"Indeed error: {e}")
        return []

def scrape_linkedin(keyword, location):
    url = f"https://www.linkedin.com/jobs/search?keywords={keyword}&location={location}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('div', class_='base-card')[:2]:
            title_elem = card.find('h3', class_='base-search-card__title')
            company_elem = card.find('h4', class_='base-search-card__subtitle')
            link_elem = card.find('a', class_='base-card__full-link')
            if title_elem:
                title = title_elem.text.strip()
                company = company_elem.text.strip() if company_elem else "LinkedIn Employer"
                link = link_elem.get('href', '') if link_elem else ""
                full_desc = fetch_job_description(link, "LinkedIn") if link else "No link"
                jobs.append({
                    "platform": "LinkedIn", "title": title, "company": company, "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"LinkedIn error: {e}")
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

        Provide your detailed analysis strictly in the following format:
        MATCH_SCORE: [Provide an accurate percentage score from 0 to 100 based on skill relevance, e.g., 85%]
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
                text_result = data["candidates"][0]["content"]["parts"][0]["text"]
                return text_result if text_result else "MATCH_SCORE: N/A\nCOVER_LETTER: No content generated."
            except (KeyError, IndexError):
                return "MATCH_SCORE: 50\nKEY_MATCHES: General Skills\nCOVER_LETTER: Analysis parsing error."
        else:
            print(f"❌ Gemini API Error: {res.status_code} - {res.text}")
            return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: API connection failed."
    except Exception as e:
        print(f"❌ Exception in evaluate_job_match: {e}")
        return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Error in evaluation."

def run_worker_loop():
    print("🚀 Complete Bot Started & Running...")
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

                print(f"🔍 Scraping for: '{keywords}' in '{loc}'...")
                
                all_jobs = []
                all_jobs.extend(scrape_trademe(keywords, loc))
                all_jobs.extend(scrape_indeed(keywords, loc))
                all_jobs.extend(scrape_linkedin(keywords, loc))
                
                print(f"✅ Total jobs found across platforms: {len(all_jobs)}")

                for job in all_jobs:
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
                    time.sleep(3)

        except Exception as e:
            print(f"❌ Error in worker cycle: {e}")

        print("💤 Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600)

if __name__ == "__main__":
    run_worker_loop()