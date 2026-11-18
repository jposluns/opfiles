#!/usr/bin/env bash
# After a PR push, require MERGEABLE and an Actions run for the supplied head.
# Registration only: use ci-status.sh afterwards to wait for CI completion.
# Exit: 0 registered, 2 usage/unknown state, 4 conflicting, 5 no registration.
#
# Repository: CI_STATUS_REPO (OWNER/NAME) when it is set; otherwise OWNER/NAME is derived at run
# time from the origin remote of this script's own checkout (a github.com HTTPS or SSH URL). There
# is no default: when neither yields a repository, the script exits 2 before any request. A NAME
# made only of dots is refused, so no request path can hold a dot segment.
#
# --timeout (default 600 s) is the registration window. It matches ci-status.sh's default
# registration grace: a run that registers later leaves less than the Quality job's 5-minute
# limit inside ci-status.sh's default 900 s wait.
#
# The default mode never reads or requires a local-quality status.
# --local-quality (merge readiness; opt-in, for use once a local publisher is deployed for this
# repository): the Actions side is pinned to
# pull_request runs of the Quality workflow (CI_STATUS_WORKFLOW_PATH, default
# .github/workflows/quality.yml), AND the LATEST `local-quality` commit status on the SHA
# (any of pending, success, failure, error) must have been created by the expected
# publisher login, configured outside the repository (LOCAL_QUALITY_EXPECTED_CREATOR, else
# the first line of ${XDG_CONFIG_HOME:-$HOME/.config}/local-quality/expected-creator).
# Registration is never a green result: use `ci-status.sh <sha> --wait --local-quality`.
# A latest status by another login is an unknown state (2); a missing side by the deadline
# is exit 5 naming that side. Ordinary post-push use omits the flag.
set -uo pipefail

fail() { printf 'pr-ci-registered: %s\n' "$*" >&2; exit 2; }
usage() { fail 'usage: tools/pr-ci-registered.sh <pr> <sha> [--timeout SECONDS] [--local-quality]'; }
(( $# >= 2 )) || usage
PR=$1 SHA=$2 BUDGET=600 LOCAL=0 TIMEOUT_SET=0
[[ $PR =~ ^[0-9]+$ && $PR =~ [1-9] && $SHA =~ ^[0-9a-f]{40}$ ]] || usage
shift 2
while (( $# )); do
  case $1 in
    --timeout)
      (( $# >= 2 && ! TIMEOUT_SET )) || usage
      BUDGET=$2 TIMEOUT_SET=1
      shift 2 ;;
    --local-quality)
      (( ! LOCAL )) || usage
      LOCAL=1
      shift ;;
    *) usage ;;
  esac
done
[[ $BUDGET =~ ^[0-9]+$ ]] || fail '--timeout must be a non-negative integer in [0, 31536000]'
# Strip zeros before arithmetic, guarding against both octal parsing and overflow.
while [[ ${#BUDGET} -gt 1 && $BUDGET == 0* ]]; do BUDGET=${BUDGET#0}; done
[[ ${#BUDGET} -le 8 ]] || fail '--timeout exceeds 31536000 seconds'
(( BUDGET <= 31536000 )) || fail '--timeout exceeds 31536000 seconds'

# Same repository selection AND the same run-selection policy as ci-status.sh:
# runs whose event is `schedule` are ignored, so a schedule run can never count
# as registration for a PR head that equals main's tip. Binary override is a
# test seam only.
REPO=${CI_STATUS_REPO:-}
if [[ -z $REPO ]]; then
  SELF=$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null) || SELF=${BASH_SOURCE[0]}
  SELF_REPO=$(cd "$(dirname "$SELF")" 2>/dev/null && env -u GIT_DIR -u GIT_WORK_TREE git rev-parse --show-toplevel 2>/dev/null) || SELF_REPO=''
  ORIGIN_URL=''
  if [[ -n $SELF_REPO ]]; then
    ORIGIN_URL=$(env -u GIT_DIR -u GIT_WORK_TREE git -C "$SELF_REPO" remote get-url origin 2>/dev/null) || ORIGIN_URL=''
  fi
  case $ORIGIN_URL in
    https://github.com/*) REPO=${ORIGIN_URL#https://github.com/} ;;
    git@github.com:*) REPO=${ORIGIN_URL#git@github.com:} ;;
    ssh://git@github.com/*) REPO=${ORIGIN_URL#ssh://git@github.com/} ;;
  esac
  REPO=${REPO%/}
  REPO=${REPO%.git}
  [[ -n $REPO ]] || fail 'no repository: set CI_STATUS_REPO to OWNER/NAME, or run from a checkout whose origin remote is a github.com repository'
fi
# The same check for both sources; a NAME of only dots (. or ..) is refused too.
[[ $REPO =~ ^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$ && ! ${REPO#*/} =~ ^\.+$ ]] || fail 'the repository must be OWNER/NAME'
GH=${PR_CI_REGISTERED_GH_BIN:-gh}
EVENTS=(pull_request push)
PIN_PATH='' EXPECTED_CREATOR='' MISSING_SIDE='Quality workflow run'
# shellcheck disable=SC2016  # $n/$s/$c are jq names, not shell expansions
RUNS_JQ='if (.workflow_runs|type) != "array" then "invalid" elif (.total_count // 0) > 1000 then "invalid" elif (.workflow_runs|length) == 0 then "0" else ([.workflow_runs[] | select(.event == "pull_request" or .event == "push")] | length) as $n | if $n == 0 then "more" else ($n|tostring) end end'
if (( LOCAL )); then
  # Both programs are pinned in tools/test_pr_ci_registered.sh; the statuses program is shared
  # with tools/ci-status.sh. Newest first: the first local-quality entry is the latest.
  # @WORKFLOW_PATH@ is replaced by the validated path below (a literal; jq never reads the environment).
  # shellcheck disable=SC2016
  RUNS_JQ_TEMPLATE='if (.workflow_runs|type) != "array" then "invalid" elif (.total_count // 0) > 1000 then "invalid" elif (.workflow_runs|length) == 0 then "0" else ([.workflow_runs[] | select(.event == "pull_request" and .path == "@WORKFLOW_PATH@")] | length) as $n | if $n == 0 then "more" else ($n|tostring) end end'
  # shellcheck disable=SC2016
  LQ_JQ='if type != "array" then "error|||" elif any(.[]; type != "object") then "error|||" elif length == 0 then "none|||" else ([.[] | select(.context == "local-quality")] | .[0]) as $s | if $s == null then (if length < 100 then "none|||" else "more|||" end) elif ($s.state | type) != "string" or ($s.creator | type) != "object" or ($s.creator.login | type) != "string" then "invalid|||" else (if $s.state == "success" then "lqsuccess" elif $s.state == "pending" then "lqpending" elif $s.state == "failure" or $s.state == "error" then "lqfail" else "invalid" end) as $c | if $c == "invalid" then "invalid|||" else $c + "|" + ($s.state | @base64) + "|" + ($s.creator.login | @base64) + "|" + (($s.description // "") | tostring | @base64) end end end'
  EVENTS=(pull_request)
  EXPECTED_CREATOR=${LOCAL_QUALITY_EXPECTED_CREATOR:-}
  if [[ -z $EXPECTED_CREATOR ]]; then
    CREATOR_FILE=${XDG_CONFIG_HOME:-${HOME:-}/.config}/local-quality/expected-creator
    if [[ -f $CREATOR_FILE && -r $CREATOR_FILE ]]; then IFS= read -r EXPECTED_CREATOR <"$CREATOR_FILE" || true; fi
  fi
  [[ $EXPECTED_CREATOR =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}(\[bot\])?$ ]] ||
    fail 'missing or malformed expected publisher login (LOCAL_QUALITY_EXPECTED_CREATOR or the XDG local-quality/expected-creator file)'
  PIN_PATH=${CI_STATUS_WORKFLOW_PATH:-.github/workflows/quality.yml}
  [[ $PIN_PATH =~ ^\.github/workflows/[A-Za-z0-9._-]+\.ya?ml$ ]] || fail 'CI_STATUS_WORKFLOW_PATH must name a file under .github/workflows/'
  RUNS_JQ=${RUNS_JQ_TEMPLATE//@WORKFLOW_PATH@/$PIN_PATH}
fi
command -v "$GH" >/dev/null 2>&1 || fail 'gh binary unavailable; state unknown'
command -v timeout >/dev/null 2>&1 || fail 'GNU timeout unavailable; state unknown'
WORK=$(mktemp -d "${TMPDIR:-/tmp}/pr-ci-registered.XXXXXX") || fail 'cannot create query scratch directory'
trap 'rm -rf -- "$WORK"' EXIT
trap 'exit 2' HUP INT TERM
SECONDS=0
SLEPT=0
QUERIES=0
OUT=''
LIST_END=''
remaining() {
  local elapsed=$SECONDS
  (( SLEPT > elapsed )) && elapsed=$SLEPT
  LEFT=$(( BUDGET - elapsed ))
}
query() {
  local allowance file
  remaining
  allowance=$LEFT
  (( allowance > 60 )) && allowance=60
  # Zero budget permits one immediate observation; boundary requests are capped
  # at 1s each. GNU timeout adds at most 1s kill grace per request.
  (( allowance < 1 )) && allowance=1
  if [[ -n $LIST_END ]]; then
    local page_left=$(( LIST_END - SECONDS ))
    (( page_left > 0 )) || fail 'Actions pagination allowance exhausted; state unknown'
    (( allowance > page_left )) && allowance=$page_left
  fi
  QUERIES=$(( QUERIES + 1 ))
  file=$WORK/query.$QUERIES
  # A fresh regular file avoids pipe capture hanging on inherited writer FDs.
  timeout -k 1 "$allowance" "$GH" "$@" >"$file" 2>/dev/null || fail 'gh request failed or timed out; state unknown'
  OUT=$(cat "$file") || fail 'cannot read gh response; state unknown'
  rm -f -- "$file"
}
while :; do
  query pr view "$PR" --repo "$REPO" --json mergeable,headRefOid --jq '[.mergeable, .headRefOid] | @tsv'
  MERGEABLE=${OUT%%$'\t'*}
  HEAD_SHA=${OUT#*$'\t'}
  [[ $OUT == *$'\t'* && $HEAD_SHA =~ ^[0-9a-f]{40}$ ]] || fail 'invalid headRefOid response; state unknown'
  if [[ $HEAD_SHA == "$SHA" ]]; then
    case $MERGEABLE in
      CONFLICTING)
        printf 'pr-ci-registered: PR #%s is CONFLICTING at %s; resolve the conflict before continuing\n' "$PR" "$SHA"
        exit 4 ;;
      MERGEABLE)
        # Actions: Read only. Never use Checks or commits/<sha>/status; see ci-status.sh.
        # (--local-quality also reads the per-context commits/<sha>/statuses list, never the combined status.)
        # Server-side event filters exclude schedules before pagination. Both
        # listings share one <=60s allowance, with a 1s floor per listing. Retain the
        # 1000-result and defensive page bounds for inconsistent responses.
        remaining
        LIST_ALLOWANCE=$LEFT
        (( LIST_ALLOWANCE > 60 )) && LIST_ALLOWANCE=60
        (( LIST_ALLOWANCE < 1 )) && LIST_ALLOWANCE=1
        LIST_END=$(( SECONDS + LIST_ALLOWANCE ))
        REGISTERED=0
        for EVENT in "${EVENTS[@]}"; do
          (( LIST_END > SECONDS )) || LIST_END=$(( SECONDS + 1 ))
          PAGE=1
          while :; do
            query api "repos/$REPO/actions/runs?head_sha=$SHA&event=$EVENT&per_page=100&page=$PAGE" --jq "$RUNS_JQ"
            [[ $OUT == more ]] || break
            (( PAGE < 10 )) || fail 'Actions pagination page bound reached; state unknown'
            PAGE=$(( PAGE + 1 ))
          done
          [[ $OUT =~ ^[0-9]+$ ]] || fail 'invalid Actions run listing; state unknown'
          if [[ $OUT =~ [1-9] ]]; then REGISTERED=1; break; fi
        done
        LIST_END=''
        if (( REGISTERED && LOCAL )); then
          # The latest local-quality status, first in page order, bounded like the run listing.
          remaining
          LIST_ALLOWANCE=$LEFT
          (( LIST_ALLOWANCE > 60 )) && LIST_ALLOWANCE=60
          (( LIST_ALLOWANCE < 1 )) && LIST_ALLOWANCE=1
          LIST_END=$(( SECONDS + LIST_ALLOWANCE ))
          PAGE=1
          while :; do
            query api "repos/$REPO/commits/$SHA/statuses?per_page=100&page=$PAGE" --jq "$LQ_JQ"
            [[ $OUT == 'more|||' ]] || break
            (( PAGE < 10 )) || fail 'local-quality status page bound reached; state unknown'
            PAGE=$(( PAGE + 1 ))
          done
          LIST_END=''
          PIPES=${OUT//[!|]/}
          (( ${#PIPES} == 3 )) || fail 'invalid local-quality status listing; state unknown'
          case ${OUT%%|*} in
            none) MISSING_SIDE='local-quality status' ;;
            lqsuccess|lqpending|lqfail)
              IFS='|' read -r _ LQ_STATE LQ_LOGIN _ <<<"$OUT"
              LQ_STATE=$(printf '%s' "$LQ_STATE" | base64 -d 2>/dev/null) || fail 'invalid local-quality status listing; state unknown'
              LQ_LOGIN=$(printf '%s' "$LQ_LOGIN" | base64 -d 2>/dev/null) || fail 'invalid local-quality status listing; state unknown'
              [[ $LQ_STATE =~ ^(pending|success|failure|error)$ ]] || fail 'invalid local-quality status listing; state unknown'
              [[ $LQ_LOGIN == "$EXPECTED_CREATOR" ]] ||
                fail 'latest local-quality status was created by an unexpected login; state unknown'
              printf 'pr-ci-registered: PR #%s is MERGEABLE; Quality run and local-quality status (%s) registered for %s; registration is not a green result\n' "$PR" "$LQ_STATE" "$SHA"
              exit 0 ;;
            *) fail 'invalid local-quality status listing; state unknown' ;;
          esac
        elif (( REGISTERED )); then
          printf 'pr-ci-registered: PR #%s is MERGEABLE; CI registered for %s\n' "$PR" "$SHA"
          exit 0
        else
          MISSING_SIDE='Quality workflow run'
        fi ;;
      UNKNOWN) ;; # GitHub may still be computing mergeability. Never succeed here.
      *) fail 'invalid mergeability response; state unknown' ;;
    esac
  fi
  remaining
  if (( LEFT <= 0 )); then
    [[ $HEAD_SHA == "$SHA" ]] || fail "PR #$PR head $HEAD_SHA differs from requested $SHA; PR moved or wrong SHA supplied"
    [[ $MERGEABLE == MERGEABLE ]] || fail 'mergeability still UNKNOWN at deadline'
    if (( LOCAL )); then
      printf 'pr-ci-registered: no %s registered for %s within %ss (PR #%s)\n' "$MISSING_SIDE" "$SHA" "$BUDGET" "$PR" >&2
    else
      printf 'pr-ci-registered: no CI run registered for %s within %ss (PR #%s)\n' "$SHA" "$BUDGET" "$PR" >&2
    fi
    exit 5
  fi
  DELAY=15
  (( LEFT < DELAY )) && DELAY=$LEFT
  sleep "$DELAY" || fail 'poll sleep failed; state unknown'
  SLEPT=$(( SLEPT + DELAY ))
done
