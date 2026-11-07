#!/usr/bin/env bash
# One-off: replace the wrong author ("Milan") on commit 6bb5a7a (1.4.1) with the repo owner.
# Run from Git Bash inside the repo folder:  bash fix-author.sh
# Nothing is pushed until you type YES at the prompt. Delete this file afterwards.
set -euo pipefail

BAD=6bb5a7a5f442f2e9fc0eaa2b4386b32492c5354b
NAME="Sabljarevic"
EMAIL="sabljarevic@protonmail.com"
BRANCH=main

cd "$(dirname "$0")"

echo "== 1/6 Sanity checks"
git rev-parse --git-dir >/dev/null
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "Not on $BRANCH. Abort."; exit 1; }
git cat-file -e "$BAD^{commit}" || { echo "Commit $BAD not found. Abort."; exit 1; }
echo "Target commit author now: $(git log -1 --format='%an <%ae>' "$BAD")"

# Make sure this repo commits as the owner (repo-local only).
if [ "$(git config user.name || true)" != "$NAME" ]; then git config user.name "$NAME"; fi
if [ "$(git config user.email || true)" != "$EMAIL" ]; then git config user.email "$EMAIL"; fi
echo "Committing as: $(git config user.name) <$(git config user.email)>"

echo "== 2/6 Make sure local $BRANCH is not behind GitHub"
git fetch origin
git merge-base --is-ancestor "origin/$BRANCH" "$BRANCH" || {
  echo "origin/$BRANCH has commits you don't have locally. Run: git pull --rebase origin $BRANCH  and re-run this script."
  exit 1
}

echo "== 3/6 Commit the CLAUDE.md change (if any)"
if ! git diff --quiet -- CLAUDE.md; then
  git add CLAUDE.md
  git commit -m "Add git identity rule to CLAUDE.md" \
             -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01S41QWwv5zzv2cHoLzeXeba"
else
  echo "CLAUDE.md has no uncommitted changes."
fi
if ! git diff --quiet; then
  echo "You have other uncommitted changes to tracked files. Commit or stash them first. Abort."
  exit 1
fi

echo "== 4/6 Backup (mirror clone next to the repo folder)"
BACKUP="../Sablja-backup-$(date +%Y%m%d-%H%M%S).git"
git clone --mirror . "$BACKUP"
echo "Backup: $BACKUP"

echo "== 5/6 Rewrite the author on $BAD (branch $BRANCH only, tags untouched)"
export FILTER_BRANCH_SQUELCH_WARNING=1
export BAD NAME EMAIL
git filter-branch -f --env-filter '
if [ "$GIT_COMMIT" = "$BAD" ]; then
  export GIT_AUTHOR_NAME="$NAME"
  export GIT_AUTHOR_EMAIL="$EMAIL"
  export GIT_COMMITTER_NAME="$NAME"
  export GIT_COMMITTER_EMAIL="$EMAIL"
fi' -- "$BRANCH"

echo "Remaining 'milan' commits on $BRANCH (should be none):"
if git log "$BRANCH" --format='%h %an <%ae>' | grep -i milan; then
  echo "Milan is still in the history. NOT pushing."; exit 1
else
  echo "none"
fi
echo "Last 5 commits:"
git log "$BRANCH" -5 --format='  %h %an  %s'

echo "== 6/6 Force-push $BRANCH to GitHub"
read -r -p "Type YES to force-push $BRANCH (backup is at $BACKUP): " ANS
if [ "$ANS" = "YES" ]; then
  git push --force-with-lease origin "$BRANCH"
  echo "Done. GitHub's contributors list can take up to a day to update."
else
  echo "Not pushed. Your local repo is rewritten; the backup is at $BACKUP."
fi
