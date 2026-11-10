#!/bin/sh
# Reconciles GitHub auto-merge for one PR. Called by loop-automerge.yml on approvals, other reviews, and pushes.
# Auto-merge should be on exactly when the PR is open, not a draft, and a login in APPROVERS has an approval on the
# current head commit (their latest opinionated review). Every run re-reads that state, so the order in which push and
# review runs finish doesn't matter.
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

if [ "$approved" = "true" ] && [ "$on" != "true" ]; then
  # --match-head-commit: never merge a commit other than the approved head.
  gh pr merge "$PR" --repo "$REPO" --auto "--$METHOD" --match-head-commit "$head"
  echo "Auto-merge is on for $REPO#$PR at $head ($METHOD)."
elif [ "$approved" != "true" ] && [ "$on" = "true" ]; then
  gh pr merge "$PR" --repo "$REPO" --disable-auto
  echo "Auto-merge is off for $REPO#$PR: no approval from $APPROVERS on head $head."
else
  echo "Nothing to change for $REPO#$PR (approved head: $approved, auto-merge on: $on)."
fi
