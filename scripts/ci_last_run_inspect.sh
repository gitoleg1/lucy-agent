#!/usr/bin/env bash
# ci_last_run_inspect.sh — איסוף לוגים/ארטיפקטים מהריצה האחרונה של GitHub Actions בצורה חסינה

set -Eeuo pipefail

# -------- פונקציות עזר --------
log()  { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
err()  { printf '[ERROR] %s\n' "$*" >&2; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "נדרש '$1' במערכת"; exit 1; }
}

jqsafe() {
  # הרצה בטוחה של jq עם טיפול בשגיאות
  jq "$@" 2>/dev/null || true
}

# -------- בדיקות קדם --------
need_cmd gh
need_cmd jq

if ! gh auth status >/dev/null 2>&1; then
  err "אין התחברות תקפה ל-gh. הרץ: gh auth login"
  exit 1
fi

# -------- זיהוי הריפו --------
REPO="${1:-}"
if [[ -z "${REPO}" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
fi
if [[ -z "${REPO}" ]]; then
  err "נכשל לזהות ריפו. אפשר להעביר REPO כארגומנט ראשון, למשל: ./ci_last_run_inspect.sh owner/repo"
  exit 1
fi
log "REPO=${REPO}"

# -------- שליפת RUN_ID עם ריטריי --------
RUN_ID=""
for i in {1..8}; do
  # נבקש 10 ריצות אחרונות כדי לעקוף באגים נקודתיים ולהעמיק בחיפוש
  runs_json="$(gh run list -R "${REPO}" --limit 10 --json databaseId,workflowName,status,conclusion,url,displayTitle,headSha,headBranch,createdAt 2>/dev/null || true)"
  if [[ -n "${runs_json}" && "${runs_json}" != "null" ]]; then
    # העדפה: ריצה של workflow בשם "CI"; אם אין — ניקח את הראשונה ברשימה
    RUN_ID="$(printf '%s\n' "${runs_json}" | jq -r '
      (.[]
       | {id:.databaseId, wf:(.workflowName//""), url, status, conclusion, createdAt})
      | select(.id != null)
      | .id
    ' | head -n1)"

    # אם לא מצאנו — ננסה שוב
    if [[ -n "${RUN_ID}" ]]; then
      break
    fi
  fi
  warn "לא הוחזר RUN_ID (ניסיון ${i}) — ממתין 3 שניות ומנסה שוב…"
  sleep 3
done

if [[ -z "${RUN_ID}" ]]; then
  err "נכשל להשיג RUN_ID גם אחרי ריטריי. בדוק/י חיבור/הרשאות/Rate-limit ונסה/י שוב."
  exit 1
fi
log "RUN_ID=${RUN_ID}"

# -------- תקציר הריצה + לינק --------
summary="$(gh run view -R "${REPO}" "${RUN_ID}" --json url,status,conclusion,headBranch,headSha,displayTitle,workflowName \
  --jq '"URL=" + .url + "\nstatus=" + .status + " conclusion=" + (.conclusion//"") + " | " + .headBranch + "@" + .headSha + "\nworkflow=" + (.workflowName//"") + " | " + (.displayTitle//"")' 2>/dev/null || true)"
if [[ -z "${summary}" ]]; then
  warn "נכשל להביא תקציר לריצה ${RUN_ID} (ייתכן 404 זמני)."
else
  echo "${summary}"
fi

# -------- תיקייה נקייה לפלט מקומי --------
rm -rf artifact ci-run.log ci-job.log ci-failed.log
mkdir -p artifact

# -------- לוג מלא של כל הריצה --------
if ! gh run view -R "${REPO}" "${RUN_ID}" --log > ci-run.log 2>/dev/null; then
  warn "לא הצלחתי להביא לוג מלא לריצה ${RUN_ID}."
fi
# הדפסה ראשונית למסך (רק התחלה, כדי לא להציף)
sed -n '1,220p' ci-run.log 2>/dev/null || true

# -------- צעדים שנכשלו (אם יש) --------
if ! gh run view -R "${REPO}" "${RUN_ID}" --log-failed > ci-failed.log 2>/dev/null; then
  : # ייתכן ואין צעדים שנכשלו/אין ג'ובים
fi
sed -n '1,220p' ci-failed.log 2>/dev/null || true

# -------- זיהוי ג'ובים ולוג שלהם --------
jobs_list="$(gh run view -R "${REPO}" "${RUN_ID}" --json jobs --jq '(.jobs//[])[]? | "\(.name)\t\(.id)"' 2>/dev/null || true)"
echo -e "\n--- Jobs בריצה ---"
if [[ -n "${jobs_list}" ]]; then
  echo "${jobs_list}"
  first_job_id="$(printf '%s\n' "${jobs_list}" | head -n1 | awk '{print $NF}')"
  if [[ -n "${first_job_id}" ]]; then
    if gh run view -R "${REPO}" --job "${first_job_id}" --log > ci-job.log 2>/dev/null; then
      sed -n '1,220p' ci-job.log || true
    else
      warn "לא הצלחתי להביא לוג לג'וב ${first_job_id}"
    fi
  fi
else
  echo "(אין ג'ובים — ייתכן שהריצה נפלה מוקדם)"
fi

# -------- הורדת ארטיפקטים (אם קיימים) --------
if gh run download -R "${REPO}" "${RUN_ID}" --name smoke-artifacts --dir ./artifact 2>/dev/null; then
  log "הורדו ארטיפקטים ל-artifact/"
  echo "---- smoke.log ----"
  sed -n '1,200p' artifact/artifacts/logs/smoke.log 2>/dev/null || echo "אין smoke.log בארטיפקט"
  echo "---- api.out ----"
  tail -n 200 artifact/tmp/api.out 2>/dev/null || echo "אין api.out בארטיפקט"
else
  warn "אין ארטיפקטים בשם 'smoke-artifacts' לריצה ${RUN_ID} או שנכשלה ההורדה."
fi

# -------- חיווי הצלחה/כישלון לפי לוג הסמוק אם קיים --------
echo "---- חיווי מעבר (אם יש smoke.log) ----"
if grep -E "SMOKE v11 — הושלם בהצלחה|Health-only ✅" artifact/artifacts/logs/smoke.log >/dev/null 2>&1; then
  echo "✅ עבר (לפי smoke.log)"
else
  echo "⚠️  לא נמצא חיווי הצלחה ב-smoke.log (אם בכלל הוסר/לא עלה)."
fi

log "סיום. קבצים שנוצרו: ci-run.log, ci-failed.log, (אופציונלי) ci-job.log, ותיקיית artifact/ אם היו ארטיפקטים."
