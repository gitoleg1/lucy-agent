# RUNBOOK — Lucy Agent

## מטרות
- להרים את ה־API מקומית או תחת `systemd --user`.
- לוודא בריאות (`/health`), הרצה בסיסית (smoke v11), ולוגים.
- טרבלשוט מהיר לתקלות נפוצות (401/403/400/307/timeout).

---

## התקנה / שדרוג מהיר (לוקאלית)
```bash
# יצירת venv והתקנת תלויות
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt || true
pip install uvicorn fastapi

# משתני סביבה שימושיים (אופציונלי בקובץ .env)
cat > .env <<'ENV'
AGENT_API_KEY=ChangeMe_SuperSecret_Long
NEXT_PUBLIC_AGENT_BASE=http://127.0.0.1:8000
APP_MODULE=lucy_agent.main:app
ENV

# הרמת שרת לוקאלי (טרמינל פתוח)
uvicorn "${APP_MODULE:-lucy_agent.main:app}" --host 127.0.0.1 --port 8000
