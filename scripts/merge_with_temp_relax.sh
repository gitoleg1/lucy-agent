#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# merge_with_temp_relax.sh
# מיזוג PR עם "הקלה זמנית" על הגנות הסניף ואז החזרתן להגדרות המחמירות.
# עובד עם GitHub CLI (gh) ומדווח לוגים ברורים.
# ------------------------------------------------------------

OWNER=""
REPO=""
PR=""
KEEP_CI=1                    # במצב הקלה – להשאיר בדיקת CI (ברירת מחדל: כן)
MERGE_METHOD="--squash"      # אפשר --merge או --rebase
DELETE_BRANCH="--delete-branch"

usage() {
  cat <<'EOF'
שימוש:
  ./merge_with_temp_relax.sh -p <PR_NUMBER> [-o <owner>] [-r <repo>] [--no-keep-ci] [--merge|--rebase] [--no-delete-branch]

דגלים:
  -p, --pr               מספר ה-PR (חובה)
  -o, --owner            בעל הריפו (ברירת מחדל: זיהוי אוטומטי מה-remote)
  -r, --repo             שם הריפו (ברירת מחדל: זיהוי אוטומטי מה-remote)
      --no-keep-ci       בהקלה – להסיר גם את דרישת ה-CI (לא מומלץ)
      --merge            מיזוג merge-commit במקום squash
      --rebase           מיזוג rebase במקום squash
      --no-delete-branch לא למחוק את סניף ה-PR לאחר המיזוג
  -h, --help             עזרה
EOF
}

# ---------- ניתוח ארגומנטים ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--pr) PR="${2:-}"; shift 2;;
    -o|--owner) OWNER="${2:-}"; shift 2;;
    -r|--repo) REPO="${2:-}"; shift 2;;
    --no-keep-ci) KEEP_CI=0; shift;;
    --merge) MERGE_METHOD="--merge"; shift;;
    --rebase) MERGE_METHOD="--rebase"; shift;;
    --no-delete-branch) DELETE_BRANCH=""; shift;;
    -h|--help) usage; exit 0;;
    *) echo "❌ ארגומנט לא מוכר: $1"; usage; exit 2;;
  esac
done

if [[ -z "${PR:-}" ]]; then
  echo "❌ שגיאה: חובה לציין מספר PR עם ‎-p‎/‎--pr‎"
  usage
  exit 2
fi

# ---------- זיהוי owner/repo מה-remote במקרה ולא נמסרו ----------
if [[ -z "${OWNER:-}" || -z "${REPO:-}" ]]; then
  if ! remote_url=$(git remote get-url origin 2>/dev/null); then
    echo "❌ לא ניתן לזהות remote 'origin' (האם זה ריפו git תקין?)"
    exit 2
  fi
  if [[ "$remote_url" =~ github\.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${OWNER:-${BASH_REMATCH[1]}}"
    REPO="${REPO:-${BASH_REMATCH[2]}}"
  else
    echo "❌ לא הצלחתי לפרש owner/repo מתוך ה-remote: $remote_url"
    exit 2
  fi
fi

echo "ℹ️  ריפו: $OWNER/$REPO | PR: #$PR"
echo "ℹ️  שיטת מיזוג: $MERGE_METHOD | מחיקת סניף אחרי מיזוג: ${DELETE_BRANCH:-לא}"

# ---------- ולידציה של gh ----------
if ! gh auth status >/dev/null 2>&1; then
  echo "❌ GitHub CLI (gh) לא מחובר. הרץ: gh auth login"
  exit 1
fi

# ---------- גיבוי קונפיג הגנות נוכחי (לא חובה לשחזור, אבל שימושי ללוגים) ----------
PROT_BACKUP="$(mktemp /tmp/protection.XXXX.json)"
echo "📥 מגבה קונפיג הגנת הסניף הנוכחי ל-$PROT_BACKUP (לוג/מידע)..."
gh api "/repos/$OWNER/$REPO/branches/main/protection" > "$PROT_BACKUP" 2>/dev/null || true

# ---------- הקלה זמנית בהגנת main ----------
echo "🛠️  מפעיל הקלה זמנית על הגנת main..."
if [[ $KEEP_CI -eq 1 ]]; then
  CHECKS='"checks":[{"context":"CI"}]'
  echo "   • נשמרת דרישת CI בזמן ההקלה."
else
  CHECKS='"checks":[]'
  echo "   • הסרת דרישת CI בזמן ההקלה (לא מומלץ)."
fi

RELAX_JSON=$(cat <<EOF
{
  "required_status_checks": { "strict": true, $CHECKS },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 0,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false
}
EOF
)

echo "$RELAX_JSON" | gh api -X PUT -H "Accept: application/vnd.github+json" \
  "/repos/$OWNER/$REPO/branches/main/protection" --input -

# ---------- מיזוג ה-PR ----------
echo "🔀 מבצע מיזוג של PR #$PR ..."
set +e
if [[ -n "$DELETE_BRANCH" ]]; then
  gh pr merge "$PR" "$MERGE_METHOD" "$DELETE_BRANCH" --repo "$OWNER/$REPO"
  MERGE_RC=$?
else
  gh pr merge "$PR" "$MERGE_METHOD" --repo "$OWNER/$REPO"
  MERGE_RC=$?
fi
set -e

# ---------- החזרת ההגנות למחמירות ----------
echo "🛡️  מחזיר הגנות סניף להגדרות המחמירות..."
STRICT_JSON=$(cat <<'EOF'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "CI" } ] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false
}
EOF
)

echo "$STRICT_JSON" | gh api -X PUT -H "Accept: application/vnd.github+json" \
  "/repos/$OWNER/$REPO/branches/main/protection" --input -

# ---------- וידוא סטטוס מיזוג + הצגת קונפיג הגנות ----------
echo "🔎 בדיקת סטטוס ה-PR וקונפיג ההגנות לאחר הפעולה:"
gh pr view "$PR" --json state,mergedAt,mergeCommit --jq '{state,mergedAt,mergeCommit:(.mergeCommit|try .oid)}' --repo "$OWNER/$REPO" || true
gh api "/repos/$OWNER/$REPO/branches/main/protection" --jq \
'{strict:.required_status_checks.strict,
  checks:[.required_status_checks.checks[].context],
  require_code_owner_reviews:.required_pull_request_reviews.require_code_owner_reviews,
  required_approving_review_count:.required_pull_request_reviews.required_approving_review_count}'

# ---------- תוצאת ריצה ----------
if [[ "$MERGE_RC" -ne 0 ]]; then
  echo "❌ המיזוג נכשל (קוד=$MERGE_RC). ההגנות כבר הוחזרו למחמירות."
  exit "$MERGE_RC"
else
  echo "✅ ה-PR מוזג וההגנות הוחזרו למחמירות. סיום ✔"
fi
