#!/usr/bin/env bash
# Hermetic regression harness for tools/ci-status.sh: the --wait registration grace, report-once,
# repository selection and --local-quality.
#
# It exercises the real script with NO live PR, NO network, and NO real waiting. Temporary PATH
# shims for gh, date, sleep, timeout, and git make time advance deterministically and script
# each query outcome. Simulated "now" lives in a state file that the sleep shim advances; the
# gh shim returns a scripted (RC, payload) per call; a date sequence file drives the clock for
# the clock-change cases. The hung-request, surviving-grandchild and signal-cleanup sections use
# real processes, because simulated time cannot show that timeout(1) actually terminates a child.
# The gh shim and the fixture gh are the only gh this harness runs; it needs no network.
#
# Payloads are the STRINGS that `gh api --jq '...'` emits. jq decides the CATEGORY itself and
# base64-encodes the display fields, so a run line is
#   category|b64(status)|b64(conclusion)|b64(name)|b64(html_url)
# and the sentinels are "norun||||" (empty run array) and "error||||" (non-array workflow_runs).
# The helpers run_resp / norun_resp build those lines from human-readable fields (via emit_run,
# which mirrors the script's jq). "__EMPTY__" is empty stdout with exit 0. Most sections test the
# script's state machine given jq output; the real-jq and --local-quality sections run the
# script's own jq programs with standalone jq. Simulated budgets are kept small (at most a few
# dozen polls per case), because every poll starts several processes; each section header shows
# the harness's elapsed seconds so far.
set -uo pipefail
# Hermetic against the host environment: settings the script or the shims read are cleared here,
# so an exported value cannot turn a case red (or green). Cases that need one set it themselves.
unset CI_STATUS_REPO CI_STATUS_TIMEOUT CI_STATUS_REGISTRATION_GRACE CI_STATUS_WORKFLOW_PATH \
  LOCAL_QUALITY_EXPECTED_CREATOR XDG_CONFIG_HOME BASH_ENV GIT_DIR GIT_WORK_TREE \
  PAGE_FIXTURES EVENT_FIXTURES ENDLESS_PAGES SLOW_PAGES

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${CI_STATUS_SCRIPT:-$HERE/ci-status.sh}"
if [ ! -f "$SCRIPT" ]; then
  printf 'FAIL: script under test not found at %s (set CI_STATUS_SCRIPT to override)\n' "$SCRIPT" >&2
  exit 1
fi
REAL_TIMEOUT="$(command -v timeout)"
if [ -z "$REAL_TIMEOUT" ]; then
  printf 'FAIL: GNU timeout is required for this harness\n' >&2
  exit 1
fi
# Real mktemp, captured so the signal-cleanup shim below can create a real temp file without
# recursing into a same-named shim on PATH. Exported so the shim invocation inherits it.
REAL_MKTEMP="$(command -v mktemp)"
if [ -z "$REAL_MKTEMP" ]; then
  printf 'FAIL: mktemp is required for this harness\n' >&2
  exit 1
fi
export REAL_MKTEMP

# Create the scratch root FIRST and prove it is a real directory BEFORE deriving SHIMDIR/STATE from
# it. A silent mktemp -d failure that left WORK empty would otherwise make SHIMDIR="/bin" and the
# heredocs below write shims into /bin; the guard makes that impossible (fail closed instead).
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ci-status-test.XXXXXX")" || { printf 'FATAL: mktemp -d failed\n' >&2; exit 1; }
if [ -z "$WORK" ] || [ ! -d "$WORK" ]; then
  printf 'FATAL: mktemp -d did not yield a directory (got: %s)\n' "$WORK" >&2
  exit 1
fi
SHIMDIR="$WORK/bin"
STATE="$WORK/state"
mkdir -p "$SHIMDIR" "$STATE"
# shellcheck disable=SC2329  # invoked indirectly via the EXIT trap below
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
export STATE

# --- write the PATH shims (single-quoted heredocs: $STATE is resolved at shim runtime) ---

# The gh shim records the full request URL (the arg carrying head_sha=) per call, so a test can
# assert every gh call targeted the configured repo at the fully-resolved SHA.
cat >"$SHIMDIR/gh" <<'EOF'
#!/usr/bin/env bash
set -u
for a in "$@"; do
  case "$a" in *head_sha=*) printf '%s\n' "$a" >>"$STATE/gh_urls" ;; esac
done
# The scripted state-machine sequences model the pull_request listing; the push listing is
# empty. Full URL recording above still records BOTH requests.
if [[ $2 == *'&event=push&'* && -z ${EVENT_FIXTURES:-} ]]; then
  printf 'norun||||'
  exit 0
fi
if [[ -n ${EVENT_FIXTURES:-} ]]; then
  [[ $2 == *'&page=1' ]] || exit 94
  case $2 in
    *'&event=pull_request&'*) event=pull_request ;;
    *'&event=push&'*) event=push ;;
    *) exit 95 ;;
  esac
  if [[ -f $EVENT_FIXTURES/all.json ]]; then
    # Simulate a deletion after page 1: filtering must precede slicing.
    jq --arg event "$event" '{workflow_runs: [.workflow_runs[] | select(.event == $event)][:100]}' "$EVENT_FIXTURES/all.json" >"$EVENT_FIXTURES/reply.json"
    jq '.workflow_runs |= .[1:]' "$EVENT_FIXTURES/all.json" >"$EVENT_FIXTURES/next.json"
    mv "$EVENT_FIXTURES/next.json" "$EVENT_FIXTURES/all.json"
    jq -r "$4" "$EVENT_FIXTURES/reply.json"
  else
    jq -r "$4" "$EVENT_FIXTURES/$event.json"
  fi
  exit
fi
c=$(cat "$STATE/ghcount" 2>/dev/null || echo 0); c=$((c+1)); printf '%s' "$c" >"$STATE/ghcount"
printf '%s\n' "$c" >>"$STATE/ghlog"
if [[ -n ${PAGE_FIXTURES:-} ]]; then
  [[ $2 == *'&per_page=100&page='* ]] || exit 91
  page=${2##*&page=}
  [[ ${ENDLESS_PAGES:-0} == 1 ]] && page=1
  [[ ${SLOW_PAGES:-0} == 1 ]] && /bin/sleep 1
  jq -r "$4" "$PAGE_FIXTURES/$page.json"
  exit
fi
line=$(sed -n "${c}p" "$STATE/responses")
[ -z "$line" ] && line=$(tail -n1 "$STATE/responses")
rc=${line%%$'\t'*}
out=${line#*$'\t'}
[ "$out" = "__EMPTY__" ] && out=""
printf '%s' "$out"
case "$out" in
  success\|*|otherterm\|*|nonterm\|*) printf '\n2026-10-31T00:00:00Z' ;;
esac
exit "$rc"
EOF

cat >"$SHIMDIR/date" <<'EOF'
#!/usr/bin/env bash
set -u
want_s=0
for a in "$@"; do [ "$a" = "+%s" ] && want_s=1; done
if [ "$want_s" = 1 ]; then
  if [ -f "$STATE/date_seq" ]; then
    c=$(cat "$STATE/date_calls" 2>/dev/null || echo 0); c=$((c+1)); printf '%s' "$c" >"$STATE/date_calls"
    v=$(sed -n "${c}p" "$STATE/date_seq"); [ -z "$v" ] && v=$(tail -n1 "$STATE/date_seq")
    printf '%s\n' "$v"
  else
    cat "$STATE/now"
  fi
  exit 0
fi
printf '00:00:00Z\n'
exit 0
EOF

cat >"$SHIMDIR/sleep" <<'EOF'
#!/usr/bin/env bash
set -u
amt=${1:-0}
cur=$(cat "$STATE/now" 2>/dev/null || echo 0)
printf '%s' "$(( cur + amt ))" >"$STATE/now"
exit 0
EOF

# The timeout shim records each invocation's kill-grace value (the N in a leading -k N, empty if the
# flag is absent) AND its duration argument, so a test can assert every gh call is wrapped, carries
# -k KILL_GRACE, and its duration is within the expected bounds. Removing -k from the production call
# leaves an empty kill-grace record, which the all_kill_grace_eq assertion catches.
#
# The counters record PR-listing invocations wrapping `gh`; both event URLs
# are recorded by the gh shim. The event fixtures separately require both requests.
# The `-k` support probe in ci-status.sh runs `timeout -k 1 1 true` during preflight; that
# call wraps `true`, not `gh`, so it is deliberately NOT recorded and cannot perturb the durcount ==
# ghcount or all_kill_grace_eq assertions.
cat >"$SHIMDIR/timeout" <<'EOF'
#!/usr/bin/env bash
set -u
k=""
while [ "${1:-}" = "-k" ]; do k="${2:-}"; shift 2; done
dur="${1:-}"
shift
if [ "${1:-}" = "gh" ] && [[ ${3:-} != *'&event=push&'* ]]; then
  printf '%s\n' "$k" >>"$STATE/timeout_kill_graces"
  printf '%s\n' "$dur" >>"$STATE/timeout_durations"
fi
exec "$@"
EOF

# The git shim resolves rev-parse deterministically. ci-status.sh resolves the rev against its OWN
# checkout, issuing first `git rev-parse --show-toplevel` and then
# `git -C <toplevel> rev-parse --verify --quiet <rev>`, scrubbing GIT_DIR/GIT_WORK_TREE via `env -u`
# and resolving the script symlink via readlink -f. Because the scrub happens BEFORE git runs and the
# -C flag is passed explicitly, this shim must: (1) record a leading -C <dir>; (2) answer
# --show-toplevel with a stable repo root, /repo; (3) resolve any non-BADREV rev to the fixed 40-hex
# SHIM_SHA and fail (exit 1) on a BADREV rev; (4) answer `remote get-url origin` with the content of
# $STATE/origin ONLY for `git -C /repo`, the script's own checkout, and otherwise fail (exit 2, no
# such remote), so an origin lookup that is not pinned to that checkout finds no repository. It
# ignores every other git subcommand. (The env-scrub and symlink resolution are exercised by a
# dedicated recording git shim in the rev-pinning section.)
cat >"$SHIMDIR/git" <<'EOF'
#!/usr/bin/env bash
set -u
dir=""
while [ "${1:-}" = "-C" ]; do dir="${2:-}"; shift 2; done
if [ "${1:-}" = "remote" ] && [ "${2:-}" = "get-url" ] && [ "${3:-}" = "origin" ]; then
  [ "$dir" = /repo ] || exit 2
  [ -f "$STATE/origin" ] || exit 2
  cat "$STATE/origin"
  exit 0
fi
if [ "${1:-}" = "rev-parse" ]; then
  shift
  for a in "$@"; do
    case "$a" in --show-toplevel) printf '/repo\n'; exit 0 ;; esac
  done
  last=""
  for a in "$@"; do last="$a"; done
  case "$last" in
    BADREV*) exit 1 ;;
    *) printf '0123456789abcdef0123456789abcdef01234567\n'; exit 0 ;;
  esac
fi
exit 0
EOF

chmod +x "$SHIMDIR"/*

# The full 40-hex SHA the git shim resolves every (non-BADREV) rev to.
SHIM_SHA="0123456789abcdef0123456789abcdef01234567"

# --- test scaffolding ---

N=0
FAILS=0
T="900"   # CI_STATUS_TIMEOUT for the next invoke
G="900"   # CI_STATUS_REGISTRATION_GRACE for the next invoke
OUT=""
RC=0

reset_state() { # [init_now]
  : >"$STATE/responses"
  printf '0' >"$STATE/ghcount"
  : >"$STATE/ghlog"
  : >"$STATE/gh_urls"
  : >"$STATE/timeout_durations"
  : >"$STATE/timeout_kill_graces"
  printf '%s' "${1:-0}" >"$STATE/now"
  rm -f "$STATE/date_seq" "$STATE/date_calls" "$STATE/origin"
}

resp() { printf '%s\t%s\n' "$1" "$2" >>"$STATE/responses"; }

# emit_run STATUS CONCLUSION NAME URL: the line `gh api --jq '...'` emits for one run, i.e.
# category|b64(status)|b64(conclusion)|b64(name)|b64(html_url). base64 -w0 matches jq @base64.
#
# COUPLING (keep in sync): emit_run and its callers run_resp / norun_resp model the EXACT output
# shape of ci-status.sh's `--jq` program (the category token plus four @base64 display fields joined
# by "|", and the "norun||||" / "error||||" sentinels). This harness tests the bash state machine
# GIVEN that jq output; it does NOT run jq itself. If ci-status.sh's jq program changes its category
# tokens, field order, delimiter, or encoding, these helpers MUST be updated to match, or the harness
# will silently test the wrong shape.
emit_run() {
  local s="$1" c="$2" n="$3" u="$4" cat
  case "$s" in
    completed) if [ "$c" = "success" ]; then cat="success"; else cat="otherterm"; fi ;;
    queued|in_progress|waiting|requested|pending|action_required) cat="nonterm" ;;
    *) cat="error" ;;
  esac
  printf '%s|%s|%s|%s|%s' "$cat" \
    "$(printf '%s' "$s" | base64 -w0)" \
    "$(printf '%s' "$c" | base64 -w0)" \
    "$(printf '%s' "$n" | base64 -w0)" \
    "$(printf '%s' "$u" | base64 -w0)"
}

run_resp()   { resp 0 "$(emit_run "$1" "$2" "$3" "$4")"; }  # a scripted successful (rc 0) run response
norun_resp() { resp 0 "norun||||"; }                        # the empty-run-array sentinel jq emits

seq_set() { printf '%s\n' "$@" >"$STATE/date_seq"; printf '0' >"$STATE/date_calls"; }

invoke() { # args -> ci-status.sh
  OUT="$("$REAL_TIMEOUT" 20 env PATH="$SHIMDIR:$PATH" STATE="$STATE" \
        CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
        bash "$SCRIPT" "$@" 2>&1)"
  RC=$?
}

# invoke_defaults: as invoke, but with both budget variables unset, so the script's own defaults apply.
invoke_defaults() { # args -> ci-status.sh
  OUT="$("$REAL_TIMEOUT" 20 env -u CI_STATUS_TIMEOUT -u CI_STATUS_REGISTRATION_GRACE \
        PATH="$SHIMDIR:$PATH" STATE="$STATE" CI_STATUS_REPO="test/repo" \
        bash "$SCRIPT" "$@" 2>&1)"
  RC=$?
}

# invoke_origin: as invoke, but with CI_STATUS_REPO unset, so the repository must come from the
# origin remote (the git shim answers from $STATE/origin, or fails when it is absent).
invoke_origin() { # args -> ci-status.sh
  OUT="$("$REAL_TIMEOUT" 20 env -u CI_STATUS_REPO PATH="$SHIMDIR:$PATH" STATE="$STATE" \
        CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
        bash "$SCRIPT" "$@" 2>&1)"
  RC=$?
}

ghcount()  { cat "$STATE/ghcount"; }
simnow()   { cat "$STATE/now"; }
durcount() { wc -l < "$STATE/timeout_durations" | tr -d ' '; }
urlcount() { wc -l < "$STATE/gh_urls" | tr -d ' '; }
lastdur()  { tail -n1 "$STATE/timeout_durations"; }
firstdur() { head -n1 "$STATE/timeout_durations"; }

# all_kill_grace_eq N: true iff at least one timeout invocation was recorded AND every recorded
# kill-grace value equals N. An invocation with no -k flag records an empty value, so removing
# `-k "$KILL_GRACE"` from the production call makes this FAIL.
all_kill_grace_eq() {
  local ok=1 had=0 k
  while IFS= read -r k; do
    had=1
    [ "$k" = "$1" ] || ok=0
  done < "$STATE/timeout_kill_graces"
  [ "$had" = 1 ] && [ "$ok" = 1 ]
}

# all_dur_in_range MAX: true iff every recorded timeout duration is an integer in (0, MAX].
all_dur_in_range() {
  local ok=1 d
  while IFS= read -r d; do
    case "$d" in ''|*[!0-9]*) ok=0; continue ;; esac
    if [ "$d" -le 0 ] || [ "$d" -gt "$1" ]; then ok=0; fi
  done < "$STATE/timeout_durations"
  [ "$ok" = 1 ]
}

# all_urls_have S1 S2: true iff every recorded gh URL contains both substrings.
all_urls_have() {
  local ok=1 u
  while IFS= read -r u; do
    grep -qF -- "$1" <<<"$u" || ok=0
    grep -qF -- "$2" <<<"$u" || ok=0
  done < "$STATE/gh_urls"
  [ "$ok" = 1 ]
}

pass()  { N=$((N+1)); printf '  ok    %s\n' "$1"; }
failc() { N=$((N+1)); FAILS=$((FAILS+1)); printf '  FAIL  %s\n' "$1"; }

ck_rc() { # want desc
  if [ "$RC" = "$1" ]; then pass "$2 (rc=$RC)"; else failc "$2 (want rc=$1 got rc=$RC; out=<<$OUT>>)"; fi
}
ck_has() { # needle desc
  if grep -qF -- "$1" <<<"$OUT"; then pass "$2"; else failc "$2 (missing '$1'; out=<<$OUT>>)"; fi
}
ck_hasnt() { # needle desc
  if grep -qF -- "$1" <<<"$OUT"; then failc "$2 (unexpected '$1'; out=<<$OUT>>)"; else pass "$2"; fi
}
ck_eq() { # got want desc
  if [ "$1" = "$2" ]; then pass "$3 ($1)"; else failc "$3 (want $2 got $1)"; fi
}
ck_ne0() { # got desc  -- asserts value is not "0"
  if [ "$1" != "0" ]; then pass "$2 (rc=$1)"; else failc "$2 (rc must never be 0)"; fi
}

section() { printf '\n== %s (at %ss) ==\n' "$1" "$SECONDS"; }

# ============================ tests ============================

section "success paths"

# >15 empty polls, then pending, then success within budgets -> 0
reset_state; T=900; G=900
i=0; while [ "$i" -lt 16 ]; do norun_resp; i=$((i+1)); done
run_resp queued - Quality http://run
run_resp completed success Quality http://run
invoke HEAD --wait
ck_rc 0 "16 empty polls then pending then success"
ck_eq "$(ghcount)" 18 "  performed 18 queries (>15 empty polls)"
if [ "$(simnow)" -lt 900 ]; then pass "  succeeded inside the overall budget"; else failc "  succeeded inside the overall budget (simnow=$(simnow))"; fi
# request-bounding coverage: every gh call is wrapped in timeout, and every URL targets the repo/SHA
ck_eq "$(durcount)" "$(ghcount)" "  every PR-listing call wrapped in timeout (durations == queries)"
if all_kill_grace_eq 5; then pass "  every timeout invocation carried -k 5 (KILL_GRACE)"; else failc "  every timeout invocation carried -k 5 (KILL_GRACE)"; fi
if all_dur_in_range 60; then pass "  each request duration in (0, 60]"; else failc "  each request duration in (0, 60]"; fi
ck_eq "$(urlcount)" "$((2 * $(ghcount)))" "  every gh call recorded a request URL"
if all_urls_have "test/repo" "head_sha=$SHIM_SHA"; then pass "  every gh URL targets test/repo at the full SHA"; else failc "  every gh URL targets test/repo at the full SHA"; fi

# pending appears just before the grace boundary, success after grace before overall deadline -> 0
reset_state; T=120; G=60
i=0; while [ "$i" -lt 3 ]; do norun_resp; i=$((i+1)); done  # polls at now=0..30
run_resp queued - Q http://r      # poll 4 at now=45 (before boundary 60): registers
run_resp queued - Q http://r      # poll 5 at now=60
run_resp completed success Q http://r  # poll 6 at now=75
invoke HEAD --wait
ck_rc 0 "registration just before grace boundary, success after grace"
if [ "$(simnow)" -gt 60 ]; then pass "  success landed after the grace boundary"; else failc "  success after grace (simnow=$(simnow))"; fi

# pending observed EXACTLY on the grace boundary (only remaining overall budget), success later -> 0
reset_state; T=120; G=60
i=0; while [ "$i" -lt 4 ]; do norun_resp; i=$((i+1)); done  # polls at now=0..45
run_resp queued - Q http://r      # poll 5 is the boundary query at now=60
run_resp completed success Q http://r
invoke HEAD --wait
ck_rc 0 "registration exactly on grace boundary, success before overall deadline"
if [ "$(simnow)" -gt 60 ]; then pass "  success landed after the grace boundary"; else failc "  success after grace (simnow=$(simnow))"; fi

# transient startup errors, then valid registration, then success -> 0
reset_state; T=120; G=60
resp 1 "HTTP 503: upstream unavailable"
resp 1 "HTTP 503: upstream unavailable"
run_resp queued - Q http://r
run_resp completed success Q http://r
invoke HEAD --wait
ck_rc 0 "transient errors then registration then success"

section "request sizing (mutation sensitivity: remaining budget vs fixed 60)"

# On a SMALL budget the first ordinary request must be sized to the remaining budget, not to the
# fixed PER_REQUEST_MAX. With T=30 G=30 the first poll is at now=0 with EFF_GRACE=30 remaining, so
# req_to = min(remaining=30, PER_REQUEST_MAX=60) = 30. The expected value is computed from the
# scenario's known budget (30), not read from the script. A mutation that hardcodes `query 60`
# records 60 for the first request and FAILS this assertion because 60 != 30.
reset_state; T=30; G=30
norun_resp
invoke HEAD --wait
ck_rc 2 "small-budget absence (T=30 G=30)"
ck_eq "$(firstdur)" 30 "  first ordinary request sized to remaining budget (min(30,60)=30), not a hardcoded 60"

section "absence (registration expiry)"

# empty throughout a shorter grace -> 2 absence, finishes well before the overall timeout
reset_state; T=900; G=120
norun_resp
invoke HEAD --wait
ck_rc 2 "empty throughout grace -> absence"
ck_has "RESULT: ABSENCE" "  absence diagnostic present"
ck_has "OBSERVED within" "  absence says no run observed within grace"
ck_eq "$(simnow)" 120 "  stopped at the grace boundary (before overall timeout)"
ck_eq "$(lastdur)" 60 "  final boundary query used the fixed 60s allowance"

# grace greater than timeout is clamped; uninterrupted absence -> 2 with no extra timeout cycle
reset_state; T=60; G=5000
norun_resp
invoke HEAD --wait
ck_rc 2 "grace>timeout clamped, uninterrupted absence"
ck_has "RESULT: ABSENCE" "  absence diagnostic (not timeout)"
ck_hasnt "RESULT: TIMEOUT" "  no extra timeout cycle after clamp"
ck_eq "$(simnow)" 60 "  stopped at the clamped boundary (== timeout)"

section "startup errors"

# startup errors throughout grace -> 2 error diagnostic (distinct from absence)
reset_state; T=900; G=120
resp 1 "HTTP 403: Resource not accessible by personal access token"
invoke HEAD --wait
ck_rc 2 "startup errors throughout grace -> error"
ck_has "RESULT: ERROR" "  error diagnostic present"
ck_hasnt "RESULT: ABSENCE" "  error does not masquerade as absence"
# An error NEVER sets run_seen, so the active budget stays the registration grace: the run stops at
# the grace boundary (120), not the overall timeout (900). A mutant that sets run_seen=1 in the error
# arm would switch to the overall budget and ride to 900, which this assertion catches.
ck_eq "$(simnow)" 120 "  error never set run_seen (stopped at grace boundary 120, not overall 900)"

# an ERROR arriving EXACTLY on the registration boundary after a norun history -> 2 error (not absence)
reset_state; T=900; G=60
norun_resp; norun_resp; norun_resp; norun_resp   # polls at now=0,15,30,45
resp 1 "HTTP 500: internal server error"          # boundary query at now=60 errors
invoke HEAD --wait
ck_rc 2 "error on the registration boundary (after norun) -> error"
ck_has "RESULT: ERROR" "  boundary error is an ERROR"
ck_hasnt "RESULT: ABSENCE" "  boundary error is not misreported as absence"

section "observed-run timeout and post-observation behaviour"

# pending through the overall deadline -> 1; registration time consumed part of the 120
reset_state; T=120; G=60
norun_resp; norun_resp; norun_resp  # registration spends 3 polls
run_resp in_progress - Q http://r   # then pending forever
invoke HEAD --wait
ck_rc 1 "pending through overall deadline -> timeout"
ck_has "RESULT: TIMEOUT" "  timeout diagnostic present"
ck_eq "$(simnow)" 120 "  overall deadline unchanged (registration consumed part of the budget)"

# empty after observation: never returns to registration; persistent absence ends at overall -> 1
reset_state; T=90; G=30
run_resp queued - Q http://r   # observed
norun_resp                     # then empty forever
invoke HEAD --wait
ck_rc 1 "empty after observation -> ends within overall deadline"
ck_hasnt "RESULT: ABSENCE" "  does not revert to absence after observation"
ck_eq "$(simnow)" 90 "  ran to the overall deadline, not the grace boundary"

# errors after observation: recovery still possible within the deadline -> 0
reset_state; T=90; G=30
run_resp queued - Q http://r
resp 1 "HTTP 503"
resp 1 "HTTP 503"
run_resp completed success Q http://r
invoke HEAD --wait
ck_rc 0 "errors after observation, then recovery -> success"

# errors after observation, never resolving -> 2 error
reset_state; T=90; G=30
run_resp queued - Q http://r
resp 1 "HTTP 503"
invoke HEAD --wait
ck_rc 2 "errors after observation, unresolved -> error"
ck_has "RESULT: ERROR" "  error diagnostic present"
ck_eq "$(simnow)" 90 "  rode errors through to the overall deadline"

section "terminal conclusions (including on the final boundary query)"

reset_state; T=900; G=900; run_resp completed success Q http://r;   invoke HEAD --wait; ck_rc 0 "completed success -> 0"
reset_state; T=900; G=900; run_resp completed failure Q http://r;   invoke HEAD --wait; ck_rc 1 "completed failure -> 1"
reset_state; T=900; G=900; run_resp completed cancelled Q http://r; invoke HEAD --wait; ck_rc 1 "completed cancelled -> 1"
reset_state; T=900; G=900; run_resp completed - Q http://r;         invoke HEAD --wait; ck_rc 1 "completed with missing conclusion -> 1"

# success arriving exactly on the final boundary query -> 0 (observation processed before expiry)
reset_state; T=60; G=60
norun_resp; norun_resp; norun_resp; norun_resp
run_resp completed success Q http://r   # poll 5 at now=60 (boundary)
invoke HEAD --wait
ck_rc 0 "success on the final boundary query -> 0"

# failure arriving on the final boundary query -> 1
reset_state; T=60; G=60
norun_resp; norun_resp; norun_resp; norun_resp
run_resp completed failure Q http://r
invoke HEAD --wait
ck_rc 1 "failure on the final boundary query -> 1"

section "never a false green"

# null status (empty first field) -> never 0 (report-once error)
reset_state; T=900; G=900; run_resp "" "-" Q http://r; invoke HEAD; ck_ne0 "$RC" "null status never 0"; ck_rc 2 "  null status -> report-once error (2)"
# malformed / non-json response with rc!=0 -> never 0
reset_state; T=900; G=900; resp 1 '{"unexpected'; invoke HEAD; ck_ne0 "$RC" "malformed response never 0"; ck_rc 2 "  malformed -> error (2)"
# a FAILED gh call whose field 1 is a genuine "success" category token -> never 0 (rc inspected
# first). Using emit_run puts a real category token in field 1 (not the "completed" non-token the
# classify validation would already coerce to error), so a mutant that SKIPS the rc-first check would
# read field 1 = success and exit 0, and these assertions fail fast on the designed rc-first invariant.
reset_state; T=900; G=900; resp 1 "$(emit_run completed success Evil http://r)"; invoke HEAD; ck_ne0 "$RC" "failed call with success-token field 1 never 0 (report-once, rc-first)"
reset_state; T=0; G=0; resp 1 "$(emit_run completed success Evil http://r)"; invoke HEAD --wait; ck_ne0 "$RC" "failed call with success-token field 1 never 0 (--wait, rc-first)"; ck_rc 2 "  classified as error (2)"
# empty stdout with rc 0 -> the classify empty-stdout guard maps it to error (report-once) -> 2. A
# mutant that dropped `if [ -z "$Q_OUT" ]` would cut an empty field 1 and (after the category
# validation) still land on error, so this documents and locks the empty-stdout branch explicitly.
reset_state; T=900; G=900; resp 0 "__EMPTY__"; invoke HEAD; ck_rc 2 "empty stdout (rc 0) -> report-once error (classify empty-stdout guard)"
# a success CATEGORY token whose decoded fields DISAGREE (status/conclusion not completed+success) is
# downgraded to error by the classify cross-check, so it can never emit a false green. A well-formed
# 5-field line with field 1 = success but status="in_progress" exercises exactly that path.
success_bad="success|$(printf '%s' in_progress | base64 -w0)|$(printf '%s' success | base64 -w0)|$(printf '%s' Q | base64 -w0)|$(printf '%s' http://r | base64 -w0)"
reset_state; T=900; G=900; resp 0 "$success_bad"; invoke HEAD; ck_ne0 "$RC" "success token with non-completed status never 0 (classify cross-check)"; ck_rc 2 "  cross-check downgrades to error (2)"
# a line-shape violation (too few "|" fields) with rc 0 is treated as error, never trusted as a
# category. A mutant that dropped the pipe-count guard would cut field 1 = "success" and false-green.
reset_state; T=900; G=900; resp 0 "success|only|three"; invoke HEAD; ck_ne0 "$RC" "wrong field count never 0 (classify line-shape guard)"; ck_rc 2 "  malformed field count -> error (2)"

section "delimiter injection and changing runs"

# a workflow name containing '|' cannot shift the gating fields (real success stays success)
reset_state; T=900; G=900; run_resp completed success "weird|name|with|pipes" http://x; invoke HEAD; ck_rc 0 "name with pipes: real success still 0"
# an injected 'completed|success' inside the NAME cannot make a non-terminal run terminal
reset_state; T=900; G=900; run_resp in_progress - "x|completed|success" http://y; invoke HEAD; ck_rc 1 "name-injected 'completed|success' cannot fake terminal (report-once pending -> 1)"

# newest run changing between polls cannot restart either deadline
reset_state; T=60; G=60
run_resp in_progress - RunA http://a
run_resp queued - RunB http://b
run_resp in_progress - RunC http://c
invoke HEAD --wait
ck_rc 1 "changing newest run -> still times out"
ck_eq "$(simnow)" 60 "  deadline not restarted by a changing newest run"

section "control-char sanitization (no forged console lines)"

# A decoded display field carrying an embedded newline must NOT be able to start a forged console
# line. classify passes STATUS/CONCL/NAME/URL through the printable-ASCII allowlist (_display_safe),
# so an injected "INJECTEDMARKER" after a newline in NAME is folded into the name field rather than
# beginning its own line. A mutant that dropped the sanitize FAILS the grep-at-line-start check.
reset_state; T=900; G=900
nl=$'\n'
resp 0 "$(emit_run completed success "Quality${nl}INJECTEDMARKER" http://r)"
invoke HEAD
ck_rc 0 "control-char name: real success still 0"
if grep -q '^INJECTEDMARKER' <<<"$OUT"; then
  failc "  newline in name cannot start a forged console line (control chars stripped)"
else
  pass "  newline in name cannot start a forged console line (control chars stripped)"
fi
# same for a URL carrying a newline + forged line
reset_state; T=900; G=900
resp 0 "$(emit_run completed success Q "http://r${nl}INJECTEDURL")"
invoke HEAD
ck_rc 0 "control-char url: real success still 0"
if grep -q '^INJECTEDURL' <<<"$OUT"; then
  failc "  newline in url cannot start a forged console line (control chars stripped)"
else
  pass "  newline in url cannot start a forged console line (control chars stripped)"
fi
# C1 and DEL: a name carrying U+009B (8-bit CSI, UTF-8 bytes 0xC2 0x9B) and a DEL byte (0x7F) must
# reach the console with neither byte, and the exit code must equal the same run with a clean name.
# A mutant that narrowed the allowlist back to a C0-only strip FAILS the byte checks.
c1name="$(printf 'Qual\xc2\x9b31mRED\xc2\x9b0mity\x7f')"
c1seq=$'\xc2\x9b'
delbyte=$'\x7f'
reset_state; T=900; G=900
resp 0 "$(emit_run completed failure Quality http://r)"
invoke HEAD
CLEAN_RC="$RC"
reset_state; T=900; G=900
resp 0 "$(emit_run completed failure "$c1name" http://r)"
invoke HEAD
ck_eq "$RC" "$CLEAN_RC" "C1/DEL name: exit code unchanged versus clean name"
if LC_ALL=C grep -qF -- "$c1seq" <<<"$OUT"; then
  failc "  C1 CSI (0xC2 0x9B) in name does not reach the console"
else
  pass "  C1 CSI (0xC2 0x9B) in name does not reach the console"
fi
if LC_ALL=C grep -qF -- "$delbyte" <<<"$OUT"; then
  failc "  DEL (0x7F) in name does not reach the console"
else
  pass "  DEL (0x7F) in name does not reach the console"
fi
if grep -qF -- "Qual31mRED0mity" <<<"$OUT"; then
  pass "  sanitized name keeps its printable ASCII characters"
else
  failc "  sanitized name keeps its printable ASCII characters (out=<<$OUT>>)"
fi
# The raw diagnostic (gh error text echoed on the error path) is sanitized the same way (_diag_safe).
reset_state; T=900; G=900
resp 1 "HTTP 500: upstream"
invoke HEAD
CLEAN_RC="$RC"
reset_state; T=900; G=900
resp 1 "$(printf 'HTTP 500: up\xc2\x9b31mstream\x7f')"
invoke HEAD
ck_eq "$RC" "$CLEAN_RC" "C1/DEL raw diagnostic: exit code unchanged versus clean text"
if LC_ALL=C grep -qF -- "$c1seq" <<<"$OUT" || LC_ALL=C grep -qF -- "$delbyte" <<<"$OUT"; then
  failc "  C1 CSI and DEL in gh diagnostic text do not reach the console"
else
  pass "  C1 CSI and DEL in gh diagnostic text do not reach the console"
fi
if grep -qF -- "raw: " <<<"$OUT"; then
  pass "  error path still prints the sanitized raw diagnostic"
else
  failc "  error path still prints the sanitized raw diagnostic (out=<<$OUT>>)"
fi

section "real jq category derivation (extracted production program)"

# The rest of the harness models jq output with emit_run and never runs the real program, so a
# jq mutation (e.g. `if $c=="success"` -> `if true`) would survive. This section EXTRACTS the exact
# --jq program from ci-status.sh and runs it via standalone jq against JSON fixtures, asserting the
# emitted CATEGORY (field 1 before the first "|"). A mutation of the production jq must make it FAIL.
if command -v jq >/dev/null 2>&1; then
  # Extract the program: from the line containing --jq ' through the line containing end', then strip
  # the leading `--jq '` and the trailing `'` (keeping `end`). Fail loudly if extraction misfires.
  q="'"
  JQ_PROG="$(sed -n "/--jq $q/,/end$q/p" "$SCRIPT")"
  JQ_PROG="${JQ_PROG#*--jq "$q"}"
  JQ_PROG="${JQ_PROG%end"$q"*}end"
  if ! grep -q 'workflow_runs' <<<"$JQ_PROG"; then
    failc "real-jq: could not extract the --jq program from $SCRIPT (extraction misfired)"
  else
    jqcat() { printf '%s' "$1" | jq '.workflow_runs |= if type == "array" then map(if has("event") then . else . + {event:"push"} end) else . end' | jq -r "$JQ_PROG" 2>/dev/null | cut -d'|' -f1; }
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"success"}]}')" success   "completed+success -> success"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"failure"}]}')" otherterm "completed+failure -> otherterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":null}]}')"      otherterm "completed+null conclusion -> otherterm"
    # ALL six recognized non-terminal statuses must classify as nonterm, so dropping any one token
    # from the jq disjunction is caught (each status below would then fall through to "error").
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"queued"}]}')"                            nonterm   "queued -> nonterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"in_progress"}]}')"                       nonterm   "in_progress -> nonterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"waiting"}]}')"                           nonterm   "waiting -> nonterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"requested"}]}')"                         nonterm   "requested -> nonterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"pending"}]}')"                           nonterm   "pending -> nonterm"
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"action_required"}]}')"                   nonterm   "action_required -> nonterm"
    # a "|" injected INTO the status field cannot shift the machine category: status is not a known
    # terminal/nonterminal token, so the run classifies as error, and field 1 is a clean "error".
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed|success"}]}')"                 error     "pipe inside status -> error (no delimiter shift)"
    # a "|"-laden NAME cannot shift the category: name is @base64-encoded and category is from status.
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"in_progress","name":"a|b|completed|success"}]}')" nonterm "pipe-laden name -> real category (nonterm)"
    ck_eq "$(jqcat '{}')"                                                                 error     "non-array workflow_runs ({}) -> error sentinel"
    ck_eq "$(jqcat '{"workflow_runs":[]}')"                                               norun     "empty array -> norun sentinel"
    # multi-run array: the production program gates on .workflow_runs[0] (newest run) ONLY, so a
    # green newest run masks an older failing one: the deliberate scoped exclusion documented as
    # NEWEST-RUN SCOPE in ci-status.sh.
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"success"},{"status":"completed","conclusion":"failure"}]}')" success "multi-run: newest [0] governs (NEWEST-RUN SCOPE)"
    # schedule runs are IGNORED when choosing the run for a SHA: a NEWER schedule run on main's tip
    # must not mask the OLDER push run's conclusion. The newest run here is a green schedule run;
    # the older push run failed, and the push run's result must govern (otherterm).
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"success","event":"schedule"},{"status":"completed","conclusion":"failure","event":"push"}]}')" otherterm "newer schedule run ignored: the older push run governs"
    # the mirror case: a failed/cancelled newer schedule run must not mask a GREEN push run either
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"failure","event":"schedule"},{"status":"completed","conclusion":"success","event":"push"}]}')" success "newer failed schedule run ignored: the green push run governs"
    # A schedule-only page must continue until a qualifying run or an empty page.
    ck_eq "$(jqcat '{"workflow_runs":[{"status":"completed","conclusion":"success","event":"schedule"}]}')" more "schedule-only page -> continue sentinel"
    # End-to-end page fixtures use the actual --jq argument received by fake gh.
    export PAGE_FIXTURES="$STATE/pages"
    mkdir "$PAGE_FIXTURES"
    jq -n '{workflow_runs: [range(30) | {event:"schedule"}]}' >"$PAGE_FIXTURES/1.json"
    printf '%s\n' '{"workflow_runs":[{"event":"push","created_at":"2026-10-31T00:00:00Z","status":"completed","conclusion":"success"},{"event":"push","status":"completed","conclusion":"failure"}]}' >"$PAGE_FIXTURES/2.json"
    reset_state; T=0; G=0; invoke HEAD
    ck_eq "$RC" 0 "page 2 newest push succeeds after 30 schedules"
    ck_eq "$(ghcount)" 2 "stop at first qualifying page"
    cp "$PAGE_FIXTURES/1.json" "$PAGE_FIXTURES/2.json"
    printf '%s\n' '{"workflow_runs":[]}' >"$PAGE_FIXTURES/3.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 2 "all schedule pages read absence"
    ck_eq "$(ghcount)" 3 "absence requires listing exhaustion"
    ck_has 'no workflow run registered' "exhausted listing reports absence"
    printf '%s\n' '{"workflow_runs":"invalid"}' >"$PAGE_FIXTURES/2.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 2 "non-array later page fails"
    ck_has 'ERROR' "invalid listing reports error"
    ck_eq "$(jqcat '{"total_count":1001,"workflow_runs":[]}')" error "over-cap empty listing is unknown"
    # A backward SECONDS reading must not inflate the next request allowance.
    cap_result=$(
      unset SECONDS; SECONDS=100
      eval "$(sed -n '/^query() {$/,/^}$/p' "$SCRIPT")"
      query_page() {
        printf '%s\n' "$1"
        if [[ $2 == 1 ]]; then Q_RC=0; Q_OUT='more||||'; SECONDS=90
        else Q_RC=0; Q_OUT='norun||||'; fi
      }
      query 5
    )
    ck_eq "$cap_result" $'5\n5\n5\n5' "backward clock retains original request cap"
    # The first listing consumes the shared allowance; push still gets 1s.
    # Removing the per-listing floor must lose the second call and fail here.
    floor_result=$(
      unset SECONDS; SECONDS=0
      eval "$(sed -n '/^query() {$/,/^}$/p' "$SCRIPT")"
      query_page() {
        printf '%s %s %s\n' "$1" "$2" "$3"
        Q_RC=0; Q_OUT='norun||||'
        SECONDS=$(( SECONDS + 1 ))
      }
      query 1
      printf '%s %s\n' "$Q_RC" "$Q_OUT"
    )
    ck_eq "$floor_result" $'1 1 pull_request\n1 1 push\n0 norun||||' "expired shared allowance preserves each listing's first page"
    printf 'unset SECONDS; SECONDS=0\n' >"$WORK/frozen-clock"
    export ENDLESS_PAGES=1
    reset_state; T=0; G=0
    BASH_ENV="$WORK/frozen-clock" invoke HEAD
    ck_eq "$RC" 2 "frozen clock endless pages fail closed"
    ck_eq "$(ghcount)" 10 "frozen clock stops at ten pages"
    ck_has 'page bound reached' "page bound is error, not absence"
    # Page eleven would be empty, but cannot establish absence past the API cap.
    unset ENDLESS_PAGES
    for page in {2..10}; do cp "$PAGE_FIXTURES/1.json" "$PAGE_FIXTURES/$page.json"; done
    printf '%s\n' '{"workflow_runs":[]}' >"$PAGE_FIXTURES/11.json"
    reset_state
    BASH_ENV="$WORK/frozen-clock" invoke HEAD
    ck_eq "$(ghcount)" 10 "empty page past cap is never requested"
    ck_has 'page bound reached' "capped listing stays unknown"
    # Endless schedule-only pages use real SECONDS and a 1s remaining allowance.
    # The outer timeout makes deleting the exhaustion guard fail boundedly.
    reset_state; T=1; G=1
    seq_set 0 0 1
    export ENDLESS_PAGES=1
    SLOW_PAGES=1 invoke HEAD --wait
    ck_eq "$RC" 2 "endless schedules exhaust pagination allowance"
    ck_has 'ERROR' "pagination exhaustion reports error"
    ck_has 'Actions pagination allowance exhausted' "pagination exhaustion branch reached"
    unset ENDLESS_PAGES
    unset PAGE_FIXTURES
    # A schedule run deleted between two reads must not move the failed run off the page that is
    # read. The fake server requires each filtered event on page 1, so schedule deletion cannot
    # affect either response (no offset page is read).
    export EVENT_FIXTURES="$STATE/events"
    mkdir "$EVENT_FIXTURES"
    printf '%s\n' '{"workflow_runs":[{"event":"pull_request","created_at":"2026-10-31T02:00:00Z","status":"completed","conclusion":"failure"}]}' >"$EVENT_FIXTURES/pull_request.json"
    printf '%s\n' '{"workflow_runs":[{"event":"push","created_at":"2026-10-31T01:00:00Z","status":"completed","conclusion":"success"}]}' >"$EVENT_FIXTURES/push.json"
    jq -s '{workflow_runs: ([range(100) | {event:"schedule"}] + .[0].workflow_runs + .[1].workflow_runs)}' "$EVENT_FIXTURES/pull_request.json" "$EVENT_FIXTURES/push.json" >"$EVENT_FIXTURES/all.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 1 "deletion cannot hide newer failing PR behind older successful push"
    ck_eq "$(urlcount)" 2 "both event listings queried without paging"
    grep -q '&event=pull_request&' "$STATE/gh_urls" || failc "PR event missing"
    grep -q '&event=push&' "$STATE/gh_urls" || failc "push event missing"
    printf '%s\n' '{"workflow_runs":[]}' >"$EVENT_FIXTURES/push.json"
    jq -s '{workflow_runs: ([range(100) | {event:"schedule"}] + .[0].workflow_runs)}' "$EVENT_FIXTURES/pull_request.json" >"$EVENT_FIXTURES/all.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 1 "deletion cannot produce false absence"
    rm "$EVENT_FIXTURES/all.json"
    printf '%s\n' '{"workflow_runs":[{"event":"push","created_at":"2026-10-31T03:00:00Z","status":"completed","conclusion":"success"}]}' >"$EVENT_FIXTURES/push.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 0 "newer push wins by created_at"
    sed -i 's/03:00:00/02:00:00/' "$EVENT_FIXTURES/push.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 1 "timestamp tie deterministically prefers pull_request"
    printf '%s\n' '{"workflow_runs":[]}' >"$EVENT_FIXTURES/pull_request.json"
    printf '%s\n' '{"workflow_runs":[]}' >"$EVENT_FIXTURES/push.json"
    reset_state; invoke HEAD
    ck_eq "$RC" 2 "schedule-only head is absent from both server-filtered listings"
    ck_eq "$(urlcount)" 2 "schedule-only head needs no paging"
    # Missing, null and empty timestamps must fail on either event candidate,
    # even when the other listing has a valid successful run.
    for event in pull_request push; do
      for timestamp in missing null empty; do
        for kind in pull_request push; do
          jq -n --arg event "$kind" '{workflow_runs: [{event:$event, created_at:"2026-10-31T00:00:00Z", status:"completed", conclusion:"success"}]}' >"$EVENT_FIXTURES/$kind.json"
        done
        jq --arg mode "$timestamp" '.workflow_runs[0] |= (if $mode == "missing" then del(.created_at) elif $mode == "null" then .created_at = null else .created_at = "" end)' "$EVENT_FIXTURES/$event.json" >"$EVENT_FIXTURES/changed.json"
        mv "$EVENT_FIXTURES/changed.json" "$EVENT_FIXTURES/$event.json"
        reset_state; invoke HEAD
        ck_eq "$RC" 2 "$event $timestamp timestamp is unknown"
        ck_has 'ERROR' "$event $timestamp timestamp is not absence"
      done
    done
    unset EVENT_FIXTURES

  fi
else
  failc "real-jq section NOT RUN: standalone jq not found (not a pass; jq is required on this host)"
fi

section "report-once preserves existing exit codes"

reset_state; T=900; G=900; run_resp completed success Q http://r; invoke HEAD; ck_rc 0 "report-once success -> 0"; ck_eq "$(ghcount)" 1 "  one query"
reset_state; T=900; G=900; run_resp completed failure Q http://r; invoke HEAD; ck_rc 1 "report-once failure -> 1"
reset_state; T=900; G=900; run_resp in_progress - Q http://r;     invoke HEAD; ck_rc 1 "report-once pending -> 1"
reset_state; T=900; G=900; norun_resp;                            invoke HEAD; ck_rc 2 "report-once absence -> 2"
reset_state; T=900; G=900; resp 1 "HTTP 404: Not Found";          invoke HEAD; ck_rc 2 "report-once error -> 2"

section "repository selection (no default owner or repository)"

# Without CI_STATUS_REPO, the repository comes from the origin remote of the script's own checkout
# (the git shim answers only `git -C /repo`); every accepted URL form, with or without a trailing
# slash, yields the same OWNER/NAME, and every request targets it.
for origin in https://github.com/fixture-owner/fixture-name.git https://github.com/fixture-owner/fixture-name \
              https://github.com/fixture-owner/fixture-name/ https://github.com/fixture-owner/fixture-name.git/ \
              git@github.com:fixture-owner/fixture-name.git ssh://git@github.com/fixture-owner/fixture-name.git; do
  reset_state; T=900; G=900; run_resp completed success Q http://r
  printf '%s\n' "$origin" >"$STATE/origin"
  invoke_origin HEAD
  ck_rc 0 "origin $origin -> success"
  if all_urls_have "repos/fixture-owner/fixture-name/" "head_sha=$SHIM_SHA"; then pass "  requests target the origin's OWNER/NAME"; else failc "  requests target the origin's OWNER/NAME ($(cat "$STATE/gh_urls"))"; fi
done
# Run from another working directory: the origin still comes from the script's own checkout.
reset_state; T=900; G=900; run_resp completed success Q http://r
printf '%s\n' https://github.com/fixture-owner/fixture-name.git >"$STATE/origin"
mkdir -p "$WORK/elsewhere"
OUT="$(cd "$WORK/elsewhere" && "$REAL_TIMEOUT" 20 env -u CI_STATUS_REPO PATH="$SHIMDIR:$PATH" STATE="$STATE" \
      CI_STATUS_TIMEOUT=900 CI_STATUS_REGISTRATION_GRACE=900 bash "$SCRIPT" HEAD 2>&1)"; RC=$?
ck_rc 0 "run from another working directory -> success"
if all_urls_have "repos/fixture-owner/fixture-name/" "head_sha=$SHIM_SHA"; then pass "  the origin came from the script's own checkout"; else failc "  the origin came from the script's own checkout ($(cat "$STATE/gh_urls"))"; fi
# CI_STATUS_REPO wins over the origin remote.
reset_state; T=900; G=900; run_resp completed success Q http://r
printf '%s\n' https://github.com/fixture-owner/fixture-name.git >"$STATE/origin"
invoke HEAD
ck_rc 0 "CI_STATUS_REPO set -> success"
if all_urls_have "repos/test/repo/" "head_sha=$SHIM_SHA"; then pass "  CI_STATUS_REPO wins over the origin remote"; else failc "  CI_STATUS_REPO wins over the origin remote"; fi
# Neither CI_STATUS_REPO nor an origin remote: exit 2 before any request, naming the remedy.
reset_state; T=900; G=900; run_resp completed success Q http://r
invoke_origin HEAD --wait
ck_rc 2 "no CI_STATUS_REPO and no origin remote -> 2"
ck_has "no repository: set CI_STATUS_REPO" "  the message names the remedy"
ck_eq "$(ghcount)" 0 "  no query performed"
# An origin that is not a github.com repository yields no repository.
reset_state; T=900; G=900; run_resp completed success Q http://r
printf '%s\n' https://example.invalid/fixture-owner/fixture-name.git >"$STATE/origin"
invoke_origin HEAD
ck_rc 2 "non-github.com origin -> 2"
ck_eq "$(ghcount)" 0 "  no query performed"
# An origin that passes the github.com prefix match is still checked as OWNER/NAME, so it cannot
# carry a query string, an extra path segment, a dot segment or a second line into a request.
for bad in https://github.com/fixture-owner/fixture-name/extra 'https://github.com/fixture-owner/fixture-name?x=1' \
           'https://github.com/fixture-owner/fixture-name&x' https://github.com/fixture-owner/.. \
           https://github.com/fixture-owner/. $'https://github.com/fixture-owner/fixture-name\nsecond-line'; do
  reset_state; T=900; G=900; run_resp completed success Q http://r
  printf '%s\n' "$bad" >"$STATE/origin"
  invoke_origin HEAD
  ck_rc 2 "crafted origin '$bad' -> 2"
  ck_has "the repository must be OWNER/NAME" "  refused as not OWNER/NAME"
  ck_eq "$(ghcount)" 0 "  no query performed"
done
# A malformed CI_STATUS_REPO is refused before any request.
for bad in fixture fixture/name/extra '-fixture/name' 'fixture/na me' fixture/. fixture/..; do
  reset_state; T=900; G=900; run_resp completed success Q http://r
  OUT="$("$REAL_TIMEOUT" 20 env PATH="$SHIMDIR:$PATH" STATE="$STATE" CI_STATUS_REPO="$bad" \
        CI_STATUS_TIMEOUT=900 CI_STATUS_REGISTRATION_GRACE=900 bash "$SCRIPT" HEAD 2>&1)"; RC=$?
  ck_rc 2 "malformed CI_STATUS_REPO '$bad' -> 2"
  ck_eq "$(ghcount)" 0 "  no query performed"
done

section "zero settings, invalid settings, options, revisions"

# zero grace is valid: absence is immediately terminal, one query, no registration retries
reset_state; T=900; G=0; norun_resp; invoke HEAD --wait; ck_rc 2 "zero grace -> immediate absence"; ck_eq "$(ghcount)" 1 "  exactly one query (no retries)"
# zero overall timeout: one immediate query, no retries
reset_state; T=0; G=900; norun_resp; invoke HEAD --wait; ck_rc 2 "zero timeout, absence -> 2"; ck_eq "$(ghcount)" 1 "  exactly one query"
reset_state; T=0; G=900; run_resp completed success Q http://r; invoke HEAD --wait; ck_rc 0 "zero timeout, immediate success -> 0"; ck_eq "$(ghcount)" 1 "  exactly one query"

# leading-zero budgets are decimal, not octal, and are accepted
reset_state; T=0900; G=0060; run_resp completed success Q http://r; invoke HEAD --wait; ck_rc 0 "leading-zero budgets accepted (T=0900 G=0060)"

# invalid settings -> exit 2 before any query
reset_state; T=abc; G=900; norun_resp; invoke HEAD --wait; ck_rc 2 "non-integer timeout -> 2"; ck_eq "$(ghcount)" 0 "  no query performed"
reset_state; T=900; G=-5;  norun_resp; invoke HEAD --wait; ck_rc 2 "negative grace -> 2"; ck_eq "$(ghcount)" 0 "  no query performed"
reset_state; T=9.5; G=900; norun_resp; invoke HEAD --wait; ck_rc 2 "decimal timeout -> 2"
reset_state; T=99999999999; G=900; norun_resp; invoke HEAD --wait; ck_rc 2 "out-of-range timeout -> 2"

# overflow-safe magnitude guard: values that would WRAP in shell arithmetic are rejected up front
reset_state; T=18446744073709551616; G=900; norun_resp; invoke HEAD --wait; ck_rc 2 "overflow timeout (2^64) rejected"; ck_eq "$(ghcount)" 0 "  no query performed"
reset_state; T=900; G=9223372036854775808; norun_resp; invoke HEAD --wait; ck_rc 2 "overflow grace (2^63) rejected"; ck_eq "$(ghcount)" 0 "  no query performed"

# unresolved revision -> exit 2
reset_state; T=900; G=900; norun_resp; invoke BADREV --wait; ck_rc 2 "unresolved revision -> 2"; ck_eq "$(ghcount)" 0 "  no query performed"
# unknown option -> exit 2
reset_state; T=900; G=900; norun_resp; invoke HEAD --bogus; ck_rc 2 "unknown option -> 2"; ck_eq "$(ghcount)" 0 "  no query performed"
# a second positional revision -> exit 2 (a stray SHA must not silently change the gated commit)
reset_state; T=900; G=900; norun_resp; invoke HEAD HEAD2 --wait; ck_rc 2 "second revision -> 2"; ck_eq "$(ghcount)" 0 "  no query performed"
ck_has "more than one revision" "  duplicate-revision diagnostic present"

section "default budgets (CI_STATUS_TIMEOUT 900, CI_STATUS_REGISTRATION_GRACE 600)"

# The default overall budget is 900 s, sized to the 5-minute Quality job after a 600 s grace. The
# date sequence puts the clock at 899 after the first pending poll (not expired, one 1 s sleep), then
# at 900 (one boundary query, then TIMEOUT). A smaller default would expire after the first poll.
reset_state; run_resp in_progress - Q http://r
seq_set 0 0 899 900 900
invoke_defaults HEAD --wait
ck_rc 1 "default overall budget: pending through the deadline -> timeout"
ck_has "TIMEOUT after 900s" "  default overall budget is 900 s"
ck_eq "$(ghcount)" 2 "  one poll before the 900 s deadline and one boundary query"

# A run still pending after 800 s, then green, succeeds under the default overall budget.
reset_state; run_resp in_progress - Q http://r; run_resp completed success Q http://r
seq_set 0 0 800 815 815
invoke_defaults HEAD --wait
ck_rc 0 "default overall budget: a run pending past 800 s still reaches success"
ck_eq "$(ghcount)" 2 "  two queries"

# The default registration grace is 600 s and stays nested under the overall budget.
reset_state; norun_resp
seq_set 0 0 599 600 600
invoke_defaults HEAD --wait
ck_rc 2 "default registration grace: no run observed -> absence"
ck_has "within the 600s registration grace" "  default registration grace is 600 s"
ck_eq "$(ghcount)" 2 "  one poll before the 600 s grace boundary and one boundary query"

section "clock changes and the final boundary query"

# the clock is already at the deadline on the first poll: exactly one boundary query, then
# terminate (the loop does not spin issuing repeated boundary queries)
reset_state; T=60; G=60; norun_resp
seq_set 0 60 60 60 60 60
invoke HEAD --wait
ck_rc 2 "clock at deadline on first poll -> absence"
ck_eq "$(ghcount)" 1 "  single boundary query, then terminate"

# a backward clock reading does not extend the wait: same query count as the monotone control
reset_state; T=60; G=60; norun_resp
seq_set 0 15 15 30 30 45 45 60 60
invoke HEAD --wait; ck_rc 2 "monotone control -> absence"
mono_count="$(ghcount)"
reset_state; T=60; G=60; norun_resp
seq_set 0 15 15 30 30 20 20 60 60   # 20 is a backward blip after 30
invoke HEAD --wait; ck_rc 2 "backward clock blip -> still absence"
# This proves BOUNDED TERMINATION under a backward blip (the SLEPT accumulator equalizes the poll
# count against the monotone control), not the wall-clock monotonic clamp specifically; the repeated
# backward/frozen-clock case below exercises the SLEPT backstop over many iterations.
ck_eq "$(ghcount)" "$mono_count" "  bounded poll count under a backward blip (termination via SLEPT backstop)"

section "repeated backward clock (cumulative-sleep backstop)"

# monotone control that reaches the deadline via the wall clock
reset_state; T=60; G=60; norun_resp
seq_set 0 15 15 30 30 45 45 60 60
invoke HEAD --wait; ck_rc 2 "monotone control -> absence"
rb_mono="$(ghcount)"

# the wall clock is frozen/backward on MOST iterations (never passes 15), so wall-clock timing
# alone would never expire. The monotonic cumulative-sleep backstop bounds total sleep to the
# budget, so the run still terminates with absence in a bounded number of queries. Without the
# SLEPT backstop this case hangs until the real 20 s timeout (rc 124).
reset_state; T=60; G=60; norun_resp
seq_set 0 15 5 15 5 15 5 15 5 15 5 15 5 15 5
invoke HEAD --wait
ck_rc 2 "repeated backward/frozen clock -> still absence (SLEPT backstop)"
ck_has "RESULT: ABSENCE" "  absence diagnostic under a frozen/backward clock"
if [ "$(ghcount)" -le $(( rb_mono + 2 )) ]; then
  pass "  bounded query count ($(ghcount) <= control+2 = $(( rb_mono + 2 )))"
else
  failc "  bounded query count ($(ghcount) vs control $rb_mono)"
fi

section "missing-binary preflight"

# A missing required binary must exit 2 with the "required binary ... not found" diagnostic BEFORE
# any query. In the source the preflight loops `gh` then `timeout` AFTER budget validation and
# BEFORE rev resolution, and nothing external runs before it, so pointing PATH at a directory that
# holds only `bash` (no `gh`) makes `command -v gh` fail and the script exit 2 before git rev-parse.
reset_state; T=900; G=900
NOGH="$WORK/nogh"; mkdir -p "$NOGH"
ln -sf "$(command -v bash)" "$NOGH/bash"
OUT="$("$REAL_TIMEOUT" 20 env PATH="$NOGH" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
      bash "$SCRIPT" HEAD --wait 2>&1)"
RC=$?
ck_rc 2 "missing gh binary -> exit 2"
ck_has "required binary gh not found" "  missing-binary diagnostic present"
ck_eq "$(ghcount)" 0 "  zero queries (preflight fired before any request)"

section "temp-file creation failure and -k probe failure"

# A temp-file creation failure inside query() must exit 2 with the temp-file diagnostic. All the
# other binaries work (gh/timeout/git via SHIMDIR, -k probe passes), only mktemp fails, so the script
# reaches query() and then fails loudly on the fresh per-poll temp file rather than riding the budget.
reset_state; T=900; G=900; run_resp completed success Q http://r
MTF="$WORK/mktempfail"; mkdir -p "$MTF"
cat >"$MTF/mktemp" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$MTF/mktemp"
OUT="$("$REAL_TIMEOUT" 20 env PATH="$MTF:$SHIMDIR:$PATH" STATE="$STATE" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
      bash "$SCRIPT" HEAD --wait 2>&1)"
RC=$?
ck_rc 2 "mktemp failure inside query -> exit 2"
ck_has "could not create a temp file" "  temp-file failure diagnostic present"

# A timeout utility that lacks -k support must fail loudly at the preflight probe (exit 2) BEFORE any
# query, rather than silently dropping kill-escalation. The NOK timeout rejects any -k invocation.
reset_state; T=900; G=900
NOK="$WORK/nok"; mkdir -p "$NOK"
cat >"$NOK/timeout" <<'EOF'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = "-k" ]; then exit 1; fi
exec "$@"
EOF
chmod +x "$NOK/timeout"
OUT="$("$REAL_TIMEOUT" 20 env PATH="$NOK:$SHIMDIR:$PATH" STATE="$STATE" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
      bash "$SCRIPT" HEAD --wait 2>&1)"
RC=$?
ck_rc 2 "timeout lacking -k support -> exit 2"
ck_has "does not support -k" "  -k probe failure diagnostic present"
ck_eq "$(ghcount)" 0 "  no query performed (probe fired before any request)"

section "host precondition: timeout(1) -k escalation (a hung request)"

# A host precondition, not a test of ci-status.sh's own code: the script's per-request bound relies
# on timeout(1) -k escalating to SIGKILL for a child that IGNORES SIGTERM, which simulated time
# cannot show. The child traps and ignores TERM (inherited across exec), so the initial TERM is a
# no-op and only the -k SIGKILL ends it. GNU and uutils timeout report 137 (128 + SIGKILL) when the
# kill escalation fires and 124 for a timeout whose TERM was obeyed. A host whose timeout does not
# escalate fails here.
marker="hungchild_$$_$RANDOM"
start_real="$(command date +%s)"
"$REAL_TIMEOUT" -k 1 1 bash -c "trap '' TERM; exec -a $marker sleep 41" >/dev/null 2>&1
rc_hung=$?
end_real="$(command date +%s)"
dur=$(( end_real - start_real ))
ck_eq "$rc_hung" 137 "TERM-ignoring hung request killed by -k escalation (rc 137)"
if [ "$dur" -le 5 ]; then pass "  terminated within the fixed allowance (${dur}s)"; else failc "  terminated within allowance (${dur}s)"; fi
# A missing pgrep must not read as a clean "no leftover child" pass.
if command -v pgrep >/dev/null 2>&1; then
  if pgrep -f "$marker" >/dev/null 2>&1; then failc "  no leftover child process"; else pass "  no leftover child process"; fi
else
  failc "  no leftover child process (pgrep unavailable; leftover check NOT RUN)"
fi

section "surviving stdout-holding grandchild does not hang the script"

# Regression guard, with REAL processes. A gh shim spawns a grandchild that ignores SIGTERM and
# INHERITS (holds) gh's stdout, then exits. ci-status.sh writes gh's stdout to a regular file, so
# the post-timeout read returns at EOF and the script proceeds to a bounded exit; with a mutant that
# restores the `Q_OUT="$(timeout ... gh ...)"` command-substitution capture, the capture's pipe stays
# open until the grandchild dies (120s), so the script HANGS and only the outer real timeout ends it
# (rc 124). We run the REAL ci-status.sh under an outer real 15s timeout and assert it exits itself.
# T=0 and G=0 give one immediate query and no real sleep; that one query is where a capture would hang.
#
# Determinism and gh-path proof. The gh HANG path is only exercised if ci-status.sh gets past
# revision resolution and actually issues the query. Under a raw real-git PATH, `git rev-parse` can
# exit 2 early (a "dubious ownership" checkout), so ci-status.sh would exit 2 BEFORE gh ran, and the
# rc==2 assertion would FALSELY pass even against a command-substitution mutant. Two measures close
# that hole: (1) resolve the rev through the harness's deterministic `git` shim (the same shim the
# other --wait tests use), so rev resolution never depends on the real repo's git ownership; the shim
# is placed in FIXA_DIR (ahead of the gh shim's own dir on PATH) so real `timeout`/`sleep`/`date` are
# still used, which this REAL-process guard requires. (2) The gh shim records that it RAN (a marker
# plus the grandchild pid), and the guard asserts both markers, so a regression that early-exits
# before gh FAILS the "gh ran" assertion instead of false-passing on rc==2.
FIXA_DIR="$WORK/fixa"; mkdir -p "$FIXA_DIR"
# Deterministic rev resolution: reuse the harness git shim (resolves HEAD to SHIM_SHA, no real git,
# no ownership dependency). FIXA_DIR is first on PATH, so this git wins while gh below also wins.
ln -sf "$SHIMDIR/git" "$FIXA_DIR/git"
: >"$STATE/fixa_grandchildren"
: >"$STATE/fixa_gh_ran"
cat >"$FIXA_DIR/gh" <<EOF
#!/usr/bin/env bash
# Record that gh actually ran (proves the query path was reached, not an early git/rev-parse exit),
# then spawn a TERM-ignoring grandchild that inherits (holds) this process's stdout (fd 1), record its
# pid, and exit 0. It does not redirect its own stdout, so it holds whatever fd 1 gh was given: the
# command-substitution pipe (mutant) or the redirected regular file (the script as written).
printf 'ran\n' >>"$STATE/fixa_gh_ran"
bash -c 'trap "" TERM; exec sleep 120' &
printf '%s\n' "\$!" >>"$STATE/fixa_grandchildren"
exit 0
EOF
chmod +x "$FIXA_DIR/gh"

fa_start="$(command date +%s)"
"$REAL_TIMEOUT" 15 env PATH="$FIXA_DIR:$PATH" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT=0 CI_STATUS_REGISTRATION_GRACE=0 \
      bash "$SCRIPT" HEAD --wait >/dev/null 2>&1
rc_fa=$?
fa_end="$(command date +%s)"
fa_dur=$(( fa_end - fa_start ))
# The gh-ran assertions come FIRST: they prove the guard exercised the gh/hang path at all. Without
# them, an early git/rev exit (rc 2 before gh) would let the rc==2 assertion below pass vacuously.
if [ -s "$STATE/fixa_gh_ran" ]; then pass "gh shim actually ran (gh/query path reached, not an early git/rev exit)"; else failc "gh shim actually ran (marker absent: an early exit before gh would false-pass rc==2)"; fi
if [ -s "$STATE/fixa_grandchildren" ]; then pass "  gh spawned the stdout-holding grandchild (hang path exercised)"; else failc "  gh spawned the stdout-holding grandchild (no pid recorded)"; fi
ck_eq "$rc_fa" 2 "surviving grandchild: script exits itself (rc 2), does not hang"
if [ "$fa_dur" -lt 15 ]; then pass "  finished before the outer bound (${fa_dur}s < 15s)"; else failc "  finished before the outer bound (${fa_dur}s; likely hung to the outer timeout)"; fi
# Teardown: kill the spawned grandchildren so they do not linger. They ignore SIGTERM by design,
# so teardown MUST use SIGKILL (a plain kill/SIGTERM would be ignored and the sleeps would leak).
while IFS= read -r gp; do
  [ -n "$gp" ] && kill -KILL "$gp" 2>/dev/null
done < "$STATE/fixa_grandchildren"

section "signal cleanup (temp files removed on a trappable signal)"

# Regression guard, with REAL processes. ci-status.sh installs INT/TERM/HUP traps that run the
# PID-globbed cleanup, AND names each temp file with its own PID (ci-status.<pid>.*), so cleanup
# matches a file the INSTANT mktemp creates it (closing the allocation-to-registration window) and on
# any trappable signal (closing the untrapped-signal leak). This shim WIDENS the window: a fake mktemp
# creates the real temp file, then sends SIGTERM to ci-status.sh (its parent) mid-query, before the
# script can register the path in any variable. No ci-status.<pid>.* file may survive; a mutant
# that drops the signal traps or uses a non-globbing cleanup leaves the file behind.
#
# An ISOLATED TMPDIR is used so the emptiness assertion sees only this run's files, and REAL_MKTEMP
# lets the shim create the file without recursing into itself on PATH.
SIGDIR="$WORK/sigcleanup"; mkdir -p "$SIGDIR"
SIGTMP="$WORK/sigtmp"; mkdir -p "$SIGTMP"
cat >"$SIGDIR/mktemp" <<'EOF'
#!/usr/bin/env bash
# Create the real temp file (via REAL_MKTEMP, so we do not recurse into this shim), record the path,
# then send SIGTERM to the parent (ci-status.sh) to interrupt it BETWEEN file creation and any
# variable assignment. This exercises both the allocation-window and the signal-trap cleanup.
set -u
f="$("$REAL_MKTEMP" "$@")"
printf '%s\n' "$f" >>"$STATE/sig_created"
kill -TERM "$PPID" 2>/dev/null
printf '%s' "$f"
exit 0
EOF
chmod +x "$SIGDIR/mktemp"
: >"$STATE/sig_created"
reset_state; T=900; G=900; run_resp completed success Q http://r
"$REAL_TIMEOUT" 20 env PATH="$SIGDIR:$SHIMDIR:$PATH" STATE="$STATE" TMPDIR="$SIGTMP" \
      REAL_MKTEMP="$REAL_MKTEMP" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
      bash "$SCRIPT" HEAD --wait >/dev/null 2>&1
sig_rc=$?
# The signal fired mid-query, so the run must NOT have exited 0 (it was interrupted before a verdict).
ck_ne0 "$sig_rc" "signalled run did not exit 0 (interrupted mid-query by SIGTERM)"
# Sanity: the shim actually created (and signalled on) a temp file, so the guard truly exercised the
# create->signal window rather than passing vacuously.
if [ -s "$STATE/sig_created" ]; then pass "  mktemp shim created a temp file and signalled mid-query"; else failc "  mktemp shim created a temp file and signalled mid-query (nothing recorded)"; fi
# No ci-status.* temp file may remain in the isolated TMPDIR after the trappable signal.
sig_leftover="$(find "$SIGTMP" -maxdepth 1 -name 'ci-status.*' 2>/dev/null | wc -l | tr -d ' ')"
ck_eq "$sig_leftover" 0 "  no ci-status temp file remains after a trappable signal (glob+trap cleanup)"

section "rev pinning (GIT_DIR/GIT_WORK_TREE scrub and symlink resolution)"

# Regression guard. ci-status.sh resolves the rev, and the origin remote, against its OWN checkout by
# (a) scrubbing an inherited GIT_DIR/GIT_WORK_TREE with `env -u` (they would otherwise override -C and
# point git at an unrelated repo), and (b) resolving BASH_SOURCE[0] through any symlink with
# `readlink -f` before taking its directory (so a symlink from another repo cannot redirect the
# --show-toplevel discovery). A dedicated recording git shim captures the inherited GIT_DIR /
# GIT_WORK_TREE, the discovery cwd (PWD) and the arguments, so these bypasses can be asserted closed.
REVDIR="$WORK/revpin"; mkdir -p "$REVDIR"
cat >"$REVDIR/git" <<'EOF'
#!/usr/bin/env bash
set -u
# Record what git ACTUALLY saw: the inherited GIT_DIR/GIT_WORK_TREE (empty if scrubbed) and the cwd
# the caller ran discovery from (proves symlink resolution). Then behave like the standard shim:
# record -C <dir>, answer --show-toplevel with that directory or the current one, resolve any
# non-BADREV rev, and answer `remote get-url origin` from $STATE/origin.
printf 'GIT_DIR=[%s] GIT_WORK_TREE=[%s] PWD=[%s] ARGV=[%s]\n' "${GIT_DIR:-}" "${GIT_WORK_TREE:-}" "$PWD" "$*" >>"$STATE/revpin_calls"
dir=""
while [ "${1:-}" = "-C" ]; do dir="${2:-}"; shift 2; done
if [ "${1:-}" = "remote" ] && [ "${2:-}" = "get-url" ] && [ "${3:-}" = "origin" ]; then
  [ -f "$STATE/origin" ] || exit 2
  cat "$STATE/origin"
  exit 0
fi
if [ "${1:-}" = "rev-parse" ]; then
  shift
  for a in "$@"; do
    case "$a" in --show-toplevel) printf '%s\n' "${dir:-$PWD}"; exit 0 ;; esac
  done
  last=""
  for a in "$@"; do last="$a"; done
  case "$last" in
    BADREV*) exit 1 ;;
    *) printf '0123456789abcdef0123456789abcdef01234567\n'; exit 0 ;;
  esac
fi
exit 0
EOF
chmod +x "$REVDIR/git"

# Sub-test 1: an inherited GIT_DIR/GIT_WORK_TREE must be scrubbed before git runs, for the rev and for
# the origin remote. Set bogus values and leave CI_STATUS_REPO unset, so the repository comes from
# the origin remote; the recording shim must NEVER see the bogus values (env -u stripped them). A
# mutant that drops the `env -u` scrub from either call lets git inherit the bogus GIT_DIR, which
# the grep below then catches.
: >"$STATE/revpin_calls"
reset_state; T=0; G=0; norun_resp
printf '%s\n' https://github.com/fixture-owner/fixture-name.git >"$STATE/origin"
"$REAL_TIMEOUT" 20 env -u CI_STATUS_REPO PATH="$REVDIR:$SHIMDIR:$PATH" STATE="$STATE" \
      GIT_DIR="/bogus/other-repo/.git" GIT_WORK_TREE="/bogus/other-repo" \
      CI_STATUS_TIMEOUT=0 CI_STATUS_REGISTRATION_GRACE=0 \
      bash "$SCRIPT" HEAD --wait >/dev/null 2>&1 || true
if [ -s "$STATE/revpin_calls" ]; then pass "GIT_DIR scrub: rev resolution invoked git"; else failc "GIT_DIR scrub: rev resolution invoked git (no call recorded)"; fi
if grep -qF -- "ARGV=[-C $(dirname "$(readlink -f "$SCRIPT")") remote get-url origin]" "$STATE/revpin_calls"; then
  pass "GIT_DIR scrub: the origin remote was read with git -C <the script's checkout>"
else
  failc "GIT_DIR scrub: the origin remote was read with git -C <the script's checkout> (calls=<<$(cat "$STATE/revpin_calls")>>)"
fi
if grep -qF -- "/bogus/other-repo" "$STATE/revpin_calls"; then
  failc "GIT_DIR/GIT_WORK_TREE scrubbed (env -u): git never saw the inherited value"
else
  pass "GIT_DIR/GIT_WORK_TREE scrubbed (env -u): git never saw the inherited value"
fi
if all_urls_have "repos/fixture-owner/fixture-name/" "head_sha=$SHIM_SHA"; then pass "  the request targets the origin's OWNER/NAME"; else failc "  the request targets the origin's OWNER/NAME ($(cat "$STATE/gh_urls"))"; fi

# Sub-test 2: invoking via a symlink from another directory must resolve the rev against the SCRIPT's
# real directory, not the symlink's location. The recording shim's PWD on the --show-toplevel call
# must be the real script dir (symlink resolved via readlink -f) and NEVER the symlink dir. A mutant
# that uses BASH_SOURCE[0] directly (no readlink -f) would run discovery from the symlink dir instead.
: >"$STATE/revpin_calls"
reset_state; T=0; G=0; norun_resp
LINKREPO="$WORK/otherrepo"; mkdir -p "$LINKREPO"
LINK="$LINKREPO/ci-status-link.sh"; ln -sf "$SCRIPT" "$LINK"
EXPECT_DIR="$(dirname "$(readlink -f "$SCRIPT")")"
"$REAL_TIMEOUT" 20 env PATH="$REVDIR:$SHIMDIR:$PATH" STATE="$STATE" \
      CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT=0 CI_STATUS_REGISTRATION_GRACE=0 \
      bash "$LINK" HEAD --wait >/dev/null 2>&1 || true
if grep -qF -- "PWD=[$EXPECT_DIR]" "$STATE/revpin_calls"; then
  pass "symlink resolved: rev discovery ran from the real script dir ($EXPECT_DIR)"
else
  failc "symlink resolved: rev discovery ran from the real script dir (want PWD=[$EXPECT_DIR]; calls=<<$(cat "$STATE/revpin_calls")>>)"
fi
if grep -qF -- "PWD=[$LINKREPO]" "$STATE/revpin_calls"; then
  failc "symlink dir must NOT be used for rev discovery (found PWD=[$LINKREPO])"
else
  pass "symlink dir not used for rev discovery"
fi

# ============================ --local-quality (opt-in) ============================

section "--local-quality: Quality AND the latest local-quality status by the expected publisher"

# A separate fixture gh runs the REAL jq programs the script passes (--jq) over JSON fixtures, so a
# mutation of either program, of the creator check or of the combination is caught here. Logins are
# synthetic (fixture-publisher, fixture-intruder). Fixture layout under $LQFIX:
#   runs.json / runs-c<poll>.json / runs-p<page>.json   Actions listing (page 1 per poll, or page N)
#   statuses-p<page>.json / statuses-c<poll>-p<page>.json   statuses list pages ([] when absent)
#   statuses-fail                                        statuses request fails (rc 1)
# <poll> is the count of page-1 Actions requests so far, so a --wait sequence can change per poll.
# The pinned statuses program, shared with tools/pr-ci-registered.sh (its test pins the same text).
# shellcheck disable=SC2016  # $s/$c are jq variables, not shell expansions
LQ_PIN='if type != "array" then "error|||" elif any(.[]; type != "object") then "error|||" elif length == 0 then "none|||" else ([.[] | select(.context == "local-quality")] | .[0]) as $s | if $s == null then (if length < 100 then "none|||" else "more|||" end) elif ($s.state | type) != "string" or ($s.creator | type) != "object" or ($s.creator.login | type) != "string" then "invalid|||" else (if $s.state == "success" then "lqsuccess" elif $s.state == "pending" then "lqpending" elif $s.state == "failure" or $s.state == "error" then "lqfail" else "invalid" end) as $c | if $c == "invalid" then "invalid|||" else $c + "|" + ($s.state | @base64) + "|" + ($s.creator.login | @base64) + "|" + (($s.description // "") | tostring | @base64) end end end'
if grep -qF -- "LQ_JQ='$LQ_PIN'" "$SCRIPT"; then pass "statuses jq matches the pinned program"; else failc "statuses jq drifted from the program pinned in this test"; fi
# The local-mode Actions program is the default program (JQ_PROG, extracted above) with ONLY its run
# filter replaced, and the workflow path reaches jq as a substituted literal: gh's embedded jq is
# never asked for $ENV, so an unsupported $ENV can neither drop the pin nor break default mode.
LQ_RUNS_JQ_TEMPLATE=""
eval "$(sed -n "/^LQ_RUNS_JQ_TEMPLATE='/,/^end end'\$/p" "$SCRIPT")"
lq_old='select(.event == "pull_request" or .event == "push")'
lq_new='select(.event == "pull_request" and .path == "@WORKFLOW_PATH@")'
if [ -n "$LQ_RUNS_JQ_TEMPLATE" ] && [ "$LQ_RUNS_JQ_TEMPLATE" = "${JQ_PROG/"$lq_old"/"$lq_new"}" ]; then
  pass "local-mode Actions jq = default jq with only the pinned run filter"
else
  failc "local-mode Actions jq drifted from the default program (template=<<$LQ_RUNS_JQ_TEMPLATE>>)"
fi
if grep -qF -- '$ENV' "$SCRIPT"; then failc "ci-status.sh must not use jq \$ENV"; else pass "ci-status.sh never uses jq \$ENV"; fi
LQBIN="$WORK/lqbin"; LQFIX="$WORK/lqfix"; LQXDG="$WORK/lqxdg"
mkdir -p "$LQBIN" "$LQXDG"
export LQFIX
cat >"$LQBIN/gh" <<'EOF'
#!/usr/bin/env bash
set -u
url=${2:-}
printf '%s\n' "$url" >>"$STATE/lq_urls"
[[ ${1:-} == api && ${3:-} == --jq && $# == 4 ]] || exit 96
page=${url##*&page=}
case $url in
  repos/test/repo/actions/runs\?*)
    c=$(cat "$STATE/lq_polls" 2>/dev/null || echo 0)
    if [[ $page == 1 ]]; then c=$((c + 1)); printf '%s' "$c" >"$STATE/lq_polls"; fi
    f="$LQFIX/runs-p$page.json"
    [[ $page == 1 && -f $LQFIX/runs-c$c.json ]] && f="$LQFIX/runs-c$c.json"
    [[ $page == 1 && ! -f $f ]] && f="$LQFIX/runs.json"
    [[ -f $f ]] || f="$LQFIX/no-runs.json"
    jq -r "$4" "$f" ;;
  repos/test/repo/commits/*/statuses\?per_page=100\&page=*)
    [[ -f $LQFIX/statuses-fail ]] && { echo 'HTTP 502: Bad Gateway' >&2; exit 1; }
    c=$(cat "$STATE/lq_polls" 2>/dev/null || echo 0)
    f="$LQFIX/statuses-c$c-p$page.json"
    [[ -f $f ]] || f="$LQFIX/statuses-p$page.json"
    [[ -f $f ]] || f="$LQFIX/no-statuses.json"
    jq -r "$4" "$f" ;;
  *) exit 97 ;;
esac
EOF
chmod +x "$LQBIN/gh"
EXPC="fixture-publisher"
lq_reset() {
  reset_state
  rm -rf "$LQFIX"; mkdir -p "$LQFIX"
  printf '%s\n' '{"workflow_runs":[]}' >"$LQFIX/no-runs.json"
  printf '%s\n' '[]' >"$LQFIX/no-statuses.json"
  : >"$STATE/lq_urls"; rm -f "$STATE/lq_polls"
  EXPC="fixture-publisher"; T=900; G=900
}
# qrun FILE CONCLUSION-OR-STATUS [PATH] [EVENT]: one Actions run in a listing file.
qrun() {
  local file=$1 st=$2 path=${3:-.github/workflows/quality.yml} event=${4:-pull_request} status=completed concl
  concl=$st
  case $st in queued|in_progress) status=$st; concl=null ;; esac
  jq -n --arg s "$status" --arg c "$concl" --arg p "$path" --arg e "$event" \
    '{workflow_runs: [{event:$e, path:$p, name:"Quality", html_url:"https://example.invalid/run/1", created_at:"2026-10-31T00:00:00Z", status:$s, conclusion:(if $c == "null" then null else $c end)}]}' >"$LQFIX/$file"
}
# st CONTEXT STATE LOGIN: one status object (newest-first lists are built with jq -s).
st() { jq -n --arg c "$1" --arg s "$2" --arg l "$3" '{context:$c, state:$s, creator:{login:$l}, description:("PASS run=0a1b2c3d4e5f base=0123456789ab skips=1 log=" + "fedcba9876543210")}'; }
lqinvoke() { # args -> ci-status.sh with the fixture gh first on PATH
  OUT="$("$REAL_TIMEOUT" 20 env PATH="$LQBIN:$SHIMDIR:$PATH" STATE="$STATE" LQFIX="$LQFIX" \
        CI_STATUS_REPO="test/repo" CI_STATUS_TIMEOUT="$T" CI_STATUS_REGISTRATION_GRACE="$G" \
        LOCAL_QUALITY_EXPECTED_CREATOR="$EXPC" XDG_CONFIG_HOME="$LQXDG" \
        bash "$SCRIPT" "$@" 2>&1)"
  RC=$?
}
lqurls() { wc -l <"$STATE/lq_urls" | tr -d ' '; }
statuses_calls() { grep -c '/statuses?' "$STATE/lq_urls"; }

# Both green -> 0, reading only the pull_request listing and the per-context statuses list.
lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 0 "LQ both green -> 0"
ck_has "local-quality: success by fixture-publisher" "  local-quality line reported"
if grep -q '&event=push&' "$STATE/lq_urls"; then failc "  push listing must not be read in local mode"; else pass "  push listing not read in local mode"; fi
if grep -Eq '/status($|\?)' "$STATE/lq_urls"; then failc "  combined commits/<sha>/status endpoint must never be read"; else pass "  combined status endpoint never read"; fi
ck_eq "$(statuses_calls)" 1 "  one statuses page read"
if grep -qF "repos/test/repo/commits/$SHIM_SHA/statuses?per_page=100&page=1" "$STATE/lq_urls"; then pass "  statuses read at the exact resolved SHA"; else failc "  statuses read at the exact resolved SHA"; fi

# A terminal local failure is actionable even when Quality's response is malformed.
for state in failure error; do
  lq_reset
  printf '%s\n' '{"workflow_runs":"invalid"}' >"$LQFIX/runs.json"
  st local-quality "$state" fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
  lqinvoke HEAD --local-quality
  ck_rc 1 "LQ terminal $state survives Quality-side error -> 1"
  ck_has "local-quality concluded '$state'" "  terminal local conclusion preserved"
done

# Quality-only success: local-quality missing is never green.
lq_reset; qrun runs.json success
lqinvoke HEAD --local-quality
ck_rc 2 "LQ Quality-only success (local missing) -> 2"
ck_has "no local-quality status registered" "  names the missing local-quality side"

# Local-only success: Quality missing is never green.
lq_reset; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ local-only success (Quality missing) -> 2"
ck_has "no Quality workflow run registered" "  names the missing Quality side"

# An unrelated workflow's green run on the SHA does not stand in for Quality (pinned path).
lq_reset; qrun runs.json success .github/workflows/other.yml
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ unrelated workflow success + local success -> 2 (not 0)"
ck_has "no Quality workflow run registered" "  unrelated workflow skipped like a schedule run"
ck_eq "$(grep -c 'actions/runs' "$STATE/lq_urls")" 2 "  a page of only other workflows continues to page 2"

# A push-event Quality run never counts in local mode (pull_request only).
lq_reset; qrun runs.json success .github/workflows/quality.yml push
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ push-event Quality run does not count -> 2"

# Unrelated contexts never count, including a case variant.
lq_reset; qrun runs.json success
{ st local-quality-x success fixture-publisher; st Local-Quality success fixture-publisher; } | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ only local-quality-x / Local-Quality contexts -> 2"
ck_has "no local-quality status registered" "  unrelated contexts are not local-quality"

# Stale success followed by a newer pending (newest first): not green.
lq_reset; qrun runs.json success
{ st local-quality pending fixture-publisher; st local-quality success fixture-publisher; } | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 1 "LQ stale success then newer pending -> 1"
ck_has "local-quality pending" "  pending reported, not green"

# Stale success followed by a newer failure: 1, terminal.
lq_reset; qrun runs.json success
{ st local-quality failure fixture-publisher; st local-quality success fixture-publisher; } | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 1 "LQ stale success then newer failure -> 1"
ck_has "local-quality concluded 'failure'" "  failure conclusion reported"

# error state is a non-success conclusion too.
lq_reset; qrun runs.json success
st local-quality error fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 1 "LQ error state -> 1"

# Newest by an intruder over an older publisher success: never green (exit 2 class).
lq_reset; qrun runs.json success
{ st local-quality success fixture-intruder; st local-quality success fixture-publisher; } | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ newest by intruder over older publisher success -> 2"
ck_has "created by fixture-intruder, not the configured publisher" "  foreign creator diagnosed"

# Older intruder, newer publisher success: green.
lq_reset; qrun runs.json success
{ st local-quality success fixture-publisher; st local-quality failure fixture-intruder; } | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 0 "LQ older intruder then newer publisher success -> 0"

# A Quality failure is a non-success even with local success.
lq_reset; qrun runs.json failure
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 1 "LQ Quality failure + local success -> 1"

# Expected-creator configuration: missing or malformed exits 2 before any request.
lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
EXPC=""
lqinvoke HEAD --local-quality
ck_rc 2 "LQ missing expected-creator config -> 2"
ck_eq "$(lqurls)" 0 "  no gh request without the expected creator"
ck_has "expected publisher login" "  missing-config diagnostic"
for bad in 'bad login' '-leading-hyphen' 'fixture-publisher;x' 'a[bot]x'; do
  lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
  EXPC="$bad"
  lqinvoke HEAD --local-quality
  ck_rc 2 "LQ malformed expected creator '$bad' -> 2"
  ck_eq "$(lqurls)" 0 "  no gh request with a malformed creator"
done
# The XDG configuration file (outside the repository) is read when the variable is unset.
lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
mkdir -p "$LQXDG/local-quality"; printf 'fixture-publisher\n' >"$LQXDG/local-quality/expected-creator"
EXPC=""
lqinvoke HEAD --local-quality
ck_rc 0 "LQ expected creator from the XDG config file -> 0"
printf 'fixture-intruder\n' >"$LQXDG/local-quality/expected-creator"
lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
EXPC=""
lqinvoke HEAD --local-quality
ck_rc 2 "LQ config file naming another login rejects the publisher's status -> 2"
rm -rf "$LQXDG/local-quality"

# Pagination: the entry on page 2 behind 100 other contexts is found.
lq_reset; qrun runs.json success
jq -n '[range(100) | {context:"other", state:"success", creator:{login:"fixture-publisher"}}]' >"$LQFIX/statuses-p1.json"
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p2.json"
lqinvoke HEAD --local-quality
ck_rc 0 "LQ local-quality entry on page 2 behind 100 other contexts -> 0"
ck_eq "$(statuses_calls)" 2 "  exactly two statuses pages read"
# A short page without the context ends the listing (absence, not a further request).
lq_reset; qrun runs.json success
jq -n '[range(99) | {context:"other", state:"success", creator:{login:"fixture-publisher"}}]' >"$LQFIX/statuses-p1.json"
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p2.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ short page ends the listing (no page 2 read) -> 2"
ck_eq "$(statuses_calls)" 1 "  one statuses page read"
# Page bound: ten full pages without the context, the entry on page 11, is unknown (2).
lq_reset; qrun runs.json success
for page in {1..10}; do
  jq -n '[range(100) | {context:"other", state:"success", creator:{login:"fixture-publisher"}}]' >"$LQFIX/statuses-p$page.json"
done
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p11.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ page bound reached -> 2"
ck_eq "$(statuses_calls)" 10 "  page 11 never requested"
ck_has "page bound reached" "  page bound diagnosed"

# Statuses API failure, non-array response, unknown state and malformed entries: 2, never green.
lq_reset; qrun runs.json success; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
: >"$LQFIX/statuses-fail"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ statuses API failure -> 2"
lq_reset; qrun runs.json success; printf '%s\n' '{"message":"Not Found"}' >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ non-array statuses response -> 2"
lq_reset; qrun runs.json success; st local-quality neutral fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ unknown state value -> 2"
lq_reset; qrun runs.json success
printf '%s\n' '[{"context":"local-quality","state":"success"}]' >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 2 "LQ entry without a creator -> 2"
lq_reset; qrun runs.json success
printf '%s\n' '[{"context":"local-quality","state":"success","creator":{"login":"fixture-publisher"},"description":"PASS\u001b[2J\nRESULT: forged"}]' >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --local-quality
ck_rc 0 "LQ control characters in the description do not change the result"
if grep -q '^RESULT: forged' <<<"$OUT"; then failc "  description cannot start a forged console line"; else pass "  description cannot start a forged console line"; fi

# Invalid workflow path override: 2 before any request (it is embedded only after validation).
lq_reset; qrun runs.json success
OUT="$("$REAL_TIMEOUT" 20 env PATH="$LQBIN:$SHIMDIR:$PATH" STATE="$STATE" LQFIX="$LQFIX" CI_STATUS_REPO="test/repo" \
      CI_STATUS_TIMEOUT=900 CI_STATUS_REGISTRATION_GRACE=900 LOCAL_QUALITY_EXPECTED_CREATOR=fixture-publisher \
      CI_STATUS_WORKFLOW_PATH='.github/workflows/q.yml" or true' bash "$SCRIPT" HEAD --local-quality 2>&1)"; RC=$?
ck_rc 2 "LQ invalid CI_STATUS_WORKFLOW_PATH -> 2"
ck_eq "$(lqurls)" 0 "  no gh request with an invalid workflow path"

# Default mode (no flag) never reads statuses, and CI_STATUS_WORKFLOW_PATH, which only
# --local-quality reads, cannot pin it to another workflow.
lq_reset; qrun runs.json success .github/workflows/quality.yml push
OUT="$("$REAL_TIMEOUT" 20 env PATH="$LQBIN:$SHIMDIR:$PATH" STATE="$STATE" LQFIX="$LQFIX" CI_STATUS_REPO="test/repo" \
      CI_STATUS_TIMEOUT=900 CI_STATUS_REGISTRATION_GRACE=900 CI_STATUS_WORKFLOW_PATH=.github/workflows/other.yml \
      bash "$SCRIPT" HEAD 2>&1)"; RC=$?
ck_rc 0 "default mode: push run still counts, CI_STATUS_WORKFLOW_PATH ignored"
ck_eq "$(statuses_calls)" 0 "  default mode never reads the statuses endpoint"
if grep -q '&event=push&' "$STATE/lq_urls"; then pass "  default mode still reads the push listing"; else failc "  default mode still reads the push listing"; fi

# --wait: local pending, then success, with Quality green -> 0.
lq_reset; T=900; G=120; qrun runs.json success
st local-quality pending fixture-publisher | jq -s . >"$LQFIX/statuses-c1-p1.json"
st local-quality pending fixture-publisher | jq -s . >"$LQFIX/statuses-c2-p1.json"
{ st local-quality success fixture-publisher; st local-quality pending fixture-publisher; } | jq -s . >"$LQFIX/statuses-c3-p1.json"
lqinvoke HEAD --wait --local-quality
ck_rc 0 "LQ --wait: local pending then success -> 0"
ck_eq "$(cat "$STATE/lq_polls")" 3 "  three polls"
# --wait: Quality green, local never registered -> ABSENCE at the grace boundary naming local-quality.
lq_reset; T=900; G=60; qrun runs.json success
lqinvoke HEAD --wait --local-quality
ck_rc 2 "LQ --wait: local never registered -> ABSENCE"
ck_has "ABSENCE; no local-quality status was OBSERVED" "  absence names the local-quality side"
ck_eq "$(simnow)" 60 "  stopped at the registration grace boundary, not the overall deadline"
# --wait: local green, Quality never registered -> ABSENCE naming Quality.
lq_reset; T=900; G=60; st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --wait --local-quality
ck_rc 2 "LQ --wait: Quality never registered -> ABSENCE"
ck_has "ABSENCE; no Quality workflow run was OBSERVED" "  absence names the Quality side"
# --wait: Quality observed pending early, local first observed after grace -> still ABSENCE (both
# must be observed to end the registration grace; one side alone does not extend it).
lq_reset; T=900; G=30; qrun runs.json in_progress
st local-quality success fixture-publisher | jq -s . >"$LQFIX/statuses-c4-p1.json"
lqinvoke HEAD --wait --local-quality
ck_rc 2 "LQ --wait: one side observed does not end the registration grace"
ck_eq "$(simnow)" 30 "  stopped at the grace boundary"
# --wait: both observed, local pending forever -> TIMEOUT 1 at the overall deadline.
lq_reset; T=90; G=30; qrun runs.json success
st local-quality pending fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --wait --local-quality
ck_rc 1 "LQ --wait: local pending through the deadline -> TIMEOUT"
ck_has "TIMEOUT after 90s" "  timeout diagnostic"
ck_eq "$(simnow)" 90 "  ran to the overall deadline"
# --wait: a foreign latest status never turns green; it rides through as an error to the deadline.
lq_reset; T=90; G=30; qrun runs.json success
st local-quality success fixture-intruder | jq -s . >"$LQFIX/statuses-p1.json"
lqinvoke HEAD --wait --local-quality
ck_rc 2 "LQ --wait: foreign latest status -> 2"
ck_has "not the configured publisher" "  foreign creator in the final diagnostic"
# Default overall budget in local mode is 18000 s.
lq_reset; qrun runs.json success; st local-quality pending fixture-publisher | jq -s . >"$LQFIX/statuses-p1.json"
seq_set 0 0 17999 18000 18000
OUT="$("$REAL_TIMEOUT" 20 env -u CI_STATUS_TIMEOUT -u CI_STATUS_REGISTRATION_GRACE PATH="$LQBIN:$SHIMDIR:$PATH" \
      STATE="$STATE" LQFIX="$LQFIX" CI_STATUS_REPO="test/repo" LOCAL_QUALITY_EXPECTED_CREATOR=fixture-publisher \
      bash "$SCRIPT" HEAD --wait --local-quality 2>&1)"; RC=$?
ck_rc 1 "LQ default overall budget: pending through the deadline -> timeout"
ck_has "TIMEOUT after 18000s" "  local-mode default overall budget is 18000 s"
# Every local-mode request is wrapped in timeout with the kill grace.
if all_kill_grace_eq 5; then pass "  every gh request in local mode carried -k 5"; else failc "  every gh request in local mode carried -k 5"; fi

# ============================ summary ============================

printf '\n'
if [ "$FAILS" -eq 0 ]; then
  printf 'PASS: ci-status harness (%s checks, 0 failures)\n' "$N"
  exit 0
else
  printf 'FAIL: ci-status harness (%s checks, %s failures)\n' "$N" "$FAILS"
  exit 1
fi
