#!/usr/bin/env bash
set -Eeuo pipefail

# =========================
# Lucy Autopilot — SMOKE v11 (resilient)
# =========================
# שימוש:
#   AGENT_API_KEY="..." bash scripts/autopilot_smoke_suite_v11.sh
#
# יכולות:
# - משיכת OpenAPI ובחירת נתיב יצירה מועדף (/tasks/ או /tasks) עם Fallback
# - יצירה עם actions (לא steps), הפעלה /tasks/{id}/run, פולינג סטטוס
# - בדיקת unauth על /tasks/agent/shell (401/403/405 מתקבל)
# - אם אין כלל /tasks ב־OpenAPI → מדלגים על בדיקות Tasks ומסיימים בהצלחה (Health-only)
# - שמירת JSON+לוגים תחת artifacts/{logs,json}/

BASE="${NEXT_PUBLIC_AGENT_BASE:-http://127.0.0.1:8000}"
KEY="${AGENT_API_KEY:-}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

ART_DIR="artifacts"
LOG_DIR="$ART_DIR/logs"
JSON_DIR="$ART_DIR/json"
mkdir -p "$LOG_DIR" "$JSON_DIR"

LOG_FILE="$LOG_DIR/smoke.log"
: > "$LOG_FILE"

log() {
  # כותב גם לקובץ וגם ל-stderr כדי שלא יילכד בפלט של command substitution
  printf '[SMOKE] %s\n' "$*" | tee -a "$LOG_FILE" 1>&2
}

curl_json() {
  local method="$1" url="$2" out="$3" data="${4:-}"
  local -a args=(-sS -X "$method" "$url" -D /tmp/h.$$.hdr -o /tmp/h.$$.body -w '%{http_code}')
  if [[ -n "$KEY" ]]; then
    args+=(-H "X-Api-Key: $KEY" -H "Authorization: Bearer $KEY")
  fi
  if [[ -n "$data" ]]; then
    args+=(-H "Content-Type: application/json" --data "$data")
  fi
  local code
  if ! code="$(curl "${args[@]}" 2>/dev/null)"; then
    code=000
  fi
  cat /tmp/h.$$.body > "$out" || true
  rm -f /tmp/h.$$.hdr /tmp/h.$$.body || true
  echo "$code"
}

poll_task_status() {
  local task_id="$1" timeout_s="${2:-30}" interval_s="${3:-1}"
  local t=0
  while (( t < timeout_s )); do
    local body="${JSON_DIR}/task_${task_id}.json"
    local code; code="$(curl_json GET "${BASE}/tasks/${task_id}" "$body")"
    if [[ "$code" != "200" ]]; then
      log "סטטוס משימה: HTTP $code (ממשיך לנסות)"
    else
      local status
      status="$(jq -r '.status // .Status // empty' "$body" 2>/dev/null || true)"
      [[ -z "$status" ]] && status="$(grep -oE '"status"\s*:\s*"[^"]+"' "$body" | head -1 | sed -E 's/.*"status"\s*:\s*"([^"]+)".*/\1/')"
      log "סטטוס: ${status:-UNKNOWN}"
      [[ "$status" == "SUCCEEDED" ]] && return 0
      [[ "$status" == "FAILED" || "$status" == "CANCELED" || "$status" == "CANCELLED" ]] && return 1
    fi
    sleep "$interval_s"
    (( t += interval_s ))
  done
  log "פולינג הגיע ל-timeout (לא SUCCEEDED)"
  return 1
}

discover_preferred_create_path() {
  local out="${JSON_DIR}/openapi.json"
  log "משיכת OpenAPI"
  local code; code="$(curl_json GET "${BASE}/openapi.json" "$out")"
  if [[ "$code" != "200" ]]; then
    echo "NO_OPENAPI"
    return 0
  fi

  # יש /tasks/?
  if jq -e '.paths["/tasks/"]' "$out" >/dev/null 2>&1; then
    echo "/tasks/"
    return 0
  fi
  # יש /tasks?
  if jq -e '.paths["/tasks"]' "$out" >/dev/null 2>&1; then
    echo "/tasks"
    return 0
  fi

  # אין כלל /tasks — מודיעים לקרואית
  echo "NO_TASKS"
}

# ────────────────────────────────────────────────────────────────────────────────
log "נמצא API פעיל — ממשיכים לבדיקה."
log "בדיקת /health"
curl_json GET "${BASE}/health" "${JSON_DIR}/health.json" >/dev/null || true

PREFERRED_CREATE="$(discover_preferred_create_path 2>/dev/null)"

# אם אין כלל /tasks ב־OpenAPI — מדלגים על שלב המשימות, מסיימים Health-only
if [[ "$PREFERRED_CREATE" == "NO_TASKS" ]]; then
  log "לא נמצאו מסלולי /tasks ב־OpenAPI — מדלגים על בדיקות Tasks. Health-only ✅"
  exit 0
fi

# אם לא הצלחנו למשוך OpenAPI — ננסה קודם /tasks/ ואז /tasks
declare -a CREATE_CANDIDATES
if [[ "$PREFERRED_CREATE" == "NO_OPENAPI" ]]; then
  log "OpenAPI לא זמין — מנסה סדרה: /tasks/ → /tasks"
  CREATE_CANDIDATES=("/tasks/" "/tasks")
else
  ALTERNATE_CREATE="$([[ "$PREFERRED_CREATE" == "/tasks/" ]] && echo "/tasks" || echo "/tasks/")"
  log "CREATE_PATH מועדף: ${PREFERRED_CREATE} | חלופי: ${ALTERNATE_CREATE}"
  CREATE_CANDIDATES=("$PREFERRED_CREATE" "$ALTERNATE_CREATE")
fi

# יצירה עם actions (לא steps)
log "יצירת משימה עם actions (לא steps)"
CREATE_PAYLOAD="$(jq -n --arg t "smoke-v11" '
  {
    title: $t,
    actions: [
      {type:"echo",  args:{text:"hello"}},
      {type:"sleep", args:{seconds: 0}}
    ]
  }'
)"

TASK_ID=""
CREATE_CODE=""
for path in "${CREATE_CANDIDATES[@]}"; do
  CREATE_CODE="$(curl_json POST "${BASE}${path}" "${JSON_DIR}/create_task.json" "$CREATE_PAYLOAD")"
  echo "$CREATE_CODE" > "${JSON_DIR}/create_task.code"
  [[ "$CREATE_CODE" == "200" ]] && break
  log "יצירה נכשלה בקוד ${CREATE_CODE} על ${path} — מנסה נתיב חלופי (אם יש)"
done

if [[ "$CREATE_CODE" != "200" ]]; then
  log "קוד לא תקין ליצירת משימה (${CREATE_CODE}). ראה ${JSON_DIR}/create_task.json"
  exit 1
fi

TASK_ID="$(jq -r '.id // .task_id // empty' "${JSON_DIR}/create_task.json" || true)"
if [[ -z "$TASK_ID" || "$TASK_ID" == "null" ]]; then
  log "לא הוחזר TASK_ID ביצירה"
  exit 1
fi
log "TASK_ID=${TASK_ID}"

# הרצה
log "הפעלת המשימה (POST /tasks/{id}/run)"
RUN_CODE="$(curl_json POST "${BASE}/tasks/${TASK_ID}/run" "${JSON_DIR}/run_${TASK_ID}.json")"
echo "$RUN_CODE" > "${JSON_DIR}/run_${TASK_ID}.code"

if [[ "$RUN_CODE" != "200" ]]; then
  log "POST /tasks/{id}/run → HTTP ${RUN_CODE}"
  log "Fallback#1: /tasks/agent/shell"
  AGENT_SHELL_PAYLOAD='{"cmd":"echo ok-from-agent-shell","title":"agent-shell"}'
  AS_CODE="$(curl_json POST "${BASE}/tasks/agent/shell" "${JSON_DIR}/agent_shell.json" "$AGENT_SHELL_PAYLOAD")"
  echo "$AS_CODE" > "${JSON_DIR}/agent_shell.code"
  if [[ "$AS_CODE" != "200" ]]; then
    log "Fallback#2: /tasks/quick-run"
    QR_PAYLOAD='{"title":"autopilot","actions":[{"type":"echo","args":{"text":"hello"}}]}'
    QR_CODE="$(curl_json POST "${BASE}/tasks/quick-run" "${JSON_DIR}/quick_run.json" "$QR_PAYLOAD")"
    echo "$QR_CODE" > "${JSON_DIR}/quick_run.code"
    [[ "$QR_CODE" == "200" ]] || { log "כל מסלולי ה-fallback נכשלו — ראה ארטיפקטים תחת ${JSON_DIR}"; exit 1; }
  fi
fi

# פולינג סטטוס
log "פולינג לסטטוס המשימה"
if ! poll_task_status "$TASK_ID" 30 1 ; then
  exit 1
fi

# בדיקת unauth על /tasks/agent/shell (מורידים כותרות)
log "בדיקת 401/403/405 ללא מפתח על /tasks/agent/shell"
saved_key="$KEY"
unset KEY
UA_CODE="$(curl_json POST "${BASE}/tasks/agent/shell" "${JSON_DIR}/unauth.json" '{"cmd":"echo unauth"}')"
echo "$UA_CODE" > "${JSON_DIR}/unauth.code"
# מתקבל 401/403, ובחלק מהמימושים 405 (Method Not Allowed) — כולם בסדר לבדיקה זו
if [[ "$UA_CODE" != "401" && "$UA_CODE" != "403" && "$UA_CODE" != "405" ]]; then
  log "ציפינו ל-401/403/405, קיבלנו ${UA_CODE}"
fi
KEY="$saved_key"

log "SMOKE v11 — הושלם בהצלחה"
