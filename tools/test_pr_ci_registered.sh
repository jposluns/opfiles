#!/usr/bin/env bash
# Hermetic contract tests for tools/pr-ci-registered.sh. gh is always fake (a fake binary, and a
# sentinel gh first on PATH that fails if reached); sleeps are simulated; no network is used.
set -euo pipefail
# Hermetic against the host environment: settings the script or the fakes read are cleared here,
# so an exported value cannot turn a case red (or green). Cases that need one set it themselves.
unset CI_STATUS_WORKFLOW_PATH LOCAL_QUALITY_EXPECTED_CREATOR XDG_CONFIG_HOME BASH_ENV GIT_DIR GIT_WORK_TREE \
  SCENARIO LQ_FIX
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/test-pr-ci-registered.XXXXXX")
trap 'rm -rf -- "$WORK"' EXIT
mkdir "$WORK/bin"
export STATE=$WORK
export PR_CI_REGISTERED_GH_BIN=$WORK/bin/fake-gh
export CI_STATUS_REPO=fixture/repository
# The exact registration jq (schedule runs never count). Pinned here and
# checked against the script, so drift fails loudly.
# shellcheck disable=SC2016  # $n is a jq variable, not a shell expansion
RUNS_JQ='if (.workflow_runs|type) != "array" then "invalid" elif (.total_count // 0) > 1000 then "invalid" elif (.workflow_runs|length) == 0 then "0" else ([.workflow_runs[] | select(.event == "pull_request" or .event == "push")] | length) as $n | if $n == 0 then "more" else ($n|tostring) end end'
export RUNS_JQ
grep -qF -- "$RUNS_JQ" "$HERE/pr-ci-registered.sh" || { echo 'FAIL: the registration jq program drifted from the test pin' >&2; exit 1; }
export REAL_TIMEOUT REAL_SLEEP
REAL_TIMEOUT=$(command -v timeout)
REAL_SLEEP=$(command -v sleep)
export PATH="$WORK/bin:$PATH"
export TEST_SHA=0123456789012345678901234567890123456789
export OTHER_SHA=fedcba9876fedcba9876fedcba9876fedcba9876
# Unsetting SECONDS removes its special clock behaviour in child bash processes.
# The script's cumulative-sleep budget then drives deterministic simulated time,
# independent of host scheduling; only the test's wrapper moves SECONDS. GNU
# timeout stays real for every fake request, with the test's own REQUEST_BOUND as
# its limit; the script's request bound is checked from the recorded argv.
# REQUEST_BOUND is far above the process start-up delay of a fake request on a
# loaded host, and below CHECK_BOUND, the limit on each run of the script, which
# is followed by KILL CHECK_GRACE seconds later.
export REQUEST_BOUND=20
CHECK_BOUND=30
CHECK_GRACE=5
printf 'unset SECONDS\n' >"$WORK/clock-env"
export BASH_ENV=$WORK/clock-env
cat >"$PR_CI_REGISTERED_GH_BIN" <<'EOF'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >>"$STATE/calls"
if [[ $1 == pr ]]; then
  [[ $# == 9 && $2 == view && $3 == 1058 && $4 == --repo && $5 == "$CI_STATUS_REPO" && $6 == --json && $7 == mergeable,headRefOid && $8 == --jq && $9 == '[.mergeable, .headRefOid] | @tsv' ]] || exit 90
  n=$(cat "$STATE/pr-count"); n=$((n + 1)); echo "$n" >"$STATE/pr-count"
  head=$TEST_SHA
  if [[ $SCENARIO == mismatch || $SCENARIO == mismatch-conflict ]] ||
     [[ $SCENARIO == moved && $n -gt 1 ]] ||
     [[ $SCENARIO == lag-one && $n -le 1 ]] ||
     [[ $SCENARIO == lag-two && $n -le 2 ]] ||
     [[ $SCENARIO == lag-conflict && $n -le 2 ]]; then head=$OTHER_SHA; fi
  reply() { printf '%s\t%s\n' "$1" "$head"; }
  case $SCENARIO in
    conflict|lag-conflict|mismatch-conflict) reply CONFLICTING ;;
    pr-failure) reply MERGEABLE; exit 1 ;;
    unknown) reply UNKNOWN ;;
    resolves) if (( n == 1 )); then reply UNKNOWN; else reply MERGEABLE; fi ;;
    resolves-conflict) if (( n == 1 )); then reply UNKNOWN; else reply CONFLICTING; fi ;;
    late-conflict) if (( n == 1 )); then reply MERGEABLE; else reply CONFLICTING; fi ;;
    bad-merge) reply null ;;
    empty-head) head=''; reply MERGEABLE ;;
    no-tab-head) printf '%s\n' MERGEABLE ;;
    bare-sha-head) printf '%s\n' "$TEST_SHA" ;;
    *) reply MERGEABLE ;;
  esac
elif [[ $1 == api ]]; then
  [[ $# == 4 && $2 == "repos/$CI_STATUS_REPO/actions/runs?head_sha=$TEST_SHA&event="*"&per_page=100&page="* && $3 == --jq && $4 == "$RUNS_JQ" ]] || exit 91
  [[ $2 == *'&event=pull_request&'* || $2 == *'&event=push&'* ]] || exit 94
  if [[ $2 == *'&event=push&'* && ( $SCENARIO == pages-* || $SCENARIO == endless-pages ) ]]; then
    echo 0
    exit
  fi
  if [[ $SCENARIO == deletion || $SCENARIO == filtered-schedule ]]; then
    [[ $2 == *'&page=1' ]] || exit 95
    event=${2#*&event=}; event=${event%%&*}
    jq --arg event "$event" '{workflow_runs: [.workflow_runs[] | select(.event == $event)][:100]}' "$STATE/deletion.json" >"$STATE/reply.json"
    jq '.workflow_runs |= .[1:]' "$STATE/deletion.json" >"$STATE/next.json"
    mv "$STATE/next.json" "$STATE/deletion.json"
    jq -r "$4" "$STATE/reply.json"
    exit
  fi
  if [[ $SCENARIO == endless-pages ]]; then
    jq -r "$4" "$STATE/pages-schedule/1.json"
    exit
  fi
  if [[ $SCENARIO == pages-* ]]; then
    page=${2##*&page=}
    jq -r "$4" "$STATE/$SCENARIO/$page.json"
    exit
  fi
  case $SCENARIO in
    api-failure) echo 1; exit 1 ;;
    # schedule-only models a head whose every run is a schedule run:
    # the jq filters them all out, so the count the script reads is 0.
    absent|late-conflict|moved|schedule-only) echo 0 ;;
    bad-count) echo null ;;
    invalid-listing) echo invalid ;;
    negative-count) echo -1 ;;
    empty-count) : ;;
    *) echo 1 ;;
  esac
else
  exit 92
fi
EOF
# Record the actual PATH-resolved wrapper, with the seconds the fake sleeps had
# simulated by then, then run real GNU timeout.
# The script's request bound is the argv recorded here, checked after
# every run (check_timeouts): -k 1, and a limit of what the budget leaves, from 1 to 60, so exactly
# 1 once the budget is zero or spent. The fake request then runs under real GNU timeout with that
# kill grace and REQUEST_BOUND as its limit, not the script's: a fake gh slowed only by a loaded
# host must not read as a gh timeout when the script allows it 1 second. A hung fake gets TERM at
# REQUEST_BOUND seconds and KILL 1 second later, so its request fails and the script exits 2. The
# limit must stay finite: the script defers its TERM trap until its foreground request ends, so
# without it a hung fake would hold the check past CHECK_BOUND, until CHECK_GRACE's KILL.
cat >"$WORK/bin/timeout" <<'EOF'
#!/usr/bin/env bash
slept=0
while read -r s; do slept=$((slept + s)); done <"$STATE/sleeps"
printf '%s %s\n' "$slept" "$*" >>"$STATE/timeouts"
if [[ $# -ge 4 && $1 == -k ]]; then exec "$REAL_TIMEOUT" "$1" "$2" "$REQUEST_BOUND" "${@:4}"; fi
exec "$REAL_TIMEOUT" "$@"
EOF
cat >"$WORK/bin/sleep" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$1" >>"$STATE/sleeps"
EOF
# A PATH sentinel prevents an accidental loss of the binary override contacting GitHub.
cat >"$WORK/bin/gh" <<'EOF'
#!/usr/bin/env bash
exit 93
EOF
chmod +x "$WORK/bin/"*
N=0
# check_timeouts LABEL GH ARGS...: every gh request of the last run had a wrapper, with -k 1 and a limit of
# what the budget left (--timeout, default 600, less the seconds slept by then) capped at 60 and at least 1
# (pr-ci-registered.sh: boundary requests get 1 second each, so a zero or spent budget asks for
# exactly 1). Exactly that limit under the simulated clock; at most that under the advancing clock, where
# SECONDS also spends the budget.
check_timeouts() {
  local label=$1 gh=$2 budget=600 previous='' arg slept kill grace limit binary args left exact=0
  shift 2
  for arg; do [[ $previous != --timeout ]] || budget=$arg; previous=$arg; done
  [[ $BASH_ENV != "$WORK/clock-env" ]] || exact=1
  : >"$STATE/wrapped-calls"
  while read -r slept kill grace limit binary args; do
    # A budget that is not a number never reaches a request.
    left=$(( 10#$budget - slept ))
    (( left <= 60 )) || left=60
    (( left >= 1 )) || left=1
    if [[ $kill != -k || $grace != 1 || ! $limit =~ ^[0-9]+$ || ${#limit} -gt 2 || $binary != "$gh" ]] ||
       (( 10#$limit < 1 || 10#$limit > left || (exact && 10#$limit != left) )); then
      printf 'FAIL %s: invalid request timeout (budget %s): %s\n' "$label" "$budget" "$(cat "$STATE/timeouts")" >&2
      exit 1
    fi
    printf '%s\n' "$args" >>"$STATE/wrapped-calls"
  done <"$STATE/timeouts"
  if ! cmp -s "$STATE/calls" "$STATE/wrapped-calls"; then
    printf 'FAIL %s: gh calls missing timeout wrappers\n' "$label" >&2
    exit 1
  fi
}
check() {
  local scenario=$1 expected=$2 message=$3 pr_calls=$4 api_calls=$5 sleeps=$6
  shift 6
  case $scenario in
    pages-schedule) api_calls=$((api_calls + 1)) ;;
    registered|lag-one|lag-two|resolves|pages-push) ;;
    pages-*|endless-pages|api-failure|bad-count|negative-count|empty-count|invalid-listing) ;;
    *) api_calls=$((api_calls * 2)) ;;
  esac
  export SCENARIO=$scenario
  : >"$STATE/timeouts"
  : >"$STATE/calls"; : >"$STATE/sleeps"; echo 0 >"$STATE/pr-count"
  local rc=0 output
  output=$("$REAL_TIMEOUT" -k "$CHECK_GRACE" "$CHECK_BOUND" bash "$HERE/pr-ci-registered.sh" "$@" 2>&1) || rc=$?
  if [[ $rc == 124 || $rc != "$expected" || $output != *"$message"* || $output == *$'\n'* || $(cat "$STATE/pr-count") != "$pr_calls" || $(grep -c '^api ' "$STATE/calls" || :) != "$api_calls" || $(paste -sd, "$STATE/sleeps") != "$sleeps" ]]; then
    printf 'FAIL %s: status=%s output=%s\n' "$scenario" "$rc" "$output" >&2
    cat "$STATE/calls" "$STATE/sleeps" >&2
    exit 1
  fi
  check_timeouts "$scenario" "$PR_CI_REGISTERED_GH_BIN" "$@"
  N=$((N + 1))
}
check registered 0 'CI registered' 1 1 '' 1058 "$TEST_SHA" --timeout 0
check registered 0 'CI registered' 1 1 '' 1058 "$TEST_SHA"
check mismatch 2 "head $OTHER_SHA differs from requested $TEST_SHA" 1 0 '' 1058 "$TEST_SHA" --timeout 0
check moved 2 "head $OTHER_SHA differs from requested $TEST_SHA" 3 1 15,15 1058 "$TEST_SHA" --timeout 30
check mismatch 2 "head $OTHER_SHA differs from requested $TEST_SHA" 3 0 15,1 1058 "$TEST_SHA" --timeout 16
check mismatch-conflict 2 "head $OTHER_SHA differs from requested $TEST_SHA" 3 0 15,15 1058 "$TEST_SHA" --timeout 30
check lag-one 0 'is MERGEABLE; CI registered' 2 1 15 1058 "$TEST_SHA" --timeout 30
check lag-two 0 'is MERGEABLE; CI registered' 3 1 15,15 1058 "$TEST_SHA" --timeout 30
check lag-conflict 4 CONFLICTING 3 0 15,15 1058 "$TEST_SHA" --timeout 30
check conflict 4 CONFLICTING 1 0 '' 1058 "$TEST_SHA" --timeout 0
check absent 5 'within 1s' 2 2 1 1058 "$TEST_SHA" --timeout 1
check absent 5 'within 16s' 3 3 15,1 1058 "$TEST_SHA" --timeout 16
check absent 5 'within 0s' 1 1 '' 1058 "$TEST_SHA" --timeout 000
check pr-failure 2 'state unknown' 1 0 '' 1058 "$TEST_SHA" --timeout 0
check api-failure 2 'state unknown' 1 1 '' 1058 "$TEST_SHA" --timeout 0
check resolves 0 'CI registered' 2 1 15 1058 "$TEST_SHA" --timeout 30
check resolves-conflict 4 CONFLICTING 2 0 15 1058 "$TEST_SHA" --timeout 30
check late-conflict 4 CONFLICTING 2 1 15 1058 "$TEST_SHA" --timeout 30
check unknown 2 'still UNKNOWN' 2 0 1 1058 "$TEST_SHA" --timeout 1
check bad-merge 2 'state unknown' 1 0 '' 1058 "$TEST_SHA" --timeout 0
for scenario in empty-head no-tab-head bare-sha-head; do
  check "$scenario" 2 'invalid headRefOid response; state unknown' 1 0 '' 1058 "$TEST_SHA" --timeout 30
done
for scenario in bad-count negative-count empty-count invalid-listing; do
  check "$scenario" 2 'state unknown' 1 1 '' 1058 "$TEST_SHA" --timeout 0
done
# A head whose runs are ALL schedule runs never reads as registered.
check schedule-only 5 'within 0s' 1 1 '' 1058 "$TEST_SHA" --timeout 0
# The registration jq itself, run with real jq against run-listing fixtures:
# a schedule run never counts, a push run does, and a non-array listing reads
# "invalid" (which the script fails on). The ci-status.sh suite requires jq on
# this host too, so a missing jq is a loud failure, not a silent skip.
command -v jq >/dev/null 2>&1 || { echo 'FAIL: jq is required for the registration-jq fixture cases' >&2; exit 1; }
jqreg() {
  local got
  got=$(printf '%s' "$2" | jq -r "$RUNS_JQ")
  if [[ $got != "$1" ]]; then
    printf 'FAIL jq fixture: want %s got %s for %s\n' "$1" "$got" "$2" >&2
    exit 1
  fi
  N=$((N + 1))
}
jqreg 1 '{"workflow_runs":[{"event":"push"}]}'
jqreg 1 '{"workflow_runs":[{"event":"pull_request"},{"event":"schedule"}]}'
jqreg more '{"workflow_runs":[{"event":"schedule"}]}'
jqreg more '{"workflow_runs":[{"event":"schedule"},{"event":"schedule"}]}'
jqreg 0 '{"workflow_runs":[]}'
jqreg invalid '{}'
jqreg invalid '{"workflow_runs":"not-an-array"}'
# Exercise the real jq through the helper, including page URLs and request bounds.
for scenario in pages-push pages-schedule pages-invalid; do
  mkdir "$STATE/$scenario"
  jq -n '{workflow_runs: [range(30) | {event:"schedule"}]}' >"$STATE/$scenario/1.json"
done
printf '%s\n' '{"workflow_runs":[{"event":"push","status":"completed","conclusion":"success"}]}' >"$STATE/pages-push/2.json"
cp "$STATE/pages-schedule/1.json" "$STATE/pages-schedule/2.json"
printf '%s\n' '{"workflow_runs":[]}' >"$STATE/pages-schedule/3.json"
printf '%s\n' '{"workflow_runs":"invalid"}' >"$STATE/pages-invalid/2.json"
check pages-push 0 'CI registered' 1 2 '' 1058 "$TEST_SHA" --timeout 0
check pages-schedule 5 'within 0s' 1 3 '' 1058 "$TEST_SHA" --timeout 0
check pages-invalid 2 'invalid Actions run listing' 1 2 '' 1058 "$TEST_SHA" --timeout 0
jqreg invalid '{"total_count":1001,"workflow_runs":[]}'
check endless-pages 2 'page bound reached; state unknown' 1 10 '' 1058 "$TEST_SHA" --timeout 0
mkdir "$STATE/pages-cap"
for page in {1..10}; do cp "$STATE/pages-schedule/1.json" "$STATE/pages-cap/$page.json"; done
printf '%s\n' '{"workflow_runs":[]}' >"$STATE/pages-cap/11.json"
check pages-cap 2 'page bound reached; state unknown' 1 10 '' 1058 "$TEST_SHA" --timeout 0
# Deletion between reads cannot hide the sole qualifying run behind schedules.
jq -n '{workflow_runs: ([range(100) | {event:"schedule"}] + [{event:"push"}])}' >"$STATE/deletion.json"
check deletion 0 'CI registered' 1 1 '' 1058 "$TEST_SHA" --timeout 0
for event in pull_request push; do
  grep -q "&event=$event&per_page=100&page=1" "$STATE/calls" || { echo "FAIL: missing $event listing" >&2; exit 1; }
done
jq -n '{workflow_runs: [range(100) | {event:"schedule"}]}' >"$STATE/deletion.json"
check filtered-schedule 5 'within 0s' 1 1 '' 1058 "$TEST_SHA" --timeout 0
# Execute the production query with a partially consumed shared listing allowance.
(
  eval "$(sed -n '/^query() {$/,/^}$/p' "$HERE/pr-ci-registered.sh")"
  remaining() { LEFT=60; }
  fail() { echo "$*" >&2; exit 2; }
  timeout() { printf '%s\n' "$3" >"$WORK/cap-result"; }
  unset SECONDS; SECONDS=10; LIST_END=40; QUERIES=0; GH=unused
  query api
)
[[ $(cat "$WORK/cap-result") == 30 ]] || { echo 'FAIL: shared listing allowance cap' >&2; exit 1; }
N=$((N + 1))
# Pin the listing floor itself, independently of query's remaining-budget cap.
# With LEFT=0 it must be one second, and page two must not reset that deadline.
(
  eval "$(sed -n '/^query() {$/,/^}$/p' "$HERE/pr-ci-registered.sh")"
  fail() { echo "$*" >&2; exit 2; }
  unset SECONDS; SECONDS=10
  remaining() { LEFT=0; }
  eval "$(sed -n '/^        remaining$/,/^        REGISTERED=0$/p' "$HERE/pr-ci-registered.sh")"
  [[ $LIST_END == 11 ]] || { echo 'FAIL: listing floor must be exactly one second' >&2; exit 1; }
  remaining() { LEFT=60; }
  timeout() { printf '%s\n' "$3" >"$WORK/floor-result"; }
  QUERIES=0; GH=unused
  query api
  [[ $(cat "$WORK/floor-result") == 1 && $LIST_END == 11 ]] || exit 1
  SECONDS=11
  if (query api); then echo 'FAIL: page two reset the listing floor' >&2; exit 1; fi
)
N=$((N + 1))
# Run each real page loop (the Actions listing, then the local-quality statuses), not query() alone, with
# the real query(). With LEFT=0 the listing allowance is one second; the fake request returns another page
# and spends that second, so page two must fail closed. A per-page LIST_END reset would keep paging.
for loop in actions statuses; do
  if [[ $loop == actions ]]; then
    block=$(sed -n "/^        remaining\$/,/^        LIST_END=''\$/p" "$HERE/pr-ci-registered.sh")
    page=more
  else
    block=$(sed -n "/^          remaining\$/,/^          LIST_END=''\$/p" "$HERE/pr-ci-registered.sh")
    page='more|||'
  fi
  [[ $block == *'while :; do'* && $block == *'query api'* ]] || { echo "FAIL: cannot extract the $loop page loop" >&2; exit 1; }
  : >"$WORK/page-requests"
  rc=0
  output=$( (
    eval "$(sed -n '/^query() {$/,/^}$/p' "$HERE/pr-ci-registered.sh")"
    fail() { printf 'pr-ci-registered: %s\n' "$*" >&2; exit 2; }
    remaining() { LEFT=0; }
    timeout() { printf '%s\n' "$page"; printf 'request\n' >>"$WORK/page-requests"; SECONDS=11; }
    unset SECONDS; SECONDS=10
    QUERIES=0 GH=unused REPO=fixture/repository SHA=$TEST_SHA LIST_END='' LOCAL=1 LQ_JQ=unused
    EVENTS=(pull_request push)
    eval "$block"
    printf 'the %s page loop ended without failing\n' "$loop"
    ) 2>&1) || rc=$?
  if [[ $rc != 2 || $output != *'Actions pagination allowance exhausted; state unknown'* ]] ||
     [[ $(wc -l <"$WORK/page-requests") != 1 ]]; then
    printf 'FAIL %s page loop reset its listing deadline: status=%s requests=%s output=%s\n' \
      "$loop" "$rc" "$(wc -l <"$WORK/page-requests")" "$output" >&2
    exit 1
  fi
  N=$((N + 1))
done
# Exhaust the shared allowance deterministically before issuing another request.
rc=0
output=$( (
  eval "$(sed -n '/^query() {$/,/^}$/p' "$HERE/pr-ci-registered.sh")"
  remaining() { LEFT=60; }
  fail() { printf 'pr-ci-registered: %s\n' "$*" >&2; exit 2; }
  unset SECONDS; SECONDS=40; LIST_END=40
  query api
  ) 2>&1) || rc=$?
if [[ $rc != 2 || $output != *'Actions pagination allowance exhausted; state unknown'* ]]; then
  printf 'FAIL exhausted allowance: status=%s output=%s\n' "$rc" "$output" >&2
  exit 1
fi
N=$((N + 1))
for value in '' -1 1.5 nope; do
  check invalid 2 'must be a non-negative integer' 0 0 '' 1058 "$TEST_SHA" --timeout "$value"
done
for value in 31536001 18446744073709551616; do
  check invalid 2 'exceeds 31536000' 0 0 '' 1058 "$TEST_SHA" --timeout "$value"
done
check registered 0 'CI registered' 1 1 '' 1058 "$TEST_SHA" --timeout 00008
check usage 2 usage 0 0 '' 1058 abcdef1
check usage 2 usage 0 0 '' 1058 ABCDEF0123456789ABCDEF0123456789ABCDEF01
check usage 2 usage 0 0 '' 1058 "${TEST_SHA}0"
check usage 2 usage 0 0 ''
check usage 2 usage 0 0 '' 1058 "$TEST_SHA" --timeout
check usage 2 usage 0 0 '' 1058 "$TEST_SHA" --bogus 1
check usage 2 usage 0 0 '' 1058 'sha&extra=1'
# Disable the real clock: only the wrapper advances SECONDS across the first
# listing boundary in the parent shell after each completed request.
cat >"$WORK/advancing-clock" <<'EOF'
unset SECONDS
SECONDS=0
timeout() {
  command timeout "$@"
  local rc=$?
  SECONDS=$(( SECONDS + 1 ))
  return "$rc"
}
EOF
export BASH_ENV=$WORK/advancing-clock
check registered 0 'CI registered' 1 1 '' 1058 "$TEST_SHA" --timeout 0
check absent 5 'within 0s' 1 1 '' 1058 "$TEST_SHA" --timeout 0
for repeat in {1..20}; do
  check absent 5 'within 4s' 2 2 1 1058 "$TEST_SHA" --timeout 4
done
export BASH_ENV=$WORK/clock-env
# The default mode never reads or requires a local-quality status.
check registered 0 'CI registered' 1 1 '' 1058 "$TEST_SHA" --timeout 0
if grep -q 'statuses' "$STATE/calls"; then echo 'FAIL: default mode read the statuses endpoint' >&2; exit 1; fi
N=$((N + 1))
# A hung fake gh, which also ignores TERM, ends inside the check's bound. Only this case uses the
# short HUNG_REQUEST_BOUND: the ordinary cases need REQUEST_BOUND's margin over a loaded host's
# start-up delay, but a hung request never completes, so its bound only sets how long the case
# takes. The wrapper gives the request HUNG_REQUEST_BOUND seconds, then TERM (ignored), then KILL
# 1 second later through the script's own -k 1, so the request fails and the script exits 2 after
# about HUNG_REQUEST_BOUND + 1 seconds, well before HUNG_CHECK_BOUND. Without the script's -k the
# ignored TERM would hold the run until HUNG_CHECK_BOUND and CHECK_GRACE's KILL, and this case fails.
HUNG_REQUEST_BOUND=3
HUNG_CHECK_BOUND=8
cat >"$WORK/bin/fake-gh-hung" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STATE/calls"
trap '' TERM
exec "$REAL_SLEEP" 300
EOF
chmod +x "$WORK/bin/fake-gh-hung"
: >"$STATE/timeouts"; : >"$STATE/calls"; : >"$STATE/sleeps"
rc=0 started=$SECONDS
output=$(PR_CI_REGISTERED_GH_BIN=$WORK/bin/fake-gh-hung REQUEST_BOUND=$HUNG_REQUEST_BOUND \
  "$REAL_TIMEOUT" -k "$CHECK_GRACE" "$HUNG_CHECK_BOUND" bash "$HERE/pr-ci-registered.sh" 1058 "$TEST_SHA" --timeout 0 2>&1) || rc=$?
elapsed=$((SECONDS - started))
if [[ $rc != 2 || $output != *'gh request failed or timed out; state unknown'* ]] ||
   (( elapsed < HUNG_REQUEST_BOUND || elapsed >= HUNG_CHECK_BOUND )); then
  printf 'FAIL hung gh: status=%s after %ss (request bound %s, check bound %s) output=%s\n' \
    "$rc" "$elapsed" "$HUNG_REQUEST_BOUND" "$HUNG_CHECK_BOUND" "$output" >&2
  exit 1
fi
check_timeouts hung-gh "$WORK/bin/fake-gh-hung" 1058 "$TEST_SHA" --timeout 0
N=$((N + 1))

# Repository selection: no default owner or repository. Without CI_STATUS_REPO, OWNER/NAME comes
# from the origin remote of the script's own checkout. A git shim first on PATH answers
# `rev-parse --show-toplevel` with /fixture-checkout, and answers `remote get-url origin` (from
# $STATE/origin) only for `git -C /fixture-checkout`, so a lookup that is not pinned to the
# script's own checkout finds no origin. A recording fake gh answers MERGEABLE and one run, so the
# requests can be checked.
cat >"$WORK/bin/git" <<'EOF'
#!/usr/bin/env bash
dir=''
while [[ ${1:-} == -C ]]; do dir=${2:-}; shift 2; done
if [[ ${1:-} == rev-parse && ${2:-} == --show-toplevel ]]; then echo /fixture-checkout; exit 0; fi
if [[ ${1:-} == remote && ${2:-} == get-url && ${3:-} == origin ]]; then
  [[ $dir == /fixture-checkout && -f $STATE/origin ]] || exit 2
  cat "$STATE/origin"
  exit 0
fi
exit 1
EOF
cat >"$WORK/bin/fake-gh-repo" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STATE/calls"
if [[ $1 == pr ]]; then printf 'MERGEABLE\t%s\n' "$TEST_SHA"; else echo 1; fi
EOF
chmod +x "$WORK/bin/git" "$WORK/bin/fake-gh-repo"
# repo_check EXPECTED_RC MESSAGE ORIGIN [CI_STATUS_REPO]: run with CI_STATUS_REPO unset (or set to
# the fourth argument), the origin remote ORIGIN (none when empty), and --timeout 0.
repo_check() {
  local expected=$1 message=$2 origin=$3 rc=0 output
  : >"$STATE/timeouts"; : >"$STATE/calls"; : >"$STATE/sleeps"; rm -f "$STATE/origin"
  [[ -z $origin ]] || printf '%s\n' "$origin" >"$STATE/origin"
  if (( $# >= 4 )); then
    output=$(CI_STATUS_REPO=$4 PR_CI_REGISTERED_GH_BIN=$WORK/bin/fake-gh-repo \
      "$REAL_TIMEOUT" -k "$CHECK_GRACE" "$CHECK_BOUND" bash "$HERE/pr-ci-registered.sh" 1058 "$TEST_SHA" --timeout 0 2>&1) || rc=$?
  else
    output=$(env -u CI_STATUS_REPO PR_CI_REGISTERED_GH_BIN="$WORK/bin/fake-gh-repo" \
      "$REAL_TIMEOUT" -k "$CHECK_GRACE" "$CHECK_BOUND" bash "$HERE/pr-ci-registered.sh" 1058 "$TEST_SHA" --timeout 0 2>&1) || rc=$?
  fi
  if [[ $rc != "$expected" || $output != *"$message"* ]]; then
    printf 'FAIL repository selection (origin %s): status=%s output=%s\n' "${origin:-none}" "$rc" "$output" >&2
    exit 1
  fi
  N=$((N + 1))
}
repo_requests() { # OWNER/NAME: every request named exactly that repository
  grep -qF -- "pr view 1058 --repo $1 " "$STATE/calls" &&
    grep -qF -- "api repos/$1/actions/runs?head_sha=$TEST_SHA" "$STATE/calls" &&
    ! grep -v -F -e "--repo $1 " -e "repos/$1/" "$STATE/calls" >/dev/null
}
for origin in https://github.com/fixture-owner/fixture-name.git https://github.com/fixture-owner/fixture-name \
              https://github.com/fixture-owner/fixture-name/ \
              git@github.com:fixture-owner/fixture-name.git ssh://git@github.com/fixture-owner/fixture-name.git; do
  repo_check 0 'CI registered' "$origin"
  repo_requests fixture-owner/fixture-name || { echo "FAIL: requests did not target the origin's repository ($origin)" >&2; exit 1; }
done
repo_check 0 'CI registered' https://github.com/fixture-owner/fixture-name.git fixture/repository
repo_requests fixture/repository || { echo 'FAIL: CI_STATUS_REPO did not win over the origin remote' >&2; exit 1; }
repo_check 2 'no repository: set CI_STATUS_REPO' ''
[[ ! -s $STATE/calls ]] || { echo 'FAIL: a request was made without a repository' >&2; exit 1; }
repo_check 2 'no repository: set CI_STATUS_REPO' https://example.invalid/fixture-owner/fixture-name.git
[[ ! -s $STATE/calls ]] || { echo 'FAIL: a request was made for a non-github.com origin' >&2; exit 1; }
for bad in fixture fixture/name/extra -fixture/name 'fixture/na me' fixture/. fixture/..; do
  repo_check 2 'the repository must be OWNER/NAME' '' "$bad"
  [[ ! -s $STATE/calls ]] || { echo "FAIL: a request was made for a malformed CI_STATUS_REPO ($bad)" >&2; exit 1; }
done
# An origin that passes the github.com prefix match is still checked as OWNER/NAME, so it cannot
# carry a query string, an extra path segment, a dot segment or a second line into a request.
for bad in https://github.com/fixture-owner/fixture-name/extra 'https://github.com/fixture-owner/fixture-name?x=1' \
           'https://github.com/fixture-owner/fixture-name&x' https://github.com/fixture-owner/.. \
           https://github.com/fixture-owner/. $'https://github.com/fixture-owner/fixture-name\nsecond-line'; do
  repo_check 2 'the repository must be OWNER/NAME' "$bad"
  [[ ! -s $STATE/calls ]] || { echo "FAIL: a request was made for a crafted origin ($bad)" >&2; exit 1; }
done

# --local-quality (opt-in): Quality pinned to pull_request runs of the workflow path, AND the
# latest local-quality status created by the expected publisher. Real jq over JSON fixtures; the
# fake gh refuses a push listing, any other URL, and any jq program but the pinned ones. Logins are
# synthetic. Fixtures: $LQ_FIX/runs-p<page>.json, statuses-p<page>.json or statuses-n<poll>-p<page>.json
# (<poll> is the pr view count), statuses-fail; absent files read as an empty listing.
export CI_STATUS_REPO=fixture/repository
# shellcheck disable=SC2016  # $n/$s/$c are jq variables, not shell expansions
LQ_RUNS_TEMPLATE='if (.workflow_runs|type) != "array" then "invalid" elif (.total_count // 0) > 1000 then "invalid" elif (.workflow_runs|length) == 0 then "0" else ([.workflow_runs[] | select(.event == "pull_request" and .path == "@WORKFLOW_PATH@")] | length) as $n | if $n == 0 then "more" else ($n|tostring) end end'
# The pinned template with the default workflow path substituted, exactly as the script must send it.
LQ_RUNS_JQ=${LQ_RUNS_TEMPLATE//@WORKFLOW_PATH@/.github/workflows/quality.yml}
# shellcheck disable=SC2016
LQ_STATUS_JQ='if type != "array" then "error|||" elif any(.[]; type != "object") then "error|||" elif length == 0 then "none|||" else ([.[] | select(.context == "local-quality")] | .[0]) as $s | if $s == null then (if length < 100 then "none|||" else "more|||" end) elif ($s.state | type) != "string" or ($s.creator | type) != "object" or ($s.creator.login | type) != "string" then "invalid|||" else (if $s.state == "success" then "lqsuccess" elif $s.state == "pending" then "lqpending" elif $s.state == "failure" or $s.state == "error" then "lqfail" else "invalid" end) as $c | if $c == "invalid" then "invalid|||" else $c + "|" + ($s.state | @base64) + "|" + ($s.creator.login | @base64) + "|" + (($s.description // "") | tostring | @base64) end end end'
export LQ_RUNS_JQ LQ_STATUS_JQ
grep -qF -- "$LQ_RUNS_TEMPLATE" "$HERE/pr-ci-registered.sh" || { echo 'FAIL: the local-mode registration jq drifted from the test pin' >&2; exit 1; }
# jq never reads the environment: the workflow path is a substituted literal, so an unsupported jq
# $ENV in gh can neither drop the pin nor change the default program.
if grep -qF -- '$ENV' "$HERE/pr-ci-registered.sh"; then echo 'FAIL: pr-ci-registered.sh uses jq $ENV' >&2; exit 1; fi
N=$((N + 1))
grep -qF -- "$LQ_STATUS_JQ" "$HERE/pr-ci-registered.sh" || { echo 'FAIL: the local-quality statuses jq drifted from the test pin' >&2; exit 1; }
export LQ_FIX=$WORK/lqfix
LQ_GH=$WORK/bin/fake-gh-lq
cat >"$LQ_GH" <<'EOF'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >>"$STATE/calls"
if [[ $1 == pr ]]; then
  [[ $# == 9 && $2 == view && $3 == 1058 && $5 == "$CI_STATUS_REPO" ]] || exit 90
  n=$(cat "$STATE/pr-count"); n=$((n + 1)); echo "$n" >"$STATE/pr-count"
  printf 'MERGEABLE\t%s\n' "$TEST_SHA"
elif [[ $1 == api ]]; then
  [[ $# == 4 && $3 == --jq ]] || exit 91
  page=${2##*&page=}
  n=$(cat "$STATE/pr-count")
  case $2 in
    "repos/$CI_STATUS_REPO/actions/runs?head_sha=$TEST_SHA&event=pull_request&per_page=100&page="*)
      [[ $4 == "$LQ_RUNS_JQ" ]] || exit 98
      f=$LQ_FIX/runs-p$page.json; [[ -f $f ]] || f=$LQ_FIX/no-runs.json
      jq -r "$4" "$f" ;;
    "repos/$CI_STATUS_REPO/commits/$TEST_SHA/statuses?per_page=100&page="*)
      [[ $4 == "$LQ_STATUS_JQ" ]] || exit 99
      [[ ! -f $LQ_FIX/statuses-fail ]] || exit 1
      f=$LQ_FIX/statuses-n$n-p$page.json; [[ -f $f ]] || f=$LQ_FIX/statuses-p$page.json
      [[ -f $f ]] || f=$LQ_FIX/no-statuses.json
      jq -r "$4" "$f" ;;
    *) exit 94 ;;
  esac
else
  exit 92
fi
EOF
chmod +x "$LQ_GH"
lq_reset() {
  rm -rf "$LQ_FIX"; mkdir -p "$LQ_FIX"
  printf '%s\n' '{"workflow_runs":[]}' >"$LQ_FIX/no-runs.json"
  printf '%s\n' '[]' >"$LQ_FIX/no-statuses.json"
  EXPC=fixture-publisher
}
lq_run() { # FILE [PATH] [EVENT]
  jq -n --arg p "${2:-.github/workflows/quality.yml}" --arg e "${3:-pull_request}" \
    '{workflow_runs: [{event:$e, path:$p, status:"in_progress"}]}' >"$LQ_FIX/$1"
}
lq_st() { jq -n --arg c "$1" --arg s "$2" --arg l "$3" '{context:$c, state:$s, creator:{login:$l}, description:"PENDING run=0a1b2c3d4e5f"}'; }
# lqcheck RC MESSAGE STATUS_CALLS SLEEPS ARGS...: run, then require the exit code, the single-line
# message, the number of statuses requests, the simulated sleeps, and a timeout wrapper on every call.
lqcheck() {
  local expected=$1 message=$2 status_calls=$3 sleeps=$4 rc=0 output got
  shift 4
  : >"$STATE/timeouts"; : >"$STATE/calls"; : >"$STATE/sleeps"; echo 0 >"$STATE/pr-count"
  output=$(PR_CI_REGISTERED_GH_BIN=$LQ_GH LOCAL_QUALITY_EXPECTED_CREATOR=$EXPC XDG_CONFIG_HOME=$WORK/lqxdg \
    "$REAL_TIMEOUT" -k "$CHECK_GRACE" "$CHECK_BOUND" bash "$HERE/pr-ci-registered.sh" "$@" 2>&1) || rc=$?
  got=$(grep -c 'statuses' "$STATE/calls" || :)
  if [[ $rc != "$expected" || $output != *"$message"* || $output == *$'\n'* || $got != "$status_calls" || $(paste -sd, "$STATE/sleeps") != "$sleeps" ]]; then
    printf 'FAIL local-quality %s: status=%s statuses=%s output=%s\n' "$*" "$rc" "$got" "$output" >&2
    cat "$STATE/calls" "$STATE/sleeps" >&2
    exit 1
  fi
  check_timeouts local-quality "$LQ_GH" "$@"
  N=$((N + 1))
}
# Registered on both sides: pending (and failure) count as REGISTERED, never as green.
lq_reset; lq_run runs-p1.json; lq_st local-quality pending fixture-publisher | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 0 'local-quality status (pending) registered' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
lqcheck 0 'registration is not a green result' 1 '' 1058 "$TEST_SHA" --timeout 0 --local-quality
lq_st local-quality failure fixture-publisher | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 0 'local-quality status (failure) registered' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
# Quality registered, no local-quality status: 5 naming the local side (unrelated contexts ignored).
lq_reset; lq_run runs-p1.json
{ lq_st local-quality-x success fixture-publisher; lq_st Local-Quality success fixture-publisher; } | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 5 'no local-quality status registered' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
lqcheck 5 'no local-quality status registered for' 2 1 1058 "$TEST_SHA" --local-quality --timeout 1
# The local status appears on the second poll: registered after one sleep.
lq_st local-quality pending fixture-publisher | jq -s . >"$LQ_FIX/statuses-n2-p1.json"
lqcheck 0 'local-quality status (pending) registered' 2 15 1058 "$TEST_SHA" --local-quality --timeout 30
# Quality missing, a push-event Quality run, or only another workflow's run: 5 naming Quality.
lq_reset; lq_st local-quality success fixture-publisher | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 5 'no Quality workflow run registered' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
lq_run runs-p1.json .github/workflows/quality.yml push
lqcheck 5 'no Quality workflow run registered' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
lq_run runs-p1.json .github/workflows/other.yml
lqcheck 5 'no Quality workflow run registered' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
# Creator check: a latest status by another login is an unknown state; an older one is not.
lq_reset; lq_run runs-p1.json
{ lq_st local-quality success fixture-intruder; lq_st local-quality pending fixture-publisher; } | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 2 'created by an unexpected login; state unknown' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
{ lq_st local-quality pending fixture-publisher; lq_st local-quality success fixture-intruder; } | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 0 'local-quality status (pending) registered' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
# Expected creator: missing or malformed exits 2 before any request; the XDG file is read.
lq_reset; lq_run runs-p1.json; lq_st local-quality pending fixture-publisher | jq -s . >"$LQ_FIX/statuses-p1.json"
EXPC=''
lqcheck 2 'missing or malformed expected publisher login' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
[[ ! -s $STATE/calls ]] || { echo 'FAIL: a request was made without the expected creator' >&2; exit 1; }
EXPC='bad login'
lqcheck 2 'missing or malformed expected publisher login' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
[[ ! -s $STATE/calls ]] || { echo 'FAIL: a request was made with a malformed creator' >&2; exit 1; }
mkdir -p "$WORK/lqxdg/local-quality"; printf 'fixture-publisher\n' >"$WORK/lqxdg/local-quality/expected-creator"
EXPC=''
lqcheck 0 'local-quality status (pending) registered' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
rm -rf "$WORK/lqxdg"
# Statuses failures, malformed entries and unknown states are unknown (2), never registered.
lq_reset; lq_run runs-p1.json; : >"$LQ_FIX/statuses-fail"
lqcheck 2 'state unknown' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
lq_reset; lq_run runs-p1.json; lq_st local-quality neutral fixture-publisher | jq -s . >"$LQ_FIX/statuses-p1.json"
lqcheck 2 'invalid local-quality status listing; state unknown' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
printf '%s\n' '[{"context":"local-quality","state":"pending"}]' >"$LQ_FIX/statuses-p1.json"
lqcheck 2 'invalid local-quality status listing; state unknown' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
printf '%s\n' '{"message":"Not Found"}' >"$LQ_FIX/statuses-p1.json"
lqcheck 2 'invalid local-quality status listing; state unknown' 1 '' 1058 "$TEST_SHA" --local-quality --timeout 0
# Pagination: page 2 behind 100 other contexts is found; ten full pages are the bound.
lq_reset; lq_run runs-p1.json
jq -n '[range(100) | {context:"other", state:"success", creator:{login:"fixture-publisher"}}]' >"$LQ_FIX/statuses-p1.json"
lq_st local-quality pending fixture-publisher | jq -s . >"$LQ_FIX/statuses-p2.json"
lqcheck 0 'local-quality status (pending) registered' 2 '' 1058 "$TEST_SHA" --local-quality --timeout 0
for page in {2..10}; do cp "$LQ_FIX/statuses-p1.json" "$LQ_FIX/statuses-p$page.json"; done
lq_st local-quality pending fixture-publisher | jq -s . >"$LQ_FIX/statuses-p11.json"
lqcheck 2 'status page bound reached; state unknown' 10 '' 1058 "$TEST_SHA" --local-quality --timeout 0
# Invalid workflow path override and argument grammar.
lq_reset; lq_run runs-p1.json
CI_STATUS_WORKFLOW_PATH='.github/workflows/q.yml" or true' lqcheck 2 'CI_STATUS_WORKFLOW_PATH must name' 0 '' 1058 "$TEST_SHA" --local-quality --timeout 0
for args in '--local-quality --local-quality' '--timeout 5 --timeout 5' '--local-quality --timeout' '--local-quality --bogus' '--local-quality 1'; do
  # shellcheck disable=SC2086  # deliberate word splitting of the argument variants
  lqcheck 2 usage 0 '' 1058 "$TEST_SHA" $args
done
# The real jq: the local program counts only pull_request runs of the pinned path.
lqjq() {
  local got
  got=$(printf '%s' "$2" | jq -r "$LQ_RUNS_JQ")
  [[ $got == "$1" ]] || { printf 'FAIL local jq fixture: want %s got %s for %s\n' "$1" "$got" "$2" >&2; exit 1; }
  N=$((N + 1))
}
lqjq 1 '{"workflow_runs":[{"event":"pull_request","path":".github/workflows/quality.yml"}]}'
lqjq more '{"workflow_runs":[{"event":"push","path":".github/workflows/quality.yml"}]}'
lqjq more '{"workflow_runs":[{"event":"pull_request","path":".github/workflows/other.yml"}]}'
lqjq 0 '{"workflow_runs":[]}'
lqjq invalid '{}'
printf 'PASS: pr-ci-registered (%s cases)\n' "$N"
