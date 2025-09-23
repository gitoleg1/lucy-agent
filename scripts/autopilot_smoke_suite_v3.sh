#!/usr/bin/env bash
set -euo pipefail

# ── קונפיג בסיסי ────────────────────────────────────────────────────────────────
API="http://127.0.0.1:8000"
JSON='-H Content-Type: application/json'

# אם יש קובץ סביבה מקומי – טען אותו (לא חובה)
[ -f "$HOME/projects/lucy-agent/.env.autopilot" ] && set -a && . "$HOME/projects/lucy-agent/.env.autopilot" && set +a

# נדרוש מפתח אם השירות אוכף אותו
AUTH_HEADER=()
if [[ -n "${LUCY_AUTOPILOT_TOKEN-}" ]]; then
  AUTH_HEADER=(-H "X-API-Key: ${LUCY_AUTOPILOT_TOKEN}")
else
  echo "⚠️  לא הוגדר LUCY_AUTOPILOT_TOKEN. אם השירות אוכף מפתח, הבדיקות ייכשלו ב-401."
fi

# פונקציית עזר ל-curl עם כותרות
curlj() { curl -sS -X POST "$API$1" "${AUTH_HEADER[@]}" $JSON -d "$2"; }

line() { printf '%s\n' "────────────────────────────────────────"; }

# ── 0) אתחול נקי ────────────────────────────────────────────────────────────────
echo "=== 0) Clean boot & base env ==="
systemctl --user restart lucy-agent.service >/dev/null 2>&1 || true
sleep 1
pid=$(systemctl --user show -p MainPID --value lucy-agent.service)
echo " $pid✅ clean boot"
line

# ── 1) Happy path ───────────────────────────────────────────────────────────────
echo "=== 1) Happy path — echo ok && true ==="
resp=$(curlj /tasks/agent/shell '{"cmd":"echo ok && true"}' || true)
status=$(jq -r '.task.status // "null"' <<<"$resp")
rc=$(jq -r '.runs[0].exit_code // "null"' <<<"$resp")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo "✅ happy path ok"
else
  echo "❌ happy path failed: status=$status rc=$rc"
  echo "$resp"
  exit 1
fi
line
sleep 1

# ── 2) Denylist ────────────────────────────────────────────────────────────────
echo "=== 2) Denylist — rm -rf / => 400 ==="
hdr=$(curl -i -sS -X POST "$API/tasks/agent/shell" "${AUTH_HEADER[@]}" $JSON \
  -d '{"cmd":"rm -rf /"}' | sed -n '1p')
echo "$hdr"
if grep -q " 400 " <<<"$hdr"; then
  echo "✅ denylist blocks rm -rf /"
else
  echo "❌ denylist expected 400"
  exit 1
fi
line
sleep 1

# ── 3) Allowlist ────────────────────────────────────────────────────────────────
echo '=== 3) Allowlist — allow only "echo" ==='
export LUCY_AUTOPILOT_ALLOW='echo'
systemctl --user restart lucy-agent.service >/dev/null
sleep 1

resp=$(curlj /tasks/agent/shell '{"cmd":"echo allowed && true"}' || true)
status=$(jq -r '.task.status // "null"' <<<"$resp")
rc=$(jq -r '.runs[0].exit_code // "null"' <<<"$resp")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo " $pid✅ allowlist allows echo"
else
  echo "❌ allowlist should allow echo"; echo "$resp"; exit 1
fi

hdr=$(curl -i -sS -X POST "$API/tasks/agent/shell" "${AUTH_HEADER[@]}" $JSON \
  -d '{"cmd":"uname -a"}' | sed -n '1p')
if grep -q " 400 " <<<"$hdr"; then
  echo "✅ allowlist blocks uname"
else
  echo "❌ allowlist blocks uname (got $(echo "$hdr" | awk '{print $2}'), expected 400)"; exit 1
fi
line
sleep 1

# ── 4) Timeout ─────────────────────────────────────────────────────────────────
echo "=== 4) Timeout — expect FAILED, exit=124, timeout=true, tails are strings ==="
export LUCY_AUTOPILOT_TIMEOUT_SECONDS=1
export LUCY_AUTOPILOT_TIMEOUT_EXIT=124
systemctl --user restart lucy-agent.service >/dev/null
sleep 1

resp=$(curlj /tasks/agent/shell '{"cmd":"sleep 5"}' || true)
status=$(jq -r '.task.status // "null"' <<<"$resp")
rc=$(jq -r '.runs[0].exit_code // "null"' <<<"$resp")
timeout=$(jq -r '.audit[-1].data.timeout // "null"' <<<"$resp")
stt=$(jq -r '(.audit[-1].data.stdout_tail|type) // "null"' <<<"$resp")
sett=$(jq -r '(.audit[-1].data.stderr_tail|type) // "null"' <<<"$resp")
echo " $pidstatus=$status rc=$rc timeout=$timeout stdout_type=$stt stderr_type=$sett"
if [[ "$status" == "FAILED" && "$rc" == "124" && "$timeout" == "true" && "$stt" == "string" && "$sett" == "string" ]]; then
  echo "✅ timeout semantics correct"
else
  echo "❌ timeout semantics wrong"; echo "$resp"; exit 1
fi
line
sleep 1

# ── 5) API Key ─────────────────────────────────────────────────────────────────
echo "=== 5) API Key — missing => 401/403, with key => 200 ==="
# בלי מפתח
hdr=$(curl -i -sS -X POST "$API/tasks/agent/shell" $JSON -d '{"cmd":"echo ok && true"}' | sed -n '1p')
code=$(awk '{print $2}' <<<"$hdr")
if [[ "$code" == "401" || "$code" == "403" ]]; then
  echo " $pid✅ auth rejects without key ($code)"
else
  echo "❌ auth: expected 401/403 without token (got $code)"; exit 1
fi

# עם מפתח
resp=$(curlj /tasks/agent/shell '{"cmd":"echo ok && true"}' || true)
status=$(jq -r '.task.status // "null"' <<<"$resp")
rc=$(jq -r '.runs[0].exit_code // "null"' <<<"$resp")
if [[ "$status" == "SUCCEEDED" && "$rc" == "0" ]]; then
  echo "✅ auth passes with valid key"
else
  echo "❌ auth failed with key"; echo "$resp"; exit 1
fi
line
echo "🎉 ALL CHECKS PASSED"
