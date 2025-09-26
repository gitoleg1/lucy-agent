#!/usr/bin/env bash
set -euo pipefail

API_BASE="http://127.0.0.1:8000"
ENV_FILE="$HOME/projects/lucy-agent/.env.autopilot"
SERVICE="lucy-agent.service"
CLIENT_MIN_INTERVAL="${LUCY_AUTOPILOT_MIN_INTERVAL_SEC:-0.6}"

say(){ printf "%s\n" "$*"; }
hr(){ printf '────────────────────────────────────────\n'; }
pause_rate(){ sleep "${CLIENT_MIN_INTERVAL}"; }

# טען TOKEN אם לא הוגדר בסביבה
if [[ -z "${LUCY_AUTOPILOT_TOKEN:-}" && -f "$ENV_FILE" ]]; then
  LUCY_AUTOPILOT_TOKEN="$(awk -F= '/^\s*LUCY_AUTOPILOT_TOKEN\s*=/{sub(/^"/,"",$2);sub(/"$/,"",$2);gsub(/\r/,"",$2);print $2}' "$ENV_FILE")"
fi
CURL_AUTH=()
if [[ -n "${LUCY_AUTOPILOT_TOKEN:-}" ]]; then
  CURL_AUTH=(-H "X-API-Key: ${LUCY_AUTOPILOT_TOKEN}")
fi

wait_health() {
  for i in {1..100}; do
    if curl -sf "${API_BASE}/health" >/dev/null; then
      say "✅ health OK"; return 0
    fi
    sleep 0.2
  done
  say "❌ health not responding"; return 1
}

post_json() {
  local endpoint="$1"; shift
  curl -sS -X POST "${API_BASE}${endpoint}" \
    -H 'Content-Type: application/json' \
    "${CURL_AUTH[@]}" \
    -d "$@"
}

post_capture_code() {
  local endpoint="$1"; local body="$2"
  local tmp="$(mktemp)"
  local code
  code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "${API_BASE}${endpoint}" -H 'Content-Type: application/json' "${CURL_AUTH[@]}" -d "$body")"
  if [[ "$code" == "429" ]]; then
    pause_rate
    code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "${API_BASE}${endpoint}" -H 'Content-Type: application/json' "${CURL_AUTH[@]}" -d "$body")"
  fi
  printf '%s\n' "$code"
  cat "$tmp" > /tmp/last_body.json
  rm -f "$tmp"
}

restart_service_and_wait() {
  systemctl --user daemon-reload >/dev/null
  systemctl --user restart "$SERVICE"
  # המתנה לעליית הפורט
  for i in {1..100}; do
    if ss -ltn "( sport = :8000 )" 2>/dev/null | grep -q 127.0.0.1:8000; then
      break
    fi
    sleep 0.2
  done
  wait_health
}

# ניהול קובץ סביבה: נבנה וריאציות מתוך המקור, ונשחזר בסוף
ORIG_ENV="$(mktemp)"
if [[ -f "$ENV_FILE" ]]; then cp -a "$ENV_FILE" "$ORIG_ENV"; else : > "$ORIG_ENV"; fi

build_env_from_orig() {
  # שימוש: build_env_from_orig VAR1=VAL1 VAR2=VAL2 ...
  local tmp="$(mktemp)"
  cp -a "$ORIG_ENV" "$tmp" 2>/dev/null || :
  for kv in "$@"; do
    local k="${kv%%=*}"
    # הסר שורות קיימות למפתח הזה
    grep -v -E "^[[:space:]]*${k}=" "$tmp" > "${tmp}.clean" || true
    mv "${tmp}.clean" "$tmp"
    # הוסף ערך חדש
    echo "$kv" >> "$tmp"
  done
  mv "$tmp" "$ENV_FILE"
}

restore_env() {
  cp -a "$ORIG_ENV" "$ENV_FILE"
}

say "=== 0) Clean boot & wait health ==="
wait_health || exit 1
hr

say "=== 1) Happy path — echo ok && true ==="
resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo ok && true"}')"
status="$(jq -r '.task.status // empty' <<<"$resp")"
rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  say "✅ happy path ok"
else
  say "❌ happy path failed"; echo "$resp"; exit 1
fi
hr; pause_rate

say "=== 2) Denylist — rm -rf / => 400 ==="
code="$(post_capture_code '/tasks/agent/shell' '{"cmd":"rm -rf /"}')"
if [[ "$code" == "400" ]]; then
  say "✅ denylist blocks rm -rf /"
else
  say "❌ denylist expected 400, got $code"; cat /tmp/last_body.json; exit 1
fi
hr; pause_rate

say "=== 3) Allowlist — allow only \"echo\" (server env) ==="
# בנה קובץ env חדש מתוך המקור עם allow=echo
build_env_from_orig "LUCY_AUTOPILOT_ALLOW=echo"
restart_service_and_wait || exit 1
pause_rate

resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo allowed && true"}')"
status="$(jq -r '.task.status // empty' <<<"$resp")"
rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  say "✅ allowlist allows echo"
else
  say "❌ allowlist echo failed"; echo "$resp"; fail_allow=1
fi

pause_rate
code="$(post_capture_code '/tasks/agent/shell' '{"cmd":"uname -a"}')"
if [[ "$code" == "400" || "$code" == "403" ]]; then
  say "✅ allowlist blocks uname"
else
  say "❌ allowlist expected 400/403 for uname, got $code"; cat /tmp/last_body.json; fail_allow=1
fi
hr

say "✅ health OK"
# שלב 4: טיימאאוט — חייב לעדכן ENV של השרת (לא export מקומי!)
say "=== 4) Timeout — expect FAILED/124/timeout=true ==="
build_env_from_orig "LUCY_AUTOPILOT_TIMEOUT_SECONDS=1" "LUCY_AUTOPILOT_TIMEOUT_EXIT=124"
restart_service_and_wait || exit 1
pause_rate

resp="$(post_json '/tasks/agent/shell' '{"cmd":"sleep 5"}')"
status="$(jq -r '.task.status // empty' <<<"$resp")"
rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
to_flag="$(jq -r '.audit[-1].data.timeout // empty' <<<"$resp")"
st_type="$(jq -r 'type' <<<"$(jq -r '.audit[-1].data.stdout_tail' <<<"$resp" 2>/dev/null)")"
er_type="$(jq -r 'type' <<<"$(jq -r '.audit[-1].data.stderr_tail' <<<"$resp" 2>/dev/null)")"
say "status=${status} rc=${rc} timeout=${to_flag} stdout_type=${st_type} stderr_type=${er_type}"
if [[ "$status" == "FAILED" && "$rc" == "124" && "$to_flag" == "true" && "$st_type" == "string" && "$er_type" == "string" ]]; then
  say "✅ timeout semantics correct"
else
  say "❌ timeout semantics wrong"; echo "$resp"; restore_env; restart_service_and_wait || true; exit 1
fi
hr

say "=== 5) API Key checks ==="
if [[ -z "${LUCY_AUTOPILOT_TOKEN:-}" ]]; then
  say "ℹ️ no token in env/.env.autopilot — skipping auth checks"
else
  code="$(curl -sS -o /tmp/noauth.json -w '%{http_code}' -X POST "${API_BASE}/tasks/agent/shell" -H 'Content-Type: application/json' -d '{"cmd":"echo ok && true"}')"
  if [[ "$code" == "429" ]]; then pause_rate; code="$(curl -sS -o /tmp/noauth.json -w '%{http_code}' -X POST "${API_BASE}/tasks/agent/shell" -H 'Content-Type: application/json' -d '{"cmd":"echo ok && true"}')"; fi
  if [[ "$code" == "401" || "$code" == "403" ]]; then
    say "✅ auth rejects without key ($code)"
  else
    say "❌ expected 401/403 without key, got $code"; cat /tmp/noauth.json; restore_env; restart_service_and_wait || true; exit 1
  fi
  pause_rate
  resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo ok && true"}')"
  status="$(jq -r '.task.status // empty' <<<"$resp")"
  rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
  if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
    say "✅ auth passes with valid key"
  else
    say "❌ auth with key failed"; echo "$resp"; restore_env; restart_service_and_wait || true; exit 1
  fi
fi
hr

# שחזור ENV למקור והפעלה מחדש לסיום
restore_env
restart_service_and_wait || true

if [[ "${fail_allow:-0}" -ne 0 ]]; then
  say "❌ allowlist stage failed (env restored)."; exit 1
fi

say "🎉 ALL CHECKS PASSED"
