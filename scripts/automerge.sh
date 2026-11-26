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

# Prints the required checks of branch $1 that have not passed on commit $2, one per line.
# Required checks come from the branch rules (rulesets) and classic branch protection. Only the latest run of a check
# counts; success, neutral, and skipped pass, as on GitHub. A required check that is missing or pending is printed.
failing_required_checks() {
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
      ok = ($4 == "completed" && ($5 == "success" || $5 == "neutral" || $5 == "skipped"))
      k = $6 SUBSEP $3
      if (!(k in id) || $2 + 0 > id[k]) { id[k] = $2 + 0; pass[k] = ok }
      if (!($6 in anyid) || $2 + 0 > anyid[$6]) { anyid[$6] = $2 + 0; anypass[$6] = ok }
    }
    $1 == "status" { spass[$3] = ($2 == "success") }
    $1 == "req" && !(($2 SUBSEP $3) in seen) { seen[$2, $3] = 1; n++; ctx[n] = $2; app[n] = $3 }
    END {
      for (i = 1; i <= n; i++) {
        if (app[i] != "") ok = ((ctx[i] SUBSEP app[i]) in pass) && pass[ctx[i], app[i]]
        else ok = ((ctx[i] in anypass) && anypass[ctx[i]]) || ((ctx[i] in spass) && spass[ctx[i]])
        if (!ok) print ctx[i]
      }
    }'
}

if [ "$approved" = "true" ] && [ "$on" != "true" ]; then
  pr_state=$(gh pr view "$PR" --repo "$REPO" --json mergeStateStatus,baseRefName --jq '"\(.mergeStateStatus) \(.baseRefName)"')
  merge_state=${pr_state%% *}
  base=${pr_state#* }
  case "$merge_state" in
    CLEAN|UNSTABLE)
      failing=$(failing_required_checks "$base" "$head")
      if [ -n "$failing" ]; then
        failing=$(printf '%s\n' "$failing" | paste -sd ',' - | sed 's/,/, /g')
        echo "::error::$REPO#$PR is $merge_state, but required checks have not passed on $head: $failing. Merge by hand."
        exit 1
      fi
      now=$(gh pr view "$PR" --repo "$REPO" --json headRefOid --jq .headRefOid)
      if [ "$now" != "$head" ]; then
        echo "::notice::$REPO#$PR moved from $head to $now; not merging. The push re-runs this check."
        exit 0
      fi
      # --match-head-commit: never merge a commit other than the approved head.
      gh pr merge "$PR" --repo "$REPO" "--$METHOD" --match-head-commit "$head"
      echo "Merged $REPO#$PR at $head ($METHOD): it was $merge_state and its required checks passed."
      ;;
    *)
      # --match-head-commit: never merge a commit other than the approved head.
      gh pr merge "$PR" --repo "$REPO" --auto "--$METHOD" --match-head-commit "$head"
      echo "Auto-merge is on for $REPO#$PR at $head ($METHOD)."
      ;;
  esac
elif [ "$approved" != "true" ] && [ "$on" = "true" ]; then
  gh pr merge "$PR" --repo "$REPO" --disable-auto
  echo "Auto-merge is off for $REPO#$PR: no approval from $APPROVERS on head $head."
else
  echo "Nothing to change for $REPO#$PR (approved head: $approved, auto-merge on: $on)."
fi
