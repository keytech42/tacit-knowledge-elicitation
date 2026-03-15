#!/usr/bin/env bash
# Project self-review gate — checks backend/frontend/worker test coverage.
# Fires on Stop event. Blocks (exit 2) when source changed without test updates.
set -euo pipefail

input=$(cat)

# Prevent infinite loop on re-check
echo "$input" | grep -qE '"stop_hook_active"\s*:\s*true' && exit 0

# Collect both uncommitted changes and last commit (Claude often commits before stopping)
uncommitted=$(git diff --name-only 2>/dev/null || true)
last_commit=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || true)
changed=$(printf '%s\n%s' "$uncommitted" "$last_commit" | sort -u | sed '/^$/d')
[ -z "$changed" ] && exit 0

gaps=""

# Backend source without backend tests
be_src=$(echo "$changed" | grep -E '^backend/app/' || true)
be_test=$(echo "$changed" | grep -E '^backend/tests/' || true)
[ -n "$be_src" ] && [ -z "$be_test" ] && gaps="${gaps}  - backend/app/ changed without backend/tests/ updates\n"

# Frontend source without E2E or spec tests
fe_src=$(echo "$changed" | grep -E '^frontend/src/' | grep -vE '\.spec\.|\.test\.' || true)
fe_test=$(echo "$changed" | grep -E '(^frontend/e2e/|\.spec\.|\.test\.)' || true)
[ -n "$fe_src" ] && [ -z "$fe_test" ] && gaps="${gaps}  - frontend/src/ changed without E2E/spec test updates\n"

# Worker source without tests
wk_src=$(echo "$changed" | grep -E '^worker/' | grep -vE '/tests/' || true)
wk_test=$(echo "$changed" | grep -E '^worker/.*tests/' || true)
[ -n "$wk_src" ] && [ -z "$wk_test" ] && gaps="${gaps}  - worker/ changed without test updates\n"

if [ -n "$gaps" ]; then
  echo "Project self-review — potential test gaps:" >&2
  echo -e "$gaps" >&2
  echo "Verify: docker compose exec api pytest -xvs" >&2
  echo "Type-check: docker compose exec web npx tsc -b --noEmit" >&2
  exit 2
fi

exit 0
