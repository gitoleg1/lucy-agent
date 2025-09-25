# ‎Lucy Agent‎

[![CI](https://github.com/gitoleg1/lucy-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gitoleg1/lucy-agent/actions/workflows/ci.yml)

סוכן ‎FastAPI‎ רזה ללא ‎greenlet‎.
ה־CI מעלה תמיד ארטיפקטים תחת ‎`smoke-artifacts/logs/*`‎ לאבחון בעיות דרך לוגים — בלי ניחושים.

---

## ‎מה הפרויקט עושה בקצרה
- ‎API‎ בסיסי עם ‎FastAPI‎
- בדיקת בריאות (‎healthcheck‎) ו-‎Smoke Test‎
- ניהול ‎CI‎ קפדני: לוגי התקנות, ‎pip check‎, לינט ובדיקות

---

## ‎הרצה מקומית
```bash
# וירטואלי (אופציונלי)
python -m venv .venv && source .venv/bin/activate

# התקנת תלויות רזות (ללא greenlet)
pip install -r requirements.txt

# הרצה
uvicorn lucy_agent.main:app --reload
