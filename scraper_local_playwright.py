from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time, os, sys
import requests

# --- secrets via .env (safer than hard-coding) ---
import os, sys
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name(".env")  # .env in same folder as this script
load_dotenv(dotenv_path=ENV_PATH)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print(f"[config] Missing BOT_TOKEN/CHAT_ID. Create {ENV_PATH} with:\n"
          "BOT_TOKEN=xxxxxxxx:yyyyyyyy\nCHAT_ID=5749350301", file=sys.stderr)
    sys.exit(1)

FORUM_URL = "https://forums.golfwrx.com/forum/56-classifieds-for-sale-forum/"
BASE_URL  = "https://forums.golfwrx.com"
KEYWORDS_FILE = "keywords.txt"
CHECK_INTERVAL = 6000  # seconds
STORAGE_STATE = "storage_state.json"  # Playwright cookies/localStorage

def load_keywords():
    if not os.path.exists(KEYWORDS_FILE):
        return []
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return [ln.strip().lower() for ln in f if ln.strip()]

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": int(CHAT_ID), "text": message}
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            try:
                info = r.json()
                print("[telegram]", r.status_code, info.get("description"), file=sys.stderr)
            except Exception:
                print("[telegram]", r.status_code, r.text[:200], file=sys.stderr)
        r.raise_for_status()
    except Exception as e:
        print("Telegram send error:", e, file=sys.stderr)

def make_context(pw, headless=True):
    browser = pw.chromium.launch(headless=headless)
    context_kwargs = {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    if os.path.exists(STORAGE_STATE):
        context_kwargs["storage_state"] = STORAGE_STATE
    ctx = browser.new_context(**context_kwargs)
    page = ctx.new_page()
    return browser, ctx, page

def fetch_html(pw):
    # TIP: set headless=False for the FIRST run to complete any visual challenge.
    browser, ctx, page = make_context(pw, headless=False)  # change back to True after first success
    try:
        # Load faster and more reliably than "networkidle"
        page.goto(FORUM_URL, wait_until="domcontentloaded", timeout=60000)

        # If Cloudflare shows a holding page, give it a moment and reload once
        body_text = page.text_content("body") or ""
        if "Just a moment" in body_text or "Checking your browser" in body_text:
            page.wait_for_timeout(5000)
            page.reload(wait_until="domcontentloaded", timeout=60000)

        # Wait for something we actually need to scrape
        page.wait_for_selector('a[href*="/topic/"]', timeout=60000)

        html = page.content()
        ctx.storage_state(path=STORAGE_STATE)  # persist cookies/localStorage for future runs
        return html
    finally:
        ctx.close()
        browser.close()

def parse_listings(html: str):
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if not title or "/topic/" not in href:
            continue
        # Normalize link
        if href.startswith("http"):
            link = href
        else:
            link = BASE_URL + href
        # De-dup by link
        if link in seen:
            continue
        seen.add(link)
        results.append((title, link))
    return results

def main():
    # Enable auto-reload of keywords when keywords.txt changes
    print("[keywords] Auto-reload enabled.")
    matches_seen = set()  # prevent re-alerting within this process
    last_mtime = None

    # Initial load + banner
    keywords = load_keywords()
    print(f"Monitoring {len(keywords)} keywords...")

    with sync_playwright() as pw:
        while True:
            try:
                # Reload keywords if the file changed (or appeared/disappeared)
                try:
                    mtime = os.path.getmtime(KEYWORDS_FILE)
                except FileNotFoundError:
                    mtime = None

                if mtime != last_mtime:
                    keywords = load_keywords()
                    last_mtime = mtime
                    print(f"[keywords] Reloaded ({len(keywords)})")

                # Fetch and parse listings
                html = fetch_html(pw)
                listings = parse_listings(html)

                for title, link in listings:
                    tl = title.lower()
                    for kw in keywords:
                        if kw and kw in tl:
                            key = (kw, link)
                            if key in matches_seen:
                                continue
                            matches_seen.add(key)
                            msg = f"🆕 Match for '{kw}': {title}\n🔗 {link}"
                            print(msg)
                            send_telegram(msg)

                time.sleep(CHECK_INTERVAL)

            except Exception as e:
                print("Error:", e, file=sys.stderr)
                time.sleep(CHECK_INTERVAL)
if __name__ == "__main__":
    main()
