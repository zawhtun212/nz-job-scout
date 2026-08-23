from playwright.async_api import async_playwright
import asyncio
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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

# 1. Seek (Playwright ဖြင့် Anti-Bot ကျော်လွှားပြီး Scrap လုပ်ခြင်း)
async def scrape_seek(keyword, location):
    formatted_keyword = keyword.replace(" ", "-")
    formatted_location = location.replace(" ", "-")
    url = f"https://www.seek.co.nz/{formatted_keyword}-jobs/in-{formatted_location}"
    
    jobs = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            print(f"🔍 Scraping Seek for '{keyword}'...")
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            articles = soup.find_all('article') or soup.find_all('div', {'data-automation': 'normalJob'})
            
            for article in articles[:2]:
                title_elem = article.find('a', {'data-automation': 'jobTitle'}) or article.find('a', class_=lambda x: x and 'job-title' in x)
                company_elem = article.find('a', {'data-automation': 'jobCompany'})
                if title_elem:
                    title = title_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://www.seek.co.nz" + href if href.startswith('/') else href
                    company = company_elem.text.strip() if company_elem else "Seek Employer"
                    desc = article.get_text(separator="\n", strip=True)
                    
                    jobs.append({
                        "platform": "Seek",
                        "title": title,
                        "company": company,
                        "url": link,
                        "description": desc[:800]
                    })
        except Exception as e:
            print(f"❌ Seek error: {e}")
        finally:
            await browser.close()
    return jobs

# 2. Trade Me (Requests + BeautifulSoup)
def scrape_trademe(keyword, location):
    jobs = []
    try:
        print(f"🔍 Scraping Trade Me for '{keyword}'...")
        formatted_keyword = keyword.replace(" ", "%20")
        url = f"https://www.trademe.co.nz/a/jobs/search?search_string={formatted_keyword}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.find_all('a', class_='o-card') or soup.find_all('div', class_='tm-search-card-list-listing-wrap')
            for card in cards[:2]:
                title_elem = card.find('h3') or card.find('span', class_='tm-search-card-list-listing-title')
                if not title_elem and card.name == 'a':
                    title_elem = card
                if title_elem:
                    title = title_elem.text.strip()
                    href = card.get('href', '') if card.name == 'a' else card.find('a').get('href', '')
                    link = "https://www.trademe.co.nz" + href if href.startswith('/') else href
                    jobs.append({
                        "platform": "Trade Me",
                        "title": title,
                        "company": "Trade Me Employer",
                        "url": link,
                        "description": title
                    })
    except Exception as e:
        print(f"❌ Trade Me error: {e}")
    return jobs

# 3. Indeed (Requests + BeautifulSoup)
def scrape_indeed(keyword, location):
    jobs = []
    try:
        print(f"🔍 Scraping Indeed for '{keyword}'...")
        formatted_keyword = keyword.replace(" ", "+")
        url = f"https://nz.indeed.com/jobs?q={formatted_keyword}&l={location.replace(' ', '+')}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.find_all('div', class_='job_seen_beacon') or soup.find_all('td', class_='resultContent')
            for card in cards[:2]:
                title_elem = card.find('span', id=lambda x: x and x.startswith('jobTitle')) or card.find('a', class_='jcs-JobTitle')
                company_elem = card.find('span', class_='companyName') or card.find('span', class_='css-1h7lukg')
                if title_elem:
                    title = title_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://nz.indeed.com" + href if href.startswith('/') else href
                    company = company_elem.text.strip() if company_elem else "Indeed Employer"
                    jobs.append({
                        "platform": "Indeed",
                        "title": title,
                        "company": company,
                        "url": link,
                        "description": title
                    })
    except Exception as e:
        print(f"❌ Indeed error: {e}")
    return jobs

# 4. LinkedIn (Requests + BeautifulSoup)
def scrape_linkedin(keyword, location):
    jobs = []
    try:
        print(f"🔍 Scraping LinkedIn for '{keyword}'...")
        formatted_keyword = keyword.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search?keywords={formatted_keyword}&location={location.replace(' ', '%20')}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.find_all('div', class_='base-card') or soup.find_all('li', class_='result-card')
            for card in cards[:2]:
                title_elem = card.find('h3', class_='base-search-card__title') or card.find('a', class_='job-card-list__title')
                company_elem = card.find('h4', class_='base-search-card__subtitle') or card.find('a', class_='job-card-container__company-name')
                link_elem = card.find('a', class_='base-card__full-link') or card.find('a', class_='job-card-list__title')
                if title_elem:
                    title = title_elem.text.strip()
                    company = company_elem.text.strip() if company_elem else "LinkedIn Employer"
                    link = link_elem.get('href', '') if link_elem else ""
                    jobs.append({
                        "platform": "LinkedIn",
                        "title": title,
                        "company": company,
                        "url": link,
                        "description": title
                    })
    except Exception as e:
        print(f"❌ LinkedIn error: {e}")
    return jobs

# Groq API (Llama 3) ဖြင့် CV ကို အကဲဖြတ်ခြင်း
def evaluate_job_match(user_cv, job_description):
    if not GROQ_API_KEY:
        return "MATCH_SCORE: 50\nKEY_MATCHES: General\nCOVER_LETTER: Error."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # f-string ကို သေချာပါအောင် ထည့်ပေးထားပါသည်
    prompt = f"""
    You are an expert New Zealand IT career coach. Analyze this CV against the Job Description.

    Candidate CV:
    {user_cv}

    Job Description:
    {job_description}

    Provide your response strictly in this format:
    MATCH_SCORE: [Percentage score from 0 to 100, e.g., 85%]
    KEY_MATCHES: [List 3 specific matching skills]
    COVER_LETTER: [Write a concise, professional cover letter tailored for this job]
    """
    
    payload = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ Groq evaluation error: {e}")
        
    return "MATCH_SCORE: 50\nKEY_MATCHES: General\nCOVER_LETTER: Error."

def send_telegram_message(telegram_id, message):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": telegram_id, "text": message, "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

async def run_worker_loop():
    print("🚀 4-Platform Job Scout Bot (Seek Playwright + Groq) Started...")
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

                all_jobs = []
                
                # 1. Seek (Async Playwright)
                seek_jobs = await scrape_seek(keywords, loc)
                all_jobs.extend(seek_jobs)
                
                # 2. Trade Me (Sync Requests)
                trademe_jobs = scrape_trademe(keywords, loc)
                all_jobs.extend(trademe_jobs)
                
                # 3. Indeed (Sync Requests)
                indeed_jobs = scrape_indeed(keywords, loc)
                all_jobs.extend(indeed_jobs)
                
                # 4. LinkedIn (Sync Requests)
                linkedin_jobs = scrape_linkedin(keywords, loc)
                all_jobs.extend(linkedin_jobs)

                print(f"✅ Total found {len(all_jobs)} jobs across all platforms.")

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
                    await asyncio.sleep(3)

        except Exception as e:
            print(f"❌ Error in worker cycle: {e}")

        print("💤 Waiting for the next check cycle (60 minutes)...")
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(run_worker_loop())