#!/bin/sh
# Runs every factory-loop check. CI's `checks` job (.github/workflows/self-checks.yml) runs this same script, so a
# check added here runs in both places. Needs python3, git, actionlint and shellcheck on PATH.
set -u
cd "$(dirname "$0")/.." || exit 1

# Keep equal to VERSION in .github/workflows/self-checks.yml.
ACTIONLINT_VERSION=1.7.12

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
import json, os, subprocess, sys

try:
    listed = subprocess.run(["git", "ls-files", "-z", "*.json"], capture_output=True, check=True).stdout
except (OSError, subprocess.CalledProcessError):
    sys.exit("json_valid: git ls-files failed (run from a git checkout)")
files = [os.fsdecode(f) for f in listed.split(b"\0") if f]
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

# Every tracked scripts/test-* runs, so a new test needs no edit here. Untracked files (backups, scratch tests) are
# skipped, because CI's checkout doesn't have them either.
found=0
for test in scripts/test-*; do
  [ -e "$test" ] || continue
  git ls-files --error-unmatch -- "$test" >/dev/null 2>&1 || continue
  found=1
  case "$test" in
    *.py) step python3 "$test" ;;
    *.sh) step sh "$test" ;;
    *) echo "FAILED: $test: no runner for this extension (use .py or .sh)" >&2; status=1 ;;
  esac
done
[ "$found" = 1 ] || { echo "FAILED: no scripts/test-* found" >&2; status=1; }

# actionlint checks run: blocks with shellcheck only when shellcheck is on PATH; CI runners have it, so it's required.
if ! command -v shellcheck >/dev/null 2>&1; then
  echo "FAILED: shellcheck is not on PATH (actionlint needs it to check run: blocks as CI does)" >&2
  status=1
elif ! command -v actionlint >/dev/null 2>&1; then
  echo "FAILED: actionlint $ACTIONLINT_VERSION is not on PATH" >&2
  status=1
else
  local_version=$(actionlint -version | head -n 1)
  [ "$local_version" = "$ACTIONLINT_VERSION" ] ||
    echo "warning: actionlint $local_version here, CI pins $ACTIONLINT_VERSION; results may differ" >&2
  step actionlint .github/workflows/*.yml templates/repo/.github/workflows/*.yml
fi

step json_valid

[ "$status" = 0 ] && printf '\nAll checks passed.\n'
exit "$status"
