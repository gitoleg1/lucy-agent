# Lucy Agent — API קליל עם Observability ו-CI

API קטן להרצת משימות (Tasks) ו-Actions. כולל:
- בדיקות smoke (v11) מקומיות וב-CI
- Health & Logs
- Runbook לצוות
- Release checklist

> הערה: המצב יכול להיות **Health-only** (כשאין מסלולי `/tasks` ב-OpenAPI) — זה תקין, וה-CI יעבור עם בדיקת `/health` בלבד.

---

## Quick Start (5 צעדים)
1. יצירת סביבה והתקנות
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt || true
