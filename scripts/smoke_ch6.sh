#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:?BASE_URL is required, e.g. http://127.0.0.1:8000}"
: "${API_KEY:?API_KEY is required}"

json_true='{"cmd":"true"}'
json_exit2='{"cmd":"exit 2"}'

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }

fail() { red "✗ $*"; exit 1; }
pass() { grn "✓ $*"; }

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/health")
[[ "$code" == "200" ]] || fail "/health expected 200, got $code"
pass "/health 200"

resp=$(curl -s -o /tmp/ch6_no_key.json -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -d "$json_true" "$BASE_URL/agent/shell")
[[ "$resp" == "401" ]] || fail "/agent/shell without key expected 401, got $resp"
grep -q '"Invalid API key"' /tmp/ch6_no_key.json || fail "detail missing for 401 without key"
pass "/agent/shell 401 ללא מפתח (detail תקין)"

resp=$(curl -s -o /tmp/ch6_bad_key.json -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H 'X-API-Key: WRONG' \
  -d "$json_true" "$BASE_URL/agent/shell")
[[ "$resp" == "401" ]] || fail "/agent/shell with wrong key expected 401, got $resp"
pass "/agent/shell 401 עם מפתח שגוי"

resp=$(curl -s -o /tmp/ch6_ok_true.json -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H "X-API-Key: ${API_KEY}" \
  -d "$json_true" "$BASE_URL/agent/shell")
[[ "$resp" == "200" ]] || fail "true expected 200, got $resp"
grep -q '"status":"SUCCEEDED"' /tmp/ch6_ok_true.json || fail "true: status not SUCCEEDED"
grep -q '"exit_code":0' /tmp/ch6_ok_true.json || fail "true: exit_code not 0"
pass "מפתח נכון + true ⇒ SUCCEEDED, exit_code=0"

resp=$(curl -s -o /tmp/ch6_ok_ex2.json -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H "X-API-Key: ${API_KEY}" \
  -d "$json_exit2" "$BASE_URL/agent/shell")
[[ "$resp" == "200" ]] || fail "exit 2 expected 200, got $resp"
grep -q '"status":"FAILED"' /tmp/ch6_ok_ex2.json || fail "exit 2: status not FAILED"
grep -q '"exit_code":2' /tmp/ch6_ok_ex2.json || fail "exit 2: exit_code not 2"
pass "מפתח נכון + 'exit 2' ⇒ FAILED, exit_code=2"

if [[ -f ".api.log" ]]; then
  grep -q "Traceback" .api.log && fail "Traceback found in .api.log"
  pass ".api.log נקי מ-Traceback"
else
  ylw ".api.log לא נמצא — ודא שהשרת הופעל עם הפניית לוג לקובץ."
  exit 1
fi

pass "SMOKE CH6: הכול ירוק"
