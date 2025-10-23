# GolfWRX Classifieds Scraper

Monitors GolfWRX Classifieds and sends Telegram alerts when new posts match your keywords.

## Why this
- Playwright renders JS and handles anti-bot checks better than plain requests.
- `.env` keeps BOT_TOKEN and CHAT_ID out of git.
- `keywords.txt` auto-reloads; no restart needed.

## Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
# edit .env with your BOT_TOKEN and CHAT_ID
