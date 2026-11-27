#!/bin/sh
# Runs every factory-loop check. CI's `checks` job (.github/workflows/self-checks.yml) runs this same script, so a
# check added here runs in both places. Needs python3, git and actionlint on PATH.
set -u
cd "$(dirname "$0")/.." || exit 1

status=0
step() {
  printf '\n== %s\n' "$*"
  if ! "$@"; then
    echo "FAILED: $*" >&2
    status=1
  fi
}

json_valid() {
  python3 - <<'PY'
import json, subprocess, sys

files = [f for f in subprocess.run(["git", "ls-files", "-z", "*.json"], capture_output=True, check=True)
         .stdout.decode().split("\0") if f]
bad = 0
for name in files:
    try:
        with open(name, encoding="utf-8") as fh:
            json.load(fh)
    except (OSError, ValueError) as err:
        print(f"{name}: {err}", file=sys.stderr)
        bad = 1
print(f"{len(files)} JSON files checked")
sys.exit(bad)
PY
}

# Every scripts/test-* runs, so a new test needs no edit here.
found=0
for test in scripts/test-*; do
  [ -e "$test" ] || continue
  found=1
  case "$test" in
    *.py) step python3 "$test" ;;
    *.sh) step sh "$test" ;;
    *) echo "FAILED: $test: no runner for this extension (use .py or .sh)" >&2; status=1 ;;
  esac
done
[ "$found" = 1 ] || { echo "FAILED: no scripts/test-* found" >&2; status=1; }

if command -v actionlint >/dev/null 2>&1; then
  step actionlint .github/workflows/*.yml templates/repo/.github/workflows/*.yml
else
  echo "FAILED: actionlint is not on PATH (CI pins the version in .github/workflows/self-checks.yml)" >&2
  status=1
fi

step json_valid

[ "$status" = 0 ] && printf '\nAll checks passed.\n'
exit "$status"
