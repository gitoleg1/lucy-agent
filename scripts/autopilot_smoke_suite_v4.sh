#!/usr/bin/env bash
set -euo pipefail

# ── הגדרות כלליות ──────────────────────────────────────────
API_BASE="http://127.0.0.1:8000"
ENV_FILE="$HOME/projects/lucy-agent/.env.autopilot"

# פרמטר חסם־קצב מקומי לבדיקה (שימושי אם השרת מכוון ל-0.5ש')
CLIENT_MIN_INTERVAL="${LUCY_AUTOPILOT_MIN_INTERVAL_SEC:-0.6}"

# טען TOKEN מהסביבה או מהקובץ .env.autopilot
if [[ -z "${LUCY_AUTOPILOT_TOKEN:-}" && -f "$ENV_FILE" ]]; then
  LUCY_AUTOPILOT_TOKEN="$(awk -F= '/^\s*LUCY_AUTOPILOT_TOKEN\s*=/{sub(/^"/,"",$2);sub(/"$/,"",$2);gsub(/\r/,"",$2);print $2}' "$ENV_FILE")"
fi

# אם יש טוקן – נכין דגל curl; אם אין – לא נשלח כותרת ונצפה ל-401 היכן שצריך
CURL_AUTH=()
if [[ -n "${LUCY_AUTOPILOT_TOKEN:-}" ]]; then
  CURL_AUTH=(-H "X-API-Key: ${LUCY_AUTOPILOT_TOKEN}")
fi

say() { printf "%s\n" "$*"; }
hr(){ printf '────────────────────────────────────────\n'; }
pause_rate(){ sleep "${CLIENT_MIN_INTERVAL}"; }

# ממתין ל-health
wait_health() {
  for i in {1..50}; do
    if curl -sf "${API_BASE}/health" >/dev/null; then
      say "✅ health OK"
      return 0
    fi
    sleep 0.2
  done
  say "❌ health not responding"
  return 1
}

# POST רגיל שמחזיר JSON (עם כותרת auth אם קיימת)
post_json() {
  local endpoint="$1"; shift
  curl -sS -X POST "${API_BASE}${endpoint}" \
    -H 'Content-Type: application/json' \
    "${CURL_AUTH[@]}" \
    -d "$@"
}

# קריאה שמחזירה קוד־סטטוס ועם retry יחיד במקרה של 429
post_capture_code() {
  local endpoint="$1"; shift
  local body="$1"; shift || true
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

# ── התחלה ──────────────────────────────────────────────────
say "=== 0) Clean boot & wait health ==="
wait_health
hr

# 1) Happy path (עם כותרת אם יש טוקן)
say "=== 1) Happy path — echo ok && true ==="
resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo ok && true"}')"
status="$(jq -r '.task.status // empty' <<<"$resp")"
rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  say "✅ happy path ok"
else
  say "❌ happy path failed"; echo "$resp"; exit 1
fi
hr
pause_rate

# 2) Denylist — rm -rf / => 400
say "=== 2) Denylist — rm -rf / => 400 ==="
code="$(post_capture_code '/tasks/agent/shell' '{"cmd":"rm -rf /"}')"
if [[ "$code" == "400" ]]; then
  say "✅ denylist blocks rm -rf /"
else
  say "❌ denylist expected 400, got $code"; cat /tmp/last_body.json; exit 1
fi
hr
pause_rate

# 3) Allowlist — נאפשר רק echo ונבדוק ש-uname נחסם
say "=== 3) Allowlist — allow only \"echo\" ==="
export LUCY_AUTOPILOT_ALLOW='echo'
wait_health
pause_rate
resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo allowed && true"}')"
status="$(jq -r '.task.status // empty' <<<"$resp")"
rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  say "✅ allowlist allows echo"
else
  say "❌ allowlist echo failed"; echo "$resp"; exit 1
fi
pause_rate
code="$(post_capture_code '/tasks/agent/shell' '{"cmd":"uname -a"}')"
if [[ "$code" == "400" || "$code" == "403" ]]; then
  say "✅ allowlist blocks uname"
else
  say "❌ allowlist expected 400/403 for uname, got $code"; cat /tmp/last_body.json; exit 1
fi
hr
pause_rate

# 4) Timeout — מצפה FAILED, 124, timeout=true, tails מחרוזות
say "=== 4) Timeout — expect FAILED/124/timeout=true ==="
export LUCY_AUTOPILOT_TIMEOUT_SECONDS=1
export LUCY_AUTOPILOT_TIMEOUT_EXIT=124
wait_health
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
  say "❌ timeout semantics wrong"; echo "$resp"; exit 1
fi
hr
pause_rate

# 5) Auth — אם אין טוקן, נדלג; אם יש — נבדוק
say "=== 5) API Key checks ==="
if [[ -z "${LUCY_AUTOPILOT_TOKEN:-}" ]]; then
  say "ℹ️ no token in env/.env.autopilot — skipping auth checks"
else
  # בלי כותרת
  code="$(curl -sS -o /tmp/noauth.json -w '%{http_code}' -X POST "${API_BASE}/tasks/agent/shell" -H 'Content-Type: application/json' -d '{"cmd":"echo ok && true"}')"
  if [[ "$code" == "429" ]]; then pause_rate; code="$(curl -sS -o /tmp/noauth.json -w '%{http_code}' -X POST "${API_BASE}/tasks/agent/shell" -H 'Content-Type: application/json' -d '{"cmd":"echo ok && true"}')"; fi
  if [[ "$code" == "401" || "$code" == "403" ]]; then
    say "✅ auth rejects without key ($code)"
  else
    say "❌ expected 401/403 without key, got $code"; cat /tmp/noauth.json; exit 1
  fi
  pause_rate
  # עם כותרת
  resp="$(post_json '/tasks/agent/shell' '{"cmd":"echo ok && true"}')"
  status="$(jq -r '.task.status // empty' <<<"$resp")"
  rc="$(jq -r '.runs[0].exit_code // empty' <<<"$resp")"
  if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
    say "✅ auth passes with valid key"
  else
    say "❌ auth with key failed"; echo "$resp"; exit 1
  fi
fi
hr

say "🎉 ALL CHECKS PASSED"
