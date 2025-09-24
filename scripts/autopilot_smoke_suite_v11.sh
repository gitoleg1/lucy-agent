#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================
# Lucy Autopilot — smoke v11 (actions-correct, auth-check on agent/shell)
# ============================================

APP_MODULE="${APP_MODULE:-lucy_agent.main:app}"
API_BASE="${NEXT_PUBLIC_AGENT_BASE:-http://127.0.0.1:8000}"
API_BASE="${API_BASE%/}"
API_HEALTH="$API_BASE/health"
API_TASKS="$API_BASE/tasks/"
API_RUN_BASE="$API_BASE/tasks"
API_AGENT_SHELL="$API_BASE/tasks/agent/shell"
API_QUICK_RUN="$API_BASE/tasks/quick-run"

# ---- API KEY (מ-.env אם לא הוגדר כסביבה)
API_KEY="${AGENT_API_KEY:-}"
if [[ -z "${API_KEY}" && -f ".env" ]]; then
  API_KEY="$(awk -F= '/^AGENT_API_KEY=/{print $2}' .env | tr -d $'\r\n ')"
fi
API_KEY="${API_KEY:-ChangeMe_SuperSecret_Long}"

ART_DIR="artifacts"
LOG_DIR="$ART_DIR/logs"
OUT_DIR="$ART_DIR/json"
mkdir -p "$LOG_DIR" "$OUT_DIR"

log() { printf '[SMOKE] %s\n' "$*" | tee -a "$LOG_DIR/smoke.log" ; }
have_cmd() { command -v "$1" >/dev/null 2>&1; }
require() { for c in "$@"; do have_cmd "$c" || { echo "Missing command: $c" >&2; exit 2; }; done; }
require curl jq

post_json_headers() {
  # post_json_headers <url> <body> <outfile>  -> מחזיר קוד HTTP
  local url="$1" body="$2" of="$3"
  curl -sS -L -o "$of" -w "%{http_code}" \
    -X POST "$url" \
    -H "X-Api-Key: $API_KEY" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body"
}

wait_health() {
  local deadline=$((SECONDS+30))
  while (( SECONDS < deadline )); do
    if curl -sf "$API_HEALTH" >/dev/null; then return 0; fi
    sleep 0.5
  done
  return 1
}

NEED_BOOT=0
if ! curl -sf "$API_HEALTH" >/dev/null 2>&1; then NEED_BOOT=1; fi

API_PID=""
if (( NEED_BOOT )); then
  have_cmd uvicorn || { echo "uvicorn not found"; exit 3; }
  log "לא נמצא API פעיל — מרימים לוקאלית: uvicorn $APP_MODULE --host 127.0.0.1 --port 8000"
  ( uvicorn "$APP_MODULE" --host 127.0.0.1 --port 8000 >"$LOG_DIR/api.out" 2>"$LOG_DIR/api.err" ) &
  API_PID=$!
  disown "$API_PID"
  wait_health || { log "כשל בהמתנה ל-/health לאחר הרמה"; exit 4; }
else
  log "נמצא API פעיל — ממשיכים לבדיקה."
fi

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# ---- 1) /health
log "בדיקת /health"
curl -sS "$API_HEALTH" | tee "$OUT_DIR/health.json" | jq . >/dev/null || true

# ---- 2) POST /tasks/ (נכון לפי OpenAPI: actions)
log "יצירת משימה עם actions (לא steps)"
CREATE_BODY='{
  "title": "smoke-v11",
  "actions": [
    { "type": "shell", "params": { "cmd": "echo start && uname -a && echo end" } }
  ]
}'
HTTP_CODE_CREATE="$(post_json_headers "$API_TASKS" "$CREATE_BODY" "$OUT_DIR/create_task.json")"
echo "$HTTP_CODE_CREATE" > "$OUT_DIR/create_task.code"
log "POST /tasks/ → HTTP $HTTP_CODE_CREATE"
if [[ "$HTTP_CODE_CREATE" == "401" || "$HTTP_CODE_CREATE" == "403" ]]; then
  log "הרשאה נכשלה (HTTP $HTTP_CODE_CREATE). בדוק AGENT_API_KEY"
  exit 11
fi
if [[ "$HTTP_CODE_CREATE" != "200" && "$HTTP_CODE_CREATE" != "201" ]]; then
  log "קוד לא תקין ליצירת משימה ($HTTP_CODE_CREATE). ראה גוף ב-$OUT_DIR/create_task.json"
  exit 12
fi

TASK_ID="$(jq -r '.id // .task_id // .data.id // empty' "$OUT_DIR/create_task.json" || true)"
if [[ -z "$TASK_ID" || "$TASK_ID" == "null" ]]; then
  log "לא נמצא TASK_ID בתגובה. הדפסה לצורך דיבוג:"
  jq . "$OUT_DIR/create_task.json" || true
  exit 13
fi
log "TASK_ID=$TASK_ID"

# ---- 3) POST /tasks/{id}/run (לפי OpenAPI אין body)
log "הפעלת המשימה (POST /tasks/{id}/run)"
RUN_URL="$API_RUN_BASE/$TASK_ID/run"
HTTP_CODE_RUN="$(post_json_headers "$RUN_URL" '{}' "$OUT_DIR/run_$TASK_ID.json")"
echo "$HTTP_CODE_RUN" > "$OUT_DIR/run_$TASK_ID.code"
log "POST /tasks/{id}/run → HTTP $HTTP_CODE_RUN"

# ---- 4) פולינג לסטטוס עד סיום
log "פולינג לסטטוס המשימה"
STATUS=""
DEADLINE=$((SECONDS+120))
while (( SECONDS < DEADLINE )); do
  TASK_JSON="$OUT_DIR/task_$TASK_ID.json"
  curl -sS -H "X-Api-Key: $API_KEY" -H "Authorization: Bearer $API_KEY" "$API_RUN_BASE/$TASK_ID" \
    | tee "$TASK_JSON" >/dev/null
  STATUS="$(jq -r '.status // empty' "$TASK_JSON")"
  log "סטטוס: $STATUS"
  case "$STATUS" in
    SUCCEEDED) break ;;
    FAILED|CANCELED|CANCELLED) log "משימה נכשלה/בוטלה"; exit 24 ;;
  esac
  sleep 1
done
[[ "$STATUS" == "SUCCEEDED" ]] || { log "פולינג הגיע ל-timeout (לא SUCCEEDED)"; exit 25; }

# ---- 5) בדיקת 401/403 ללא מפתח — על endpoint מוגן (/tasks/agent/shell)
log "בדיקת 401/403 ללא מפתח על /tasks/agent/shell"
SHELL_BODY_UNAUTH='{"cmd":"echo ok","title":"agent-shell"}'
HTTP_CODE_NOAUTH="$(curl -sS -L -o "$OUT_DIR/unauth.json" -w "%{http_code}" \
  -X POST "$API_AGENT_SHELL" \
  -H "Content-Type: application/json" \
  -d "$SHELL_BODY_UNAUTH")"
echo "$HTTP_CODE_NOAUTH" > "$OUT_DIR/unauth.code"
if [[ "$HTTP_CODE_NOAUTH" != "401" && "$HTTP_CODE_NOAUTH" != "403" ]]; then
  log "ציפינו ל-401/403, קיבלנו $HTTP_CODE_NOAUTH"
  exit 26
fi

log "SMOKE v11 — הושלם בהצלחה"
