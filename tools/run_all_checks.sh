#!/usr/bin/env bash
# The opfiles gate runner. Usage: tools/run_all_checks.sh [--ci]
#
# One runner for the whole repository: the pre-import gates (scaffold plan, section 4), the vendored
# AIQT rules gate, the agents-parity gate, the provenance deviations and addendum gates, their tests,
# the opfiles.ai site generator's self-test and drift gate (tools/gen_draft_site.py), and every gate
# of the imported OPF tooling's standalone runner (OPF-SELF-CONTAIN), which this runner absorbed when
# the OPF export landed at the repository root.
#
# Two modes, and the split between them is explicit:
#   local (no argument): the full run. Every gate below runs, including the tests of the two CI
#     helpers (ci-status-test and pr-ci-registered-test), every OPF self-test suite (the slowest
#     gates), the local-only names-fuzz gate (tools/test_names_fuzz.py, which compares the names
#     gate with GNU grep), the names-fuzz-self-test gate (the same file with --self-test, which
#     checks that the fuzz catches two weakened stubs of the names gate) and the local-only
#     line-width gate (tools/check_line_width.py, which needs the history back to the merge base of
#     HEAD with origin/main: in a copy with no git history, or with no origin/main, it exits 2 and
#     this run lists it as CANNOT-EVALUATE (exit 2) among the FAILED GATES and fails, so run the
#     full suite in a git clone that has origin/main). This is the run that counts as the local
#     full suite.
#   --ci: the hosted "Quality gates" job (.github/workflows/quality.yml), which has a 5-minute limit,
#     so it runs only the fast gates: the pre-import gates, the AIQT, agents-parity, provenance
#     deviations and provenance addendum gates and their self-tests, the two site generator gates
#     (draft-site-self-test and draft-site-drift) and the fast OPF contract gates
#     (child-status and its self-test, opf-homes-contract, opf-init-contract-check,
#     opf-selftest-registry, opf-prompt-pack, opf-declaration, opf-enforce-residuals and
#     commonmark-headings-selftest), and the four gates of the pinned site template copy
#     (baseline-pin, its self-test and that self-test's registry-driven execution, and
#     baseline-palette), line-width-self-test and public-export-self-test. The two helper tests,
#     the two names-fuzz gates, the line-width gate, the public-export gate and the heavy OPF
#     self-test suites do not run: the summary
#     lists each as NOT RUN with the reason, and the last line says this was the CI subset, so a CI
#     pass is never read as a full pass. The names gate runs with --ci (no denylist on a hosted
#     runner), as the gate names-ci-subset; the summary lists the full names gate as NOT RUN. The
#     public-export gate needs the same denylist, so it runs with --ci as public-export-ci-subset
#     (its structural checks, and the names checks that need no denylist); the summary lists the
#     full public-export gate as NOT RUN.
#   gate_settings below holds the reason for every gate --ci does not run; a gate it does not name
#   runs in both modes.
#
# Registrations. Each gate is one line `run_gate NAME python3 -I -B "<this directory>/SCRIPT" ARGS`,
# starting in the first column, before `report_gates`; a bash gate runs through tools/run_bash_gate.py
# so its line has that shape too. The imported OPF registration self-tests (tools/_opf_pack_manifest.py,
# tools/check_opf_init_p0.py and tools/_opf_adopt_observe.py) read every line that starts with
# run_gate as the roster of a local run and run this runner with a python3 fixture first on PATH: in a
# local run the recorded python3 calls must be exactly that roster, once each and in order, so the gate
# that only --ci runs is registered by run_ci_gate instead, and a local run dispatches its gates one
# at a time unless OPFILES_CHECK_JOBS says otherwise. The same self-tests mutate the dispatch block of
# gate_process and the FAILED GATES line below, so those keep the imported runner's text, and a failing
# local run ends with the imported runner's verdict line, OPF STANDALONE SUBSET: FAILED, which
# tools/_opf_pack_manifest.py reads. tools/_opf_pack_manifest.py and tools/check_opf_init_p0.py also
# edit the first run_gate line (one starting with run_gate and a space) that holds the here variable
# followed by a slash, or the OPF homes self-test's quoted gate name, and fail without one: keep both
# on a registration line. Both also fail if the whole text of their own registration line, or of the
# first run_gate line, appears anywhere else in the runner, for example at the end of a comment that
# quotes it.
#
# Concurrency. A local run starts one gate at a time by default and the --ci run up to one per core;
# OPFILES_CHECK_JOBS sets another count. The runner does not pass OPFILES_CHECK_JOBS or
# OPFILES_GATE_TIMEOUT on to its gates, so a gate that runs this runner itself (the self-tests above)
# runs it with the defaults. Each gate runs in its own subshell, from the repository root, with its own
# temporary directory as TMPDIR and stdin from /dev/null, its output kept in its own log.
#
# Signals. A background job of a non-interactive shell starts with SIGINT and SIGQUIT ignored, and an
# exec keeps an ignored signal ignored, so every gate would inherit that ignore from its subshell: a
# Python gate would see SIG_IGN for SIGINT instead of default_int_handler, and a self-test that
# delivers SIGINT would fail under this runner while passing in the foreground. gate_process therefore
# sets both back to their default action (trap -) just before the gate's dispatch, so every gate starts
# with them at default, and ignores them again in its own shell once the gate ends; the watchdogs keep
# them ignored. The reset is made in the gate's own shell rather than by a separate launcher process:
# a Python launcher would be an extra python3 call, which the OPF registration self-tests reject (see
# Registrations), an external launcher could not dispatch a gate that is a shell function (see
# Bounds), and a bash launcher cannot reset a signal that was ignored when it started. For that last
# reason a runner that is itself started with SIGINT or SIGQUIT ignored cannot undo that for its gates.
# Python also ignores SIGPIPE and SIGXFSZ at startup; tools/run_bash_gate.py sets those back to their
# default action before it starts a bash gate. The runner's own INT and TERM traps (see Reporting)
# belong to the runner's shell and are not affected.
#
# Bounds. Each gate has a wall-clock bound: OPFILES_GATE_TIMEOUT seconds (default 900; the workflow
# sets 90 to fit its job), raised for the heavy local-only OPF self-tests named in gate_settings
# (opf-tooling-selftest needs about 80 minutes on the reference host). A watchdog beside each gate
# records an overrun, sends TERM to every process below the gate's subshell and KILL 10 seconds later.
# The gate is then reported as TIMED OUT and counted as failed, whatever its exit status: a gate
# stopped at its bound never reads as a pass. The gate's dispatch runs in the gate's own shell, not
# under an external wrapper, so a shell function the caller defines (as the OPF self-tests do for
# python3) still dispatches it.
#
# Reporting. A line "finished NAME" is printed as each gate ends, so a run cut off from outside still
# shows which gates had finished. Each gate's output and the summary are then printed in the fixed gate
# order below, whatever order the gates finish in. A gate that cannot evaluate (exit 2, for example the
# names gate without its denylist) counts as failed: a gate that did not evaluate is never a pass. On
# INT or TERM the runner sends TERM to every process below it, KILL 10 seconds later to any still
# running, and only then removes the gates' temporary directories. The run exits 1 when any gate fails,
# and 2 when it cannot start.
#
# Never pipe this to a truncating sink: a masked exit code defeats the gate.
set -uo pipefail
# This script's directory, resolved in checked steps: a dirname that fails or prints nothing exits 2
# here, before any gate. CDPATH is cleared so that cd neither resolves through a CDPATH entry nor
# prints a match. The root is reached with a second cd, so the first here-and-slash in this file stays
# on a registration line (see Registrations above).
dir=$(dirname -- "$0") || exit 2
[ -n "$dir" ] || exit 2
here="$(CDPATH= cd -- "$dir/." && pwd)" || exit 2
root="$(CDPATH= cd -- "$here" && cd .. && pwd)" || exit 2

mode=local
case "$#:${1:-}" in
  0:) ;;
  1:--ci) mode=ci ;;
  *) echo "usage: tools/run_all_checks.sh [--ci]"; exit 2 ;;
esac

# Each Python gate launches isolated: `python3 -I -B`. -I drops the script's own directory from
# sys.path, so a sibling file cannot shadow a standard library import; -B and this variable keep
# bytecode out of the tree.
export PYTHONDONTWRITEBYTECODE=1

positive_int() {
  case "$2" in
    ''|*[!0-9]*|0) printf 'FATAL: %s must be a positive integer (got: %s)\n' "$1" "$2"; exit 2 ;;
  esac
}
if [ "$mode" = ci ]; then
  cores="$(nproc 2>/dev/null)" || cores=1
  jobs="${OPFILES_CHECK_JOBS:-$cores}"
else
  jobs="${OPFILES_CHECK_JOBS:-1}"
fi
gate_timeout="${OPFILES_GATE_TIMEOUT:-900}"
# Seconds between the TERM and the KILL that stop a gate at its bound, or every gate on INT or TERM.
kill_grace=10
positive_int OPFILES_CHECK_JOBS "$jobs"
positive_int OPFILES_GATE_TIMEOUT "$gate_timeout"
unset OPFILES_CHECK_JOBS OPFILES_GATE_TIMEOUT
for tool in ps awk mkfifo; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'FATAL: %s is required to bound each gate\n' "$tool"
    exit 2
  fi
done

work="$(mktemp -d "${TMPDIR:-/tmp}/run_all_checks.XXXXXX")" || work=""
if [ -z "$work" ] || [ ! -d "$work" ]; then
  echo "FATAL: could not create the runner's temporary directory"
  exit 2
fi
trap 'rm -rf -- "$work"' EXIT
# Explicit modes, so a restrictive umask (the OPF self-tests run this runner under umask 0200) cannot
# leave the runner unable to write its own scratch. The FIFO is never written: each watchdog waits on
# it with a builtin read, so a stopped watchdog leaves no sleeping child behind.
if ! chmod 700 -- "$work" || ! mkfifo -m 600 -- "$work/never"; then
  echo "FATAL: could not prepare the runner's temporary directory"
  exit 2
fi

# descendants PID [SKIP]: print the pid of every process below PID, from one ps snapshot, leaving out
# SKIP and every process below it.
descendants() {
  ps -A -o pid= -o ppid= 2>/dev/null | awk -v top="$1" -v skip="${2:-}" '
    { parent[$1] = $2 }
    END {
      below[top] = 1
      do {
        grew = 0
        for (pid in parent)
          if (!(pid in below) && pid != skip && (parent[pid] in below)) { below[pid] = 1; grew = 1 }
      } while (grew)
      for (pid in below) if (pid != top) print pid
    }'
}

# stop_gates: on INT or TERM to the runner, send TERM to every process below the runner (the gates'
# subshells, the gates and their children, the watchdogs), wait up to kill_grace seconds for them to
# end, then send KILL to any still running, and reap the gates' subshells.
# shellcheck disable=SC2329  # invoked by the traps below
stop_gates() {
  local pids pid alive="" tries=0
  pids="$(descendants "$$")"
  [ -n "$pids" ] || return 0
  # shellcheck disable=SC2086  # one pid per word
  kill -TERM $pids 2>/dev/null
  while [ "$tries" -lt $((kill_grace * 10)) ]; do
    alive=""
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then alive="$alive $pid"; fi
    done
    [ -n "$alive" ] || break
    sleep 0.1
    tries=$((tries + 1))
  done
  # shellcheck disable=SC2086  # one pid per word
  [ -z "$alive" ] || kill -KILL $alive 2>/dev/null
  wait 2>/dev/null
}
trap 'stop_gates; exit 130' INT
trap 'stop_gates; exit 143' TERM

failed=0
# Name each failing gate as it is reported and list the names again before the FAILED line, so a
# failing run never needs a hand re-run to find which gate failed.
failed_names=""
gate_names=()
gate_bounds=()
skipped_names=()
skipped_reasons=()
running=0

# gate_settings NAME: set gate_bound, the gate's wall-clock bound in seconds, and gate_skip, the reason
# this mode does not run the gate (empty when it runs). A raised bound is a floor: an
# OPFILES_GATE_TIMEOUT above it applies to that gate as well. The two largest suites get 6000 s: the
# OPF tooling self-test needs about 80 minutes on the reference host, and opf.py --self-test runs the
# adopt-apply suite in process as one of its own legs, so that suite alone needs no more. The OPF init
# self-test took 859 s of its 900 s in a full parallel run, so it gets 1800 s; so does the OPF homes
# self-test, which ran past 900 s in a full parallel run once its pins grew. The public-export gate
# and its --ci subset get 3000 s: the exporter and the names scan over the built tree each have an
# 840 s budget, plus the gate's own git runs (300 s each), so the worst case exceeds the 900 s
# default, and a run that overruns a budget must fail with the gate's own named error, not the
# watchdog's TIMED OUT. public-export-self-test gets 9000 s for the same reason: it bounds each of
# its 33 fixture gate invocations at 120 s and each of its 77 fixture git runs at 60 s (both
# bounds in tools/check_public_export.py), a worst case of 8580 s. In --ci mode every OPF
# self-test suite (each opf-...-selftest gate, each registry-driven execution of an OPF suite, and the
# CommonMark conformance suite) is NOT RUN. The baseline-pin self-test and its registry-driven
# execution are not OPF suites and match neither pattern, so --ci runs them.
gate_settings() {
  gate_bound="$gate_timeout"
  case "$1" in
    opf-tooling-selftest|opf-adopt-apply-selftest) [ "$gate_bound" -ge 6000 ] || gate_bound=6000 ;;
    opf-init-selftest|opf-homes-selftest) [ "$gate_bound" -ge 1800 ] || gate_bound=1800 ;;
    public-export|public-export-ci-subset) [ "$gate_bound" -ge 3000 ] || gate_bound=3000 ;;
    public-export-self-test) [ "$gate_bound" -ge 9000 ] || gate_bound=9000 ;;
  esac
  gate_skip=""
  [ "$mode" = ci ] || return 0
  case "$1" in
    names)
      gate_skip="--ci mode; it needs the local denylist, so names-ci-subset runs the checks that need none" ;;
    ci-status-test|pr-ci-registered-test)
      gate_skip="--ci mode; too slow for the 5-minute job, so the full local run runs it" ;;
    names-fuzz|names-fuzz-self-test)
      gate_skip="--ci mode; a local-only gate (it needs GNU grep), so the full local run runs it" ;;
    line-width)
      gate_skip="--ci mode; a local-only gate (it needs the merge base with origin/main)" ;;
    public-export)
      gate_skip="--ci mode; it needs the local denylist, so public-export-ci-subset runs the checks that need none" ;;
    opf-*-selftest|opf-*-selftest-execution|commonmark-conformance)
      gate_skip="--ci mode; an OPF self-test suite, run by the full local run" ;;
  esac
}

# watch_gate PID BOUND DIR: the watchdog of one gate, started in the background by the gate's subshell
# PID. After BOUND seconds it records the overrun in DIR/timed-out, sends TERM to every process below
# PID except itself and, kill_grace seconds later, KILL to each process it sent TERM to and each still
# below PID (a pid reused within those seconds would be sent KILL too). The gate's subshell stops the
# watchdog as soon as the gate ends. A wait on the FIFO that does not time out (it cannot be opened)
# falls back to sleep, so the bound still holds.
watch_gate() {
  # me, not BASHPID inside the command substitutions: there it would name the substitution's subshell.
  local pids status=0 me="$BASHPID"
  read -r -t "$2" _ <>"$work/never" || status=$?
  [ "$status" -gt 128 ] || sleep "$2"
  : >"$3/timed-out"
  pids="$(descendants "$1" "$me")"
  # shellcheck disable=SC2086  # one pid per word
  [ -z "$pids" ] || kill -TERM $pids 2>/dev/null
  status=0
  read -r -t "$kill_grace" _ <>"$work/never" || status=$?
  [ "$status" -gt 128 ] || sleep "$kill_grace"
  pids="$pids $(descendants "$1" "$me")"
  # shellcheck disable=SC2086  # one pid per word
  kill -KILL $pids 2>/dev/null
}

# run_gate NAME COMMAND...: start one gate in the background, once a job slot is free, or record it as
# NOT RUN when this mode does not run it. Its output, exit status, elapsed seconds and failure state go
# to its own files, so waiting for a free slot never consumes a status.
run_gate() {
  local name="$1"; shift
  local index
  gate_settings "$name"
  if [ -n "$gate_skip" ]; then
    skip_gate "$name" "$gate_skip"
    return 0
  fi
  index="${#gate_names[@]}"
  gate_names+=("$name")
  gate_bounds+=("$gate_bound")
  if ! mkdir -m 700 -- "$work/$index" "$work/$index/tmp"; then
    printf 'FATAL: could not create the temporary directory of gate %s\n' "$name"
    exit 2
  fi
  while [ "$running" -ge "$jobs" ]; do
    wait -n 2>/dev/null
    running=$((running - 1))
  done
  gate_process "$work/$index" "$gate_bound" "$@" &
  running=$((running + 1))
}

# run_ci_gate NAME COMMAND...: a gate that only the --ci run runs, in place of a gate --ci lists as NOT
# RUN. It is not a run_gate line, so the roster of a local run is exactly what a local run dispatches.
run_ci_gate() {
  [ "$mode" != ci ] || run_gate "$@"
}

# gate_process DIR BOUND COMMAND...: one gate, in its own subshell (the function's body is a
# subshell), so its failed and failed_names describe this gate alone and report_gates reads them back
# from DIR. The dispatch block keeps the imported runner's text, which the OPF self-tests mutate; the
# redirection around it sends the gate's output, and its GATE FAILED line, to the gate's log.
gate_process() (
  local dir="$1" bound="$2" self="$BASHPID" watchdog started elapsed status note=""
  shift 2
  failed=0
  failed_names=""
  cd -- "$root" || exit 2
  export TMPDIR="$dir/tmp"
  # self, not BASHPID: the words of a background command expand in the forked child.
  watch_gate "$self" "$bound" "$dir" </dev/null >/dev/null 2>&1 &
  watchdog=$!
  started=$SECONDS
  # The gate starts with SIGINT and SIGQUIT at their default action, not the ignore this background
  # subshell started with (see Signals above); the subshell ignores them again once the gate ends.
  trap - INT QUIT
  {
  if "$@"; then :; else
    local rc=$?
    failed=1
    failed_names="${failed_names:+${failed_names}, }${name}"
    echo "GATE FAILED: ${name} (exit ${rc})"
  fi
  } >"$dir/log" 2>&1 </dev/null
  trap '' INT QUIT
  elapsed=$((SECONDS - started))
  status="${rc:-0}"
  kill -TERM "$watchdog" 2>/dev/null
  wait "$watchdog" 2>/dev/null
  [ ! -e "$dir/timed-out" ] || note=", stopped at its ${bound}s bound"
  printf '%s\n' "$status" >"$dir/rc"
  printf '%s\n' "$elapsed" >"$dir/elapsed"
  printf '%s\n' "$failed" >"$dir/failed"
  printf '%s\n' "$failed_names" >"$dir/names"
  printf 'finished %s (exit %s, %ss%s)\n' "$name" "$status" "$elapsed" "$note"
)

# skip_gate NAME REASON: record a gate that this mode does not run; the summary lists it as NOT RUN.
skip_gate() {
  skipped_names+=("$1")
  skipped_reasons+=("$2")
}

# report_gates: wait for every gate, then print each gate's output and status in the fixed order, then
# the gates that did not run, and set failed and failed_names. A gate stopped at its bound, or one that
# left no failure state, counts as failed and is named even when its own state did not name it.
report_gates() {
  local index name bound rc elapsed gate_failed names note status summary=""
  wait
  echo
  for index in "${!gate_names[@]}"; do
    name="${gate_names[$index]}"
    bound="${gate_bounds[$index]}"
    rc="$(cat -- "$work/$index/rc" 2>/dev/null)" || rc=""
    elapsed="$(cat -- "$work/$index/elapsed" 2>/dev/null)" || elapsed=""
    gate_failed="$(cat -- "$work/$index/failed" 2>/dev/null)" || gate_failed=""
    names="$(cat -- "$work/$index/names" 2>/dev/null)" || names=""
    note=""
    case "$elapsed" in ''|*[!0-9]*) elapsed="?" ;; esac
    case "$rc" in ''|*[!0-9]*) rc="unknown" ;; esac
    if [ -e "$work/$index/timed-out" ]; then
      status="TIMED OUT after ${bound}s (exit ${rc})"
      gate_failed=1
      if [ -z "$names" ]; then
        names="$name"
        note="GATE FAILED: ${name} (stopped at its ${bound}s bound)"
      fi
    elif [ "$rc" = unknown ] || { [ "$gate_failed" != 0 ] && [ "$gate_failed" != 1 ]; }; then
      status="NO EXIT STATUS RECORDED"
      gate_failed=1
      if [ -z "$names" ]; then
        names="$name"
        note="GATE FAILED: ${name} (no exit status recorded)"
      fi
    elif [ "$gate_failed" = 0 ]; then
      status="PASS"
    elif [ "$rc" = 2 ]; then
      status="CANNOT-EVALUATE (exit 2)"
    else
      status="FAIL (exit ${rc})"
    fi
    echo "--- ${name} ---"
    cat -- "$work/$index/log" 2>/dev/null
    [ -z "$note" ] || echo "$note"
    if [ "$gate_failed" = 1 ]; then
      failed=1
      [ -z "$names" ] || failed_names="${failed_names:+${failed_names}, }${names}"
    fi
    echo
    summary="${summary}$(printf '  %-44s %-36s %ss' "$name" "$status" "$elapsed")"$'\n'
  done
  for index in "${!skipped_names[@]}"; do
    summary="${summary}$(printf '  %-44s NOT RUN: %s' "${skipped_names[$index]}" "${skipped_reasons[$index]}")"$'\n'
  done
  echo "SUMMARY (fixed gate order; status, then elapsed seconds):"
  printf '%s' "$summary"
  echo
}

echo "opfiles checks (${mode} mode): up to ${jobs} gate(s) at once, ${gate_timeout}s bound per gate (longer for the heavy OPF self-tests in gate_settings)"
echo

# The pre-import gates (scaffold plan, section 4, items 1 to 7), the tests of the gates and of
# this runner, the vendored AIQT rules gate, the CLAUDE.md and AGENTS.md parity gate, the
# provenance deviations gate (every imported file and every deviation record of
# PROVENANCE-inventory.json against the files, the import facts and the PROVENANCE.md pin), the
# provenance addendum gate (each record of PROVENANCE-addendum.json against the committed copy of
# the handover's SHA256SUMS and against its landed file), and their self-tests. The two provenance
# gates and their self-tests are fast, so all four run in --ci mode too.
run_gate "secrets"               python3 -I -B "$here/run_bash_gate.py" check_secrets.sh
run_gate "names"                 python3 -I -B "$here/check_names.py"
run_ci_gate "names-ci-subset"    python3 -I -B "$here/check_names.py" --ci
run_gate "dashes"                python3 -I -B "$here/check_no_dashes.py"
run_gate "links"                 python3 -I -B "$here/check_links.py"
run_gate "workflow-contract"     python3 -I -B "$here/check_quality_workflow.py"
run_gate "ci-python-pin"         python3 -I -B "$here/check_ci_python_pin.py"
run_gate "gate-tests"            python3 -I -B "$here/test_gates.py"
run_gate "runner-test"           python3 -I -B "$here/run_bash_gate.py" test_run_all_checks.sh
run_gate "aiqt-vendored"         python3 -I -B "$here/check_aiqt_vendored.py"
run_gate "aiqt-vendored-self-test" python3 -I -B "$here/check_aiqt_vendored.py" --self-test
run_gate "agents-parity"         python3 -I -B "$here/check_agents_parity.py"
run_gate "agents-parity-self-test" python3 -I -B "$here/check_agents_parity.py" --self-test
run_gate "provenance-deviations" python3 -I -B "$here/check_provenance_deviations.py"
run_gate "provenance-deviations-self-test" python3 -I -B "$here/check_provenance_deviations.py" --self-test
run_gate "provenance-addendum"   python3 -I -B "$here/check_provenance_addendum.py"
run_gate "provenance-addendum-self-test" python3 -I -B "$here/check_provenance_addendum.py" --self-test
run_gate "ci-status-test"        python3 -I -B "$here/run_bash_gate.py" test_ci_status.sh
run_gate "pr-ci-registered-test" python3 -I -B "$here/run_bash_gate.py" test_pr_ci_registered.sh
run_gate "names-fuzz"            python3 -I -B "$here/test_names_fuzz.py"
run_gate "names-fuzz-self-test"  python3 -I -B "$here/test_names_fuzz.py" --self-test

# The opfiles.ai site generator (tools/gen_draft_site.py): its self-test, and the drift gate that rebuilds
# every page from site/draft-src/ and the reference CLI status lines and fails on any byte difference with
# the committed files. Both are fast, so both run in --ci mode too.
run_gate "draft-site-self-test"  python3 -I -B "$here/gen_draft_site.py" --self-test
run_gate "draft-site-drift"      python3 -I -B "$here/gen_draft_site.py" --check

# The gates of the imported standalone OPF runner, in its order. Child exit status first (see
# _child_status.py): under an inherited SIGCHLD ignore a gate would read its failed children as passes,
# so the probe runs in every mode and its failure fails the run.
run_gate "child-status"                python3 -I -B "$here/_child_status.py"
run_gate "child-status-selftest"       python3 -I -B "$here/_child_status.py" --self-test
run_gate "opf-homes-selftest"          python3 -I -B "$here/check_opf_homes.py" --self-test
run_gate "opf-homes-contract"          python3 -I -B "$here/check_opf_homes.py"
run_gate "opf-tooling-selftest"        python3 -I -B "$here/opf.py" --self-test
run_gate "opf-journal-direct-selftest" python3 -I -B "$here/_journal.py" --self-test
run_gate "opf-observe-direct-selftest" python3 -I -B "$here/_opf_observe.py" --self-test
run_gate "opf-drift-selftest"          python3 -I -B "$here/check_opf_drift.py" --self-test
run_gate "opf-doctor-selftest"         python3 -I -B "$here/check_opf_doctor.py" --self-test
run_gate "opf-init-selftest"           python3 -I -B "$here/check_opf_init.py" --self-test
run_gate "opf-init-contract-selftest"  python3 -I -B "$here/_opf_init_contract.py" --self-test
run_gate "opf-init-contract-check-selftest" python3 -I -B "$here/check_opf_init_contract.py" --self-test
run_gate "opf-init-contract-check"     python3 -I -B "$here/check_opf_init_contract.py"
run_gate "opf-selftest-execution-selftest" python3 -I -B "$here/check_opf_selftest_execution.py" --self-test
run_gate "opf-selftest-registry"       python3 -I -B "$here/check_opf_selftest_execution.py" --registry
run_gate "opf-init-contract-check-selftest-execution" python3 -I -B "$here/check_opf_selftest_execution.py" --suite opf-init-contract-check-selftest
run_gate "opf-adopt-selftest"          python3 -I -B "$here/_opf_adopt.py" --self-test
run_gate "opf-adopt-apply-selftest"    python3 -I -B "$here/_opf_adopt_apply.py" --self-test
run_gate "opf-adopt-state-selftest"    python3 -I -B "$here/_opf_adopt_state.py" --self-test
run_gate "opf-adopt-hook-selftest"     python3 -I -B "$here/_opf_adopt_hook.py" --self-test
run_gate "opf-adopt-complete-selftest" python3 -I -B "$here/_opf_adopt_complete.py" --self-test
run_gate "opf-import-batch-selftest"   python3 -I -B "$here/_opf_import_batch.py" --self-test
run_gate "opf-import-complete-selftest" python3 -I -B "$here/_opf_import_complete.py" --self-test
run_gate "opf-release-history-selftest" python3 -I -B "$here/_opf_release_history.py" --self-test
run_gate "opf-pack-manifest-selftest"  python3 -I -B "$here/_opf_pack_manifest.py" --self-test
run_gate "opf-adopt-observe-selftest"  python3 -I -B "$here/_opf_adopt_observe.py" --self-test
run_gate "opf-adopt-discover-selftest" python3 -I -B "$here/_opf_adopt_discover.py" --self-test
run_gate "opf-prompt-pack-selftest"    python3 -I -B "$here/check_opf_prompt_pack.py" --self-test
run_gate "opf-prompt-pack"             python3 -I -B "$here/check_opf_prompt_pack.py"
run_gate "opf-oplock-selftest"         python3 -I -B "$here/_opf_oplock.py" --self-test
run_gate "opf-init-substrate-selftest" python3 -I -B "$here/_opf_init_substrate.py" --self-test
run_gate "opf-init-builders-selftest"  python3 -I -B "$here/_opf_init.py" --self-test
run_gate "opf-init-operation-selftest" python3 -I -B "$here/_opf_init_operation.py" --self-test
run_gate "opf-init-p0-selftest"        python3 -I -B "$here/check_opf_init_p0.py" --self-test --red-on-revert
run_gate "commonmark-headings-selftest" python3 -I -B "$here/selftest_commonmark_headings.py"
run_gate "commonmark-conformance"      python3 -I -B "$here/selftest_commonmark_conformance.py"
# The gates handed over after the import (guardrails main 504f422d; PROVENANCE.md): the release gate
# for the implementation declaration (OPF-SPEC section 16.1), its self-test and the registry-driven
# execution of that self-test, then the enforcement-pack residual register gate and its self-test.
run_gate "opf-declaration"             python3 -I -B "$here/check_opf_declaration.py"
run_gate "opf-declaration-selftest"    python3 -I -B "$here/check_opf_declaration.py" --self-test
run_gate "opf-declaration-selftest-execution" python3 -I -B "$here/check_opf_selftest_execution.py" --suite opf-declaration-selftest
run_gate "opf-enforce-residuals"       python3 -I -B "$here/check_opf_enforce_residuals.py"
run_gate "opf-enforce-residuals-selftest" python3 -I -B "$here/check_opf_enforce_residuals.py" --self-test
# The pinned copy of the shared site template (handed over likewise): the pin gate over
# .baseline/opfiles-pin.toml, its self-test and the registry-driven execution of that self-test, then the
# template's palette gate (.baseline/check_palette.py, pinned byte for byte) over the opfiles palette of
# the pinned palettes.css. All four are fast and none matches an OPF self-test pattern, so --ci runs them.
run_gate "baseline-pin"                python3 -I -B "$here/check_baseline_pin.py"
run_gate "baseline-pin-selftest"       python3 -I -B "$here/check_baseline_pin.py" --self-test
run_gate "baseline-pin-selftest-execution" python3 -I -B "$here/check_opf_selftest_execution.py" --suite baseline-pin-selftest
run_gate "baseline-palette"            python3 -I -B "$here/../.baseline/check_palette.py" --palettes site/draft/assets/baseline/palettes.css --site opfiles
# The line-width gate (tools/check_line_width.py): in three passes, HEAD's committed content, the
# index and the work tree, no line changed or added since the base (by default the merge base of
# HEAD with origin/main) is wider than its file's width at the base, or than 120 in a file new
# since the base. A file's width at the base is the widest line it had there (the maximum, not a
# percentile, so one wide line there lets every changed line of that file be as wide), but never
# less than 100. A file its suffix names as checked that was not text at the base and now holds a
# NUL byte also fails the gate, whatever its widths. It needs that history, which the hosted job's
# depth-1 checkout of the pull request head lacks, so --ci lists it as NOT RUN. In a copy with no
# git history, or with no origin/main, it exits 2 (CANNOT EVALUATE, naming the reason), which a
# full local run reports as a failed gate. Its self-test builds its own repositories and runs in
# both modes.
run_gate "line-width"                  python3 -I -B "$here/check_line_width.py"
run_gate "line-width-self-test"        python3 -I -B "$here/check_line_width.py" --self-test
# The public-export gate (tools/check_public_export.py): rebuilds the public export of
# tools/public_export/export_public.py into a temporary directory and fails unless the built tree
# is exactly the whole tracked tree of HEAD (the maintainer ruled that every tracked file ships),
# byte-identical, with modes kept, no symlink, a matching manifest and no tracked path the names
# scan would skip; it then runs the names scan over the built tree with the denylist machinery of
# tools/check_names.py and the line-level carve-out record tools/public_export/carve-out.toml.
# The full gate needs the local denylist, so --ci lists it as NOT RUN and public-export-ci-subset
# runs the structural checks and the names checks that need none. The self-test builds its own
# repositories and runs in both modes.
run_gate "public-export"               python3 -I -B "$here/check_public_export.py"
run_ci_gate "public-export-ci-subset"  python3 -I -B "$here/check_public_export.py" --ci
run_gate "public-export-self-test"     python3 -I -B "$here/check_public_export.py" --self-test
report_gates

if [ "$failed" -ne 0 ]; then
  echo "FAILED GATES: ${failed_names}"
  if [ "$mode" = ci ]; then
    echo "OPFILES CHECKS (ci mode): FAILED"
  else
    echo "OPF STANDALONE SUBSET: FAILED"
  fi
  exit 1
fi
if [ "$mode" = ci ]; then
  echo "OPFILES CHECKS: CI SUBSET OK (not a full run: ${#skipped_names[@]} gate(s) NOT RUN; run tools/run_all_checks.sh with no argument for the full run)"
else
  echo "OPFILES CHECKS: OK"
fi
exit 0
