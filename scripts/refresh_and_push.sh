#!/usr/bin/env sh
set -eu
PRIMARY_REMOTE="${PRIMARY_REMOTE:-primary}"
SECONDARY_REMOTE="${SECONDARY_REMOTE:-secondary}"
BRANCH="${BRANCH:-main}"
NO_PUSH="${NO_PUSH:-0}"

cd "$(dirname "$0")/.."

allowed_files='README.md
data/trending-ai.json
data/trending-archive.json'

python_bin="${PYTHON:-}"
if [ -z "$python_bin" ]; then
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  else
    python_bin="python"
  fi
fi

changed_paths() {
  git status --porcelain | sed -E 's/^.. //; s#\\#/#g'
}

is_allowed_path() {
  path="$1"
  printf '%s\n' "$allowed_files" | grep -Fxq "$path"
}

initial_changes="$(changed_paths)"
if [ -n "$initial_changes" ]; then
  printf 'Working tree is dirty before refresh. Commit or stash first:\n%s\n' "$initial_changes" >&2
  exit 1
fi

"$python_bin" scripts/update_trending.py --windows daily,weekly,monthly --limit 20 --archive-limit 50

changes="$(changed_paths)"
if [ -z "$changes" ]; then
  echo "No refresh changes to commit."
  exit 0
fi

unexpected=""
for path in $changes; do
  if ! is_allowed_path "$path"; then
    unexpected="${unexpected}${path}
"
  fi
done

if [ -n "$unexpected" ]; then
  printf 'Refresh changed unexpected files; not committing or pushing:\n%s\n' "$unexpected" >&2
  exit 1
fi

git add -- README.md data/trending-ai.json data/trending-archive.json

if git diff --cached --quiet; then
  echo "No staged refresh changes to commit."
  exit 0
fi

git commit -m "Refresh trending repos"

if [ "$NO_PUSH" = "1" ]; then
  echo "Committed refresh changes; push skipped because NO_PUSH=1."
  exit 0
fi

if ! git remote | grep -Fxq "$PRIMARY_REMOTE"; then
  echo "Missing git remote '$PRIMARY_REMOTE'. Add it before running this script." >&2
  exit 1
fi

if ! git remote | grep -Fxq "$SECONDARY_REMOTE"; then
  echo "Missing git remote '$SECONDARY_REMOTE'. Add it before running this script." >&2
  exit 1
fi

git push "$PRIMARY_REMOTE" "HEAD:$BRANCH"
git push "$SECONDARY_REMOTE" "HEAD:$BRANCH"

echo "Refresh pushed to configured remotes."
