#!/bin/sh
# Exercises scripts/automerge.sh against a stubbed gh. Exit 0 when every case behaves as expected.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
# The stub answers from STUB_* env vars and logs merge calls to $STUB_CALLS. Each answer is the --jq output.
# STUB_PR: head, auto-merge on, eligible, then "login state commit" lines. STUB_MERGE_STATE: mergeStateStatus.
# STUB_RULES / STUB_PROTECTION: required checks ("req" lines). STUB_RUNS / STUB_STATUSES: checks on commit abc only,
# so a lookup of any other commit is an unexpected call. STUB_HEAD_NOW: the head re-read right before merging.
cat > "$tmp/bin/gh" <<'STUB'
#!/bin/sh
case "$*" in
  "api repos/o/r --jq"*) [ -n "${STUB_API_FAIL:-}" ] && { echo "HTTP 503" >&2; exit 1; }; echo "$STUB_ALLOW" ;;
  "api graphql"*) [ -n "${STUB_GQL_FAIL:-}" ] && { echo "HTTP 502" >&2; exit 1; }; printf '%b\n' "$STUB_PR" ;;
  "api --paginate repos/o/r/rules/branches/main?"*)
    [ -n "${STUB_RULES_FAIL:-}" ] && { echo "HTTP 403" >&2; exit 1; }; printf '%b' "$STUB_RULES" ;;
  "api repos/o/r/branches/main --jq"*) printf '%b' "${STUB_PROTECTION:-}" ;;
  "api --paginate repos/o/r/commits/abc/check-runs?"*) printf '%b' "$STUB_RUNS" ;;
  "api --paginate repos/o/r/commits/abc/status?"*) printf '%b' "${STUB_STATUSES:-}" ;;
  "pr view 7 --repo o/r --json mergeStateStatus,baseRefName "*) echo "${STUB_MERGE_STATE:-BLOCKED} main" ;;
  "pr view 7 --repo o/r --json headRefOid "*) echo "${STUB_HEAD_NOW:-abc}" ;;
  "pr merge"*) echo "$*" >> "$STUB_CALLS"; exit "${STUB_MERGE_RC:-0}" ;;
  *) echo "unexpected gh $*" >&2; exit 99 ;;
esac
STUB
chmod +x "$tmp/bin/gh"
fail=0

# check NAME EXPECTED_RC EXPECTED_CALL [VAR=VALUE...]
# By default "review / review" (app 15368) is required and passed, and this job's own check is still running.
check() {
  name=$1; want_rc=$2; want_call=$3; shift 3
  : > "$tmp/calls"
  env PATH="$tmp/bin:$PATH" STUB_CALLS="$tmp/calls" REPO=o/r PR=7 METHOD=squash APPROVERS=nazar,ana \
    STUB_ALLOW=true STUB_PR='abc\nfalse\ntrue\nnazar APPROVED abc' \
    STUB_RULES='req\treview / review\t15368\n' \
    STUB_RUNS='run\t5\t15368\tcompleted\tsuccess\treview / review\nrun\t6\t15368\tin_progress\t\tautomerge / automerge\n' \
    "$@" sh "$root/scripts/automerge.sh" >/dev/null 2>&1
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
now="pr merge 7 --repo o/r --squash --match-head-commit abc"
check "approver approved head: turn on" 0 "$on"
check "second approver in list counts" 0 "$on" STUB_PR='abc\nfalse\ntrue\nana APPROVED abc'
check "merge_method is passed" 0 "pr merge 7 --repo o/r --auto --rebase --match-head-commit abc" METHOD=rebase
check "already on and approved: no call" 0 "" STUB_PR='abc\ntrue\ntrue\nnazar APPROVED abc'
check "approval on old commit, on: turn off" 0 "$off" STUB_PR='abc\ntrue\ntrue\nnazar APPROVED old'
check "approval on old commit, off: no call" 0 "" STUB_PR='abc\nfalse\ntrue\nnazar APPROVED old'
check "non-approver approval: no call" 0 "" STUB_PR='abc\nfalse\ntrue\nbob APPROVED abc'
check "login case is ignored" 0 "$on" APPROVERS='NazarUsik, ana' STUB_PR='abc\nfalse\ntrue\nnazarusik APPROVED abc'
check "login case is ignored (review side)" 0 "$on" STUB_PR='abc\nfalse\ntrue\nNAZAR APPROVED abc'
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

# Mergeable PRs: GitHub refuses auto-merge, so an approved head with passing required checks is merged directly.
check "BLOCKED: turn on auto-merge" 0 "$on" STUB_MERGE_STATE=BLOCKED
check "other states keep auto-merge" 0 "$on" STUB_MERGE_STATE=BEHIND
check "CLEAN, required checks pass: merge" 0 "$now" STUB_MERGE_STATE=CLEAN
check "UNSTABLE, own job pending: merge" 0 "$now" STUB_MERGE_STATE=UNSTABLE
check "UNSTABLE, non-required check failed: merge" 0 "$now" STUB_MERGE_STATE=UNSTABLE \
  STUB_RUNS='run\t5\t15368\tcompleted\tsuccess\treview / review\nrun\t7\t15368\tcompleted\tfailure\tbuild\n'
check "merge_method is passed to the merge" 0 "pr merge 7 --repo o/r --rebase --match-head-commit abc" \
  METHOD=rebase STUB_MERGE_STATE=CLEAN
check "direct merge failure fails" 1 "$now" STUB_MERGE_STATE=CLEAN STUB_MERGE_RC=1
check "neutral and skipped required checks pass" 0 "$now" STUB_MERGE_STATE=CLEAN \
  STUB_RULES='req\ta\t15368\nreq\tb\t15368\n' STUB_RUNS='run\t1\t15368\tcompleted\tneutral\ta\nrun\t2\t15368\tcompleted\tskipped\tb\n'
check "latest run counts: newer success" 0 "$now" STUB_MERGE_STATE=CLEAN \
  STUB_RUNS='run\t5\t15368\tcompleted\tcancelled\treview / review\nrun\t9\t15368\tcompleted\tsuccess\treview / review\n'
check "latest run counts: newer failure" 1 "" STUB_MERGE_STATE=CLEAN \
  STUB_RUNS='run\t9\t15368\tcompleted\tfailure\treview / review\nrun\t5\t15368\tcompleted\tsuccess\treview / review\n'
check "required check pending: no merge" 1 "" STUB_MERGE_STATE=UNSTABLE \
  STUB_RUNS='run\t5\t15368\tin_progress\t\treview / review\n'
check "required check missing: no merge" 1 "" STUB_MERGE_STATE=CLEAN STUB_RUNS=''
check "required check failed: no merge" 1 "" STUB_MERGE_STATE=UNSTABLE \
  STUB_RUNS='run\t5\t15368\tcompleted\tfailure\treview / review\n'
check "required check from another app: no merge" 1 "" STUB_MERGE_STATE=CLEAN \
  STUB_RUNS='run\t5\t999\tcompleted\tsuccess\treview / review\n'
check "required check without app: any app counts" 0 "$now" STUB_MERGE_STATE=CLEAN \
  STUB_RULES='req\tci\t\n' STUB_RUNS='run\t5\t999\tcompleted\tsuccess\tci\n'
check "required commit status success: merge" 0 "$now" STUB_MERGE_STATE=CLEAN \
  STUB_RULES='req\tlegacy\t\n' STUB_RUNS='' STUB_STATUSES='status\tsuccess\tlegacy\n'
check "required commit status pending: no merge" 1 "" STUB_MERGE_STATE=CLEAN \
  STUB_RULES='req\tlegacy\t\n' STUB_RUNS='' STUB_STATUSES='status\tpending\tlegacy\n'
check "branch protection checks are required too" 1 "" STUB_MERGE_STATE=CLEAN STUB_PROTECTION='req\tlint\t\n'
check "rules lookup failure fails" 1 "" STUB_MERGE_STATE=CLEAN STUB_RULES_FAIL=1
check "head moved before merge: no call" 0 "" STUB_MERGE_STATE=CLEAN STUB_HEAD_NOW=def
check "CLEAN, already on: no call" 0 "" STUB_MERGE_STATE=CLEAN STUB_PR='abc\ntrue\ntrue\nnazar APPROVED abc'
check "CLEAN, approval on old commit: no call" 0 "" STUB_MERGE_STATE=CLEAN STUB_PR='abc\nfalse\ntrue\nnazar APPROVED old'
check "CLEAN, non-approver approval: no call" 0 "" STUB_MERGE_STATE=CLEAN STUB_PR='abc\nfalse\ntrue\nbob APPROVED abc'
check "CLEAN, draft: no call" 0 "" STUB_MERGE_STATE=CLEAN STUB_PR='abc\nfalse\nfalse\nnazar APPROVED abc'
exit $fail
