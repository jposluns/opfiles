#!/usr/bin/env bash
# Report, and optionally wait for, the CI conclusion for a commit.
#
# WHY THIS EXISTS. `gh pr checks`, `gh pr status`, and `gh run watch` all resolve
# GraphQL `statusCheckRollup`, which reads the Checks API. A fine-grained personal
# access token CANNOT be granted Checks access: it is a standing GitHub limitation,
# not a missing setting, so those commands return
#   "Resource not accessible by personal access token"
# and no permission change fixes it. Only a GitHub App, or a classic token with the
# `repo` scope, can read Checks.
#
# DO NOT substitute `commits/<sha>/status`. GitHub Actions publishes through Check
# Runs, not the older Statuses API, so that endpoint returns `state: pending` with
# `total_count: 0` FOREVER, even on a commit whose workflow succeeded.
# Anything treating it as the green signal hangs; anything inverting it merges on a lie.
#
# This reads `actions/runs?head_sha=`, which needs only Actions: Read.
#
# REPOSITORY. CI_STATUS_REPO (OWNER/NAME) when it is set; otherwise OWNER/NAME is derived at run
# time from the origin remote of this script's own checkout (a github.com HTTPS or SSH URL). There
# is no default: when neither yields a repository, the script exits 2 before any query. A NAME
# made only of dots is refused, so no request path can hold a dot segment.
#
# LOCAL-QUALITY MODE (--local-quality; opt-in). The default mode never reads or requires a
# local-quality status. A local publisher, once one is deployed for this repository, posts a
# commit status with context exactly `local-quality` on the PR head SHA. That is a SEPARATE
# surface from Actions: it is read from the per-context list
# `commits/<sha>/statuses` (Commit statuses: read), never from the combined
# `commits/<sha>/status` endpoint, whose top-level state the warning above still applies to,
# and it never reports an Actions conclusion. With --local-quality the result is green ONLY
# when BOTH hold: (1) the newest pull_request run of the pinned Quality workflow
# (CI_STATUS_WORKFLOW_PATH, default .github/workflows/quality.yml; runs of other workflows
# and push runs are skipped) completed with success, and (2) the LATEST `local-quality`
# status on the SHA is `success` AND was created by the expected publisher login, configured
# OUTSIDE the repository: LOCAL_QUALITY_EXPECTED_CREATOR, else the first line of
# ${XDG_CONFIG_HOME:-$HOME/.config}/local-quality/expected-creator. A missing or malformed
# value exits 2 before any query. A latest status by any other login is never green (exit 2
# class), because GitHub's required check would read that latest status too. Missing or
# pending is never green. The description is display only. Registration is tracked
# separately for the two sides under the one overall deadline: the registration grace ends
# only when both have been observed, and a side never observed by then is an ABSENCE naming
# that side. In this mode the default CI_STATUS_TIMEOUT is 18000s, sized for a full local
# run plus queue time and margin: it waits for the local publisher's run, which the 5-minute
# limit of the hosted Quality job does not bound. A creator check binds the reader to one
# account; it does not stop that account's other holders, and it cannot enforce GitHub's web
# merge path.
#
# NEWEST-RUN SCOPE (deliberate scoped exclusion). This tool evaluates only the NEWEST workflow run
# for the commit among pull_request and push events. Separate server-filtered
# listings exclude schedule runs before pagination. The newest candidates
# are compared by created_at, with pull_request winning ties. One workflow can
# produce several runs on a commit; selecting one is not an all-runs merge gate.
# Gating on every run of every workflow is not implemented.
#
# Usage:
#   tools/ci-status.sh                 # current HEAD, report once
#   tools/ci-status.sh <sha>           # a given commit, report once
#   tools/ci-status.sh <sha> --wait    # poll until terminal, bounded and fail-loud
#   tools/ci-status.sh <sha> --wait --local-quality   # merge readiness: Quality AND local-quality
#
# TWO BUDGETS UNDER --wait (nested, NOT additive).
#   CI_STATUS_TIMEOUT             (default 900s) is the OVERALL polling budget, measured
#                                 from invocation start. Nothing extends it. The default is
#                                 sized to the Quality job: a run has the 600s grace below to
#                                 register, and GitHub then ends the job within its 5-minute
#                                 limit (timeout-minutes: 5), so 900s covers the whole job.
#   CI_STATUS_REGISTRATION_GRACE  (default 600s) is the maximum time to wait for a run to
#                                 FIRST register (be observed). It is NESTED under the
#                                 overall budget: registration time is consumed FROM the
#                                 overall budget, and the effective grace is clamped to the
#                                 overall timeout (a grace larger than the timeout is capped;
#                                 the registration window ends at whichever comes first,
#                                 start+grace or the overall deadline).
#   Both are validated as non-negative decimal integers in [0, 31536000]; a non-integer,
#   negative, or out-of-range value exits 2 before any query. Zero grace is VALID: a
#   confirmed absence is then immediately terminal (one query, no registration retries).
#   Zero overall timeout permits one immediate query and no retries of any kind.
#
# ELAPSED TIME is tracked against the wall clock (`date +%s`, clamped to a monotonic maximum so a
# reading below the running maximum is ignored) FOR ACCURACY, and, INDEPENDENTLY, a monotonic
# cumulative-sleep accumulator bounds the total time spent SLEEPING to the active budget and so
# GUARANTEES TERMINATION regardless of the wall clock: the accumulator only ever increases, by the
# script's own chosen sleeps. Expiry and the remaining-budget sizing take the TIGHTER of the
# wall-clock deadline and this accumulator. Under a NORMAL (forward-advancing) wall clock the
# overall deadline additionally bounds total ELAPSED time to approximately the budget plus the
# boundary-query allowance, the 1s listing floor and kill grace. Under a FROZEN or BACKWARD
# wall clock the loop still terminates: each listing is bounded to ten pages independently
# of the clock.
# Total ELAPSED time is bounded by the cumulative sleeps PLUS the per-request
# `timeout` allowances (request durations are NOT counted by the sleep accumulator), which can
# EXCEED the nominal budget. A truly monotonic time source (for example /proc/uptime) would tighten
# the elapsed bound under a frozen or backward clock and is a possible future hardening. The
# deadlines are absolute instants derived once from the start time.
#
# PER-REQUEST BOUNDING. Every `gh` call is wrapped in GNU `timeout` (SIGTERM, then SIGKILL
# after a fixed kill grace) so a hung request and its child are terminated. An ordinary
# request is capped by BOTH the remaining active budget AND a fixed finite per-request limit
# (PER_REQUEST_MAX). The immediate zero-budget query and a final boundary query PER DEADLINE PHASE
# (at most two per invocation, one at the registration boundary and one at the overall deadline) get
# a fixed finite allowance (BOUNDARY_ALLOWANCE). Each event listing gets a 1s first-page
# floor if the shared allowance has expired. This extends the query allowance, not the
# overall or registration deadline. Under a NORMAL (forward-advancing) wall clock the
# MAXIMUM TOTAL INVOCATION DURATION is therefore approximately
#   CI_STATUS_TIMEOUT + BOUNDARY_ALLOWANCE + 1s + KILL_GRACE + minor per-iteration overhead
# (request processing is not free; this is a bound, not a promise of zero overhead). Under a FROZEN
# or BACKWARD wall clock the sleep accumulator still forces termination, but because request
# durations are NOT counted by it, total elapsed time is bounded by the cumulative sleeps plus the
# sum of the per-request `timeout` allowances and can exceed that nominal figure (see ELAPSED TIME).
#
# LOCAL-SETUP FAULTS fail loudly up front. A missing `gh`/`timeout` binary and a temp-file
# creation failure exit 2 in seconds, rather than riding the full budget as repeated "transient"
# query errors; the API-error ride-through is reserved for genuine API/response faults.
#
# EXIT-CODE CONTRACT.
#   0  an OBSERVED run completed with conclusion=success.
#   1  an observed run completed non-success (any other conclusion, or a missing one);
#      OR (--wait) an observed run never concluded before the overall deadline (timeout);
#      OR (--wait) a run was observed then the API reported no run through the deadline;
#      OR (report-once) a recognized non-terminal run.
#      With --local-quality, 1 also covers a local-quality failure or error status, and a
#      pending status on either side at the deadline or in report-once.
#   2  (--wait) no run was OBSERVED within the registration grace (ABSENCE);
#      OR (--local-quality) a missing, malformed, unknown-state or foreign-creator
#         local-quality status, or a missing or malformed expected-creator setting;
#      OR (report-once) no run is registered yet (never-registered);
#      OR an API/response/timeout ERROR that never resolved (inability to determine state);
#      OR an invalid setting, an unknown option, a duplicate revision, a missing local binary,
#         a temp-file failure, an unresolved revision, or no repository (see REPOSITORY).
#   Report-once (no --wait) NEVER returns 0 for a non-terminal run. Only --wait polls, and
#   only --wait has the registration grace and error/absence ride-through.
#
# The three failure diagnostics are deliberately distinct: ABSENCE (no run observed within
# grace), TIMEOUT (a run was observed but did not conclude), and ERROR (state could not be
# determined). An error NEVER sets the run-observed flag and NEVER masquerades as absence.
set -uo pipefail

PER_REQUEST_MAX=60      # fixed finite cap (seconds) on an ordinary gh request
BOUNDARY_ALLOWANCE=60   # fixed finite cap (seconds) on the immediate zero-budget query and on a final boundary query per deadline phase (at most two per --wait invocation)
KILL_GRACE=5            # seconds after SIGTERM before timeout(1) sends SIGKILL
MAX_SECONDS=31536000    # accepted upper bound (365 days) for each budget env var
POLL_INTERVAL=15        # cadence (seconds) between polls under --wait

REPO=""                 # OWNER/NAME, set before any query (see REPOSITORY above)

# Globals set by helpers (initialized so `set -u` and shellcheck are satisfied).
NOW=0
MONO=0
Q_OUT=""
Q_RC=0
Q_ERR=""
CAT=""
STATUS=""
CONCL=""
NAME=""
URL=""
# --local-quality state (unused, and the reads below never run, without the flag).
LOCAL=0
PIN_PATH=""          # the validated Quality workflow path, substituted into LQ_RUNS_JQ
LQ_RUNS_JQ=""
EXPECTED_CREATOR=""
LQ_OUT=""
LQ_RC=0
LQ_ERR=""
LQ_CAT=""
LQ_STATE=""
LQ_LOGIN=""
LQ_DESC=""
A_SEEN=0
L_SEEN=0
MISSING=""
run_seen=0
# The local-quality statuses program (LQ_JQ below; tools/test_ci_status.sh pins its text).
# Newest first: the first `local-quality` entry in page order is the latest. jq decides the
# category; the state, creator login and description are @base64 fields, so no "|" can shift them.
# shellcheck disable=SC2016  # $s/$c are jq variables, not shell expansions
# The --local-quality Actions program: the default query_page program with ONLY its run filter
# replaced (the harness checks that equality). @WORKFLOW_PATH@ is replaced by the validated path
# (allowlisted characters only, so it cannot leave the jq string literal) before any request.
# shellcheck disable=SC2016  # $r/$s/$c/$cat are jq variables inside a single-quoted jq program, not shell expansions
LQ_RUNS_JQ_TEMPLATE='if (.workflow_runs|type) != "array" then "error||||"
elif (.total_count // 0) > 1000 then "error||||"
else [.workflow_runs[] | select(.event == "pull_request" and .path == "@WORKFLOW_PATH@")] as $runs
| if (.workflow_runs|length) == 0 then "norun||||"
elif ($runs|length) == 0 then "more||||"
else $runs[0] as $r
  | ($r.status // "") as $s | ($r.conclusion // "-") as $c
  | (if $s=="completed" then (if $c=="success" then "success" else "otherterm" end)
     elif ($s=="queued" or $s=="in_progress" or $s=="waiting" or $s=="requested" or $s=="pending" or $s=="action_required") then "nonterm"
     else "error" end) as $cat
  | $cat + "|" + ($s|@base64) + "|" + ($c|@base64) + "|" + (($r.name//"")|@base64) + "|" + (($r.html_url//"")|@base64) + "\n" + ($r.created_at // "")
end end'
LQ_JQ='if type != "array" then "error|||" elif any(.[]; type != "object") then "error|||" elif length == 0 then "none|||" else ([.[] | select(.context == "local-quality")] | .[0]) as $s | if $s == null then (if length < 100 then "none|||" else "more|||" end) elif ($s.state | type) != "string" or ($s.creator | type) != "object" or ($s.creator.login | type) != "string" then "invalid|||" else (if $s.state == "success" then "lqsuccess" elif $s.state == "pending" then "lqpending" elif $s.state == "failure" or $s.state == "error" then "lqfail" else "invalid" end) as $c | if $c == "invalid" then "invalid|||" else $c + "|" + ($s.state | @base64) + "|" + ($s.creator.login | @base64) + "|" + (($s.description // "") | tostring | @base64) end end end'

ts() { date -u +%H:%M:%SZ; }

# _display_safe: printable-ASCII allowlist (0x20-0x7e) for single-line display fields. It removes C0
# controls, DEL (0x7f), and every byte >= 0x80, so no C1 control (for example U+009B, 8-bit CSI) in any
# encoding survives; non-ASCII text degrades to its ASCII characters, acceptable for a display field.
_display_safe() { LC_ALL=C tr -cd '\040-\176'; }
# _diag_safe: the same allowlist plus tab and newline, for readable multi-line raw diagnostics.
_diag_safe() { LC_ALL=C tr -cd '\011\012\040-\176'; }

# now: read the wall clock and clamp it to a monotonic maximum. A reading below the running
# maximum (a backward clock) is ignored, so elapsed time never decreases and a wait cannot be
# extended by moving the clock back. Sets the global NOW.
now() {
  local raw
  raw="$(date +%s)"
  if [ "$raw" -gt "$MONO" ]; then MONO="$raw"; fi
  NOW="$MONO"
}

# validate_budget NAME VALUE: exit 2 unless VALUE is a non-negative decimal integer within range.
validate_budget() {
  local name="$1" val="$2" s
  case "$val" in
    ''|*[!0-9]*)
      printf 'ERROR: %s must be a non-negative integer number of seconds (got: %s).\n' "$name" "$val" >&2
      exit 2
      ;;
  esac
  # Magnitude guard, immune to integer overflow: strip leading zeros, then compare the remaining
  # digit count against the maximum's digit count BEFORE any arithmetic. A value like
  # 18446744073709551616 would WRAP in `$(( ... ))` and pass a plain numeric comparison; catching it
  # by length first means the arithmetic below only ever sees a value that fits in a signed 64-bit int.
  s="$val"
  while [ "${s#0}" != "$s" ] && [ -n "$s" ]; do s="${s#0}"; done
  [ -z "$s" ] && s=0
  if [ "${#s}" -gt "${#MAX_SECONDS}" ]; then
    printf 'ERROR: %s exceeds the maximum of %s seconds (got: %s).\n' "$name" "$MAX_SECONDS" "$val" >&2
    exit 2
  fi
  if [ "$(( 10#$val ))" -gt "$MAX_SECONDS" ]; then
    printf 'ERROR: %s exceeds the maximum of %s seconds (got: %s).\n' "$name" "$MAX_SECONDS" "$val" >&2
    exit 2
  fi
}

# query TIMEOUT_SECONDS: both event listings share one bounded allowance (including
# zero-budget/boundary allowances). At each listing start, an expired allowance gets
# a 1s first-page floor; extra pages never reset it. Overall/registration deadlines
# stay fixed. Each request keeps KILL_GRACE. Exhaustion within a listing is an error.
# Listings over 1000 total results fail closed; ten schedule-only pages also fail.
# Empty pages within that window end the listing; nonempty schedule-only pages advance in API order.
# Sets Q_OUT (jq result or raw text),
# Q_RC (gh / timeout exit status), Q_ERR (stderr). The CATEGORY is decided INSIDE jq from the
# structured fields (.status / .conclusion), so a "|" inside any display field cannot shift the
# machine-read classification (the delimiter-injection false-green). The display fields
# (status, conclusion, name, html_url) are @base64-encoded: the base64 alphabet contains no "|",
# so they cannot inject a delimiter either. A non-array .workflow_runs is an explicit "error"
# sentinel and an empty array is an explicit "norun" sentinel, kept distinct from a real run whose
# nullable .status must never be mistaken for "no run yet".
#
# gh STDOUT and STDERR are redirected to FRESH per-poll regular files, read AFTER `timeout` returns,
# then UNLINKED immediately. Two properties matter, and both are load-bearing:
#   (1) Reading a regular file returns at EOF and cannot be held open by a surviving writer, so a gh
#       grandchild that ignores SIGTERM and inherits stdout cannot block the read past the timeout
#       and kill grace. A `Q_OUT="$(timeout ... gh ...)"` command-substitution capture WOULD block,
#       because its pipe stays open until EVERY descendant closes it.
#   (2) A FRESH file per poll means a descendant that survived a PRIOR poll and still holds that
#       poll's fd writes into an ALREADY-UNLINKED inode, so it cannot contaminate the file THIS poll
#       reads. Reusing one truncated file does NOT revoke the survivor's fd, and its late write could
#       overwrite the next poll's result and produce a FALSE GREEN; a fresh file per poll removes
#       that channel entirely.
# Each temp file's name embeds this process's PID (ci-status.<pid>.out|err.XXXXXX). query() unlinks
# its own pair inline for immediate reclaim during a long run, and the EXIT/INT/TERM/HUP trap
# (see cleanup()) glob-removes every ci-status.<pid>.* file this run created, so a signal or an exit
# arriving between mktemp and any assignment still leaves nothing behind.
query_page() {
  local to="$1" page="$2" event="$3" of ef
  of="$(mktemp "${TMPDIR:-/tmp}/ci-status.$$.out.XXXXXX")" || {
    printf 'ERROR: could not create a temp file (TMPDIR=%s).\n' "${TMPDIR:-/tmp}" >&2
    exit 2
  }
  ef="$(mktemp "${TMPDIR:-/tmp}/ci-status.$$.err.XXXXXX")" || {
    rm -f "$of"
    printf 'ERROR: could not create a temp file (TMPDIR=%s).\n' "${TMPDIR:-/tmp}" >&2
    exit 2
  }
  # --local-quality: LQ_RUNS_JQ is this same program with only the run filter replaced, pinning
  # pull_request runs of the validated Quality workflow path (other workflows' runs then read as
  # "more", like schedule runs). The path is a literal substituted after validation, never read
  # from the environment inside jq.
  if [ "$LOCAL" = 1 ]; then
    timeout -k "$KILL_GRACE" "$to" gh api "repos/${REPO}/actions/runs?head_sha=${SHA}&event=${event}&per_page=100&page=${page}" \
      --jq "$LQ_RUNS_JQ" >"$of" 2>"$ef"
  else
  # shellcheck disable=SC2016  # $r/$s/$c/$cat are jq variables inside a single-quoted jq program, not shell expansions
  timeout -k "$KILL_GRACE" "$to" gh api "repos/${REPO}/actions/runs?head_sha=${SHA}&event=${event}&per_page=100&page=${page}" \
    --jq 'if (.workflow_runs|type) != "array" then "error||||"
elif (.total_count // 0) > 1000 then "error||||"
else [.workflow_runs[] | select(.event == "pull_request" or .event == "push")] as $runs
| if (.workflow_runs|length) == 0 then "norun||||"
elif ($runs|length) == 0 then "more||||"
else $runs[0] as $r
  | ($r.status // "") as $s | ($r.conclusion // "-") as $c
  | (if $s=="completed" then (if $c=="success" then "success" else "otherterm" end)
     elif ($s=="queued" or $s=="in_progress" or $s=="waiting" or $s=="requested" or $s=="pending" or $s=="action_required") then "nonterm"
     else "error" end) as $cat
  | $cat + "|" + ($s|@base64) + "|" + ($c|@base64) + "|" + (($r.name//"")|@base64) + "|" + (($r.html_url//"")|@base64) + "\n" + ($r.created_at // "")
end end' >"$of" 2>"$ef"
  fi
  Q_RC=$?
  Q_OUT="$(cat "$of" 2>/dev/null)"
  Q_CREATED=""
  if [[ $Q_OUT == *$'\n'* ]]; then
    Q_CREATED=${Q_OUT#*$'\n'}
    Q_OUT=${Q_OUT%%$'\n'*}
    if [[ -n $Q_CREATED && ! $Q_CREATED =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
      Q_OUT='error||||'
    fi
  fi
  Q_ERR="$(cat "$ef" 2>/dev/null)"
  rm -f "$of" "$ef"
}

query() {
  local to="$1" page end=$(( SECONDS + $1 )) event
  local best='norun||||' newest='' candidate pipes
  # Each filtered listing starts with its newest qualifying run. Schedule
  # deletion cannot shift a qualifying run across a page boundary. Both
  # events share the original allowance, with a 1s first-page floor per
  # listing after expiry; equal timestamps prefer pull_request.
  for event in pull_request push; do
    # --local-quality reads the Quality workflow's pull_request runs only.
    if [ "${LOCAL:-0}" = 1 ] && [ "$event" = push ]; then continue; fi
    # Preserve a first-page observation when the shared budget just expired.
    (( end > SECONDS )) || end=$(( SECONDS + 1 ))
    page=1
    while :; do
      to=$(( end - SECONDS ))
      (( to > $1 )) && to=$1
      if (( to <= 0 )); then
        Q_RC=124; Q_OUT=''; Q_ERR='Actions pagination allowance exhausted'
        return
      fi
      query_page "$to" "$page" "$event"
      [[ $Q_RC == 0 ]] || return
      [[ $Q_OUT == 'more||||' ]] || break
      # Retain the defensive page bound even for inconsistent API responses.
      if (( page >= 10 )); then
        Q_RC=2; Q_OUT=''; Q_ERR='Actions pagination page bound reached; state unknown'
        return
      fi
      page=$(( page + 1 ))
    done
    # Validate each candidate before comparing, including an older candidate.
    # The selected candidate is decoded by classify below. Check success's
    # canonical jq fields here too, so a malformed older run cannot be hidden.
    pipes=${Q_OUT//[!|]/}
    if [[ ${#pipes} != 4 || ( $Q_OUT == success\|* && $Q_OUT != 'success|Y29tcGxldGVk|c3VjY2Vzcw==|'* ) ]]; then
      Q_OUT='error||||'; return
    fi
    # A malformed or error response from either listing must fail closed.
    case $Q_OUT in
      norun\|\|\|\|) continue ;;
      success\|*|otherterm\|*|nonterm\|*) ;;
      *) return ;;
    esac
    candidate=${Q_CREATED:-}
    if [[ -z $candidate ]]; then
      Q_OUT='error||||'; return
    fi
    if [[ $best == 'norun||||' || $candidate > $newest ]]; then
      best=$Q_OUT; newest=$candidate
    fi
  done
  Q_OUT=$best
}

# classify: turn the last query result into exactly one category. rc is inspected FIRST, so a
# failed call whose stdout happens to contain success-like text is an error, never a success; an
# empty stdout is likewise an error. Next the LINE SHAPE is checked: a well-formed line (a run line
# or a sentinel) carries EXACTLY four "|" delimiters (five fields), so a delimiter-free, truncated,
# or wrong-field-count line is treated as an error rather than trusted. Otherwise the CATEGORY is
# field 1 verbatim (a safe token that jq already decided: success / otherterm / nonterm / error /
# norun). STATUS/CONCL/NAME/URL are the base64-decoded display fields with control characters
# stripped, used ONLY for the human line and the diagnostic messages; the category is NEVER
# re-derived from them in bash, with one fail-closed exception: a `success` category must be BACKED
# by decoded status=="completed" AND conclusion=="success", or it is downgraded to error (a
# defence-in-depth cross-check that never changes behaviour for real jq output). Decoding an empty
# field yields an empty string, which is correct for the "error||||" / "norun||||" sentinels.
classify() {
  local f2 f3 f4 f5 pipes
  CAT=""; STATUS=""; CONCL=""; NAME=""; URL=""
  if [ "$Q_RC" -ne 0 ]; then CAT="error"; return; fi
  if [ -z "$Q_OUT" ]; then CAT="error"; return; fi
  # Line-shape guard: keep only the "|" characters and require exactly four. A malformed line
  # (no delimiters, too few, or too many fields) is an error, never a trusted category. Fail-closed.
  pipes="${Q_OUT//[!|]/}"
  if [ "${#pipes}" -ne 4 ]; then CAT="error"; return; fi
  CAT="$(printf '%s' "$Q_OUT" | cut -d'|' -f1)"
  # Field 1 must be one of the five tokens jq is designed to emit. Anything else (a jq change, a
  # corrupted response, an unexpected shape) is treated as an error rather than trusted, so a stray
  # token can never fall through as a false green or spin the polling loop. Fail-closed.
  case "$CAT" in
    success|otherterm|nonterm|norun|error) ;;
    *) CAT="error" ;;
  esac
  f2="$(printf '%s' "$Q_OUT" | cut -d'|' -f2)"
  f3="$(printf '%s' "$Q_OUT" | cut -d'|' -f3)"
  f4="$(printf '%s' "$Q_OUT" | cut -d'|' -f4)"
  f5="$(printf '%s' "$Q_OUT" | cut -d'|' -f5)"
  # Decode the display fields through a printable-ASCII allowlist (_display_safe), which removes C0
  # controls, DEL, and C1 controls together with any other non-ASCII byte. A field therefore cannot forge
  # a "RESULT: ..." line or inject a terminal escape, and the machine category (field 1 / rc) is untouched.
  STATUS="$(printf '%s' "$f2" | base64 -d 2>/dev/null | _display_safe)"
  CONCL="$(printf '%s' "$f3" | base64 -d 2>/dev/null | _display_safe)"
  NAME="$(printf '%s' "$f4" | base64 -d 2>/dev/null | _display_safe)"
  URL="$(printf '%s' "$f5" | base64 -d 2>/dev/null | _display_safe)"
  # Defence-in-depth: a success category must be backed by a completed+success record. If the decoded
  # fields disagree (a crafted or corrupted line whose field 1 says success), downgrade to error
  # rather than emit a false green. Real jq output always agrees, so this never changes behaviour.
  if [ "$CAT" = "success" ] && { [ "$STATUS" != "completed" ] || [ "$CONCL" != "success" ]; }; then
    CAT="error"
  fi
}

report_run() {
  printf '%s  %s: %s / %s\n' "$(ts)" "$NAME" "$STATUS" "$CONCL"
  if [ -n "$URL" ] && [ "$URL" != "-" ]; then printf '  %s\n' "$URL"; fi
  if [ "$LOCAL" = 1 ] && [ -n "$LQ_STATE" ]; then
    printf '%s  local-quality: %s by %s: %s\n' "$(ts)" "$LQ_STATE" "$LQ_LOGIN" "$LQ_DESC"
  fi
}

# load_expected_creator: --local-quality only. The publisher login is configuration held OUTSIDE
# the repository (environment, else the user's XDG config file), validated before any query.
load_expected_creator() {
  local v="${LOCAL_QUALITY_EXPECTED_CREATOR:-}" f
  if [ -z "$v" ]; then
    f="${XDG_CONFIG_HOME:-${HOME:-}/.config}/local-quality/expected-creator"
    if [ -f "$f" ] && [ -r "$f" ]; then IFS= read -r v <"$f" || true; fi
  fi
  if ! [[ $v =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}(\[bot\])?$ ]]; then
    printf 'ERROR: --local-quality needs the expected publisher login in LOCAL_QUALITY_EXPECTED_CREATOR or %s (missing or malformed).\n' \
      '${XDG_CONFIG_HOME:-$HOME/.config}/local-quality/expected-creator' >&2
    exit 2
  fi
  EXPECTED_CREATOR="$v"
}

# lq_query_page TIMEOUT PAGE: one bounded statuses page, captured through fresh regular files like
# query_page (same PID-named template, so cleanup() covers them).
lq_query_page() {
  local to="$1" page="$2" of ef
  of="$(mktemp "${TMPDIR:-/tmp}/ci-status.$$.out.XXXXXX")" || {
    printf 'ERROR: could not create a temp file (TMPDIR=%s).\n' "${TMPDIR:-/tmp}" >&2
    exit 2
  }
  ef="$(mktemp "${TMPDIR:-/tmp}/ci-status.$$.err.XXXXXX")" || {
    rm -f "$of"
    printf 'ERROR: could not create a temp file (TMPDIR=%s).\n' "${TMPDIR:-/tmp}" >&2
    exit 2
  }
  timeout -k "$KILL_GRACE" "$to" gh api "repos/${REPO}/commits/${SHA}/statuses?per_page=100&page=${page}" \
    --jq "$LQ_JQ" >"$of" 2>"$ef"
  LQ_RC=$?
  LQ_OUT="$(cat "$of" 2>/dev/null)"
  LQ_ERR="$(cat "$ef" 2>/dev/null)"
  rm -f "$of" "$ef"
}

# lq_query TIMEOUT: find the LATEST local-quality status (first in page order), bounded to ten pages
# within one allowance of TIMEOUT seconds (the first page always gets at least 1s). Sets LQ_CAT to
# lqsuccess / lqpending / lqfail (latest entry by the expected creator), none (no entry), foreign
# (latest entry by another login), invalid (malformed entry or unknown state) or error (unreadable).
lq_query() {
  local cap="$1" end=$(( SECONDS + $1 )) page=1 to pipes f2 f3 f4 login
  LQ_CAT="error"; LQ_STATE=""; LQ_LOGIN=""; LQ_DESC=""
  while :; do
    to=$(( end - SECONDS ))
    (( to > cap )) && to=$cap
    if (( to <= 0 )); then
      if (( page == 1 )); then to=1; else
        LQ_OUT=''; LQ_ERR='local-quality pagination allowance exhausted'; return
      fi
    fi
    lq_query_page "$to" "$page"
    if [ "$LQ_RC" -ne 0 ] || [ -z "$LQ_OUT" ]; then LQ_CAT="error"; return; fi
    pipes="${LQ_OUT//[!|]/}"
    if [ "${#pipes}" -ne 3 ]; then LQ_CAT="error"; return; fi
    LQ_CAT="${LQ_OUT%%|*}"
    [ "$LQ_CAT" = more ] || break
    if (( page >= 10 )); then
      LQ_CAT="error"; LQ_OUT=''; LQ_ERR='local-quality status page bound reached; state unknown'; return
    fi
    page=$(( page + 1 ))
  done
  case "$LQ_CAT" in
    none|invalid|error) return ;;
    lqsuccess|lqpending|lqfail) ;;
    *) LQ_CAT="error"; return ;;
  esac
  f2="$(printf '%s' "$LQ_OUT" | cut -d'|' -f2)"
  f3="$(printf '%s' "$LQ_OUT" | cut -d'|' -f3)"
  f4="$(printf '%s' "$LQ_OUT" | cut -d'|' -f4)"
  LQ_STATE="$(printf '%s' "$f2" | base64 -d 2>/dev/null | _display_safe)"
  login="$(printf '%s' "$f3" | base64 -d 2>/dev/null)"
  LQ_LOGIN="$(printf '%s' "$login" | _display_safe | cut -c1-64)"
  LQ_DESC="$(printf '%s' "$f4" | base64 -d 2>/dev/null | _display_safe | cut -c1-140)"
  # Defence in depth: the decoded state must back the jq category.
  case "$LQ_CAT:$LQ_STATE" in
    lqsuccess:success|lqpending:pending|lqfail:failure|lqfail:error) ;;
    *) LQ_CAT="invalid"; return ;;
  esac
  # The creator check: only the configured publisher's latest status counts.
  if [ "$login" != "$EXPECTED_CREATOR" ]; then LQ_CAT="foreign"; fi
}

# combine_local TIMEOUT: --local-quality only. Reads the local-quality status and folds it with the
# Actions category already in CAT into one category (success / otherterm / lqfail / nonterm / norun /
# error). Each side's first observation is recorded separately; run_seen (the end of the
# registration grace) requires both.
combine_local() {
  local acat="$CAT"
  lq_query "$1"
  case "$acat" in success|otherterm|nonterm) A_SEEN=1 ;; esac
  case "$LQ_CAT" in lqsuccess|lqpending|lqfail) L_SEEN=1 ;; esac
  if [ "$A_SEEN" = 1 ] && [ "$L_SEEN" = 1 ]; then run_seen=1; fi
  MISSING=""
  if [ "$acat" = error ] && [ "$LQ_CAT" = lqfail ]; then CAT="lqfail"; return; fi
  [ "$acat" = error ] && return
  case "$LQ_CAT" in
    error) CAT="error"; Q_OUT="local-quality: ${LQ_OUT}"; Q_ERR="$LQ_ERR"; return ;;
    invalid) CAT="error"; Q_OUT='local-quality: malformed entry or unknown state'; Q_ERR=''; return ;;
    foreign)
      CAT="error"; Q_ERR=''
      Q_OUT="local-quality: the latest status was created by ${LQ_LOGIN}, not the configured publisher"
      return ;;
  esac
  [ "$acat" = otherterm ] && return
  if [ "$LQ_CAT" = lqfail ]; then CAT="lqfail"; return; fi
  if [ "$acat" = success ] && [ "$LQ_CAT" = lqsuccess ]; then CAT="success"; return; fi
  [ "$acat" = norun ] && MISSING="Quality workflow run"
  [ "$LQ_CAT" = none ] && MISSING="${MISSING:+$MISSING and }local-quality status"
  if [ -n "$MISSING" ]; then CAT="norun"; return; fi
  CAT="nonterm"
  [ "$acat" = success ] && STATUS="completed, local-quality ${LQ_STATE}"
  return 0
}

# never_seen: the sides not yet observed, for an ABSENCE diagnostic.
never_seen() {
  local s=""
  [ "$A_SEEN" = 1 ] || s="Quality workflow run"
  [ "$L_SEEN" = 1 ] || s="${s:+$s and }local-quality status"
  printf '%s' "$s"
}

# cleanup: remove EVERY temp file this process created, matched by the PID embedded in the name
# (ci-status.<pid>.*). Because the name carries $$, the glob matches a file the INSTANT mktemp
# creates it, before any variable assignment, so a signal or exit arriving in that window still
# leaves nothing behind; and it catches any poll's files. query() also unlinks its own pair inline
# for immediate reclaim during a long run; this glob is the signal/allocation-window backstop.
# TMPDIR is read once per process and is stable within a run, so the create template and this glob
# always resolve the same directory. HONEST LIMIT: an untrappable SIGKILL landing between mktemp and
# the inline rm can still strand one file; that is inherent to file-based capture and cannot be
# closed in shell.
cleanup() { rm -f "${TMPDIR:-/tmp}/ci-status.$$."* 2>/dev/null || true; }
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM HUP

# Argument parsing. Accept --wait in any position; the first non-flag argument is the rev; a
# SECOND non-flag argument is an error (a stray SHA must not silently change the gated commit);
# anything else starting with a hyphen is an unknown option.
SHA_IN="HEAD"
SHA_SET=0
WAIT=""
for arg in "$@"; do
  case "$arg" in
    --wait) WAIT="--wait" ;;
    --local-quality) LOCAL=1 ;;
    -*) printf 'ERROR: unknown option %s (only --wait and --local-quality are supported).\n' "$arg" >&2; exit 2 ;;
    *)
      if [ "$SHA_SET" -eq 1 ]; then
        printf 'ERROR: more than one revision given (already had %s, then %s); pass at most one commit.\n' "$SHA_IN" "$arg" >&2
        exit 2
      fi
      SHA_IN="$arg"; SHA_SET=1
      ;;
  esac
done

# Validate the two budgets before any query, so an invalid setting never spends a request.
# The defaults are sized to the hosted Quality job (timeout-minutes: 5 in
# .github/workflows/quality.yml): a run has 600 s to register, then GitHub ends the job within
# 300 s, so 900 s covers the whole job and a wait never runs long past a job GitHub has ended.
# --local-quality also waits for a full local run, which that limit does not bound (see above).
DEFAULT_TIMEOUT=900
DEFAULT_GRACE=600
[ "$LOCAL" = 1 ] && DEFAULT_TIMEOUT=18000
validate_budget "CI_STATUS_TIMEOUT" "${CI_STATUS_TIMEOUT:-$DEFAULT_TIMEOUT}"
validate_budget "CI_STATUS_REGISTRATION_GRACE" "${CI_STATUS_REGISTRATION_GRACE:-$DEFAULT_GRACE}"
TIMEOUT="$(( 10#${CI_STATUS_TIMEOUT:-$DEFAULT_TIMEOUT} ))"
GRACE="$(( 10#${CI_STATUS_REGISTRATION_GRACE:-$DEFAULT_GRACE} ))"
# Effective grace is clamped to the overall timeout: the registration window can never exceed
# the overall budget, even when a larger grace is configured.
if [ "$GRACE" -gt "$TIMEOUT" ]; then EFF_GRACE="$TIMEOUT"; else EFF_GRACE="$GRACE"; fi

# --local-quality settings, validated before any query. The workflow path is substituted into the
# jq program as a literal only after this allowlist check.
if [ "$LOCAL" = 1 ]; then
  load_expected_creator
  PIN_PATH="${CI_STATUS_WORKFLOW_PATH:-.github/workflows/quality.yml}"
  if ! [[ $PIN_PATH =~ ^\.github/workflows/[A-Za-z0-9._-]+\.ya?ml$ ]]; then
    printf 'ERROR: CI_STATUS_WORKFLOW_PATH must name a file under .github/workflows/ (got: %s).\n' \
      "$(printf '%s' "$PIN_PATH" | _display_safe)" >&2
    exit 2
  fi
  LQ_RUNS_JQ="${LQ_RUNS_JQ_TEMPLATE//@WORKFLOW_PATH@/$PIN_PATH}"
fi

# Local-setup preflight: a missing required binary must fail in seconds, not ride the whole budget
# as repeated "transient" query errors. This is a local fault detectable up front; it does NOT
# weaken the ride-through for genuine API/response errors.
for bin in gh timeout; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    printf 'ERROR: required binary %s not found on PATH.\n' "$bin" >&2
    exit 2
  fi
done

# Confirm the timeout utility actually supports -k. Some minimal timeout implementations lack -k and
# would silently drop the kill-escalation, so a hung request would ride the full per-request allowance
# as an error instead of being terminated. Probe once, up front, so the fault fails loudly rather than
# at runtime.
if ! timeout -k 1 1 true >/dev/null 2>&1; then
  printf 'ERROR: the timeout utility does not support -k (need GNU/uutils coreutils timeout).\n' >&2
  exit 2
fi

# Resolve whatever rev was given to a FULL 40-character SHA, against THIS script's OWN repository
# rather than the ambient working directory, an inherited GIT_DIR/GIT_WORK_TREE, or a symlink's
# location. Three redirections are neutralized: a drifted cwd (a sibling checkout) cannot win because
# discovery runs from the script's directory; an inherited GIT_DIR/GIT_WORK_TREE cannot win because
# it is scrubbed (env -u ...) and so cannot override -C; and a symlink from another repo cannot win
# because BASH_SOURCE[0] is resolved through the symlink with readlink -f before its directory is
# taken. Rev resolution is pinned to the script's own checkout; if the script is not inside a git
# repo, it falls back to the ambient resolution (still env-scrubbed).
# The head_sha= filter matches only on the full SHA, so a short one silently returns zero runs; an
# unresolvable rev is an error, not an absent run, so fail loudly.
SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || printf '%s' "${BASH_SOURCE[0]}")"
SELF_REPO="$(cd "$(dirname "$SELF")" 2>/dev/null && env -u GIT_DIR -u GIT_WORK_TREE git rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$SELF_REPO" ]; then
  SHA="$(env -u GIT_DIR -u GIT_WORK_TREE git -C "$SELF_REPO" rev-parse --verify --quiet "${SHA_IN}^{commit}" 2>/dev/null)" || SHA=""
else
  SHA="$(env -u GIT_DIR -u GIT_WORK_TREE git rev-parse --verify --quiet "${SHA_IN}^{commit}" 2>/dev/null)" || SHA=""
fi
if [ -z "$SHA" ]; then
  printf 'ERROR: %s does not resolve to a commit in this repository.\n' "${SHA_IN}" >&2
  exit 2
fi

# The API repository: CI_STATUS_REPO when set, else OWNER/NAME from the origin remote of the
# script's OWN checkout (never the ambient directory's). There is no default owner or repository.
REPO="${CI_STATUS_REPO:-}"
if [ -z "$REPO" ] && [ -n "$SELF_REPO" ]; then
  ORIGIN_URL="$(env -u GIT_DIR -u GIT_WORK_TREE git -C "$SELF_REPO" remote get-url origin 2>/dev/null)" || ORIGIN_URL=""
  case "$ORIGIN_URL" in
    https://github.com/*) REPO="${ORIGIN_URL#https://github.com/}" ;;
    git@github.com:*) REPO="${ORIGIN_URL#git@github.com:}" ;;
    ssh://git@github.com/*) REPO="${ORIGIN_URL#ssh://git@github.com/}" ;;
  esac
  REPO="${REPO%/}"
  REPO="${REPO%.git}"
fi
if [ -z "$REPO" ]; then
  printf 'ERROR: no repository: set CI_STATUS_REPO to OWNER/NAME, or run this script from a checkout whose origin remote is a github.com repository.\n' >&2
  exit 2
fi
# The same check for both sources. A NAME made only of dots (. or ..) would put a dot segment
# into the request path, so it is refused too.
if ! [[ $REPO =~ ^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$ ]] || [[ ${REPO#*/} =~ ^\.+$ ]]; then
  printf 'ERROR: the repository must be OWNER/NAME (got: %s).\n' "$(printf '%s' "$REPO" | _display_safe)" >&2
  exit 2
fi

now
START="$NOW"
OVERALL_DEADLINE=$(( START + TIMEOUT ))
REG_DEADLINE=$(( START + EFF_GRACE ))

# Report-once: a single bounded query, classified, with the original exit semantics. The final
# `*)` arm is defensive: an unexpected category can never fall through into the polling loop.
if [ "$WAIT" != "--wait" ]; then
  query "$BOUNDARY_ALLOWANCE"
  classify
  [ "$LOCAL" = 1 ] && combine_local "$BOUNDARY_ALLOWANCE"
  case "$CAT" in
    success)   report_run; exit 0 ;;
    otherterm) report_run; printf 'RESULT: CI concluded %s, not success.\n' "'${CONCL}'"; exit 1 ;;
    lqfail)    report_run; printf 'RESULT: local-quality concluded %s, not success.\n' "'${LQ_STATE}'"; exit 1 ;;
    nonterm)   report_run; printf 'RESULT: run not terminal (status: %s); use --wait to gate on completion.\n' "'${STATUS}'"; exit 1 ;;
    norun)
      if [ "$LOCAL" = 1 ]; then
        printf '%s  no %s registered for this commit yet\n' "$(ts)" "$MISSING"
      else
        printf '%s  no workflow run registered for this commit yet\n' "$(ts)"
      fi
      exit 2 ;;
    error)
      if [ "$LOCAL" = 1 ]; then
        printf 'ERROR: could not determine the Quality and local-quality state for %s in %s\n' "$SHA" "$REPO"
      else
        printf 'ERROR: could not read workflow runs for %s in %s\n' "$SHA" "$REPO"
      fi
      printf '  raw: %s\n' "$(printf '%s' "${Q_OUT}${Q_ERR:+ | stderr: ${Q_ERR}}" | _diag_safe)"
      exit 2
      ;;
    *)
      printf 'ERROR: internal classification error.\n' >&2
      exit 2
      ;;
  esac
fi

# --wait: poll until a terminal state, an absence at the registration boundary, an
# unresolved error, or the overall deadline. run_seen flips to 1 the first time a recognized
# run status is observed and is NEVER reset; it selects which deadline/budget bounds an absence or
# error (registration before observation, overall after). Expiry and request sizing take the
# TIGHTER of the wall-clock deadline and the cumulative-sleep backstop SLEPT, so a backward or
# frozen wall clock cannot extend the wait or stall the loop.
run_seen=0
SLEPT=0
while :; do
  now
  cur="$NOW"
  if [ "$run_seen" -eq 0 ]; then
    active_deadline="$REG_DEADLINE"; active_budget="$EFF_GRACE"
  else
    active_deadline="$OVERALL_DEADLINE"; active_budget="$TIMEOUT"
  fi
  wall_remaining=$(( active_deadline - cur ))
  slept_remaining=$(( active_budget - SLEPT ))
  if [ "$slept_remaining" -lt "$wall_remaining" ]; then remaining="$slept_remaining"; else remaining="$wall_remaining"; fi
  if [ "$remaining" -le 0 ]; then
    req_to="$BOUNDARY_ALLOWANCE"
  else
    req_to="$remaining"
    [ "$req_to" -gt "$PER_REQUEST_MAX" ] && req_to="$PER_REQUEST_MAX"
  fi

  query "$req_to"
  classify
  # --local-quality: run_seen is set inside combine_local only when BOTH sides were observed.
  [ "$LOCAL" = 1 ] && combine_local "$req_to"

  # Process a recognized observation BEFORE testing expiry, so a terminal or pending result
  # seen on the boundary is honoured.
  case "$CAT" in
    success)
      report_run; exit 0
      ;;
    otherterm)
      report_run; printf 'RESULT: CI concluded %s, not success.\n' "'${CONCL}'"; exit 1
      ;;
    lqfail)
      report_run; printf 'RESULT: local-quality concluded %s, not success.\n' "'${LQ_STATE}'"; exit 1
      ;;
    nonterm)
      report_run
      run_seen=1
      ;;
    norun)
      if [ "$LOCAL" = 1 ]; then
        printf '%s  no %s registered for this commit yet\n' "$(ts)" "$MISSING"
      else
        printf '%s  no workflow run registered for this commit yet\n' "$(ts)"
      fi
      ;;
    error)
      printf '%s  transient error reading workflow runs (will retry within budget)\n' "$(ts)"
      ;;
    *)
      printf 'ERROR: internal classification error.\n' >&2
      exit 2
      ;;
  esac

  # Recompute the active deadline/budget: observing a run just moved the budget from registration
  # to overall, so a pending run seen exactly on the registration boundary continues on the
  # remaining overall budget rather than expiring.
  if [ "$run_seen" -eq 0 ]; then
    active_deadline="$REG_DEADLINE"; active_budget="$EFF_GRACE"
  else
    active_deadline="$OVERALL_DEADLINE"; active_budget="$TIMEOUT"
  fi
  now
  cur="$NOW"
  # Expired when the wall clock has reached the deadline OR the cumulative sleep has reached the
  # budget. The SLEPT term guarantees termination even if the wall clock is frozen or moving back.
  if [ "$cur" -ge "$active_deadline" ] || [ "$SLEPT" -ge "$active_budget" ]; then
    case "$CAT" in
      nonterm)
        printf 'RESULT: TIMEOUT after %ss; last status %s (run observed, never concluded).\n' "$TIMEOUT" "'${STATUS}'"
        exit 1
        ;;
      norun)
        if [ "$run_seen" -eq 0 ] && [ "$LOCAL" = 1 ]; then
          printf 'RESULT: ABSENCE; no %s was OBSERVED within the %ss registration grace for %s.\n' "$(never_seen)" "$EFF_GRACE" "$SHA"
          printf '  Check the Quality pull_request run and that the local-quality publisher was enqueued for this head.\n'
          exit 2
        elif [ "$run_seen" -eq 0 ]; then
          printf 'RESULT: ABSENCE; no workflow run was OBSERVED within the %ss registration grace for %s.\n' "$EFF_GRACE" "$SHA"
          printf '  Check that a workflow is triggered by this event and branch.\n'
          exit 2
        else
          printf 'RESULT: TIMEOUT after %ss; a run was observed but the API then reported no run through the deadline for %s.\n' "$TIMEOUT" "$SHA"
          exit 1
        fi
        ;;
      error)
        if [ "$run_seen" -eq 0 ]; then
          printf 'RESULT: ERROR; could not determine CI state within the %ss registration grace for %s (API/response error).\n' "$EFF_GRACE" "$SHA"
        else
          printf 'RESULT: ERROR; a run was observed but CI state could not be determined through the %ss deadline for %s.\n' "$TIMEOUT" "$SHA"
        fi
        printf '  raw: %s\n' "$(printf '%s' "${Q_OUT}${Q_ERR:+ | stderr: ${Q_ERR}}" | _diag_safe)"
        exit 2
        ;;
      *)
        printf 'ERROR: internal classification error.\n' >&2
        exit 2
        ;;
    esac
  fi

  # Not expired: sleep, capped so it lands on (never past) the active deadline AND never carries
  # the cumulative sleep past the budget. Both caps are positive here (not expired), so the sleep
  # is always >0 and SLEPT strictly increases, which is what guarantees termination.
  gap=$(( active_deadline - cur ))
  slept_gap=$(( active_budget - SLEPT ))
  s="$POLL_INTERVAL"
  [ "$s" -gt "$gap" ] && s="$gap"
  [ "$s" -gt "$slept_gap" ] && s="$slept_gap"
  # Defensive floor: both caps are positive in the not-expired path, so s is already >=1; this guards
  # against a future change letting s reach 0 or below, which would stall SLEPT and break termination.
  [ "$s" -lt 1 ] && s=1
  sleep "$s"
  SLEPT=$(( SLEPT + s ))
done
