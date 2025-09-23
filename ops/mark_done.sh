#!/usr/bin/env bash
set -euo pipefail

# איפה ה-SPEC (אפשר לשנות זמנית בהרצה עם: SPEC_PATH=/path/to/AGENT_SPEC.md done ...)
SPEC="${SPEC_PATH:-$HOME/projects/lucy-agent/AGENT_SPEC.md}"

usage() {
  cat <<'EOF'
שימוש:
  done "מזהה-או-כותרת"     # מסמן סעיף כבוצע (V)
  done status               # מציג מצב/אחוזים ו-5 המשימות הבאות
  done list                 # מציג רשימות מלאות: DONE ו-TODO
EOF
}

if [[ ! -f "$SPEC" ]]; then
  echo "ERROR: קובץ SPEC לא קיים: $SPEC"
  exit 2
fi

cmd="${1:-}"
if [[ -z "$cmd" ]]; then
  usage; exit 1
fi

status_view() {
  total=$(grep -E '^\s*-\s*\[[ xX]\]' -c "$SPEC" || true)
  donec=$(grep -Ei '^\s*-\s*\[[x]\]'   -c "$SPEC" || true)
  todoc=$(( total - donec ))
  percent=0
  [[ $total -gt 0 ]] && percent=$(( donec * 100 / total ))

  echo "📊 התקדמות: $donec/$total  (${percent}%)"
  echo

  echo "🔜 5 הבאות בתור:"
  # מציג את 5 ה-TODO הראשונות (מנקה את ה-[ ] ומשאיר את הטקסט)
  grep -E '^\s*-\s*\[\s\]\s' "$SPEC" \
    | sed -E 's/^\s*-\s*\[\s\]\s*//' \
    | head -n 5 \
    || true
}

list_view() {
  echo "✅ DONE:"
  grep -Ei '^\s*-\s*\[x\]\s' "$SPEC" \
    | sed -E 's/^\s*-\s*\[x\]\s*//' || true
  echo
  echo "📝 TODO:"
  grep -E '^\s*-\s*\[\s\]\s' "$SPEC" \
    | sed -E 's/^\s*-\s*\[\s\]\s*//' || true
}

mark_done() {
  local Q="$1"
  local changed=0
  # מסמן את ההתאמה הראשונה (case-insensitive) אם עדיין לא מסומן
  awk -v q="$Q" '
  BEGIN{IGNORECASE=1}
  {
    if (!changed && $0 ~ /^[[:space:]]*-\s*\[[[:space:]xX]\]\s/ && tolower($0) ~ tolower(q)) {
      if ($0 ~ /\[[xX]\]/) { print; changed=2; next }  # כבר מסומן
      gsub(/\[[[:space:]]\]/,"[x]")
      print
      changed=1
      next
    }
    print
  }
  END{ exit (changed==0?10:(changed==2?11:0)) }
  ' "$SPEC" > "${SPEC}.new" || rc=$?

  if [[ "${rc:-0}" -eq 10 ]]; then
    rm -f "${SPEC}.new"
    echo "לא נמצא סעיף שמתאים לחיפוש: \"$Q\""
    exit 3
  elif [[ "${rc:-0}" -eq 11 ]]; then
    rm -f "${SPEC}.new"
    echo "הסעיף המבוקש כבר מסומן כבוצע."
    status_view
    exit 0
  fi

  mv "${SPEC}.new" "$SPEC"

  # כותרת הסעיף שסומן
  title="$(grep -inE "^\s*-\s*\[[xX]\]\s.*${Q}.*" -m1 "$SPEC" \
           | sed -E 's/^[^:]*:\s*-\s*\[[xX]\]\s*//')"

  echo "✅ סומן כהושלם: ${title:-$Q}"
  echo
  status_view
}

case "$cmd" in
  status) status_view ;;
  list)   list_view   ;;
  -h|--help|help) usage ;;
  *)      mark_done "$cmd" ;;
esac
