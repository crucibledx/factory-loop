#!/bin/sh
# Exercises scripts/automerge.sh against a stubbed gh. Exit 0 when every case behaves as expected.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
# The stub answers from STUB_* env vars and logs merge calls to $tmp/calls.
cat > "$tmp/bin/gh" <<'STUB'
#!/bin/sh
case "$1 $2" in
  "api repos/"*) [ -n "${STUB_API_FAIL:-}" ] && { echo "HTTP 503" >&2; exit 1; }; echo "$STUB_ALLOW" ;;
  "pr view")
    [ -n "${STUB_VIEW_FAIL:-}" ] && { echo "HTTP 502" >&2; exit 1; }
    case "$*" in *headRefOid*) echo "$STUB_HEAD" ;; *autoMergeRequest*) echo "$STUB_AUTO" ;; esac ;;
  "pr merge") echo "$*" >> "$STUB_CALLS"; exit "${STUB_MERGE_RC:-0}" ;;
  *) echo "unexpected gh $*" >&2; exit 99 ;;
esac
STUB
chmod +x "$tmp/bin/gh"
fail=0

# check NAME EXPECTED_RC EXPECTED_CALL MODE [VAR=VALUE...]
check() {
  name=$1; want_rc=$2; want_call=$3; mode=$4; shift 4
  : > "$tmp/calls"
  env PATH="$tmp/bin:$PATH" STUB_CALLS="$tmp/calls" REPO=o/r PR=7 SHA=abc METHOD=squash \
    STUB_ALLOW=true STUB_HEAD=abc STUB_AUTO=true "$@" sh "$root/scripts/automerge.sh" "$mode" >/dev/null 2>&1
  rc=$?
  call=$(cat "$tmp/calls")
  if [ "$rc" -ne "$want_rc" ] || [ "$call" != "$want_call" ]; then
    echo "FAIL $name: rc=$rc (want $want_rc), call='$call' (want '$want_call')"; fail=1
  else
    echo "ok   $name"
  fi
}

check "enable on approved head" 0 "pr merge 7 --repo o/r --auto --squash --match-head-commit abc" enable
check "enable uses merge_method" 0 "pr merge 7 --repo o/r --auto --rebase --match-head-commit abc" enable METHOD=rebase
check "bad merge_method fails" 1 "" enable METHOD=fast
check "head moved: skip" 0 "" enable STUB_HEAD=def
check "auto-merge not allowed: skip" 0 "" enable STUB_ALLOW=false
check "repo lookup failure fails" 1 "" enable STUB_API_FAIL=1
check "head lookup failure fails" 1 "" enable STUB_VIEW_FAIL=1
check "merge failure fails" 1 "pr merge 7 --repo o/r --auto --squash --match-head-commit abc" enable STUB_MERGE_RC=1
check "push disables auto-merge" 0 "pr merge 7 --repo o/r --disable-auto" disable
check "push with auto-merge off: no call" 0 "" disable STUB_AUTO=false
check "state lookup failure fails" 1 "" disable STUB_VIEW_FAIL=1
check "unknown mode" 2 "" bogus
exit $fail
