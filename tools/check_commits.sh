#!/usr/bin/env bash
# Check out each commit in a range and run the tests and the lint there, then return to the branch you were on.
# Usage: bash tools/check_commits.sh [range]   (default: every commit on the current branch)
# Needs a clean working tree; ignored files (.venv, .local, the OCR model) stay in place across checkouts.
set -uo pipefail
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain)" ]; then
	echo "commit or stash your changes first" >&2
	exit 1
fi
branch="$(git rev-parse --abbrev-ref HEAD)"
range="${1:-$branch}"
trap 'git checkout -q "$branch"' EXIT
for sha in $(git rev-list --reverse "$range"); do
	git checkout -q "$sha"
	tests="$(uv run --no-sync python -m pytest -q -p no:cacheprovider 2>&1 | tail -1)"
	code=$?
	uv run --no-sync ruff check -q . > /dev/null 2>&1 && lint=ok || lint=FAIL
	printf '%s | %s | lint %s\n' "$(git log --oneline -1 | cut -c1-60)" "$tests" "$lint"
done
