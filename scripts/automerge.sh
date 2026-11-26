#!/bin/sh
# Reconciles GitHub auto-merge for one PR. Called by loop-automerge.yml on approvals, other reviews, and pushes.
# Auto-merge should be on exactly when the PR is open, not a draft, and a login in APPROVERS has an approval on the
# current head commit (their latest opinionated review). Every run re-reads that state, so the order in which push and
# review runs finish doesn't matter.
# GitHub only accepts auto-merge while the PR is BLOCKED. When the approved PR is already mergeable (CLEAN, or UNSTABLE
# because a non-required check, such as this job's own, is pending or failed), the script merges it directly, but only
# after it has read every required check of the base branch as passing on the approved head.
# Env: REPO (owner/name), PR (number), APPROVERS (comma-separated logins), METHOD (squash|merge|rebase).
# Lookups run as plain assignments so an API failure fails the job (set -e) instead of looking like a skip.
set -eu

case "$METHOD" in squash|merge|rebase) ;; *) echo "::error::merge_method must be squash, merge, or rebase"; exit 1;; esac

allow=$(gh api "repos/$REPO" --jq .allow_auto_merge)
if [ "$allow" != "true" ]; then
  echo "::notice::Auto-merge is not allowed in $REPO (repo settings, or a private repo on the Free plan). Merge by hand."
  exit 0
fi

# Line 1: head sha. Line 2: auto-merge on. Line 3: eligible (open and not a draft). Then "login state commit" per reviewer.
info=$(gh api graphql \
  -f query='query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p){
    headRefOid state isDraft autoMergeRequest{enabledAt}
    latestOpinionatedReviews(first:100){nodes{author{login} state commit{oid}}}}}}' \
  -f o="${REPO%%/*}" -f n="${REPO#*/}" -F p="$PR" \
  --jq '.data.repository.pullRequest | .headRefOid, (.autoMergeRequest != null), (.state == "OPEN" and (.isDraft | not)),
        (.latestOpinionatedReviews.nodes[] | "\(.author.login) \(.state) \(.commit.oid)")')

head=$(printf '%s\n' "$info" | sed -n 1p)
on=$(printf '%s\n' "$info" | sed -n 2p)
eligible=$(printf '%s\n' "$info" | sed -n 3p)
[ -n "$head" ] || { echo "::error::Could not read PR $REPO#$PR"; exit 1; }

approved=false
reviews=$(printf '%s\n' "$info" | sed -n '4,$p')
# GitHub logins are case-insensitive.
approvers=$(printf '%s' "$APPROVERS" | tr '[:upper:]' '[:lower:]' | tr -d ' ')
if [ "$eligible" = "true" ] && [ -n "$reviews" ]; then
  while read -r login state oid; do
    login=$(printf '%s' "$login" | tr '[:upper:]' '[:lower:]')
    case ",$approvers," in
      *",$login,"*) if [ "$state" = APPROVED ] && [ "$oid" = "$head" ]; then approved=true; fi ;;
    esac
  done <<REVIEWS
$reviews
REVIEWS
fi

# Prints "pending<TAB>check" or "failed<TAB>check" for each required check of branch $1 that has not passed on
# commit $2. Required checks come from the branch rules (rulesets) and classic branch protection. Only the latest run
# of a check counts; success, neutral, and skipped pass, as on GitHub. A check reported both as a check run and as a
# commit status must pass in both. A missing check is pending: it may not have started yet.
required_checks_not_passed() {
  rules=$(gh api --paginate "repos/$REPO/rules/branches/$1?per_page=100" \
    --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[]
          | ["req", .context, (.integration_id // "" | tostring)] | @tsv')
  protection=$(gh api "repos/$REPO/branches/$1" \
    --jq '.protection.required_status_checks.checks[]? | ["req", .context, (.app_id // "" | tostring)] | @tsv')
  runs=$(gh api --paginate "repos/$REPO/commits/$2/check-runs?per_page=100" \
    --jq '.check_runs[] | ["run", .id, .app.id, .status, (.conclusion // ""), .name] | @tsv')
  statuses=$(gh api --paginate "repos/$REPO/commits/$2/status?per_page=100" \
    --jq '.statuses[] | ["status", .state, .context] | @tsv')
  printf '%s\n%s\n%s\n%s\n' "$runs" "$statuses" "$rules" "$protection" | awk -F '\t' '
    $1 == "run" {
      v = $4 != "completed" ? "pending" : ($5 == "success" || $5 == "neutral" || $5 == "skipped") ? "passed" : "failed"
      k = $6 SUBSEP $3
      if (!(k in id) || $2 + 0 > id[k]) { id[k] = $2 + 0; run[k] = v }
      if (!($6 in anyid) || $2 + 0 > anyid[$6]) { anyid[$6] = $2 + 0; anyrun[$6] = v }
    }
    $1 == "status" { status[$3] = $2 == "success" ? "passed" : $2 == "pending" ? "pending" : "failed" }
    $1 == "req" && !(($2 SUBSEP $3) in seen) { seen[$2, $3] = 1; n++; ctx[n] = $2; app[n] = $3 }
    END {
      for (i = 1; i <= n; i++) {
        c = ctx[i]
        if (app[i] != "") v = ((c SUBSEP app[i]) in run) ? run[c, app[i]] : "pending"
        else {
          r = (c in anyrun) ? anyrun[c] : ""; s = (c in status) ? status[c] : ""
          v = (r == "failed" || s == "failed") ? "failed" : (r == "pending" || s == "pending" || r s == "") ? "pending" : "passed"
        }
        if (v != "passed") print v "\t" c
      }
    }'
}

if [ "$approved" = "true" ] && [ "$on" != "true" ]; then
  pr_state=$(gh pr view "$PR" --repo "$REPO" --json mergeStateStatus,baseRefName,id \
    --jq '"\(.mergeStateStatus) \(.baseRefName) \(.id)"')
  merge_state=${pr_state%% *}
  rest=${pr_state#* }
  base=${rest%% *}
  pr_id=${rest#* }
  merge_now=false
  case "$merge_state" in
    CLEAN|UNSTABLE)
      checks=$(required_checks_not_passed "$base" "$head")
      failed=$(printf '%s\n' "$checks" | awk -F '\t' '$1 == "failed" { print $2 }' | paste -sd ',' - | sed 's/,/, /g')
      pending=$(printf '%s\n' "$checks" | awk -F '\t' '$1 == "pending" { print $2 }' | paste -sd ',' - | sed 's/,/, /g')
      if [ -n "$failed" ]; then
        echo "::error::$REPO#$PR is $merge_state, but required checks failed on $head: $failed. Merge by hand."
        exit 1
      elif [ -n "$pending" ]; then
        # GitHub's merge state can lag a required check that just started; auto-merge waits for it.
        echo "::notice::Required checks are still pending on $head: $pending. Turning on auto-merge instead."
      else
        merge_now=true
      fi
      ;;
  esac
  if [ "$merge_now" = "true" ]; then
    now=$(gh pr view "$PR" --repo "$REPO" --json headRefOid --jq .headRefOid)
    if [ "$now" != "$head" ]; then
      echo "::notice::$REPO#$PR moved from $head to $now; not merging. The push re-runs this check."
      exit 0
    fi
    # --match-head-commit: never merge a commit other than the approved head.
    gh pr merge "$PR" --repo "$REPO" "--$METHOD" --match-head-commit "$head"
    echo "Merged $REPO#$PR at $head ($METHOD): it was $merge_state and its required checks passed."
  else
    # The mutation, not `gh pr merge --auto`: gh merges at once when it sees the PR as mergeable, which would skip the
    # required-check reading above. expectedHeadOid: never merge a commit other than the approved head.
    gh api graphql --silent \
      -f query='mutation($id:ID!,$method:PullRequestMergeMethod!,$sha:GitObjectID!){
        enablePullRequestAutoMerge(input:{pullRequestId:$id,mergeMethod:$method,expectedHeadOid:$sha}){clientMutationId}}' \
      -f id="$pr_id" -f method="$(printf '%s' "$METHOD" | tr '[:lower:]' '[:upper:]')" -f sha="$head"
    echo "Auto-merge is on for $REPO#$PR at $head ($METHOD)."
  fi
elif [ "$approved" != "true" ] && [ "$on" = "true" ]; then
  gh pr merge "$PR" --repo "$REPO" --disable-auto
  echo "Auto-merge is off for $REPO#$PR: no approval from $APPROVERS on head $head."
else
  echo "Nothing to change for $REPO#$PR (approved head: $approved, auto-merge on: $on)."
fi
