#!/usr/bin/env bash
# Project PR preparation reminder — injects context before gh pr create.
# Fires on PreToolUse (Bash). Only activates when command contains "gh pr create".

input=$(cat)
echo "$input" | grep -q 'gh pr create' || exit 0

cat <<'EOF'
{"hookSpecificOutput":{"additionalContext":"PR checklist: 1) Verify tests pass: docker compose exec api pytest -xvs. 2) Verify types: docker compose exec web npx tsc -b --noEmit. 3) After creating, consider adding PR comments for design rationale, maintenance notes, or testing instructions — only if not redundant with the PR body."}}
EOF
exit 0
