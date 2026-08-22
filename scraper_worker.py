from bs4 import BeautifulSoup
import requests
import psycopg2
import time
import os
import urllib.parse

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
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
        elif platform == "Trade Me":
            desc_elem = soup.find("div", class_="o-card") or soup.find("tm-property-view-detailed-attributes")
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
        print(f"Error fetching job details from {url}: {e}")
        return "Detailed description fetch failed."

def scrape_seek(keyword, location):
    formatted_kw = keyword.replace(" ", "-").lower()
    formatted_loc = location.replace(" ", "-").lower()
    url = f"https://www.seek.co.nz/{formatted_kw}-jobs/in-{formatted_loc}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('article')[:3]:
            title_elem = card.find('a', {'data-automation': 'jobTitle'}) or card.find('a', {'data-type': 'job-title'}) or card.find('a')
            company_elem = card.find('a', {'data-automation': 'jobCompany'}) or card.find('a', {'data-type': 'company-name'})
            if title_elem and title_elem.text:
                title = title_elem.text.strip()
                href = title_elem.get('href', '')
                link = "https://www.seek.co.nz" + href.split('?')[0] if href.startswith('/') else href
                company = company_elem.text.strip() if company_elem else "Direct Employer"
                
                print(f"🔗 Fetching full details for Seek job: {title}")
                full_desc = fetch_job_description(link, "Seek")
                jobs.append({
                    "platform": "Seek", "title": title, "company": company, "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"Seek scrape error: {e}")
        return []

def scrape_linkedin(keyword, location):
    encoded_kw = urllib.parse.quote(keyword)
    encoded_loc = urllib.parse.quote(location)
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_kw}&location={encoded_loc}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('li')[:3]:
            title_elem = card.find('h3', class_='base-search-card__title')
            company_elem = card.find('h4', class_='base-search-card__subtitle')
            link_elem = card.find('a', class_='base-card__full-link')
            if title_elem and link_elem:
                link = link_elem['href'].split('?')[0]
                title = title_elem.text.strip()
                
                print(f"🔗 Fetching full details for LinkedIn job: {title}")
                full_desc = fetch_job_description(link, "LinkedIn")
                jobs.append({
                    "platform": "LinkedIn", "title": title, "company": company_elem.text.strip() if company_elem else "Employer", "url": link, "description": full_desc
                })
        return jobs
    except Exception as e:
        print(f"LinkedIn scrape error: {e}")
        return []

def scrape_indeed(keyword, location):
    url = f"https://nz.indeed.com/jobs?q={urllib.parse.quote(keyword)}&l={urllib.parse.quote(location)}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        for card in soup.find_all('div', class_='job_seen_beacon') or soup.find_all('div', class_='cardOutline'):
            title_elem = card.find('h2', class_='jobTitle') or card.find('a', class_='jcs-JobTitle')
            company_elem = card.find('span', class_='companyName') or card.find('span', attrs={'data-testid': 'company-name'})
            link_elem = card.find('a', class_='jcs-JobTitle') or card.find('a')
            
            if title_elem and link_elem:
                title = title_elem.get_text(strip=True)
                company = company_elem.get_text(strip=True) if company_elem else "Indeed Employer"
                href = link_elem.get('href', '')
                link = f"https://nz.indeed.com{href}" if href.startswith('/') else href
                link = link.split('?')[0]
                
                print(f"🔗 Fetching full details for Indeed job: {title}")
                full_desc = fetch_job_description(link, "Indeed")
                jobs.append({
                    "platform": "Indeed", "title": title, "company": company, "url": link, "description": full_desc
                })
        return jobs[:3]
    except Exception as e:
        print(f"Indeed scrape error: {e}")
        return []

def scrape_trademe(keyword, location):
    formatted_kw = keyword.replace(" ", "-").lower()
    url = f"https://www.trademe.co.nz/a/jobs/{location.lower()}/{formatted_kw}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return []
        soup = BeautifulSoup(res.text, 'html.parser')
        jobs = []
        cards = soup.find_all("tg-card", class_="tm-marketplace-card") or soup.find_all('a', href=True)
        for card in cards[:3]:
            a_tag = card if card.name == 'a' else card.find('a')
            if a_tag and a_tag.has_attr('href'):
                href = a_tag['href']
                if '/a/jobs/' in href and ('listing' in href or len(href.split('/')) > 4):
                    title = a_tag.get_text(strip=True)
                    if len(title) > 5:
                        link = f"https://www.trademe.co.nz{href}" if href.startswith('/') else href
                        link = link.split('?')[0]
                        
                        print(f"🔗 Fetching full details for Trade Me job: {title}")
                        full_desc = fetch_job_description(link, "Trade Me")
                        jobs.append({
                            "platform": "Trade Me", "title": title, "company": "TradeMe Employer", "url": link, "description": full_desc
                        })
        return jobs
    except Exception as e:
        print(f"TradeMe scrape error: {e}")
        return []

def evaluate_job_match(user_cv, job_description):
    try:
        # မော်ဒယ်နာမည်ကို gemini-3.6-flash သို့ ပြောင်းလဲထားသည်
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GOOGLE_API_KEY}"
        prompt = f"""
        You are an expert New Zealand IT career coach and professional recruiter. 
        Carefully analyze the candidate's CV against the full Job Description below.

        Candidate CV:
        {user_cv}

        Full Job Description:
        {job_description}

        Provide your analysis strictly in the following readable format:
        MATCH_SCORE: [Provide an accurate percentage score from 0 to 100 based on skill relevance]
        KEY_MATCHES: [List 3-4 specific matching skills found in both CV and Job Description]
        COVER_LETTER: [Write a compelling, highly professional, tailored cover letter for this specific New Zealand job opening, ready to be sent to the hiring manager]
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
                print(f"JSON Parse Error: {parse_err}, Response: {data}")
                return "MATCH_SCORE: 50\nKEY_MATCHES: General IT Skills\nCOVER_LETTER: Generated analysis structure was unexpected."
        else:
            print(f"API Error Response Status {res.status_code}: {res.text}")
            return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Unable to generate due to API connection issue."
    except Exception as e:
        print(f"AI Matcher Error: {e}")
        return "MATCH_SCORE: 0\nKEY_MATCHES: None\nCOVER_LETTER: Unable to generate due to exception."

def run_worker_loop():
    print("🚀 Robust Multi-Platform Job Scout Bot Started...")
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, job_keywords, location, user_cv FROM users WHERE subscription_status = 'active'")
            active_users = cursor.fetchall()
            cursor.close()
            conn.close()

            print(f"👥 Found {len(active_users)} active user(s) to process.")

            for user in active_users:
                telegram_id, keywords, location, user_cv = user
                if not keywords: continue
                loc = location if location else "All New Zealand"

                print(f"🔍 Scraping jobs for keyword: '{keywords}' in location: '{loc}'...")
                all_jobs = (
                    scrape_seek(keywords, loc) + 
                    scrape_linkedin(keywords, loc) + 
                    scrape_indeed(keywords, loc) + 
                    scrape_trademe(keywords, loc)
                )
                print(f"✅ Found {len(all_jobs)} total jobs with full details.")

                for job in all_jobs:
                    analysis = evaluate_job_match(user_cv, job['description']) if user_cv else "MATCH_SCORE: 0\nKEY_MATCHES: N/A\nCOVER_LETTER: Please save your CV profile first."
                    
                    message = f"[{job['platform']}] New Match!\n\nPosition: {job['title']}\nCompany: {job['company']}\nURL: {job['url']}\n\nAnalysis:\n{analysis}"
                    
                    telegram_res = send_telegram_message(telegram_id, message)
                    print(f"🤖 Telegram status for {telegram_id}: {telegram_res}")
                    time.sleep(3)

        except Exception as e:
            print(f"❌ Error in worker cycle: {e}")

        print("💤 Waiting for the next check cycle (60 minutes)...")
        time.sleep(3600)

if __name__ == "__main__":
    run_worker_loop()