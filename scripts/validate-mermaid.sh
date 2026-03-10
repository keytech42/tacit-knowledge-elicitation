#!/usr/bin/env bash
# Validate all mermaid code blocks in markdown files.
# Exits non-zero if any diagram has a syntax error.
#
# Usage: ./scripts/validate-mermaid.sh [file ...]
# If no files given, scans all *.md files in the repo.

set -euo pipefail

if ! command -v mmdc &>/dev/null; then
  echo "Installing @mermaid-js/mermaid-cli..."
  npm install -g @mermaid-js/mermaid-cli
fi

# Collect target files
if [ $# -gt 0 ]; then
  files=("$@")
else
  mapfile -t files < <(find . -name '*.md' -not -path './.claude/*' -not -path './.git/*' -not -path '*/.pytest_cache/*' -not -path '*/node_modules/*')
fi

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

# Puppeteer config for headless CI environments (no sandbox needed on GH Actions)
cat > "$tmpdir/puppeteer.json" <<'PCONF'
{
  "headless": "new",
  "args": ["--no-sandbox", "--disable-setuid-sandbox"]
}
PCONF

errors=0

for file in "${files[@]}"; do
  # Extract mermaid blocks with awk: each block gets its own temp file
  block_idx=0
  in_block=false
  block_file=""

  while IFS= read -r line; do
    if [[ "$line" =~ ^\`\`\`mermaid ]]; then
      in_block=true
      block_file="$tmpdir/$(basename "$file" .md)_${block_idx}.mmd"
      : > "$block_file"
      continue
    fi

    if $in_block && [[ "$line" =~ ^\`\`\` ]]; then
      in_block=false

      if [ -s "$block_file" ]; then
        if ! mmdc -i "$block_file" -o "$tmpdir/out.svg" --quiet -p "$tmpdir/puppeteer.json" 2>/dev/null; then
          echo "FAIL: $file (mermaid block #$((block_idx + 1)))"
          errors=$((errors + 1))
        else
          echo "  OK: $file (block #$((block_idx + 1)))"
        fi
      fi

      block_idx=$((block_idx + 1))
      continue
    fi

    if $in_block; then
      echo "$line" >> "$block_file"
    fi
  done < "$file"
done

if [ $errors -gt 0 ]; then
  echo ""
  echo "$errors mermaid diagram(s) failed validation."
  exit 1
fi

echo ""
echo "All mermaid diagrams valid."
