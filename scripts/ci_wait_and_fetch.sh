#!/usr/bin/env bash
# scripts/ci_wait_and_fetch.sh
# מחכה לריצה האחרונה של ה־CI להסתיים (ללא אינטראקציה), ואז מוריד ארטיפקטים ומציג לוגים.

set -euo pipefail

REPO="${1:-}"
if [[ -z "${REPO}" ]]; then
  echo "[INFO] מזהה ריפו דרך gh…"
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
fi
echo "[INFO] REPO=${REPO}"

echo "[INFO] לוכד/ת RUN_ID של הריצה האחרונה…"
# נוסיף ריטריי קטן למקרי 500/404 רגעיים
RUN_ID=""
for i in {1..6}; do
  RUN_ID="$(gh run list -R "${REPO}" --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
  [[ -n "${RUN_ID}" ]] && break
  echo "[WARN] לא הוחזר RUN_ID (ניסיון ${i}) — ממתין/ה 5 שניות…"
  sleep 5
done
if [[ -z "${RUN_ID}" ]]; then
  echo "[ERROR] נכשל להשיג RUN_ID גם אחרי ריטריי. בדוק/י חיבור/הרשאות gh ונסו שוב."
  exit 1
fi
echo "[INFO] RUN_ID=${RUN_ID}"

echo "[INFO] מציג/ה תקציר הריצה…"
gh run view -R "${REPO}" "${RUN_ID}" --json url,status,conclusion,workflowName,displayTitle,headBranch,headSha \
  --jq '"URL=" + .url + "\nstatus=" + .status + " conclusion=" + (.conclusion//"") + " | " + .headBranch + "@" + .headSha + "\nworkflow=" + .workflowName + " | " + .displayTitle'

echo "[INFO] ממתין/ה לאותה ריצה שתסתיים (לא אינטראקטיבי)…"
# חשוב: מציינים את ה־RUN_ID כדי לא לקבל תפריט בחירה
gh run watch -R "${REPO}" "${RUN_ID}" --exit-status || true

echo "[INFO] מוריד/ה ארטיפקטים (smoke-artifacts)…"
rm -rf artifact && mkdir -p artifact
if gh run download -R "${REPO}" "${RUN_ID}" --name smoke-artifacts --dir ./artifact 2>/dev/null; then
  echo "[INFO] הורדו ארטיפקטים ל־./artifact"
else
  echo "[WARN] לא נמצאו ארטיפקטים בשם 'smoke-artifacts' לריצה ${RUN_ID}"
fi

echo "---- smoke.log ----"
sed -n '1,200p' artifact/artifacts/logs/smoke.log 2>/dev/null || echo "אין smoke.log בארטיפקט"

echo "---- api.out ----"
# הועלה מה־CI כ־/tmp/api.out ולכן יורד ל־artifact/tmp/api.out
tail -n 200 artifact/tmp/api.out 2>/dev/null || echo "אין api.out בארטיפקט"

echo "---- חיווי מעבר ----"
if grep -Eq "SMOKE v11 — הושלם בהצלחה|Health-only ✅" artifact/artifacts/logs/smoke.log 2>/dev/null; then
  echo "✅ נמצאה אינדיקציית הצלחה בסמוק"
else
  echo "⚠️  לא נמצאה אינדיקציית הצלחה בסמוק (בדוק/י את הלוגים למעלה)"
fi

echo "[INFO] סיום. קבצים: artifact/ (אם קיימים)."
