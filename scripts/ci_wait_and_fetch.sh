#!/usr/bin/env bash
# scripts/ci_wait_and_fetch.sh
# מחכה לריצה האחרונה ב-GitHub Actions שתסתיים, מוריד ארטיפקטים ומציג לוגים רלוונטיים.
set -euo pipefail

log() { printf '[INFO] %s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }

# 1) זיהוי הריפו ו-RUN_ID אחרון
log "מזהה ריפו דרך gh…"
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
log "REPO=$REPO"

log "לוכד/ת RUN_ID של הריצה האחרונה…"
RUN_ID=$(gh run list --repo "$REPO" --limit 1 --json databaseId --jq '.[0].databaseId')
if [[ -z "${RUN_ID:-}" ]]; then
  warn "לא נמצא RUN_ID"; exit 1
fi
log "RUN_ID=$RUN_ID"

# 2) תקציר מצב הריצה
log "מציג/ה תקציר הריצה…"
gh run view "$RUN_ID" --repo "$REPO" --json databaseId,url,status,conclusion,headBranch,headSha,workflowName,displayTitle \
  --jq '"URL="+.url, "status="+.status+" conclusion="+( .conclusion//"n/a")+" | "+.headBranch+"@"+.headSha[0:7], "workflow="+.workflowName+" | "+.displayTitle'

# 3) המתנה עד סיום (אם עדיין רצה)
log "ממתין/ה לריצה שתסתיים (לא אינטראקטיבי)…"
# אם כבר הסתיים, הפקודה תחזור מיד
gh run watch "$RUN_ID" --repo "$REPO" || true

# 4) הצגת לוגים מרוכזת לקונסול
log "מציג/ה לוגים…"
# נציג HEAD של ה־job העיקרי (תמיד יש רק job אחד אצלך בשם ci)
gh run view "$RUN_ID" --repo "$REPO" --log | sed -n '1,400p' || true

# 5) הורדת ארטיפקטים (כולל /tmp/api.out והלוגים שה־workflow מעלה)
ART_DIR="./artifact"
log "מוריד/ה ארטיפקטים (smoke-artifacts)…"
mkdir -p "$ART_DIR"
gh run download "$RUN_ID" --repo "$REPO" -n smoke-artifacts -D "$ART_DIR" || warn "אין ארטיפקטים להוריד"

# 6) תצוגת לוגים מהארטיפקט/טמפ
echo "---- smoke.log ----"
sed -n '1,200p' "$ART_DIR/artifacts/logs/smoke.log" 2>/dev/null || echo "אין smoke.log בארטיפקט"

echo "---- env.txt ----"
sed -n '1,120p' "$ART_DIR/artifacts/logs/env.txt" 2>/dev/null || echo "אין env.txt בארטיפקט"

echo "---- api.out (סוף 200 שורות) ----"
tail -n 200 /tmp/api.out 2>/dev/null \
  || tail -n 200 "$ART_DIR/tmp/api.out" 2>/dev/null \
  || echo "אין api.out"

log "סיום. קבצים בתיקייה: $ART_DIR (אם קיימים)."
