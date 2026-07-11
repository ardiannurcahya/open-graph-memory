#!/bin/sh
set -eu

files=$(git ls-files --cached --others --exclude-standard)
if printf '%s\n' "$files" | grep -E '(^|/)\.env$|\.tsbuildinfo$|apps/web/vite\.config\.(js|d\.ts)$'; then
  echo "secret or generated artifact detected" >&2
  exit 1
fi

# Scan tracked and untracked text files, excluding this script's own signatures.
for file in $files; do
  [ "$file" = "scripts/security-gate.sh" ] && continue
  [ -f "$file" ] || continue
  if grep -InE '(ghp_|github_pat_|AKIA[0-9A-Z]{16})' "$file"; then
    echo "credential-shaped value detected" >&2
    exit 1
  fi
done
