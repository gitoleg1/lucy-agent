# AGENT_SPEC — Lucy Agent (v1)

מטרה: לבנות ולהריץ עבור לוסי פרויקטי תוכנה וקונפיגורציה מקצה-אל-קצה, עם קו אישורים ברור ופיקוח מינימלי מצד אולג (מהנייד).

---

## 1) תפקיד האייג'נט
- עוזר אוטונומי המממש משימות שהלוסי מגדירה לו, כולל:
  - חיבור דו-כיווני לשיחות מלאות ב־**Telegram**/**WhatsApp** (כולל אישורי פעולות “אשר/דחה”).
  - **בניית בוטים** לוואטסאפ לניהול שיחות/הזמנות.
  - **ניהול Google Ads**: תצוגה, דוחות, ובהמשך שינויי תקציב/בידים (רק באישור).
  - **בניית אתרי WordPress**: הקמה, תוכן, תבניות, ו־rollback בסיסי.
  - **הרצת Playbooks/סקריפטים** ב־Shell/Browser ובכל פלטפורמה שנזדקק לה.
  - **בנייה ופיתוח תוכנות בפועל** (code scaffolding, יצירת פרויקטים, קונפיגורציות, דיפלוי)—Cross-Platform.

---

## 2) יעדים מרכזיים
1. **ערוץ אישורים**: כל פעולה בינונית/גבוהת סיכון תופיע כ־Task ממתין לאישור (בטלגרם/וואטסאפ/UI).
2. **Runner מבודד + Playbooks**: הפעלה בסביבה מבודדת (משתמש ייעודי/מכולה) עם ספריית פלייבוקים.
3. **אינטגרציות**:
   - Telegram Bot (webhook או long-poll).
   - WhatsApp (Twilio או Meta Cloud API).
   - Google Ads (OAuth; תחילה Read-Only).
   - WordPress REST (User+App Password או OAuth).
4. **UI ניהול**: מסך “פעולות ממתינות”, היסטוריית Audit, סטטוס ריצות.
5. **Secrets & Webhooks**: ניהול סודות מאובטח + Tunnel ל-webhooks לשרת המקומי.

---

## 3) מדיניות אישורים (Approval Policy)
- **נמוך**: קריאה/דוחות/מידע בלבד — **רץ אוטומטי**.
- **בינוני**: כתיבת תוכן, יצירת בוט בסיסי, סטייג'ינג — **אישור בלחיצה**.
- **גבוה**: שינויי תקציב/בידים, דיפלוי הפצה — **אישור בלחיצה + גבולות תקציב/סיכון**.
- כל פעולה המתייגת כסף/הפצה = גבוהה כברירת מחדל.

---

## 4) ארכיטקטורה (תמצית)
- **API** (FastAPI/Uvicorn) מקומי על `127.0.0.1:8000`.
- **UI** (Next.js) על `127.0.0.1:3004` — מסכי Tasks/Audit/Settings.
- **Runner** מבודד: משתמש `lucy-runner` או Container; גישה כתיבה רק לתיקיות יעודיות.
- **Playbooks**: תרחישים לשימוש חוזר (למשל: `whatsapp-orders`, `wp-new-site`, `wp-post`, `gads-report`).
- **Approvals**: מצב Task = `pending|approved|rejected|running|done|failed`.
- **Notifications**: טלגרם/וואטסאפ עם קישורי אישור/דחייה.
- **Audit**: לוג פעולות חתום (זמן, מבצע, פרמטרים, תוצאה, artefacts).

---

## 5) אינטגרציות – דרישות חיבור
- **Telegram**: Bot Token מ־@BotFather; webhook דרך Tunnel או long-poll.
- **WhatsApp**: Twilio Sandbox/Number או Meta WABA + Templates מאושרות.
- **Google Ads**: OAuth Client (Client ID/Secret) + Customer ID; תחילה **Read-Only**.
- **WordPress**: URL + User/App Password או OAuth; הרשאות ליצירה/עדכון/מדיה.

---

## 6) יכולות בנייה ופיתוח תוכנות (Cross-Platform)
האייג'נט מסוגל לבנות ולהרים פרויקטים בקוד על פי הנחיות לוסי:
- יצירת שלדים (scaffolding) למסגרות פופולריות (Node/Python/WordPress Plugins/Next.js וכו’).
- קונפיגורציה של תלויות, סביבות, ושירותי צד שלישי.
- כתיבת קבצי CI/דיפלוי בסיסיים, והפעלת בדיקות.
- עבודה ב־Shell/Browser/API—לפי הצורך, בפלייבוקים מאובטחים עם אישורים.

---

## 7) אבטחה ותפעול
- **Hardening** לשירותים (systemd): קריאה-בלבד למערכת, כתיבה מוקצית לפרויקט, רשת לוקאלית בלבד.
- **Secrets** בקבצי env/Store מאובטח, רוטציות לפי הצורך.
- **Tunnel** מאובטח (למשל Cloudflare Tunnel/Caddy) לקבלת webhooks מבחוץ.
- **Rate-limits/Guards**: מנגנוני הגנה לפעולות רגישות (כסף/הפצה/מחיקה).

---

## 8) Roadmap קצר (MVP→M1)
**MVP (שבוע 1–2):**
- Telegram approvals (pending/approve/reject).
- Runner מבודד + 2 פלייבוקים:
  1) WhatsApp orders bot (Skeleton: Twilio/Meta; echo + template test).
  2) WordPress: יצירת אתר בסיסי + פוסט.
- UI: מסך פעולות ממתינות + Audit בסיסי.
- Google Ads: OAuth Read-Only + תצוגת קמפיינים ב-UI.

**M1 (שבוע 3–4):**
- WhatsApp production (templates, states).
- WordPress: ניהול מדיה/תבניות + rollback בסיסי.
- Google Ads: שינויי bids/budget עם require_approval + guardrails.
- ספריית Playbooks מתרחבת (SEO, גיבויים, דיפלוי).

---

## 9) הגדרות הצלחה (Success Criteria)
- ≥90% מהפעולות השוטפות עוברות דרך האייג'נט ללא מעורבות אולג.
- SLA לאישור: < 2 דקות מרגע בקשה (טלגרם/וואטסאפ/טלפון).
- אפס פעולות כספיות ללא אישור; Audit מלא לכל פעולה בינונית/גבוהה.

---

## 10) מה דרוש מאולג (חד-פעמי/עדכונים)
- Telegram Bot Token, WhatsApp (Twilio/Meta), Google Ads OAuth, WordPress creds.
- אישור שימוש ב-Tunnel מאובטח.
- קביעת גבולות תקציב וגארד-ריילס לשינויים בגוגל אדס.

---

_מסמך זה הוא אמת המידה ליישור קו. כל שינוי במדיניות האישור או באינטגרציות יתועד כאן ויקבל גרסת משנה._
