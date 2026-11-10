#!/bin/sh
# Turns GitHub auto-merge on for an approved commit, or off after a new push. Called by loop-automerge.yml.
# Env: REPO (owner/name), PR (number); for enable also SHA (approved commit) and METHOD (squash|merge|rebase).
# Lookups run as plain assignments so an API failure fails the job (set -e) instead of looking like a skip.
set -eu
mode="${1:-}"

case "$mode" in
  enable)
    case "$METHOD" in squash|merge|rebase) ;; *) echo "::error::merge_method must be squash, merge, or rebase"; exit 1;; esac
    allow=$(gh api "repos/$REPO" --jq .allow_auto_merge)
    if [ "$allow" != "true" ]; then
      echo "::notice::Auto-merge is not allowed in $REPO (repo settings, or a private repo on the Free plan). Merge by hand."
      exit 0
    fi
    head=$(gh pr view "$PR" --repo "$REPO" --json headRefOid --jq .headRefOid)
    if [ "$head" != "$SHA" ]; then
      echo "::notice::The PR has commits after the approved one ($SHA); approve the new head to merge."
      exit 0
    fi
    # --match-head-commit: never merge a commit other than the one that was approved.
    gh pr merge "$PR" --repo "$REPO" --auto "--$METHOD" --match-head-commit "$SHA"
    echo "Auto-merge is on for $REPO#$PR at $SHA ($METHOD)."
    ;;
  disable)
    on=$(gh pr view "$PR" --repo "$REPO" --json autoMergeRequest --jq '.autoMergeRequest != null')
    if [ "$on" != "true" ]; then
      echo "Auto-merge is already off for $REPO#$PR."
      exit 0
    fi
    gh pr merge "$PR" --repo "$REPO" --disable-auto
    echo "New push: auto-merge is off for $REPO#$PR until an approver approves the new head."
    ;;
  *)
    echo "usage: automerge.sh enable|disable" >&2
    exit 2
    ;;
esac
