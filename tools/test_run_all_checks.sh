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
# The private-only gate list, extracted as the one multi-line private_only_gates assignment (from
# its opening line to the first line ending with the closing quote), so the profile checks below
# read the runner's own set.
PRIVATE_ONLY="$(sed -n '/^private_only_gates="/,/"$/p' "$RUNNER")"
if [ -z "$PRIVATE_ONLY" ]; then
  printf 'FAIL: cannot extract private_only_gates from %s\n' "$RUNNER"
  exit 1
fi
export PRIVATE_ONLY

# The small runner: the runner's globals and TERM trap, the extracted functions, then the gates of
# the case (its fourth argument), then the failure variables. Arguments: DIR GATE_TIMEOUT JOBS SCRIPT
# [MODE] [PROFILE]. The KILL that follows a TERM comes 1 second later here (10 in the runner).
cat >"$WORK/mini.sh" <<'EOF'
set -uo pipefail
root="$1"; work="$1/work"; gate_timeout="$2"; jobs="$3"; mode="${5:-local}"; kill_grace=1
profile="${6:-private}"
mkdir -p "$work" && mkfifo -m 600 "$work/never" || exit 2
failed=0; failed_names=""; gate_names=(); gate_bounds=(); skipped_names=(); skipped_reasons=(); running=0
eval "$PRIVATE_ONLY"
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
settings() { # MODE GATE_TIMEOUT NAME [PROFILE]: print the gate's bound and NOT RUN reason
  bash -c 'mode="$1"; gate_timeout="$2"; profile="${4:-private}"; eval "$PRIVATE_ONLY";
    eval "$FUNCS"; gate_settings "$3"; printf "%s|%s" "$gate_bound" "$gate_skip"' _ "$@"
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

printf '== the tree profile ==\n'
reason="private-only: its inputs stay in the development repository"
# Every private-only gate is registered (run_gate, or run_ci_gate for the --ci replacement
# public-export-ci-subset), is listed as NOT RUN with the exact reason in the public profile in
# both modes, and is never given that reason in the private profile. This list is compared with
# the runner's private_only_gates set below, so a gate added to one alone fails the test.
EXPECTED_PRIVATE_ONLY="aiqt-vendored aiqt-vendored-self-test agents-parity agents-parity-self-test \
provenance-deviations provenance-deviations-self-test provenance-addendum \
provenance-addendum-self-test draft-site-self-test draft-site-drift opf-homes-selftest \
opf-homes-contract opf-selftest-registry commonmark-headings-selftest commonmark-conformance \
baseline-pin baseline-pin-selftest baseline-pin-selftest-execution baseline-palette \
opf-declaration opf-declaration-selftest opf-declaration-selftest-execution \
public-export public-export-ci-subset public-export-self-test"
listed="$(bash -c 'set -f; eval "$PRIVATE_ONLY"; printf "%s\n" $private_only_gates' | LC_ALL=C sort)"
expected="$(set -f; printf '%s\n' $EXPECTED_PRIVATE_ONLY | LC_ALL=C sort)"
[ -n "$listed" ] && [ "$listed" = "$expected" ]
check $? "the tested private-only list is exactly the runner's private_only_gates set" \
  "runner=<<$listed>> tested=<<$expected>>"
for name in $EXPECTED_PRIVATE_ONLY; do
  grep -Eq "^run_(ci_)?gate \"$name\" " "$RUNNER" &&
    case "$(settings local 900 "$name" public)" in *"|$reason") true ;; *) false ;; esac &&
    case "$(settings ci 90 "$name" public)" in *"|$reason") true ;; *) false ;; esac &&
    case "$(settings local 900 "$name" private)" in *"|$reason") false ;; *) true ;; esac
  check $? "$name is registered and NOT RUN as private-only in the public profile only" \
    "public=$(settings local 900 "$name" public) private=$(settings local 900 "$name" private)"
done
# A sample of the kept gates still runs in a public-profile local run.
for name in secrets names dashes links workflow-contract ci-python-pin gate-tests runner-test \
    child-status opf-init-contract-check opf-prompt-pack opf-enforce-residuals \
    line-width line-width-self-test; do
  case "$(settings local 900 "$name" public)" in *"|") true ;; *) false ;; esac
  check $? "$name still runs in a public-profile local run" \
    "settings=$(settings local 900 "$name" public)"
done
out="$(bash "$WORK/mini.sh" "$WORK/pubprof" 30 4 \
  'run_gate kept true; run_gate baseline-pin false; report_gates' local public)"
grep -Eq "^  baseline-pin +NOT RUN: $reason\$" <<<"$out" && grep -Eq '^  kept +PASS ' <<<"$out" &&
  grep -qx 'failed=0 failed_names=' <<<"$out"
check $? "a public-profile local run lists a private-only gate as NOT RUN, not a failure" \
  "out=<<$out>>"
out="$(bash "$WORK/mini.sh" "$WORK/pubprofci" 30 4 \
  'run_gate kept true; run_ci_gate public-export-ci-subset false; report_gates' ci public)"
grep -Eq "^  public-export-ci-subset +NOT RUN: $reason\$" <<<"$out" &&
  grep -qx 'failed=0 failed_names=' <<<"$out"
check $? "a public-profile --ci run lists the private-only run_ci_gate gate as NOT RUN" \
  "out=<<$out>>"
out="$(bash "$WORK/mini.sh" "$WORK/privprof" 30 4 'run_gate baseline-pin true; report_gates')"
grep -Eq '^  baseline-pin +PASS ' <<<"$out"
check $? "the private profile still runs a private-only gate" "out=<<$out>>"
# The runner's own profile read fails closed: a copy of the runner beside an absent, unreadable
# or unexpected profile exits 2 with CANNOT EVALUATE before the usage check and before any gate;
# a valid profile reaches the usage check (--bogus keeps the copy from running real gates).
mkdir -p "$WORK/profrepo/tools"
cp -- "$RUNNER" "$WORK/profrepo/tools/run_all_checks.sh"
PROF_RUNNER="$WORK/profrepo/tools/run_all_checks.sh"
PROF_FILE="$WORK/profrepo/.opf-tree-profile"
expect_profile_refusal() { # LABEL
  out="$(bash "$PROF_RUNNER" --bogus 2>&1)"; rc=$?
  [ "$rc" = 2 ] && grep -q 'CANNOT EVALUATE' <<<"$out" && ! grep -q '^usage:' <<<"$out" &&
    ! grep -q '^finished ' <<<"$out"
  check $? "$1" "rc=$rc out=<<$out>>"
}
expect_profile_refusal "a missing .opf-tree-profile is CANNOT EVALUATE (exit 2) before any gate"
printf 'Private\n' >"$PROF_FILE"
expect_profile_refusal "a profile in another letter case is refused"
printf 'public\nextra\n' >"$PROF_FILE"
expect_profile_refusal "a profile with a second line is refused"
: >"$PROF_FILE"
expect_profile_refusal "an empty profile is refused"
rm -f -- "$PROF_FILE" && mkdir -- "$PROF_FILE"
expect_profile_refusal "an unreadable profile (a directory) is refused"
rmdir -- "$PROF_FILE"
printf 'private\n' >"$PROF_FILE"
out="$(bash "$PROF_RUNNER" --bogus 2>&1)"; rc=$?
[ "$rc" = 2 ] && grep -q '^usage: tools/run_all_checks.sh' <<<"$out" &&
  ! grep -q 'CANNOT EVALUATE' <<<"$out"
check $? "the single line private is accepted (the usage check is reached)" "rc=$rc out=<<$out>>"
printf 'public' >"$PROF_FILE"
expect_profile_refusal "a profile holding public without its final newline is refused"
printf 'private' >"$PROF_FILE"
expect_profile_refusal "a profile holding private without its final newline is refused"
printf 'public\n' >"$WORK/profrepo/profile-target"
rm -f -- "$PROF_FILE" && ln -s profile-target "$PROF_FILE"
expect_profile_refusal "a symlink profile is refused even when its target holds public"
rm -f -- "$PROF_FILE" "$WORK/profrepo/profile-target" && mkfifo -m 600 "$PROF_FILE"
expect_profile_refusal "a non-regular profile (a FIFO) is refused"
rm -f -- "$PROF_FILE"
printf 'public\n' >"$PROF_FILE"
out="$(bash "$PROF_RUNNER" --bogus 2>&1)"; rc=$?
[ "$rc" = 2 ] && grep -q '^usage: tools/run_all_checks.sh' <<<"$out" &&
  ! grep -q 'CANNOT EVALUATE' <<<"$out"
check $? "the newline-terminated line public is accepted with no excluded path present" \
  "rc=$rc out=<<$out>>"
# A private tree mislabelled public is refused: while any path of the export's exclusion set is
# still present beside a public profile, the runner exits 2 (fail closed) before any gate; the
# private profile keeps running such a tree.
printf 'governance\n' >"$WORK/profrepo/CLAUDE.md"
expect_profile_refusal "a public profile is refused while an excluded file (CLAUDE.md) is present"
printf 'private\n' >"$PROF_FILE"
out="$(bash "$PROF_RUNNER" --bogus 2>&1)"; rc=$?
[ "$rc" = 2 ] && grep -q '^usage: tools/run_all_checks.sh' <<<"$out" &&
  ! grep -q 'CANNOT EVALUATE' <<<"$out"
check $? "the private profile still runs a tree that holds excluded paths" "rc=$rc out=<<$out>>"
printf 'public\n' >"$PROF_FILE"
rm -f -- "$WORK/profrepo/CLAUDE.md" && mkdir -p "$WORK/profrepo/site"
expect_profile_refusal "a public profile is refused while an excluded directory (site) is present"
rmdir -- "$WORK/profrepo/site"
ln -s missing-target "$WORK/profrepo/.baseline"
expect_profile_refusal "a public profile is refused while an excluded path is a dangling symlink"
rm -f -- "$WORK/profrepo/.baseline"
# The profile bytes come from the file the checks approved, not from the path read again: a cat
# first on PATH swaps the private profile for a symlink to public bytes when it is started, after
# the checks. Read through the path again, the swapped bytes would mislabel this tree (which holds
# CLAUDE.md) public and be refused; read from the approved file, the private bytes reach usage.
printf 'private\n' >"$PROF_FILE"
printf 'public\n' >"$WORK/profrepo/profile-target"
printf 'governance\n' >"$WORK/profrepo/CLAUDE.md"
mkdir -p "$WORK/swapbin"
printf '#!/bin/sh\nrm -f -- "$SWAP_PROFILE" && ln -s profile-target "$SWAP_PROFILE" || exit 3\nexec %s "$@"\n' \
  "$(command -v cat)" >"$WORK/swapbin/cat"
chmod 755 "$WORK/swapbin/cat"
out="$(SWAP_PROFILE="$PROF_FILE" PATH="$WORK/swapbin:$PATH" bash "$PROF_RUNNER" --bogus 2>&1)"; rc=$?
[ -L "$PROF_FILE" ] && [ "$rc" = 2 ] && grep -q '^usage: tools/run_all_checks.sh' <<<"$out" &&
  ! grep -q 'CANNOT EVALUATE' <<<"$out"
check $? "a profile swapped for a symlink after the checks does not change the bytes read" \
  "rc=$rc out=<<$out>>"
rm -f -- "$PROF_FILE" "$WORK/profrepo/profile-target" "$WORK/profrepo/CLAUDE.md"
# The runner's public_excluded_paths cannot be read from the exporter in the public tree, where
# the exporter is itself excluded, so it is pinned here, in the private tree, to exactly the
# exporter's EXCLUDE_DIR_PREFIXES (without their final slash) plus its EXCLUDE_FILES: a path
# added to either alone fails. In the public tree the exporter is absent by design.
EXPORTER="$(dirname -- "$RUNNER")/public_export/export_public.py"
tree_profile="$(cat -- "$(dirname -- "$RUNNER")/../.opf-tree-profile" 2>/dev/null && printf .)"
case "$tree_profile" in
  public$'\n.')
    printf '  note  the public tree holds no exporter, so the exclusion list pin does not apply\n' ;;
  private$'\n.')
    excluded_line="$(sed -n '/^public_excluded_paths="/,/"$/p' "$RUNNER")"
    runner_set="$(bash -c 'set -f; eval "$1"; printf "%s\n" $public_excluded_paths' _ \
      "$excluded_line" | LC_ALL=C sort)"
    exporter_set="$(python3 -I -B -c 'import runpy, sys
names = runpy.run_path(sys.argv[1])
for item in {p.rstrip("/") for p in names["EXCLUDE_DIR_PREFIXES"]} | set(names["EXCLUDE_FILES"]):
    print(item)' "$EXPORTER" | LC_ALL=C sort)"
    [ -n "$runner_set" ] && [ "$runner_set" = "$exporter_set" ]
    check $? "the runner's public_excluded_paths is exactly the exporter's exclusion set" \
      "runner=<<$runner_set>> exporter=<<$exporter_set>>" ;;
  *)
    failc "the tree profile beside the runner reads private or public (got <<$tree_profile>>)" ;;
esac

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
