#!/bin/sh
# Adds the Crucible loop files to a repository without overwriting existing ones.
# Usage: scripts/install.sh /path/to/repo
set -eu
repo="${1:?usage: install.sh /path/to/repo}"
here="$(cd "$(dirname "$0")/.." && pwd)"
copy() {
  src="$here/templates/repo/$1"; dst="$repo/$1"
  if [ -e "$dst" ]; then echo "skip   $1 (exists)"; return; fi
  mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; echo "added  $1"
}
copy .github/workflows/crucible-loop.yml
copy .factory/settings.json
mkdir -p "$repo/specs"
if [ -f "$repo/AGENTS.md" ] && grep -q '^## Loop contract' "$repo/AGENTS.md"; then
  echo "skip   AGENTS.md loop contract (exists)"
else
  echo "todo   append templates/repo/AGENTS.loop-contract.md to AGENTS.md and adjust the commands"
fi
