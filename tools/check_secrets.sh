#!/usr/bin/env bash
# Secrets gate: scan the repository's files with the pinned gitleaks release.
# In a git checkout it scans a copy of exactly the tracked files and the untracked files that
# .gitignore does not exclude, so an ignored machine-local file is never scanned; outside a git
# checkout it scans the whole directory.
# It fails when gitleaks is not on PATH or reports a version other than PINNED, so a missing or
# different scanner is never read as a pass. CI installs the same release, verified by its sha256
# (.github/workflows/quality.yml); change PINNED and the workflow's GITLEAKS_VERSION and
# GITLEAKS_SHA256 together (tools/check_quality_workflow.py checks the two versions agree).
# Exit: 0 no leaks, 1 leaks found or the scanner is absent or another version, 2 setup error.
set -uo pipefail
PINNED=8.30.1
dir=$(dirname -- "$0") || exit 2
[ -n "$dir" ] || exit 2
root="$(CDPATH= cd -- "$dir/.." && pwd)" || exit 2

if ! command -v gitleaks >/dev/null 2>&1; then
  printf 'FAIL: gitleaks is not on PATH. Install release %s; its sha256 is in .github/workflows/quality.yml.\n' "$PINNED"
  exit 1
fi
version="$(gitleaks version 2>/dev/null)" || version=""
# Printable ASCII only, one bounded line, for the comparison and the message.
version="$(printf '%s' "$version" | LC_ALL=C tr -cd '\040-\176' | cut -c1-64)"
version="${version#v}"
if [ "$version" != "$PINNED" ]; then
  printf 'FAIL: gitleaks reports version %s; this gate requires %s.\n' "${version:-(none)}" "$PINNED"
  exit 1
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/check_secrets.XXXXXX")" || work=""
if [ -z "$work" ] || [ ! -d "$work" ]; then
  printf 'CANNOT-EVALUATE: could not create a temporary directory.\n'
  exit 2
fi
trap 'rm -rf -- "$work"' EXIT
scan="$root"
what="the whole directory (not a git checkout)"
if env -u GIT_DIR -u GIT_WORK_TREE git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  mkdir -- "$work/files" || exit 2
  # --ignore-failed-read skips a tracked file that was deleted from the working tree.
  if ! env -u GIT_DIR -u GIT_WORK_TREE git -C "$root" ls-files -z --cached --others --exclude-standard |
      (CDPATH= cd -- "$root" && tar --null --no-recursion --ignore-failed-read -T - -cf -) |
      tar -xf - -C "$work/files"; then
    printf 'CANNOT-EVALUATE: could not copy the tracked and unignored files for scanning.\n'
    exit 2
  fi
  scan="$work/files"
  what="the tracked and unignored files"
fi
rc=0
gitleaks dir "$scan" --no-banner --redact --exit-code 1 || rc=$?
if [ "$rc" -ne 0 ]; then
  printf 'FAIL: gitleaks %s reported findings or an error (exit %s). Treat a real secret as compromised: rotate it first, then remove it.\n' "$PINNED" "$rc"
  exit 1
fi
printf 'PASS: gitleaks %s found no leaks in %s\n' "$PINNED" "$what"
exit 0
