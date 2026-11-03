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
copy .factory/loop-contract.md
if [ ! -d "$repo/specs" ]; then
  mkdir -p "$repo/specs"
  printf '# Specs\n\nProject specs for this repo. Process and template: crucibledx/hq specs/README.md.\n' > "$repo/specs/README.md"
  echo "added  specs/README.md"
fi
echo "todo   edit .factory/loop-contract.md with this repo's real commands"
