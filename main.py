import os
import time
import csv
import json
import datetime
import threading
import requests
from flask import Flask
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pyairtable import Api
from pyairtable import Table

print("[DEBUG] AIRTABLE_TOKEN =", os.getenv("AIRTABLE_TOKEN"))
print("[DEBUG] AIRTABLE_BASE_ID =", os.getenv("AIRTABLE_BASE_ID"))
print("[DEBUG] AIRTABLE_TABLE_NAME =", os.getenv("AIRTABLE_TABLE_NAME"))

app = Flask(__name__)

@app.route("/")
def home():
    return "alive"

# Load config
with open("config.json") as f:
    config = json.load(f)

KEYWORDS    = [kw.lower() for kw in config.get("keywords", [])]
MAX_RESULTS = config.get("max_results", 50)
RESUME_PATH = config.get("resume_path", "resume.pdf")
USER_DATA   = config.get("user_data", {})
CSV_PATH    = "applied_jobs.csv"

# Airtable ENV + client
api = Api(os.getenv("AIRTABLE_TOKEN"))
airtable = api.table(
    os.getenv("AIRTABLE_BASE_ID"),
    os.getenv("AIRTABLE_TABLE_NAME")
)

def load_applied_urls():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "title", "company", "url"])
        return set()
    with open(CSV_PATH, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return {row[3] for row in reader if len(row) >= 4}

def log_application(job):
    ts  = datetime.datetime.utcnow().isoformat()
    row = [ts, job["title"], job["company"], job["url"]]

    # 1) Append CSV
    with open(CSV_PATH, "a", newline="") as f:
        csv.writer(f).writerow(row)
    print(f"[CSV LOG] {','.join(row)}", flush=True)
    print(f"[LOG] Applied → {job['url']}", flush=True)

    # 2) Airtable record
    try:
        rec = airtable.create({
            "Time_stamp": ts,
            "Title":      job["title"],
            "Company":    job["company"],
            "URL":        job["url"]
        })
        print(f"[AIRTABLE ✅] Logged as {rec['id']}", flush=True)
    except Exception as e:
        print(f"[AIRTABLE ERROR] {e}", flush=True)

def location_allowed(text):
    raw = config.get("location_filter", "")
    if not raw.strip():
        return True
    locs = [loc.strip().lower() for loc in raw.split(",") if loc.strip()]
    text = text.lower()
    return any(loc in text for loc in locs)

def scrape_remotive():
    print("[SCRAPE] Remotive...", flush=True)
    jobs = []
    try:
        url = "https://remotive.com/api/remote-jobs?category=Data%20Analysis"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json().get("jobs", [])
        for job in data:
            text = (job.get("title","") + " " + job.get("company_name","") + " " +
                    job.get("description","")).lower()
            if any(kw in text for kw in KEYWORDS) and location_allowed(text):
                jobs.append({
                    "url": job["url"],
                    "title": job["title"],
                    "company": job.get("company_name","Unknown")
                })
    except Exception as e:
        print(f"[ERROR] Remotive API: {e}", flush=True)
    print(f"[DEBUG] Remotive found {len(jobs)} jobs after filter", flush=True)
    return jobs



def scrape_remoteok():
    print("[SCRAPE] RemoteOK...", flush=True)
    jobs = []
    try:
        url = "https://remoteok.com/api"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=20)
        data = r.json()
        for job in data:
            title = job.get("position","Remote Job")
            company = job.get("company","Unknown")
            full_url = job.get("url")  # remoteok likely gives full URL
            text = (title + " " + company).lower()
            if any(kw in text for kw in KEYWORDS) and location_allowed(text):
                jobs.append({"url": full_url, "title": title, "company": company})
    except Exception as e:
        print(f"[ERROR] RemoteOK API: {e}", flush=True)
    print(f"[DEBUG] RemoteOK found {len(jobs)} jobs after filter", flush=True)
    return jobs


def scrape_weworkremotely():
    print("[SCRAPE] WeWorkRemotely...", flush=True)
    url = "https://weworkremotely.com/categories/remote-programming-jobs"
    jobs = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for sec in soup.select("section.jobs li.feature")[:MAX_RESULTS]:
            l = sec.select_one("a")
            if not l:
                continue
            href = l["href"]
            full_url = "https://weworkremotely.com" + href
            title = sec.get_text(strip=True)
            text = (title + " " + full_url).lower()
            if any(kw in title.lower() for kw in KEYWORDS) and location_allowed(text):
                jobs.append({"url": full_url, "title": title, "company": "Unknown"})
    except Exception as e:
        print(f"[ERROR] WWR: {e}", flush=True)
    return jobs

def scrape_jobspresso():
    print("[SCRAPE] Jobspresso...", flush=True)
    url = "https://jobspresso.co/remote-ai-data-jobs/"
    jobs = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.select("ul.jobs li.job_listing")[:MAX_RESULTS]:
            a = li.select_one("a")
            if not a:
                continue
            href = a["href"]
            title = a.get("title", "Remote Job")
            company = li.select_one(".company")
            company_name = company.get_text(strip=True) if company else "Unknown"
            text = (title + " " + company_name + " " + href).lower()
            if any(kw in title.lower() for kw in KEYWORDS) and location_allowed(text):
                jobs.append({"url": href, "title": title, "company": company_name})
    except Exception as e:
        print(f"[ERROR] Jobspresso: {e}", flush=True)
    return jobs

def scrape_remoteco():
    print("[SCRAPE] Remote.co...", flush=True)
    url = "https://remote.co/remote-jobs/data-science/"
    jobs = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("li.job_listing")[:MAX_RESULTS]:
            a = row.select_one("a")
            if not a:
                continue
            href = a["href"]
            title = a.get("title", "Remote Job")
            company = row.select_one(".company")
            company_name = company.get_text(strip=True) if company else "Unknown"
            text = (title + " " + company_name + " " + href).lower()
            if any(kw in title.lower() for kw in KEYWORDS) and location_allowed(text):
                jobs.append({"url": href, "title": title, "company": company_name})
    except Exception as e:
        print(f"[ERROR] Remote.co: {e}", flush=True)
    return jobs


def get_jobs():
    all_jobs = []
    for fn in (scrape_remotive,
               scrape_remoteok,
               scrape_weworkremotely,
               scrape_jobspresso,
               scrape_remoteco):
        try:
            scraped = fn()
            print(f"[DEBUG] {fn.__name__} scraped {len(scraped)} jobs before filter", flush=True)
            all_jobs.extend(scraped)
        except Exception as e:
            print(f"[SCRAPE ERROR] {fn.__name__}: {e}", flush=True)
        time.sleep(3)
    # dedupe
    seen, unique = set(), []
    for j in all_jobs:
        if j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)
        if len(unique) >= MAX_RESULTS:
            break
    print(f"[SCRAPE] {len(unique)} unique jobs found", flush=True)
    return unique


from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def apply_to_job(job):
    print(f"[AUTO] Applying → {job['url']}", flush=True)
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)

    try:
        # 1) Load the Remotive detail page
        driver.get(job["url"])
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # 2) Click the off-site “Apply” link (Lever, Greenhouse, etc.)
        try:
            # just one wait using partial link text
            apply_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Apply"))
            )
            apply_link.click()

            # 3) If a new tab opened, switch to it
            WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
            driver.switch_to.window(driver.window_handles[-1])

            # 4) Wait for the external page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("[AUTO] On external ATS:", driver.current_url, flush=True)

        except Exception:
            print("[AUTO WARNING] Off-site link not found or timeout; falling back", flush=True)

        # 5) Fill the real ATS form
        for inp in driver.find_elements(By.TAG_NAME, "input"):
            name = (inp.get_attribute("name") or "").lower()
            if "email" in name:
                inp.send_keys(USER_DATA.get("email", ""))
            elif "name" in name:
                inp.send_keys(USER_DATA.get("full_name", ""))
            elif "phone" in name:
                inp.send_keys(USER_DATA.get("phone", ""))

        # upload resume
        for f in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            f.send_keys(os.path.abspath(RESUME_PATH))

        # 6) Submit on the ATS
        submit = None
        # look for the most common selectors in order
        candidates = [
            ("//button[contains(text(),'Submit')]", By.XPATH),
            ("//button[contains(text(),'Apply')]", By.XPATH),
            ("input[type='submit']", By.CSS_SELECTOR),
        ]
        for sel, by in candidates:
            els = driver.find_elements(by, sel)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    submit = el
                    break
            if submit:
                break

        if not submit:
            print("[AUTO ERROR] No submit button on ATS page, skipping", flush=True)
            return

        driver.execute_script("arguments[0].scrollIntoView(true);", submit)
        driver.execute_script("arguments[0].click();", submit)
        print("[AUTO] Success—form submitted on external ATS", flush=True)

    except Exception as e:
        print(f"[AUTO ERROR] {e}", flush=True)

    finally:
        driver.quit()


'''
def apply_to_job_(job):
    print(f"[AUTO] Applying → {job['url']}", flush=True)
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(job["url"])
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # fill inputs
        for inp in driver.find_elements(By.TAG_NAME, "input"):
            name = (inp.get_attribute("name") or "").lower()
            if "email" in name:
                inp.send_keys(USER_DATA.get("email",""))
            elif "name" in name:
                inp.send_keys(USER_DATA.get("full_name",""))
            elif "phone" in name:
                inp.send_keys(USER_DATA.get("phone",""))
        # upload resume
        for f in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            f.send_keys(os.path.abspath(RESUME_PATH))

        # gather candidates: button.apply, a.apply, input[type=submit]
        candidates = []
        candidates += driver.find_elements(By.XPATH,
            "//button[contains(translate(text(),'APPLY','apply'),'apply')]")
        candidates += driver.find_elements(By.XPATH,
            "//a[contains(translate(text(),'APPLY','apply'),'apply')]")
        candidates += driver.find_elements(By.CSS_SELECTOR,
            "input[type='submit']")
        # pick the first visible & enabled
        apply_btn = None
        for el in candidates:
            if el.is_displayed() and el.is_enabled():
                apply_btn = el
                break

        if not apply_btn:
            # debug: list what elements we saw
            snippets = [el.get_attribute("outerHTML") for el in candidates]
            print("[AUTO ERROR] No APPLY element found; candidates were:", flush=True)
            for s in snippets:
                print(s, flush=True)
            return

        # click via JS
        driver.execute_script("arguments[0].scrollIntoView(true);", apply_btn)
        driver.execute_script("arguments[0].click();", apply_btn)
        print("[AUTO] Success", flush=True)

    except Exception as e:
        print(f"[AUTO ERROR] {e}", flush=True)
    finally:
        driver.quit()
'''

def bot_cycle():
    applied = load_applied_urls()
    print(f"[BOT] {len(applied)} URLs loaded", flush=True)
    jobs = get_jobs()
    print(f"[BOT] {len(jobs)} jobs fetched", flush=True)
    for job in jobs:
        if job["url"] in applied:
            print(f"[BOT] Skipping {job['url']}", flush=True)
            continue
        apply_to_job(job)
        log_application(job)
        applied.add(job["url"])
    print("[BOT] Cycle complete", flush=True)

def scheduler():
    bot_cycle()
    while True:
        time.sleep(30)
        bot_cycle()

if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    print("[MAIN] Scheduler started", flush=True)
    app.run(host="0.0.0.0", port=3000, use_reloader=False)
