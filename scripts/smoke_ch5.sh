#!/usr/bin/env bash
set -euo pipefail

# === הגדרות בסיס ===
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
API_KEY="${API_KEY:-changeme}"

pass() { echo -e "\033[32mPASS\033[0m - $*"; }
fail() { echo -e "\033[31mFAIL\033[0m - $*"; exit 1; }

echo "== Lucy Autopilot - Smoke Test (Chapter 5) =="
echo "BASE_URL=${BASE_URL}"
echo "API_KEY=${API_KEY:0:2}******"

# 0) בריאות שרת
echo "[0] GET /health ..."
code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
[[ "$code" == "200" ]] || fail "health returned HTTP ${code}"
pass "/health = 200"

# 1) הצלחה: true
echo "[1] POST /agent/shell (true) ..."
resp_true=$(curl -sS -X POST "${BASE_URL}/agent/shell" \
  -H "content-type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  --data '{"cmd":"true"}' || true)

echo "$resp_true" | grep -qi '"status"[[:space:]]*:[[:space:]]*"SUCCEEDED"' \
  || fail "expected status=SUCCEEDED; got: $resp_true"
echo "$resp_true" | grep -qi '"exit_code"[[:space:]]*:[[:space:]]*0' \
  || fail "expected exit_code=0; got: $resp_true"
pass "true ⇒ SUCCEEDED (exit_code=0)"

# 2) כישלון: exit 2
echo "[2] POST /agent/shell (exit 2) ..."
resp_fail=$(curl -sS -X POST "${BASE_URL}/agent/shell" \
  -H "content-type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  --data '{"cmd":"bash -lc '\''exit 2'\''"}' || true)

echo "$resp_fail" | grep -qi '"status"[[:space:]]*:[[:space:]]*"FAILED"' \
  || fail "expected status=FAILED; got: $resp_fail"
echo "$resp_fail" | grep -qi '"exit_code"[[:space:]]*:[[:space:]]*2' \
  || fail "expected exit_code=2; got: $resp_fail"
pass "exit 2 ⇒ FAILED (exit_code=2)"

# 3) לוג אפליקציה (אופציונלי): אין Tracebacks
LOG_FILE="${LOG_FILE:-.api.log}"
if [[ -f "$LOG_FILE" ]]; then
  echo "[3] Checking ${LOG_FILE} for tracebacks ..."
  if grep -qi "traceback" "$LOG_FILE"; then
    fail "Traceback found in ${LOG_FILE}"
  fi
  pass "${LOG_FILE} clean (no Traceback)"
else
  echo "(info) ${LOG_FILE} not found; דלגנו על בדיקת לוג."
fi

echo "== Chapter 5: ALL CHECKS PASS =="
