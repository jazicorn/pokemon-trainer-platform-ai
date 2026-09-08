#!/usr/bin/env bash
# Manually run a release from the console, mirroring what .github/workflows/release.yml
# does in CI. Use this if the automated release never fired (e.g. release.yml itself
# failed or was skipped) and you don't want to wait on a push to main to retrigger it.
#
# What it does, in order:
#   1. Refuses to run on a dirty tree or off `main`.
#   2. Runs `cz bump` to compute the next version from Conventional Commits since the
#      last tag, update pyproject.toml, and create the release commit + tag.
#   3. Regenerates uv.lock so it matches the bumped version (cz bump doesn't touch it —
#      see release.yml's "Sync uv.lock" step for why this matters) and folds it into the
#      same commit, moving the tag to match.
#   4. Pushes the branch, then the tag, EXPLICITLY BY NAME.
#
# That last point is deliberate, not a style choice: `git push --follow-tags` only
# pushes *annotated* tags, and `cz bump` creates lightweight ones by default (cz.toml
# doesn't set annotated_tag). `--follow-tags` silently no-ops on a lightweight tag —
# exit 0, nothing pushed — which is exactly how a real release here once landed the
# version-bump commit on main but never pushed the tag, so image-publish.yml (which
# only triggers on a pushed `v*` tag) never ran and no Docker image was built.
#
# Usage:
#   ./scripts/release.sh          # bump + tag + push
#   ./scripts/release.sh --dry-run  # show what would happen, change nothing

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "main" ]]; then
  echo "error: releases are cut from main, but you're on '$branch'." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is dirty. Commit or stash your changes first." >&2
  git status --short >&2
  exit 1
fi

echo "Fetching latest from origin/main..."
git fetch origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "error: local main is not up to date with origin/main. Run 'git pull' first." >&2
  exit 1
fi

if $DRY_RUN; then
  echo "--- dry run: showing what cz bump would do (no changes made) ---"
  uv run cz bump --dry-run
  exit 0
fi

echo "Running cz bump..."
set +e
uv run cz bump --yes
status=$?
set -e

case $status in
  0)
    echo "Bump succeeded."
    ;;
  3 | 21)
    # 3  = NoCommitsFoundError (no commits since the last tag)
    # 21 = NoneIncrementExit (commits exist, but none warrant a bump)
    echo "No commits warrant a release. Nothing to do."
    exit 0
    ;;
  *)
    echo "error: cz bump failed with exit code $status." >&2
    exit "$status"
    ;;
esac

echo "Syncing uv.lock with the bumped version..."
uv lock
if ! git diff --quiet -- uv.lock; then
  git add uv.lock
  git commit --amend --no-edit
  tag=$(git describe --tags --abbrev=0)
  git tag -f "$tag" HEAD
fi

tag=$(git describe --tags --abbrev=0)
echo
echo "Ready to push:"
echo "  branch: main -> origin/main"
echo "  tag:    $tag -> origin/$tag"
read -r -p "Push now? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Not pushed. Your local main and tag are ready — push manually when you're ready:"
  echo "  git push origin main"
  echo "  git push origin $tag"
  exit 0
fi

git push origin main
git push origin "$tag"
echo "Pushed $tag. image-publish.yml should now build and push the GHCR image."
