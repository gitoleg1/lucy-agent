#!/usr/bin/env bash
set -euo pipefail

# טוען משתני סביבה מה-.env אם קיים
export $(grep -v '^#' .env | xargs -d '\n' -I{} echo {}) 2>/dev/null || true

# מבטיח ש-src יהיה על ה-PYTHONPATH (לייבוא lucy_agent)
export PYTHONPATH="src:${PYTHONPATH:-}"

poetry run uvicorn lucy_agent.main:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
