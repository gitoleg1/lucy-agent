#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] מזהה ריפו דרך gh…"
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
echo "[INFO] REPO=${REPO}"

echo "[INFO] לוכד/ת RUN_ID של הריצה האחרונה…"
RUN_ID=$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
echo "[INFO] RUN_ID=${RUN_ID}"

echo "[INFO] מציג/ה תקציר הריצה…"
gh run view "$RUN_ID" || true

echo "[INFO] ממתין/ה לריצה שתסתיים (לא אינטראקטיבי)…"
gh run watch "$RUN_ID" || true
echo "[INFO] Run ${RUN_ID} completed"

echo "[INFO] מביא/ה מזהי jobs…"
JOBS_JSON=$(gh run view "$RUN_ID" --json jobs -q '.jobs')
JOB_IDS=$(echo "$JOBS_JSON" | jq -r '.[].id' 2>/dev/null || true)

if [[ -n "${JOB_IDS}" ]]; then
  for J in ${JOB_IDS}; do
    echo "[INFO] מציג/ה לוג של ה-Job (id=${J})…"
    gh job view "${J}" --log || true
  done
else
  echo "⚠️  לא נמצאו jobs בריצה (אנסה להביא לוג כללי)…"
  gh run view "$RUN_ID" --log || echo "⚠️  לא הצלחתי להביא לוג כללי."
fi

echo "[INFO] מנקה תיקיית ארטיפקטים מקומית: ./artifact …"
rm -rf artifact || true
mkdir -p artifact

echo "[INFO] מוריד/ה ארטיפקטים (smoke-artifacts)…"
if gh run download "$RUN_ID" -n smoke-artifacts -D artifact; then
  echo "[INFO] הורדה הושלמה אל: artifact"
else
  echo "⚠️  אין ארטיפקטים בשם smoke-artifacts (או שההורדה נכשלה)."
fi

echo "---- smoke.log ----"
sed -n '1,200p' artifact/artifacts/logs/smoke.log 2>/dev/null || echo "אין smoke.log בארטיפקט"

echo "---- env.txt ----"
sed -n '1,200p' artifact/artifacts/json/env.txt 2>/dev/null || echo "אין env.txt בארטיפקט"

echo "---- api.out (סוף 200 שורות) ----"
tail -n 200 /tmp/api.out 2>/dev/null || tail -n 200 artifact/tmp/api.out 2>/dev/null || echo "אין api.out בארטיפקט"

echo "[INFO] סיום. קבצים בתיקייה: ./artifact (אם קיימים)."
