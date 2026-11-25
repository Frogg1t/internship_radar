# JKU Job Radar

Automated internship & junior job notification system seeded from the 52 organizations in [companies_photos](../companies_photos) (JKU Karrierecenter — Artificial Intelligence) plus **JKU Jobbörse** (`jobboerse.jku.at`) and **karriere.at**.

## How It Works

1. **Multi-tier extraction**: Checks structured ATS feeds first (`JobPosting` JSON-LD, Personio XML, Greenhouse, Lever, SmartRecruiters, Workday) and falls back to career link extraction + JKU/karriere.at boards.
2. **Bilingual EN/DE scoring** (`config/profile.yaml`): Boosts `Internship` / `Praktikum` / `Werkstudent` / `Junior` + `AI` / `ML` / `Python` / `Software` + `Linz` / `Upper Austria` / `Remote`, while excluding `Senior` / `Lehrling` / unrelated roles.
3. **Deduplication** (`data/seen_jobs.json`): Stores canonicalized SHA-256 fingerprints so you only receive alerts for newly published openings.
4. **Telegram alerts**: Pushes formatted HTML cards with clickable apply links via GitHub Actions every 6 hours.

---

## Setup Guide (5 Minutes)

### 1. Create Your Telegram Bot
1. Open Telegram and message `@BotFather` -> `/newbot` -> copy the **Bot Token**.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser (or use `@userinfobot`) to find your numeric `chat.id`.

### 2. Push to GitHub & Add Secrets
1. Create a GitHub repository (private recommended since `seen_jobs.json` will be committed automatically) and push this workspace:
   ```powershell
   git add .
   git commit -m "feat: add JKU job-radar notification system"
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
2. In your GitHub repo, go to **Settings -> Secrets and variables -> Actions** and add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

### 3. Run First Bootstrap Scan
Go to **Actions -> JKU Job Radar -> Run workflow**:
- Set `bootstrap = true` for the very first run so it records currently open postings in `seen_jobs.json` and sends only the top 10 matches instead of flooding your chat.
- All subsequent scheduled runs (`06:00`, `12:00`, `18:00` UTC) will automatically alert you whenever any new matching internship or junior job appears.

---

## Local Commands (Python 3.11+ or Docker)

Using Docker:
```powershell
docker run --rm -v "${PWD}/job-radar:/app" -w /app python:3.12-slim sh -c "pip install -e '.[dev]' && pytest -v"
docker run --rm -v "${PWD}/job-radar:/app" -w /app python:3.12-slim sh -c "pip install -e . && python -m job_radar.main discover --tier A"
docker run --rm -v "${PWD}/job-radar:/app" -w /app python:3.12-slim sh -c "pip install -e . && python -m job_radar.main run --dry-run"
```

Using local Python:
```powershell
cd job-radar
pip install -e ".[dev]"
pytest -v
python -m job_radar.main discover --tier A
python -m job_radar.main run --dry-run
```
