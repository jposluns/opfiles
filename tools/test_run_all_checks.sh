#!/usr/bin/env bash
# Tests for tools/run_all_checks.sh and tools/run_bash_gate.py. The runner's gate functions are
# extracted from the runner and run in a small runner shell against fake gates, with real processes
# and real signals. No gate of the repository runs here.
set -uo pipefail
unset BASH_ENV
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${RUN_ALL_CHECKS_SCRIPT:-$HERE/run_all_checks.sh}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/test-run-all-checks.XXXXXX")" || { echo 'FATAL: mktemp -d failed'; exit 1; }
if [ -z "$WORK" ] || [ ! -d "$WORK" ]; then echo 'FATAL: no scratch directory'; exit 1; fi
GRANDCHILD=""
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  if [ -n "$GRANDCHILD" ]; then kill -KILL "$GRANDCHILD" 2>/dev/null; fi
  rm -rf -- "$WORK"
}
trap cleanup EXIT
N=0
FAILS=0
pass() { N=$((N + 1)); printf '  ok    %s\n' "$1"; }
failc() { N=$((N + 1)); FAILS=$((FAILS + 1)); printf '  FAIL  %s\n' "$1"; }
check() { # CONDITION-STATUS LABEL DETAIL
  if [ "$1" = 0 ]; then pass "$2"; else failc "$2 ($3)"; fi
}

FUNCS=""
for fn in descendants stop_gates gate_settings watch_gate run_gate run_ci_gate gate_process skip_gate report_gates; do
  body="$(sed -n "/^${fn}() [({]\$/,/^[)}]\$/p" "$RUNNER")"
  if [ -z "$body" ]; then
    printf 'FAIL: cannot extract %s from %s\n' "$fn" "$RUNNER"
    exit 1
  fi
  FUNCS="${FUNCS}${body}"$'\n'
done
export FUNCS

# The small runner: the runner's globals and TERM trap, the extracted functions, then the gates of
# the case (its fourth argument), then the failure variables. Arguments: DIR GATE_TIMEOUT JOBS SCRIPT
# [MODE]. The KILL that follows a TERM comes 1 second later here (10 in the runner).
cat >"$WORK/mini.sh" <<'EOF'
set -uo pipefail
root="$1"; work="$1/work"; gate_timeout="$2"; jobs="$3"; mode="${5:-local}"; kill_grace=1
mkdir -p "$work" && mkfifo -m 600 "$work/never" || exit 2
failed=0; failed_names=""; gate_names=(); gate_bounds=(); skipped_names=(); skipped_reasons=(); running=0
eval "$FUNCS"
trap 'stop_gates; exit 143' TERM
eval "$4"
printf 'failed=%s failed_names=%s\n' "$failed" "$failed_names"
EOF

line_of() { grep -nF -- "$2" <<<"$1" | head -n1 | cut -d: -f1; }

printf '== progress lines, fixed report order, exit statuses ==\n'
out="$(bash "$WORK/mini.sh" "$WORK/order" 30 4 \
  'run_gate slow bash -c "sleep 2; echo slow-output"; run_gate quick bash -c "echo quick-output; exit 3"; report_gates')"
fq="$(line_of "$out" 'finished quick (exit 3')"
fs="$(line_of "$out" 'finished slow (exit 0')"
rs="$(line_of "$out" '--- slow ---')"
rq="$(line_of "$out" '--- quick ---')"
[ -n "$fq" ] && [ -n "$fs" ] && [ -n "$rs" ] && [ "$fq" -lt "$fs" ] && [ "$fs" -lt "$rs" ]
check $? "a finished line is printed as each gate ends, before the report" "out=<<$out>>"
[ -n "$rs" ] && [ -n "$rq" ] && [ "$rs" -lt "$rq" ]
check $? "the report keeps the fixed gate order, not the finishing order" "out=<<$out>>"
grep -Eq '^  quick +FAIL \(exit 3\) ' <<<"$out" && grep -Eq '^  slow +PASS ' <<<"$out"
check $? "the summary keeps each gate's own exit status" "out=<<$out>>"
grep -qx 'GATE FAILED: quick (exit 3)' <<<"$out" && grep -qx 'failed=1 failed_names=quick' <<<"$out"
check $? "a failing gate is named in its GATE FAILED line and in failed_names" "out=<<$out>>"

printf '== one gate at a time ==\n'
out="$(bash "$WORK/mini.sh" "$WORK/serial" 30 1 \
  'run_gate first bash -c "sleep 1; echo first-output"; run_gate second bash -c "echo second-output"; report_gates')"
f1="$(line_of "$out" 'finished first (exit 0')"
f2="$(line_of "$out" 'finished second (exit 0')"
[ -n "$f1" ] && [ -n "$f2" ] && [ "$f1" -lt "$f2" ] && grep -qx 'failed=0 failed_names=' <<<"$out"
check $? "with one job slot each gate starts only after the one before it ends" "out=<<$out>>"
greet() { echo "function-dispatched $*"; }
export -f greet
out="$(bash "$WORK/mini.sh" "$WORK/function" 30 1 'run_gate fn greet one; report_gates')"
grep -qx 'function-dispatched one' <<<"$out" && grep -Eq '^  fn +PASS ' <<<"$out"
check $? "a gate command that is a shell function is dispatched in the gate's own shell" "out=<<$out>>"
unset -f greet

printf '== every gate starts with SIGINT and SIGQUIT at their default action ==\n'
# A background job of a non-interactive shell starts with SIGINT and SIGQUIT ignored; the runner
# sets both back for each gate, so a Python gate sees default_int_handler and SIG_DFL. The small
# runner is started with both at default, as a runner started from a terminal or a foreground script
# has them: bash cannot reset a signal that was ignored when it started.
# with_default_signals COMMAND...: run COMMAND with SIGINT and SIGQUIT at their default action.
with_default_signals() {
  python3 -I -B -c 'import os, signal, sys
for number in (signal.SIGINT, signal.SIGQUIT):
    signal.signal(number, signal.SIG_DFL)
os.execvp(sys.argv[1], sys.argv[1:])' "$@"
}
cat >"$WORK/signals.py" <<'EOF'
import signal
sigint = signal.getsignal(signal.SIGINT) is signal.default_int_handler
sigquit = signal.getsignal(signal.SIGQUIT) == signal.SIG_DFL
print("sigint-default=%s sigquit-default=%s" % (sigint, sigquit))
raise SystemExit(0 if sigint and sigquit else 1)
EOF
# The control: started in the background with no reset, the same probe sees both signals ignored,
# so the check below fails if the runner's reset is removed.
out="$(with_default_signals bash -c '( python3 -I -B "$1" ) & wait "$!"' _ "$WORK/signals.py")"
# Some hosts (for example a CI runner) do not ignore these signals for background jobs; there the
# control cannot show the reset matters, so it is reported as a note, never as a pass or a failure.
if [ "$out" = "sigint-default=True sigquit-default=True" ]; then
  printf "  note  this host does not ignore SIGINT and SIGQUIT for background jobs, so the control does not apply\n"
else
  [ "$out" = "sigint-default=False sigquit-default=False" ]
  check $? "a Python process started as a plain background job sees SIGINT and SIGQUIT ignored" "out=<<$out>>"
fi
out="$(with_default_signals bash "$WORK/mini.sh" "$WORK/signals" 30 1 \
  "run_gate signals python3 -I -B '$WORK/signals.py'; report_gates")"
grep -qx 'sigint-default=True sigquit-default=True' <<<"$out" && grep -Eq '^  signals +PASS ' <<<"$out"
check $? "a Python gate started by the runner sees default_int_handler for SIGINT and SIG_DFL for SIGQUIT" "out=<<$out>>"

printf '== a timeout is told apart from a gate exit 124 ==\n'
out="$(bash "$WORK/mini.sh" "$WORK/own124" 30 1 'run_gate own124 bash -c "exit 124"; report_gates')"
grep -Eq '^  own124 +FAIL \(exit 124\) ' <<<"$out" && ! grep -q 'TIMED OUT' <<<"$out"
check $? "a gate that exits 124 at once is a FAIL, not a timeout" "out=<<$out>>"
out="$(bash "$WORK/mini.sh" "$WORK/timedout" 1 1 'run_gate hang sleep 30; report_gates')"
grep -Eq '^  hang +TIMED OUT after 1s \(exit 143\) ' <<<"$out" && grep -qx 'failed=1 failed_names=hang' <<<"$out"
check $? "a gate stopped at the bound is reported as TIMED OUT and fails" "out=<<$out>>"
out="$(bash "$WORK/mini.sh" "$WORK/sneaky" 1 1 \
  "run_gate sneaky bash -c 'trap \"exit 0\" TERM; sleep 30 & wait'; report_gates")"
grep -Eq '^  sneaky +TIMED OUT after 1s \(exit 0\) ' <<<"$out" &&
  grep -qx 'GATE FAILED: sneaky (stopped at its 1s bound)' <<<"$out" &&
  grep -qx 'failed=1 failed_names=sneaky' <<<"$out"
check $? "a gate that exits 0 when stopped at its bound still fails as TIMED OUT" "out=<<$out>>"
start=$SECONDS
out="$(bash "$WORK/mini.sh" "$WORK/stubborn" 1 1 \
  "run_gate stubborn bash -c 'trap \"\" TERM; while :; do sleep 0.2; done'; report_gates")"
took=$((SECONDS - start))
grep -Eq '^  stubborn +TIMED OUT after 1s \(exit 137\) ' <<<"$out" && [ "$took" -lt 10 ]
check $? "a gate that ignores TERM is killed after the grace period" "took=${took}s out=<<$out>>"
gate="bash -c 'sleep 60 & echo \$! >\"$WORK/bound-grandchild\"; wait'"
out="$(bash "$WORK/mini.sh" "$WORK/bounded" 1 1 "run_gate tree $gate; report_gates")"
bound_grandchild="$(cat "$WORK/bound-grandchild" 2>/dev/null)"
gone=1
if [ -n "$bound_grandchild" ]; then
  for _ in $(seq 1 30); do
    if ! kill -0 "$bound_grandchild" 2>/dev/null; then gone=0; break; fi
    sleep 0.1
  done
fi
check "$gone" "a gate stopped at its bound loses its grandchildren too" "pid=${bound_grandchild:-none} out=<<$out>>"
[ -z "$bound_grandchild" ] || kill -KILL "$bound_grandchild" 2>/dev/null

printf '== per-gate bounds and the --ci split ==\n'
settings() { # MODE GATE_TIMEOUT NAME: print the gate's bound and NOT RUN reason
  bash -c 'mode="$1"; gate_timeout="$2"; eval "$FUNCS"; gate_settings "$3"; printf "%s|%s" "$gate_bound" "$gate_skip"' _ "$@"
}
[ "$(settings local 900 opf-tooling-selftest)" = "6000|" ] &&
  [ "$(settings local 900 opf-adopt-apply-selftest)" = "6000|" ] &&
  [ "$(settings local 900 dashes)" = "900|" ] &&
  [ "$(settings local 9000 opf-tooling-selftest)" = "9000|" ]
check $? "the heavy OPF self-tests have raised bounds, a floor under OPFILES_GATE_TIMEOUT" \
  "tooling=$(settings local 900 opf-tooling-selftest) dashes=$(settings local 900 dashes)"
# The handover gates are named too, so an edit to the --ci skip pattern (opf-*-selftest and
# opf-*-selftest-execution) cannot silently run an OPF execution suite in --ci, or skip a check or a
# baseline-* gate there.
for name in ci-status-test pr-ci-registered-test names-fuzz names-fuzz-self-test names opf-tooling-selftest commonmark-conformance \
    opf-declaration-selftest opf-declaration-selftest-execution opf-enforce-residuals-selftest \
    line-width public-export; do
  grep -Eq "^run_gate \"$name\" " "$RUNNER" && case "$(settings ci 90 "$name")" in *"|--ci mode; "*) true ;; *) false ;; esac
  check $? "$name runs in the full run and is listed as NOT RUN in --ci mode" "settings=$(settings ci 90 "$name")"
done
for name in secrets dashes provenance-deviations provenance-deviations-self-test provenance-addendum provenance-addendum-self-test child-status opf-homes-contract opf-selftest-registry commonmark-headings-selftest \
    opf-declaration opf-enforce-residuals baseline-pin baseline-pin-selftest baseline-pin-selftest-execution baseline-palette \
    line-width-self-test; do
  grep -Eq "^run_gate \"$name\" " "$RUNNER" && [ "$(settings ci 90 "$name")" = "90|" ]
  check $? "$name runs in both modes" "settings=$(settings ci 90 "$name")"
done
# The --ci replacement gates: each is registered by run_ci_gate (never run_gate, so a local run's
# roster does not hold it), its registration ends with --ci, and gate_settings gives it no skip
# reason, so the --ci run runs it in place of the full gate it replaces.
for name in names-ci-subset public-export-ci-subset; do
  grep -Eq "^run_ci_gate \"$name\" +python3 -I -B \"\\\$here/[^\"]+\" --ci\$" "$RUNNER" &&
    ! grep -Eq "^run_gate \"$name\" " "$RUNNER" &&
    case "$(settings ci 90 "$name")" in *"|") true ;; *) false ;; esac
  check $? "$name is registered by run_ci_gate with --ci and --ci runs it" "settings=$(settings ci 90 "$name")"
done
# The public-export gate and its --ci subset rebuild the export (an 840 s exporter budget) and run
# the names scan over the built tree (another 840 s), plus git, so their bound is raised above
# that worst case; public-export-self-test bounds its 33 fixture gate invocations at 120 s and its
# 77 fixture git runs at 60 s, so its bound is raised above that worst case (8580 s) too. Each is
# a floor under OPFILES_GATE_TIMEOUT like the heavy OPF self-tests' bounds, and the self-test is
# registered by run_gate and keeps running in both modes (no --ci skip reason).
grep -Eq "^run_gate \"public-export-self-test\" " "$RUNNER" &&
  [ "$(settings local 900 public-export)" = "3000|" ] &&
  [ "$(settings ci 90 public-export-ci-subset)" = "3000|" ] &&
  [ "$(settings local 900 public-export-self-test)" = "9000|" ] &&
  [ "$(settings ci 90 public-export-self-test)" = "9000|" ] &&
  [ "$(settings local 9000 public-export)" = "9000|" ] &&
  [ "$(settings local 12000 public-export-self-test)" = "12000|" ]
check $? "public-export-self-test is registered; public-export bound floors hold in both modes" \
  "public-export=$(settings local 900 public-export) subset=$(settings ci 90 public-export-ci-subset) self-test=$(settings ci 90 public-export-self-test)"
out="$(bash "$WORK/mini.sh" "$WORK/skip" 30 4 \
  'run_gate fast true; run_gate names-fuzz false; run_ci_gate ci-only true; report_gates' ci)"
grep -Eq '^  names-fuzz +NOT RUN: --ci mode; ' <<<"$out" && grep -Eq '^  ci-only +PASS ' <<<"$out" &&
  grep -qx 'failed=0 failed_names=' <<<"$out"
check $? "--ci lists a local-only gate as NOT RUN, not a failure, and runs a run_ci_gate gate" "out=<<$out>>"
out="$(bash "$WORK/mini.sh" "$WORK/local" 30 4 'run_ci_gate ci-only false; report_gates')"
! grep -q 'ci-only' <<<"$out" && grep -qx 'failed=0 failed_names=' <<<"$out"
check $? "a local run does not run a run_ci_gate gate" "out=<<$out>>"

printf '== TERM to the runner stops a running gate and its children ==\n'
# The gate starts a background sleep (a grandchild of the gate's subshell), records its pid, and
# waits. TERM to the runner must end that sleep too.
gate="bash -c 'sleep 60 & echo \$! >\"$WORK/grandchild\"; wait'"
bash "$WORK/mini.sh" "$WORK/signal" 60 1 "run_gate hang $gate; report_gates" >"$WORK/signal.out" 2>&1 &
mini=$!
for _ in $(seq 1 100); do
  [ -s "$WORK/grandchild" ] && break
  sleep 0.1
done
GRANDCHILD="$(cat "$WORK/grandchild" 2>/dev/null)"
if [ -z "$GRANDCHILD" ]; then
  failc "the gate started its grandchild (no pid recorded within 10 s)"
else
  kill -TERM "$mini"
  rc=0
  wait "$mini" || rc=$?
  check "$([ "$rc" = 143 ]; echo $?)" "the runner exits 143 on TERM" "rc=$rc"
  # alive PID: true while the process exists and is not a zombie.
  alive() {
    local state=""
    if [ -r "/proc/$1/stat" ]; then
      state="$(sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | cut -d' ' -f1)"
      [ -n "$state" ] && [ "$state" != Z ]
    else
      kill -0 "$1" 2>/dev/null
    fi
  }
  gone=1
  for _ in $(seq 1 50); do
    if ! alive "$GRANDCHILD"; then gone=0; break; fi
    sleep 0.1
  done
  check "$gone" "the gate's grandchild is gone within 5 s of the TERM" "pid $GRANDCHILD still runs; out=<<$(cat "$WORK/signal.out")>>"
fi

printf '== the runner itself ==\n'
out="$(bash "$RUNNER" --bogus 2>&1)"; rc=$?
[ "$rc" = 2 ] && grep -q '^usage: tools/run_all_checks.sh \[--ci\]$' <<<"$out" && ! grep -q '^finished ' <<<"$out"
check $? "an unknown argument exits 2 with the usage line, before any gate" "rc=$rc out=<<$out>>"
out="$(bash "$RUNNER" --ci extra 2>&1)"; rc=$?
[ "$rc" = 2 ] && ! grep -q '^finished ' <<<"$out"
check $? "a second argument exits 2 before any gate" "rc=$rc out=<<$out>>"
# The registration contract the OPF self-tests read: every line that starts with run_gate is one
# python3 -I -B launch of a script in the runner's directory, in the first column.
bad="$(grep -E '^[[:space:]]*run_gate ' "$RUNNER" | grep -Ev '^run_gate "[^"$]+" +python3 -I -B "\$here/[^"$]+"( [^$]*)?$')"
[ -z "$bad" ] && [ "$(grep -c '^run_gate ' "$RUNNER")" -gt 40 ]
check $? "every registration is a first-column python3 -I -B run_gate line" "bad=<<$bad>>"

printf '== the bash gate launcher ==\n'
mkdir -p "$WORK/launcher" && cp -- "$HERE/run_bash_gate.py" "$WORK/launcher/run_bash_gate.py"
printf '#!/usr/bin/env bash\necho "fake-gate $*"\nexit 7\n' >"$WORK/launcher/fake.sh"
printf 'exit 0\n' >"$WORK/launcher/notes.txt"
ln -s fake.sh "$WORK/launcher/linked.sh"
out="$(python3 -I -B "$WORK/launcher/run_bash_gate.py" fake.sh one two 2>&1)"; rc=$?
[ "$rc" = 7 ] && [ "$out" = "fake-gate one two" ]
check $? "the launcher runs the script with its arguments and returns its exit status" "rc=$rc out=<<$out>>"
# Python ignores SIGPIPE at startup and an exec keeps it ignored; the launcher must set it back to
# the default, so that in the script a writer into a closed pipe is stopped by SIGPIPE (status 141).
printf '#!/usr/bin/env bash\nyes | head -n 1 >/dev/null\necho "yes-status ${PIPESTATUS[0]}"\n' >"$WORK/launcher/pipe.sh"
out="$(python3 -I -B "$WORK/launcher/run_bash_gate.py" pipe.sh 2>&1)"; rc=$?
[ "$rc" = 0 ] && [ "$out" = "yes-status 141" ]
check $? "a script run through the launcher sees 'yes | head -n 1' end yes with status 141" "rc=$rc out=<<$out>>"
for refused in "" "../launcher/fake.sh" "notes.txt" "linked.sh" "missing.sh"; do
  if [ -n "$refused" ]; then
    out="$(python3 -I -B "$WORK/launcher/run_bash_gate.py" "$refused" 2>&1)"; rc=$?
  else
    out="$(python3 -I -B "$WORK/launcher/run_bash_gate.py" 2>&1)"; rc=$?
  fi
  [ "$rc" = 2 ] && ! grep -q 'fake-gate' <<<"$out"
  check $? "the launcher refuses with exit 2: '${refused:-no script}'" "rc=$rc out=<<$out>>"
done

printf '\n'
if [ "$FAILS" -eq 0 ]; then
  printf 'PASS: runner tests (%s checks, 0 failures)\n' "$N"
  exit 0
fi
printf 'FAIL: runner tests (%s checks, %s failures)\n' "$N" "$FAILS"
exit 1
