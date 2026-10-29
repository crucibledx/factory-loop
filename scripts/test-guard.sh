#!/bin/sh
# Exercises hooks/guard-git.sh with sample commands. Exit 0 when every case behaves as expected.
set -u
guard="$(cd "$(dirname "$0")/.." && pwd)/plugins/crucible-loop/hooks/guard-git.sh"
fail=0
check() {
  expected="$1"; cmd="$2"
  printf '{"tool_name":"Execute","tool_input":{"command":%s}}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$cmd")" \
    | sh "$guard" 2>/dev/null
  got=$?
  if [ "$got" -ne "$expected" ]; then echo "FAIL ($got != $expected): $cmd"; fail=1; else echo "ok   ($got): $cmd"; fi
}
check 2 "git push origin main"
check 2 "git push origin HEAD:main"
check 2 "git push -f origin loop/0001-x"
check 2 "git push --force origin loop/0001-x"
check 2 "gh pr merge 12 --squash"
check 0 "git push origin loop/0001-x"
check 0 "git push -u origin spec/0002-positioning"
check 0 "git push --force-with-lease origin loop/0001-x"
check 0 "git status"
exit $fail
