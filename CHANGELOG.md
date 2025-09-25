# Changelog

## [0.1.0] - 2025-09-25
### Added
- תשתית CI אחת בשם **CI** עם טריגרים: `push`, `pull_request`, ו-`workflow_dispatch`.
- לכידת לוגים מלאה כארטיסיפקטים: `pip-install.out/.err`, `pip-debug.txt`, `pip-config.txt`, `pip-freeze.txt`, `pip-check.out/.err`, `lint.out`, `pytest.out`, ו-`install.rc`/`pip-check.rc`.
- סקריפטים מסייעים מקומית: `/tmp/ci_logs.sh` ו-`/tmp/ci_fail.sh` לתחקור ריצות.

### Changed
- הסרה יזומה של `SQLAlchemy` כדי לאכוף **No greenlet** בסביבת ה-CI.
- תיקוני lint בקובץ `src/lucy_agent/routers/stream.py` והעברה למודל `APIRouter` נקי.

### Fixed
- כשלי `ruff` (פקודה לא נכונה) → שימוש ב-`ruff check .`.
- הבטחת העלאת ארטיפקטים תמיד (כולל `overwrite: true`) למניעת 409.

### Notes
- בדיקות: `1 passed`.
- גרסאות מרכזיות: `fastapi==0.115.14`, `httpx==0.27.2`, `pytest==8.4.2`, `starlette==0.46.2`, ללא `greenlet`.
