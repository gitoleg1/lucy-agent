#!/usr/bin/env bash
set -euo pipefail

API="http://127.0.0.1:8000"
TOKEN="${TOKEN:-supersecret}"

say() { printf "%s\n" "────────────────────────────────────────"; echo "$@"; }

wait_health() {
  for i in {1..100}; do
    if curl -sf "$API/health" >/dev/null; then
      echo "✅ health OK"
      return 0
    fi
    sleep 0.2
  done
  echo "❌ health check timed out"; exit 1
}

post() {
  local body="$1"
  shift || true
  curl -sS -H 'Content-Type: application/json' -H "X-API-Key: $TOKEN" -X POST "$API/tasks/agent/shell" -d "$body" "$@"
}

echo "=== 0) Clean boot & wait health ==="
wait_health

say "=== 1) Happy path — echo ok && true ==="
out="$(post '{"cmd":"echo ok && true"}')"
status=$(jq -r '.task.status' <<<"$out")
rc=$(jq -r '.runs[0].exit_code' <<<"$out")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo "✅ happy path ok"
else
  echo "❌ happy path failed"; echo "$out"; exit 1
fi

say "=== 2) Blocked command — rm -rf / (deny/allow policy) ==="
code=$(curl -sS -o /tmp/policy_out.json -w "%{http_code}" \
  -H 'Content-Type: application/json' -H "X-API-Key: $TOKEN" \
  -X POST "$API/tasks/agent/shell" -d '{"cmd":"rm -rf /"}')
if [[ "$code" != "400" && "$code" != "403" ]]; then
  echo "❌ expected 400/403 for dangerous command, got $code"; cat /tmp/policy_out.json; exit 1
fi
if ! jq -e '.detail|test("denylist|allowlist")' </tmp/policy_out.json >/dev/null; then
  echo "❌ policy response missing keyword"; cat /tmp/policy_out.json; exit 1
fi
echo "✅ dangerous command blocked by policy"

say "=== 3) Allowlist — allow only \"echo\" (server env) ==="
out="$(post '{"cmd":"echo allowed && true"}')"
status=$(jq -r '.task.status' <<<"$out"); rc=$(jq -r '.runs[0].exit_code' <<<"$out")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo "✅ allowlist allows echo"
else
  echo "❌ allowlist echo failed"; echo "$out"; exit 1
fi

code=$(curl -sS -o /tmp/ua_out.json -w "%{http_code}" \
  -H 'Content-Type: application/json' -H "X-API-Key: $TOKEN" \
  -X POST "$API/tasks/agent/shell" -d '{"cmd":"uname -a"}')
if [[ "$code" != "400" && "$code" != "403" ]]; then
  echo "❌ allowlist expected 400/403 for uname, got $code"; cat /tmp/ua_out.json; exit 1
fi
if ! jq -e '.detail|test("allowlist")' </tmp/ua_out.json >/dev/null; then
  echo "❌ allowlist response missing keyword"; cat /tmp/ua_out.json; exit 1
fi
echo "✅ allowlist blocks uname"

say "=== 4) Timeout — expect FAILED/124/timeout=true ==="
# חשוב: לשמור על allowlist=echo, לכן מריצים echo ואז sleep
sleep 1  # להימנע מ-429
out="$(post '{"cmd":"echo start; sleep 5; echo end"}')"
status=$(jq -r '.task.status' <<<"$out")
rc=$(jq -r '.runs[0].exit_code' <<<"$out")
timeout_flag=$(jq -r '.audit[-1].data.timeout' <<<"$out")
stdout_t=$(jq -r '(.audit[-1].data.stdout_tail|type?)' <<<"$out")
stderr_t=$(jq -r '(.audit[-1].data.stderr_tail|type?)' <<<"$out")

echo "status=$status rc=$rc timeout=$timeout_flag stdout_type=$stdout_t stderr_type=$stderr_t"

if [[ "$status" != "FAILED" || "$rc" != "124" || "$timeout_flag" != "true" || "$stdout_t" != "string" || "$stderr_t" != "string" ]]; then
  echo "❌ timeout semantics wrong"; echo "$out"; exit 1
fi
echo "✅ timeout semantics correct"

say "=== 5) API Key checks ==="
code=$(curl -sS -o /tmp/unauth.json -w "%{http_code}" -H 'Content-Type: application/json' \
  -X POST "$API/tasks/agent/shell" -d '{"cmd":"echo ok && true"}')
if [[ "$code" != "401" && "$code" != "403" ]]; then
  echo "❌ auth: expected 401/403 without token, got $code"; cat /tmp/unauth.json; exit 1
fi
echo "✅ auth rejects without key (401/403)"

out="$(post '{"cmd":"echo ok && true"}')"
status=$(jq -r '.task.status' <<<"$out"); rc=$(jq -r '.runs[0].exit_code' <<<"$out")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo "✅ auth passes with valid key"
else
  echo "❌ auth with key failed"; echo "$out"; exit 1
fi

say "🎉 ALL CHECKS PASSED"
