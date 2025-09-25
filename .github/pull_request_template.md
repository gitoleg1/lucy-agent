## תקציר
<!-- מה המטרה של ה-PR? -->

## סוג השינוי
- [ ] תיקון באגים
- [ ] פיצ'ר חדש
- [ ] שינוי לא שובר (Refactor/Docs/CI)

## בדיקות מקומיות שבוצעו
הרצתי מקומית לפני פתיחת PR:
```bash
ruff check .
black --check .
PYTHONPATH=src pytest -q
