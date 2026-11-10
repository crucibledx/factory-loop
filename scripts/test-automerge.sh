#!/bin/sh
# Exercises scripts/automerge.sh against a stubbed gh. Exit 0 when every case behaves as expected.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
# The stub answers from STUB_* env vars and logs merge calls to $STUB_CALLS.
# STUB_PR is the --jq output of the PR query: head, auto-merge on, eligible, then "login state commit" lines.
cat > "$tmp/bin/gh" <<'STUB'
#!/bin/sh
case "$1 $2" in
  "api repos/"*) [ -n "${STUB_API_FAIL:-}" ] && { echo "HTTP 503" >&2; exit 1; }; echo "$STUB_ALLOW" ;;
  "api graphql") [ -n "${STUB_GQL_FAIL:-}" ] && { echo "HTTP 502" >&2; exit 1; }; printf '%b\n' "$STUB_PR" ;;
  "pr merge") echo "$*" >> "$STUB_CALLS"; exit "${STUB_MERGE_RC:-0}" ;;
  *) echo "unexpected gh $*" >&2; exit 99 ;;
esac
STUB
chmod +x "$tmp/bin/gh"
fail=0

# check NAME EXPECTED_RC EXPECTED_CALL [VAR=VALUE...]
check() {
  name=$1; want_rc=$2; want_call=$3; shift 3
  : > "$tmp/calls"
  env PATH="$tmp/bin:$PATH" STUB_CALLS="$tmp/calls" REPO=o/r PR=7 METHOD=squash APPROVERS=nazar,ana \
    STUB_ALLOW=true STUB_PR='abc\nfalse\ntrue\nnazar APPROVED abc' "$@" sh "$root/scripts/automerge.sh" >/dev/null 2>&1
  rc=$?
  call=$(cat "$tmp/calls")
  if [ "$rc" -ne "$want_rc" ] || [ "$call" != "$want_call" ]; then
    echo "FAIL $name: rc=$rc (want $want_rc), call='$call' (want '$want_call')"; fail=1
  else
    echo "ok   $name"
  fi
}

on="pr merge 7 --repo o/r --auto --squash --match-head-commit abc"
off="pr merge 7 --repo o/r --disable-auto"
check "approver approved head: turn on" 0 "$on"
check "second approver in list counts" 0 "$on" STUB_PR='abc\nfalse\ntrue\nana APPROVED abc'
check "merge_method is passed" 0 "pr merge 7 --repo o/r --auto --rebase --match-head-commit abc" METHOD=rebase
check "already on and approved: no call" 0 "" STUB_PR='abc\ntrue\ntrue\nnazar APPROVED abc'
check "approval on old commit, on: turn off" 0 "$off" STUB_PR='abc\ntrue\ntrue\nnazar APPROVED old'
check "approval on old commit, off: no call" 0 "" STUB_PR='abc\nfalse\ntrue\nnazar APPROVED old'
check "non-approver approval: no call" 0 "" STUB_PR='abc\nfalse\ntrue\nbob APPROVED abc'
check "login prefix is not a match" 0 "" STUB_PR='abc\nfalse\ntrue\nnaz APPROVED abc'
check "non-approver approval while on: off" 0 "$off" STUB_PR='abc\ntrue\ntrue\nbob APPROVED abc'
check "changes requested while on: off" 0 "$off" STUB_PR='abc\ntrue\ntrue\nnazar CHANGES_REQUESTED abc'
check "draft while on: off" 0 "$off" STUB_PR='abc\ntrue\nfalse\nnazar APPROVED abc'
check "no reviews: no call" 0 "" STUB_PR='abc\nfalse\ntrue'
check "auto-merge not allowed: skip" 0 "" STUB_ALLOW=false
check "bad merge_method fails" 1 "" METHOD=fast
check "repo lookup failure fails" 1 "" STUB_API_FAIL=1
check "PR lookup failure fails" 1 "" STUB_GQL_FAIL=1
check "empty PR data fails" 1 "" STUB_PR=''
check "merge failure fails" 1 "$on" STUB_MERGE_RC=1
exit $fail
