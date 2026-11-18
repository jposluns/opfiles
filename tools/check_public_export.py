#!/usr/bin/env python3
"""Public-export gate: the rebuilt public tree is exactly the whole tracked tree of HEAD.

Usage:
  python3 tools/check_public_export.py [--root PATH] [--ci]
  python3 tools/check_public_export.py --self-test

The gate runs tools/public_export/export_public.py to rebuild the public export into its own
temporary directory, then checks the result against the committed HEAD it was built from:

  1. the built tree holds exactly the tracked files of HEAD, with no exclusion set (the maintainer
     ruled that every tracked file ships; tools/public_export/README.md), which the gate recomputes
     itself from git ls-tree -r HEAD, so an exporter that drifts is caught: an extra path and a
     missing path are each a finding;
  2. every built file is byte-identical to its blob at HEAD (the gate reads the blobs itself with
     git cat-file and compares SHA-256), and its executable bit matches its git mode;
  3. nothing in the built tree is a symlink or any other non-regular file;
  4. the manifest the exporter wrote (path, git mode, SHA-256, sorted by path) matches the built
     tree exactly;
  5. no tracked path holds a directory component the names scan skips, so the scan's file census
     is exactly the export and the scan cannot pass over a partial view. The gate reads the skip
     list from the one top-level literal SKIP_DIRS assignment of tools/check_names.py at HEAD (the
     scanner the gate runs): a column-0 line of the form SKIP_DIRS = <literal>, whose value must be
     a non-empty set of directory names; no such line, two or more, a value that is not a literal
     on that one line, or a literal that is not such a set is CANNOT EVALUATE. That read covers
     only that assignment: any other skip logic in tools/check_names.py (such as a later
     SKIP_DIRS |= or SKIP_DIRS.add, or a further filter in its listed_paths) is not read, so it
     must be mirrored here.

Names. When the tree is structurally sound, the gate runs the names scan over the built tree with
the same denylist machinery as the names gate: it launches the built tree's own copy of
tools/check_names.py (python3 -I -B, as the runner launches it), whose root is the built tree.
The scan runs with GIT_CEILING_DIRECTORIES set to the gate's temporary directory, so git's
repository discovery cannot reach an enclosing repository (whose ignore rules could hide the
built tree and let the scan pass over no files) and the scan's file listing falls back to walking
the built tree itself: together with check 5 above, the scan reads exactly the exported files.
A denylist finding is covered only as the carve-out entry for its file records it (the recorded
functional names of plan.md section 4 item 11: the D4 footer, the security contact, the digest
anchor, repository links and the attribution wording). An entry with a lines list covers findings
only on its listed lines, whatever their number, and pins each listed line's content: the SHA-256
of the line's bytes at HEAD, the lines split as the scan splits them (at each LF only, the LF not
part of the line, no empty last line after a final LF). The gate compares every content pin with
the committed bytes on every run that reaches the comparison, in both modes, whether or not the
scan reports a finding, and records each mismatch before the names scan runs: a run that reaches a
verdict fails on it, and a run whose names scan cannot evaluate prints it above its CANNOT
EVALUATE error (exit 2). A run that cannot evaluate before the comparison (a missing or malformed
carve-out record or skip list, an export that does not build, or a git failure) compares nothing
and exits 2. So no run passes unless every content pin matches, and any edit to a listed line, and
a listed line the file no longer has, keeps the gate from passing until the line is deliberately
re-pinned. An entry with a matches list covers findings anywhere in its file, and the
gate fails unless each pinned denylist entry is reported exactly its pinned number of times and no
unpinned denylist entry is reported there at all.

Exactly this is caught: a finding in a file the carve-out does not name; a finding on a line a
lines entry does not list; any change to the bytes of a listed line (so a name added to a listed
line fails, whatever denylist entry it matches, and so does a same-line swap between denylist
entries); under a matches list, a per-denylist-entry count above or below its pin and any finding
of an unpinned denylist entry (so a single swap to an unpinned denylist entry, or one that changes
a pinned entry's count, fails); a path that matches the denylist; an email address; and a
home-directory path. Exactly this is not caught. Under a lines list, nothing on a listed line can
change without failing; since a finding on a listed line is covered whatever its number, a change
of the denylist itself that changes the findings on an unchanged listed line passes. Under a
matches list, the gate does not catch any change that keeps every pinned denylist entry's count in
the file and adds no unpinned entry, including moving a finding to another line, replacing a name
with other text matching the same entry, and reciprocal swaps between pinned entries; since the
scan reports one finding per (line, denylist entry) however often that entry matches within the
line, another match of an entry already reported on that line keeps the count too. Those changes
rest on review of changes to covered files. The match count pins are compared only when the scan
reports a finding: a scan that reports no finding at all leaves every count pin unchecked (the
content pins are still compared); that residual is accepted, since it means the scan found
nothing forbidden to publish. When the denylist is unavailable or
unusable the scan reports CANNOT-EVALUATE and exits 2, and this gate does the same, printing the
scan's own output: the names part behaves exactly as tools/check_names.py does in that case. When
the tree is not structurally sound the names scan is not run (scanning a wrong tree proves
nothing) and the structural findings fail the gate.

Modes:
  local (the default): every check above, with the full names scan, which needs the local
    denylist (OPFILES_NAMES_DENYLIST, or the names gate's default file).
  CI (the --ci argument): the hosted runner has no denylist, so the names scan runs with --ci
    (the email and home-directory checks only) and the denylist scan over the built tree stays
    local-only, the same split tools/run_all_checks.sh makes for the names gate; the structural
    checks run in full. No match count pin is compared in --ci (the denylist scan did not run, so
    every pinned count would be a vacuous zero) and every --ci scan finding is uncovered; the line
    content pins are compared, since they need no denylist.
    tools/run_all_checks.sh therefore lists public-export as NOT RUN in --ci and runs
    public-export-ci-subset, this mode, instead.
  --self-test: builds its own repositories in a temporary directory and checks that each failure
    is caught: an extra path, a missing path, a tracked governance path an exporter wrongly leaves
    out, a changed byte, a symlink, a non-regular file (a FIFO), a manifest that does not match
    the tree, a lost executable bit, an uncovered name, a finding on a line its entry does not
    list, a listed line's content change (a name of another denylist entry added to it, another
    match of the entry already reported on it, a same-line swap between denylist entries, and the
    same in --ci), a wrong content pin when the scan reports no finding, a match count above and
    below an entry's pin, a count-neutral swap of a covered name to another denylist entry, an
    unpinned denylist entry added alone under a matches list, a stale carve-out entry, a tracked
    path the names scan would skip (under the default skip list and under a skip name added to
    the scanner's SKIP_DIRS assignment), the CANNOT-EVALUATE pass-through for an unavailable
    denylist, and an edited listed line named by its content pin on that CANNOT EVALUATE path; a
    faithful export with covered names, an uncommitted carve-out edit (which must not change the
    verdict, since the record is read from HEAD), and the --ci subset are the green controls.
    Green cases pin the documented residuals: under a lines list, a denylist change that adds a
    finding on an unchanged listed line passes; under a matches list, a reciprocal swap between two
    pinned denylist entries, a finding moved to another line, a name replaced by other text
    matching the same denylist entry, and another match of an entry already reported on that line
    all pass; and a scan that reports no finding leaves a wrong match pin unchecked and passes.
    In-process cases show that the skip-list read and the lines pin format fail closed (CANNOT
    EVALUATE) on input they do not accept. The self-test fails unless every finding kind of
    FINDING_KINDS below went red, with exit 1, in at least one case.

The carve-out (tools/public_export/carve-out.toml, read from HEAD, the commit the verdict is
about, so an uncommitted edit of the record cannot change the verdict; the gate's own code and
the exporter still run from the work tree, as every gate's code does) must have format-version 1
and a non-empty entry list; each entry has path (a normalized relative path, named by at most one
entry), class (one of CLASSES below), reason (a non-empty string), and exactly one of lines (a
non-empty list of [line, sha256] pairs: a covered line number and the lowercase hexadecimal
SHA-256 of that line's bytes at HEAD) or matches (a non-empty list of [denylist entry, count]
pairs: a denylist entry index the scan reports for that file and the exact finding count pinned
for it). An entry whose path is not in the export is a finding, so the record cannot go stale
silently.

git runs as tools/check_line_width.py runs it: PATH and HOME from the caller and no other
variable, no system or global configuration, no replace refs, no lazy fetch. The names scan runs
with the caller's full environment plus GIT_CEILING_DIRECTORIES (see Names above), as the names
gate itself does, so OPFILES_NAMES_DENYLIST and HOME reach it.

The __main__ block opens with the canonical `--self-test` statement tools/opf.py requires of every
module of tools/ that binds self_test, so a run with --self-test alone calls self_test() directly
and exits with its status; any other arguments go to main(). self_test() runs the cases
(self_test_cases()) and turns an unexpected error inside them into CANNOT EVALUATE (exit 2), not
a failure (exit 1), as main() does for the gate itself.

Exit: 0 pass; 1 a finding; 2 cannot evaluate (the export did not build, git failed, the carve-out
is missing or malformed, the names scan cannot evaluate, an unexpected error in the gate or the
self-test, or a usage error).
"""
import argparse
import ast
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib

TOOL = "check_public_export"
GATE = "public-export"
# No exclusion set: the maintainer ruled that every file tracked at HEAD ships. Keep this gate in
# step with tools/public_export/export_public.py (the gate recomputes the tracked tree on its own).
FILE_MODES = {"100644": 0o644, "100755": 0o755}
EXPORTER_REL = "tools/public_export/export_public.py"
CARVE_OUT_REL = "tools/public_export/carve-out.toml"
NAMES_REL = "tools/check_names.py"
CLASSES = ("attribution", "d4-footer", "digest-anchor", "repository-link", "security-contact")
CARVE_TOP_KEYS = ("format-version", "entry")
ENTRY_KEYS = ("path", "class", "reason")
ENTRY_CHOICE_KEYS = ("lines", "matches")
# The one top-level literal SKIP_DIRS assignment of tools/check_names.py at HEAD, whose value is
# the set of directory names the names scan skips: scan_skip_dirs below reads that one line of the
# scanner and nothing else, so any other skip logic in the scanner must be mirrored here.
SKIP_DIRS_LINE = re.compile(r"^SKIP_DIRS = (.+)$", re.MULTILINE)
# A lines entry's content pin: the lowercase hexadecimal SHA-256 of the covered line's bytes.
LINE_PIN = re.compile(r"[0-9a-f]{64}")
GIT = "git"
GIT_TIMEOUT = 300
SCAN_TIMEOUT = 840
# The self-test runs this gate and git against small fixture repositories only, so each such
# subprocess gets a short budget; tools/run_all_checks.sh sizes the public-export-self-test gate
# bound above the sum of these budgets over every subprocess the self-test can start.
SELF_TEST_GATE_TIMEOUT = 120
SELF_TEST_GIT_TIMEOUT = 60
GIT_ENV_KEEP = ("PATH", "HOME")
GIT_ENV_SET = {"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
               "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
# A names-scan finding line that can be covered: a denylist match in a line of a file. Any other
# finding line (a path match, an email address, a home-directory path, or a line this parser does
# not read) is never coverable, so the gate fails closed on anything new.
LINE_FINDING = re.compile(r"^  (?P<path>.+):(?P<line>\d+): denylist entry (?P<entry>\d+)$")
# Every kind of finding; the self-test fails unless each one went red, with exit 1, in at least
# one of its cases.
FINDING_KINDS = ("extra-path", "missing-path", "changed-bytes", "mode-changed", "symlink",
                 "not-regular", "manifest", "carve-out-stale", "carve-out-content", "scan-census",
                 "names")
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CANNOT = 2


class CannotEvaluate(Exception):
    """Raised when the gate cannot reach a verdict. findings holds the finding lines already
    established when it was raised (the content-pin mismatches, when the names scan cannot
    evaluate), which check prints before the error."""

    findings = ()


def git_env(source=None):
    """Return the environment git runs in: GIT_ENV_KEEP of source (default os.environ), and
    GIT_ENV_SET."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items() if key in GIT_ENV_KEEP}
    env.update(GIT_ENV_SET)
    return env


def run_git(root, env, args, what, data=None):
    """Run git in root and return its stdout bytes, or raise CannotEvaluate naming what failed."""
    try:
        proc = subprocess.run([GIT, "-C", root] + list(args), input=data,
                              stdin=None if data is not None else subprocess.DEVNULL,
                              capture_output=True, env=env, timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate("git could not be run to %s (%s)" % (what, exc)) from None
    if proc.returncode != 0:
        raise CannotEvaluate("git failed to %s (exit %d: %s)" % (
            what, proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout


def expected_tree(root, env):
    """Return (HEAD commit, {path: (git mode, blob id)} of the whole tracked tree at HEAD).

    A symlink or a submodule anywhere in the committed tree, or any other unsupported mode, is
    CannotEvaluate: the exporter refuses the same tree, so there is nothing sound to compare.
    """
    head = run_git(root, env, ["rev-parse", "--verify", "HEAD^{commit}"],
                   "resolve HEAD").decode("ascii").strip()
    out = run_git(root, env, ["ls-tree", "-z", "-r", "--full-tree", "HEAD"],
                  "list the committed tree of HEAD")
    expected = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _sep, raw = record.partition(b"\t")
        fields = meta.split(b" ")
        if len(fields) != 3 or not raw:
            raise CannotEvaluate("unexpected git ls-tree record: %r" % record[:200])
        try:
            mode = fields[0].decode("ascii")
            kind = fields[1].decode("ascii")
            blob = fields[2].decode("ascii")
            path = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CannotEvaluate("a tracked path or entry is not decodable: %s" % exc) from None
        if mode == "120000":
            raise CannotEvaluate("%s is a symlink at HEAD; the export refuses symlinks" % path)
        if mode == "160000" or kind == "commit":
            raise CannotEvaluate("%s is a submodule at HEAD; the export refuses submodules"
                                 % path)
        if kind != "blob" or mode not in FILE_MODES:
            raise CannotEvaluate("%s has mode %s (%s), which the export does not support"
                                 % (path, mode, kind))
        expected[path] = (mode, blob)
    if not expected:
        raise CannotEvaluate("HEAD holds no exportable file")
    return head, expected


def read_blobs(root, env, blobs):
    """Return {blob id: its bytes} through one git cat-file --batch run."""
    unique = sorted(set(blobs))
    request = "".join(blob + "\n" for blob in unique).encode("ascii")
    out = run_git(root, env, ["cat-file", "--batch"], "read the blobs of HEAD", data=request)
    contents = {}
    position = 0
    for blob in unique:
        try:
            newline = out.index(b"\n", position)
        except ValueError:
            raise CannotEvaluate("git cat-file ended before the reply for blob %s"
                                 % blob) from None
        header = out[position:newline].decode("ascii", "replace").split(" ")
        if len(header) != 3 or header[0] != blob or header[1] != "blob":
            raise CannotEvaluate("git cat-file did not return blob %s (got: %s)"
                                 % (blob, " ".join(header)))
        try:
            size = int(header[2])
        except ValueError:
            raise CannotEvaluate("git cat-file reported a non-numeric size for blob %s"
                                 % blob) from None
        start = newline + 1
        end = start + size
        if out[end:end + 1] != b"\n":
            raise CannotEvaluate("git cat-file's reply for blob %s is truncated" % blob)
        contents[blob] = out[start:end]
        position = end + 1
    return contents


def build_export(root, work):
    """Run the exporter into work; return (built tree directory, manifest path)."""
    exporter = os.path.join(root, *EXPORTER_REL.split("/"))
    output = os.path.join(work, "tree")
    manifest = os.path.join(work, "manifest")
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", exporter, "--root", root,
             "--output", output, "--manifest", manifest],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=SCAN_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate("the exporter could not be run (%s)" % exc) from None
    if proc.returncode != 0:
        raise CannotEvaluate("the exporter failed (exit %d): %s" % (
            proc.returncode,
            (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()))
    return output, manifest


def scan_built(output):
    """Walk the built tree; return ({path: (SHA-256, git mode)}, symlink paths, other paths).

    Nothing is followed: a symlink (to anything) and any other non-regular entry are reported,
    never read.
    """
    files = {}
    symlinks = []
    others = []
    for current, dirnames, filenames in os.walk(output, followlinks=False):
        rel_dir = os.path.relpath(current, output)
        prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
        for name in sorted(dirnames):
            if os.path.islink(os.path.join(current, name)):
                symlinks.append(prefix + name + "/")
        for name in sorted(filenames):
            full = os.path.join(current, name)
            rel = prefix + name
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode):
                symlinks.append(rel)
                continue
            if not stat.S_ISREG(mode):
                others.append(rel)
                continue
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            files[rel] = (digest, "100755" if mode & stat.S_IXUSR else "100644")
    return files, symlinks, others


def read_manifest(manifest):
    """Return ({path: (git mode, SHA-256)}, problems) parsed from the manifest file."""
    problems = []
    entries = {}
    try:
        with open(manifest, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {}, ["the manifest cannot be read (%s)" % exc]
    for number, line in enumerate(lines, 1):
        fields = line.rstrip("\n").split("\t")
        if len(fields) != 3 or fields[1] not in FILE_MODES \
                or not re.fullmatch(r"[0-9a-f]{64}", fields[2]) or not fields[0]:
            problems.append("manifest line %d is not path, git mode and sha256" % number)
            continue
        if fields[0] in entries:
            problems.append("manifest line %d repeats the path %s" % (number, fields[0]))
            continue
        entries[fields[0]] = (fields[1], fields[2])
    return entries, problems


def pin_pairs(label, name, value, key_name):
    """Return {key: pinned count} from a carve-out entry's non-empty list of [key, count] pairs
    of positive integers with no key repeated, or raise CannotEvaluate."""
    if not isinstance(value, list) or not value:
        raise CannotEvaluate("%s %s is not a non-empty list of [%s, count] pairs"
                             % (label, name, key_name))
    pins = {}
    for item in value:
        if not isinstance(item, list) or len(item) != 2 \
                or any(type(part) is not int or part < 1 for part in item):
            raise CannotEvaluate("%s %s holds %r, not a [%s, count] pair of positive integers"
                                 % (label, name, item, key_name))
        if item[0] in pins:
            raise CannotEvaluate("%s %s pins %s %d twice" % (label, name, key_name, item[0]))
        pins[item[0]] = item[1]
    return pins


def line_pins(label, value):
    """Return {line: pinned SHA-256} from a carve-out entry's non-empty list of [line, sha256]
    pairs (a positive integer and 64 lowercase hexadecimal digits) with no line repeated, or raise
    CannotEvaluate."""
    if not isinstance(value, list) or not value:
        raise CannotEvaluate("%s lines is not a non-empty list of [line, sha256] pairs" % label)
    pins = {}
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or type(item[0]) is not int \
                or item[0] < 1 or not isinstance(item[1], str) \
                or not LINE_PIN.fullmatch(item[1]):
            raise CannotEvaluate("%s lines holds %r, not a [line, sha256] pair of a positive"
                                 " integer and 64 lowercase hexadecimal digits" % (label, item))
        if item[0] in pins:
            raise CannotEvaluate("%s lines pins line %d twice" % (label, item[0]))
        pins[item[0]] = item[1]
    return pins


def scan_lines(data):
    """Return the lines of data as the names scan reads them (tools/check_names.py grep_lines):
    split at each LF only, the LF not part of the line, and no empty last line after a final LF."""
    lines = data.split(b"\n")
    if not lines[-1]:
        lines.pop()
    return lines


def content_pin_findings(rel, data, pins):
    """Return the mismatch lines of a lines entry's content pins against its file's bytes at
    HEAD: a pinned line the file does not have, or a line whose SHA-256 is not its pin."""
    lines = scan_lines(data)
    mismatches = []
    for number in sorted(pins):
        if number > len(lines):
            mismatches.append("%s:%d: its carve-out entry pins this line's content, but the file"
                              " at HEAD has %d line(s)" % (rel, number, len(lines)))
            continue
        digest = hashlib.sha256(lines[number - 1]).hexdigest()
        if digest != pins[number]:
            mismatches.append("%s:%d: the line's bytes at HEAD have SHA-256 %s, but its carve-out"
                              " entry pins %s (re-pin it only after reviewing the edit)"
                              % (rel, number, digest, pins[number]))
    return mismatches


def load_carve_out(data):
    """Return {covered path: ("lines", {line: pinned SHA-256}) or ("matches", {denylist entry:
    pinned count})}, parsed from the carve-out record's bytes at HEAD, after validating the whole
    record."""
    try:
        record = tomllib.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CannotEvaluate("%s at HEAD is not UTF-8 (%s)" % (CARVE_OUT_REL, exc)) from None
    except tomllib.TOMLDecodeError as exc:
        raise CannotEvaluate("%s at HEAD is not valid TOML (%s)" % (CARVE_OUT_REL, exc)) from None
    if not isinstance(record, dict) or set(record) != set(CARVE_TOP_KEYS):
        raise CannotEvaluate("%s must have exactly the top-level keys %s"
                             % (CARVE_OUT_REL, " and ".join(CARVE_TOP_KEYS)))
    if record["format-version"] != 1:
        raise CannotEvaluate("%s has format-version %r; this gate reads version 1"
                             % (CARVE_OUT_REL, record["format-version"]))
    entries = record["entry"]
    if not isinstance(entries, list) or not entries:
        raise CannotEvaluate("%s has no non-empty entry list" % CARVE_OUT_REL)
    covered = {}
    for index, entry in enumerate(entries):
        label = "%s: entry[%d]" % (CARVE_OUT_REL, index)
        if not isinstance(entry, dict):
            raise CannotEvaluate(label + " is not a table")
        missing = [key for key in ENTRY_KEYS if key not in entry]
        unknown = sorted(set(entry) - set(ENTRY_KEYS) - set(ENTRY_CHOICE_KEYS))
        chosen = [key for key in ENTRY_CHOICE_KEYS if key in entry]
        if missing or unknown or len(chosen) != 1:
            raise CannotEvaluate("%s must have path, class, reason and exactly one of lines and"
                                 " matches (missing: %s; unknown: %s; of lines and matches: %s)"
                                 % (label, ", ".join(missing) or "none",
                                    ", ".join(unknown) or "none", ", ".join(chosen) or "none"))
        rel = entry["path"]
        if not isinstance(rel, str) or not rel or rel.startswith("/") \
                or any(part in ("", ".", "..") for part in rel.split("/")):
            raise CannotEvaluate(label + " path is not a normalized relative path")
        if rel in covered:
            raise CannotEvaluate("%s names %s, which an earlier entry already names"
                                 % (label, rel))
        if entry["class"] not in CLASSES:
            raise CannotEvaluate("%s class is not one of %s" % (label, ", ".join(CLASSES)))
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise CannotEvaluate(label + " reason is not a non-empty string")
        if chosen == ["lines"]:
            covered[rel] = ("lines", line_pins(label, entry["lines"]))
        else:
            covered[rel] = ("matches",
                            pin_pairs(label, "matches", entry["matches"], "denylist entry"))
    return covered


def scan_skip_dirs(data):
    """Return the directory names the names scan skips, parsed from the one top-level literal
    SKIP_DIRS assignment (a column-0 line SKIP_DIRS = <literal>) in the bytes of
    tools/check_names.py at HEAD; raise CannotEvaluate when there is not exactly one such line or
    its value is not a non-empty literal set of names on that line. Only that assignment is read:
    any other skip logic in the scanner is not, and must be mirrored in this gate."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CannotEvaluate("%s at HEAD is not UTF-8 (%s)" % (NAMES_REL, exc)) from None
    found = SKIP_DIRS_LINE.findall(text)
    if len(found) != 1:
        raise CannotEvaluate("%s at HEAD holds %d top-level SKIP_DIRS assignments; this gate"
                             " reads the scan's skip list from exactly one"
                             % (NAMES_REL, len(found)))
    try:
        value = ast.literal_eval(found[0])
    except (ValueError, SyntaxError) as exc:
        raise CannotEvaluate("the SKIP_DIRS assignment of %s at HEAD is not a literal this gate"
                             " can read (%s)" % (NAMES_REL, exc)) from None
    if not isinstance(value, (set, frozenset)) or not value \
            or not all(isinstance(item, str) and item for item in value):
        raise CannotEvaluate("the SKIP_DIRS of %s at HEAD is not a non-empty set of directory"
                             " names" % NAMES_REL)
    return frozenset(value)


def run_names_scan(output, work, ci):
    """Run the built tree's tools/check_names.py over the built tree; return (exit, output).

    GIT_CEILING_DIRECTORIES stops git's repository discovery at the gate's temporary directory
    work, so the scan's file listing cannot read an enclosing repository (whose ignore rules
    could hide the built tree and let the scan pass over no files) and falls back to walking the
    built tree itself.
    """
    scanner = os.path.join(output, *NAMES_REL.split("/"))
    command = [sys.executable, "-I", "-B", scanner] + (["--ci"] if ci else [])
    env = dict(os.environ)
    env["GIT_CEILING_DIRECTORIES"] = os.path.realpath(work)
    try:
        proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                              env=env, timeout=SCAN_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate("the names scan could not be run (%s)" % exc) from None
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")


def names_findings(scan_output, covered):
    """Return (uncovered finding lines, count pin mismatch lines, covered count) from the scan
    output.

    Only a denylist match in a line of a file the carve-out names is coverable: on a line its
    entry's lines list pins (whatever the number of findings there; that line's content pin,
    compared by content_pin_findings, fixes its bytes), or against its entry's matches pin for the
    denylist entry the scan reports, where every pinned count must equal the scan's count exactly.
    A path match, an email
    address, a home-directory path, a finding on a line a lines entry does not pin, a finding of
    a denylist entry a matches entry does not pin and any finding line this parser does not read
    are uncovered, so the gate fails closed on anything new.
    """
    uncovered = []
    counts = {}
    for line in scan_output.splitlines():
        if not line.startswith("  "):
            continue
        match = LINE_FINDING.fullmatch(line)
        if match is not None and match.group("path") in covered:
            choice, pins = covered[match.group("path")]
            key = int(match.group("line") if choice == "lines" else match.group("entry"))
            if key in pins:
                counts[(match.group("path"), key)] = counts.get((match.group("path"), key), 0) + 1
                continue
        uncovered.append(line.strip())
    mismatches = []
    covered_count = 0
    for rel in sorted(covered):
        choice, pins = covered[rel]
        for key in sorted(pins):
            count = counts.get((rel, key), 0)
            if choice == "lines" or count == pins[key]:
                covered_count += count
            else:
                mismatches.append("%s: %d match(es) of denylist entry %d, but its carve-out"
                                  " entry pins %d" % (rel, count, key, pins[key]))
    return uncovered, mismatches, covered_count


def evaluate(root, ci):
    """Return (exit, output lines) for the repository at root; raise CannotEvaluate."""
    env = git_env()
    head, expected = expected_tree(root, env)
    if CARVE_OUT_REL not in expected:
        raise CannotEvaluate("%s is not tracked at HEAD, so there is no committed carve-out"
                             " record to read" % CARVE_OUT_REL)
    covered = load_carve_out(run_git(root, env, ["cat-file", "blob", expected[CARVE_OUT_REL][1]],
                                     "read the carve-out record at HEAD"))
    if NAMES_REL not in expected:
        raise CannotEvaluate("%s is not tracked at HEAD, so the names scan cannot run"
                             % NAMES_REL)
    skip_dirs = scan_skip_dirs(run_git(root, env, ["cat-file", "blob", expected[NAMES_REL][1]],
                                       "read the names scanner at HEAD"))
    findings = []

    def find(message, kind):
        findings.append("FAIL: %s [%s]" % (message, kind))

    work = tempfile.mkdtemp(prefix="public-export.")
    try:
        output, manifest = build_export(root, work)
        built, symlinks, others = scan_built(output)
        for rel in symlinks:
            find("%s: the built tree holds a symlink" % rel, "symlink")
        for rel in others:
            find("%s: the built tree holds a non-regular file" % rel, "not-regular")
        present = set(built) | {rel.rstrip("/") for rel in symlinks} | set(others)
        for rel in sorted(set(built) - set(expected)):
            find("%s: an extra path in the built tree, not tracked at HEAD" % rel, "extra-path")
        for rel in sorted(set(expected) - present):
            find("%s: tracked at HEAD but missing from the built tree" % rel, "missing-path")
        contents = read_blobs(root, env, [blob for _mode, blob in expected.values()])
        # Every lines entry's content pins, against its file's bytes at HEAD: these need no
        # denylist, so they are compared in both modes and whatever the names scan reports. They
        # are recorded here, before the names scan can raise, so a names scan that cannot
        # evaluate still reports them (above its error); they do not stop the names scan.
        content_findings = []
        for rel in sorted(rel for rel in covered if rel in expected):
            choice, pins = covered[rel]
            if choice == "lines":
                content_findings.extend(
                    "FAIL: %s [carve-out-content]" % line
                    for line in content_pin_findings(rel, contents[expected[rel][1]], pins))
        for rel in sorted(set(built) & set(expected)):
            digest, built_mode = built[rel]
            mode, blob = expected[rel]
            if digest != hashlib.sha256(contents[blob]).hexdigest():
                find("%s: its bytes differ from its blob at HEAD" % rel, "changed-bytes")
            if built_mode != mode:
                find("%s: its mode is %s, but its git mode at HEAD is %s"
                     % (rel, built_mode, mode), "mode-changed")
        recorded, problems = read_manifest(manifest)
        for problem in problems:
            find(problem, "manifest")
        if not problems and recorded != {rel: (mode, digest)
                                         for rel, (digest, mode) in built.items()}:
            for rel in sorted(set(recorded) ^ set(built)):
                find("%s: in the manifest or the built tree, but not both" % rel, "manifest")
            for rel in sorted(set(recorded) & set(built)):
                if recorded[rel] != (built[rel][1], built[rel][0]):
                    find("%s: the manifest's mode or sha256 does not match the built file"
                         % rel, "manifest")
        for rel in sorted(set(covered) - set(expected)):
            find("%s: a carve-out entry names a path that is not in the export" % rel,
                 "carve-out-stale")
        for rel in sorted(rel for rel in expected
                          if any(part in skip_dirs for part in rel.split("/"))):
            find("%s: the names scan skips this path, so its census would not be the export"
                 % rel, "scan-census")
        names_note = "not run: the built tree does not match HEAD"
        if not findings:
            try:
                code, scan_output = run_names_scan(output, work, ci)
                if code not in (0, 1):
                    raise CannotEvaluate(
                        "the names scan over the built tree did not evaluate (exit %d), as "
                        "tools/check_names.py reports:\n%s" % (code, scan_output.rstrip("\n")))
            except CannotEvaluate as exc:
                exc.findings = tuple(content_findings)
                raise
            if code == 0:
                names_note = ("the checks that need no denylist passed; the denylist scan over "
                              "the built tree is local-only") if ci else "no finding"
            else:
                # In --ci the denylist scan did not run, so no count pin is compared (its count
                # would be a vacuous zero) and every scan finding is uncovered.
                uncovered, mismatches, covered_count = names_findings(scan_output,
                                                                      {} if ci else covered)
                for line in uncovered:
                    find("names scan: %s (not covered by %s)" % (line, CARVE_OUT_REL), "names")
                for line in mismatches:
                    find("names scan: %s" % line, "names")
                names_note = ("%d finding(s), each covered by the carve-out" % covered_count
                              if not uncovered and not mismatches else "uncovered findings")
        findings.extend(content_findings)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    lines = list(findings)
    if findings:
        lines.append("%s: FAIL (%d finding(s))" % (GATE, len(findings)))
        return EXIT_FAIL, lines
    executables = sum(1 for mode, _blob in expected.values() if mode == "100755")
    content_pins = sum(len(pins) for choice, pins in covered.values() if choice == "lines")
    lines.append("%s: PASS (%d files (%d executable), the whole tracked tree of HEAD %s; no "
                 "symlink; the manifest matches; the scan census is the export; %d carve-out line "
                 "content pin(s) match HEAD; names scan: %s)"
                 % (GATE, len(expected), executables, head[:12], content_pins, names_note))
    return EXIT_PASS, lines


def check(root, ci=False):
    """Return (exit, output lines) for the repository at root."""
    try:
        return evaluate(root, ci)
    except CannotEvaluate as exc:
        return EXIT_CANNOT, list(exc.findings) + ["ERROR: %s" % exc,
                                                  "%s: CANNOT EVALUATE (1 error)" % GATE]


def default_root():
    """Return the parent of this tool's directory, resolved with os.path.realpath."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# The self-test. Every repository it builds is in a temporary directory, with git's global and
# system configuration switched off and a fixed identity, so no setting of the host applies. The
# fixture repositories carry the real exporter and the real names gate (read from this tool's own
# tree), a fixture carve-out and a fixture denylist outside the repository; each red case swaps
# the work-tree exporter for a wrapper that runs the real exporter and then tampers with the
# output, so each failure is shown to be caught by this gate, not by the exporter. The gate reads
# the carve-out from HEAD, so a case that changes the record or a covered file commits the
# change, runs the gate, and commits the original back.

WRAPPER_TEMPLATE = '''#!/usr/bin/env python3
"""Self-test stand-in for export_public.py: run the real exporter, then tamper ({mode})."""
import hashlib
import os
import subprocess
import sys

argv = sys.argv[1:]
proc = subprocess.run([sys.executable, "-I", "-B", {real!r}] + argv)
if proc.returncode != 0:
    sys.exit(proc.returncode)
output = argv[argv.index("--output") + 1]
manifest = argv[argv.index("--manifest") + 1]


def manifest_lines():
    with open(manifest, "r", encoding="utf-8") as handle:
        return handle.readlines()


def write_manifest(lines):
    with open(manifest, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(rel, data):
    with open(os.path.join(output, rel), "wb") as handle:
        handle.write(data)


mode = {mode!r}
if mode == "extra":
    write("extra.txt", b"extra\\n")
    write_manifest(sorted(manifest_lines() + ["extra.txt\\t100644\\t%s\\n" % digest(b"extra\\n")]))
elif mode == "missing":
    os.unlink(os.path.join(output, "README.md"))
    write_manifest([line for line in manifest_lines() if not line.startswith("README.md\\t")])
elif mode == "changed":
    write("README.md", b"changed\\n")
    write_manifest([("README.md\\t100644\\t%s\\n" % digest(b"changed\\n"))
                    if line.startswith("README.md\\t") else line for line in manifest_lines()])
elif mode == "symlink":
    target = os.path.join(output, "README.md")
    aside = manifest + ".bytes"
    os.rename(target, aside)
    os.symlink(aside, target)
elif mode == "fifo":
    target = os.path.join(output, "README.md")
    os.unlink(target)
    os.mkfifo(target)
elif mode == "exclude":
    os.unlink(os.path.join(output, "CLAUDE.md"))
    write_manifest([line for line in manifest_lines() if not line.startswith("CLAUDE.md\\t")])
elif mode == "manifest":
    write_manifest([("README.md\\t100644\\t%s\\n" % ("0" * 64))
                    if line.startswith("README.md\\t") else line for line in manifest_lines()])
elif mode == "chmod":
    os.chmod(os.path.join(output, "bin", "run.sh"), 0o644)
sys.exit(0)
'''

# The committed bytes of the fixture files the red cases replace for one run each; the fixture
# denylist holds two entries, fixtureterm (entry 1) and otherterm (entry 2), so a count-neutral
# swap between denylist entries and a same-line addition of another entry's name can be shown red.
FIXTURE_COVERED_MD = b"the fixtureterm anchor\n"
FIXTURE_PINNED_MD = b"fixtureterm one\nfixtureterm two\n"
FIXTURE_DENYLIST = "fixtureterm\notherterm\n"
# A denylist whose one entry matches nothing in the fixture, so the names scan reports no finding.
FIXTURE_NO_MATCH_DENYLIST = "qqqnomatchqqq\n"
# The fixture lines entry pins docs/covered.md line 1 by the SHA-256 of its bytes.
FIXTURE_LINES = "lines = [[1, \"%s\"]]" % hashlib.sha256(b"the fixtureterm anchor").hexdigest()

FIXTURE_CARVE_OUT = (
    "format-version = 1\n\n"
    "[[entry]]\n"
    "path = \"docs/covered.md\"\n"
    "class = \"digest-anchor\"\n"
    "reason = \"Self-test fixture: the covered functional name, on its exact line.\"\n"
    + FIXTURE_LINES + "\n\n"
    "[[entry]]\n"
    "path = \"docs/pinned.md\"\n"
    "class = \"d4-footer\"\n"
    "reason = \"Self-test fixture: the pinned per-denylist-entry match counts.\"\n"
    "matches = [[1, 2]]\n"
)


def hermetic_env(home):
    """Return a git environment with no variable of the host but PATH, and a fixed identity."""
    stamp = "2026-01-01T00:00:00Z"
    return {"PATH": os.environ.get("PATH", os.defpath), "HOME": home, "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "public-export self-test",
            "GIT_AUTHOR_EMAIL": "self-test@invalid",
            "GIT_COMMITTER_NAME": "public-export self-test",
            "GIT_COMMITTER_EMAIL": "self-test@invalid", "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp, "GIT_TERMINAL_PROMPT": "0"}


def fixture_git(env):
    """Return setup(repo, *args), which runs git in repo for a fixture."""
    def setup(repo, *args):
        try:
            proc = subprocess.run([GIT, "-C", repo, "-c", "commit.gpgsign=false"] + list(args),
                                  stdin=subprocess.DEVNULL, capture_output=True, env=env,
                                  timeout=SELF_TEST_GIT_TIMEOUT, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise CannotEvaluate("git could not be run to set up a fixture (%s)" % exc) from None
        if proc.returncode != 0:
            raise CannotEvaluate("git %s failed setting up a fixture (exit %d: %s)" % (
                args[0], proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))
        return proc.stdout
    return setup


def write_file(root, rel, data, executable=False):
    """Write data at rel below root, creating directories, with the executable bit as asked."""
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o755 if executable else 0o644)


def fixture_names_bytes():
    """Return the bytes of the real names gate, read from this tool's own directory."""
    here = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(here, "check_names.py"), "rb") as handle:
        return handle.read()


def build_fixture(tmp, setup):
    """Build the fixture repository: tracked content, the real exporter and names gate, a
    fixture carve-out, governance files (which ship too), and one executable; return its path."""
    repo = os.path.join(tmp, "fixture")
    os.makedirs(repo)
    here = os.path.dirname(os.path.realpath(__file__))
    names_bytes = fixture_names_bytes()
    with open(os.path.join(here, "public_export", "export_public.py"), "rb") as handle:
        exporter_bytes = handle.read()
    write_file(repo, "README.md", b"# Fixture\n")
    write_file(repo, "docs/covered.md", FIXTURE_COVERED_MD)
    write_file(repo, "docs/pinned.md", FIXTURE_PINNED_MD)
    write_file(repo, "bin/run.sh", b"#!/bin/sh\nexit 0\n", executable=True)
    write_file(repo, "CLAUDE.md", b"governance\n")
    write_file(repo, "AGENTS.md", b"governance\n")
    write_file(repo, ".claude/settings.json", b"{}\n")
    write_file(repo, ".aiqt/pin.toml", b"pin = 1\n")
    write_file(repo, NAMES_REL, names_bytes)
    write_file(repo, EXPORTER_REL, exporter_bytes)
    write_file(repo, CARVE_OUT_REL, FIXTURE_CARVE_OUT.encode("ascii"))
    write_file(repo, "tools/public_export/README.md", b"fixture\n")
    setup(repo, "init", "-q", "-b", "main")
    setup(repo, "add", "-A")
    setup(repo, "commit", "-q", "-m", "base")
    return repo


def self_test():
    """Run the self-test (self_test_cases); return its status, or 2 (CANNOT EVALUATE) when it
    raises an unexpected error, since a crash inside the self-test proves nothing either way."""
    try:
        return self_test_cases()
    except Exception as exc:
        print("%s: CANNOT EVALUATE (self-test raised an unexpected error: %s: %s)"
              % (GATE, type(exc).__name__, exc), file=sys.stderr)
        return EXIT_CANNOT


def self_test_cases():
    """Run every case; return 0 when all pass, 1 when any fails, 2 when it cannot evaluate."""
    total = failures = 0
    red_kinds = set()

    def report(ok, label, detail=""):
        nonlocal total, failures
        total += 1
        if not ok:
            failures += 1
            print("  FAIL  %s%s" % (label, (": " + detail) if detail else ""))
        else:
            print("  ok    %s" % label)

    with tempfile.TemporaryDirectory(prefix="check_public_export.") as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        env = hermetic_env(home)
        setup = fixture_git(env)
        repo = build_fixture(tmp, setup)
        exporter_work = os.path.join(repo, *EXPORTER_REL.split("/"))
        with open(exporter_work, "rb") as handle:
            real_exporter = handle.read()
        denylist = os.path.join(tmp, "terms.regex")
        with open(denylist, "w", encoding="ascii") as handle:
            handle.write(FIXTURE_DENYLIST)
        originals = {CARVE_OUT_REL: FIXTURE_CARVE_OUT.encode("ascii"),
                     "docs/covered.md": FIXTURE_COVERED_MD, "docs/pinned.md": FIXTURE_PINNED_MD}
        runs = 0

        def run_gate(label, args=(), with_denylist=True, wrapper=None, carve_out=None,
                     files=None, denylist_text=None):
            """Run this gate against the fixture; return (exit, output). carve_out and files
            replace committed fixture files for the one run: the gate reads HEAD, so each
            replacement is committed first and the original bytes are committed back after.
            denylist_text replaces the fixture denylist for the one run (a file outside the
            fixture repository)."""
            nonlocal runs
            runs += 1
            changes = dict(files or {})
            if carve_out is not None:
                changes[CARVE_OUT_REL] = carve_out.encode("ascii")
            if changes:
                for rel in sorted(changes):
                    write_file(repo, rel, changes[rel])
                setup(repo, "add", "-A")
                setup(repo, "commit", "-q", "-m", "case: " + label)
            if wrapper is not None:
                text = WRAPPER_TEMPLATE.format(
                    real=os.path.join(tmp, "real_export_public.py"), mode=wrapper)
                with open(exporter_work, "w", encoding="ascii") as handle:
                    handle.write(text)
            case_tmp = os.path.join(tmp, "case-%d" % runs)
            os.makedirs(case_tmp)
            gate_env = {"PATH": env["PATH"], "HOME": home, "TMPDIR": case_tmp,
                        "PYTHONDONTWRITEBYTECODE": "1"}
            if with_denylist:
                gate_env["OPFILES_NAMES_DENYLIST"] = denylist
                if denylist_text is not None:
                    gate_env["OPFILES_NAMES_DENYLIST"] = os.path.join(tmp, "terms-%d.regex" % runs)
                    with open(gate_env["OPFILES_NAMES_DENYLIST"], "w", encoding="ascii") as handle:
                        handle.write(denylist_text)
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "-B", os.path.realpath(__file__),
                     "--root", repo] + list(args),
                    stdin=subprocess.DEVNULL, capture_output=True, env=gate_env,
                    timeout=SELF_TEST_GATE_TIMEOUT, check=False)
            except (OSError, subprocess.SubprocessError) as exc:
                raise CannotEvaluate("the gate could not be run for %s (%s)"
                                     % (label, exc)) from None
            finally:
                if wrapper is not None:
                    with open(exporter_work, "wb") as handle:
                        handle.write(real_exporter)
                    os.chmod(exporter_work, 0o644)
                if changes:
                    for rel in sorted(changes):
                        write_file(repo, rel, originals[rel])
                    setup(repo, "add", "-A")
                    setup(repo, "commit", "-q", "-m", "restore: " + label)
            return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")

        def expect(label, code, needles, result, absent=()):
            got, out = result
            needles = [needles] if isinstance(needles, str) else list(needles)
            ok = got == code and all(needle in out for needle in needles) \
                and not any(item in out for item in absent)
            if ok and code == EXIT_FAIL:
                red_kinds.update(kind for kind in FINDING_KINDS
                                 if any(("[%s]" % kind) in needle for needle in needles))
            report(ok, label,
                   "expected exit %d with %r and without %r, got exit %d: %s"
                   % (code, needles, list(absent), got, out))

        # The real exporter the wrappers run must be callable from outside the fixture work tree.
        with open(os.path.join(tmp, "real_export_public.py"), "wb") as handle:
            handle.write(real_exporter)

        expect("green: a faithful export passes, with the covered names counted", EXIT_PASS,
               ["%s: PASS" % GATE, "covered by the carve-out"], run_gate("green"))
        expect("an extra path is caught", EXIT_FAIL, "[extra-path]",
               run_gate("extra", wrapper="extra"))
        expect("a missing path is caught", EXIT_FAIL, "[missing-path]",
               run_gate("missing", wrapper="missing"))
        expect("a changed byte is caught", EXIT_FAIL, "[changed-bytes]",
               run_gate("changed", wrapper="changed"))
        expect("a symlink is caught, even to identical bytes", EXIT_FAIL, "[symlink]",
               run_gate("symlink", wrapper="symlink"), absent=["[changed-bytes]"])
        expect("a non-regular file in the built tree is caught", EXIT_FAIL, "[not-regular]",
               run_gate("fifo", wrapper="fifo"))
        expect("a tracked governance path left out of the export is caught", EXIT_FAIL,
               ["[missing-path]", "CLAUDE.md"], run_gate("exclude", wrapper="exclude"))
        expect("a manifest that does not match the tree is caught", EXIT_FAIL, "[manifest]",
               run_gate("manifest", wrapper="manifest"))
        expect("a lost executable bit is caught", EXIT_FAIL, "[mode-changed]",
               run_gate("chmod", wrapper="chmod"))
        expect("a stale carve-out entry is caught", EXIT_FAIL, "[carve-out-stale]",
               run_gate("stale", carve_out=FIXTURE_CARVE_OUT.replace(
                   "docs/covered.md", "docs/gone.md")))
        expect("a finding on a line its entry does not list is caught", EXIT_FAIL,
               ["[names]", "docs/covered.md"],
               run_gate("unlisted-line", carve_out=FIXTURE_CARVE_OUT.replace(
                   FIXTURE_LINES, FIXTURE_LINES.replace("[[1, ", "[[3, "))))
        expect("a match count above its entry's pin is caught", EXIT_FAIL,
               ["[names]", "docs/pinned.md", "pins 1"],
               run_gate("over-pin", carve_out=FIXTURE_CARVE_OUT.replace(
                   "matches = [[1, 2]]", "matches = [[1, 1]]")))
        expect("a match count below its entry's pin is caught", EXIT_FAIL,
               ["[names]", "docs/pinned.md", "pins 3"],
               run_gate("under-pin", carve_out=FIXTURE_CARVE_OUT.replace(
                   "matches = [[1, 2]]", "matches = [[1, 3]]")))
        expect("a count-neutral swap of a covered name to another denylist entry is caught",
               EXIT_FAIL, ["[names]", "docs/pinned.md", "pins 2", "denylist entry 2"],
               run_gate("swap", files={"docs/pinned.md": b"fixtureterm one\notherterm two\n"}))
        expect("an unpinned denylist entry added alone under a matches list is caught",
               EXIT_FAIL, ["[names]", "docs/pinned.md:3: denylist entry 2"],
               run_gate("unpinned-entry", files={
                   "docs/pinned.md": b"fixtureterm one\nfixtureterm two\notherterm\n"}),
               absent=["pins 2"])
        expect("a name of another denylist entry added to a listed line is caught by its"
               " content pin", EXIT_FAIL, ["[carve-out-content]", "docs/covered.md:1"],
               run_gate("same-line",
                        files={"docs/covered.md": b"the fixtureterm anchor and otherterm\n"}))
        expect("another match of the denylist entry already reported on a listed line is caught"
               " by its content pin", EXIT_FAIL, ["[carve-out-content]", "docs/covered.md:1"],
               run_gate("same-line-same-entry",
                        files={"docs/covered.md": b"the fixtureterm anchor and fixtureterm\n"}),
               absent=["[names]"])
        expect("a same-line swap between denylist entries on a listed line is caught by its"
               " content pin", EXIT_FAIL, ["[carve-out-content]", "docs/covered.md:1"],
               run_gate("same-line-swap", files={"docs/covered.md": b"the otherterm anchor\n"}),
               absent=["[names]"])
        expect("a listed line's content pin is compared in --ci, where no denylist is needed",
               EXIT_FAIL, ["[carve-out-content]", "docs/covered.md:1"],
               run_gate("ci-content", args=["--ci"], with_denylist=False,
                        files={"docs/covered.md": b"the fixtureterm anchor and otherterm\n"}))
        expect("a wrong content pin is caught when the scan reports no finding (a denylist"
               " matching nothing, a wrong match pin left unchecked)", EXIT_FAIL,
               ["[carve-out-content]", "docs/covered.md:1"],
               run_gate("no-finding-content", carve_out=FIXTURE_CARVE_OUT.replace(
                   "matches = [[1, 2]]", "matches = [[1, 5]]").replace(
                   FIXTURE_LINES, "lines = [[1, \"%s\"]]" % ("0" * 64)),
                   denylist_text=FIXTURE_NO_MATCH_DENYLIST),
               absent=["[names]"])
        # Documented residuals of a matches list: each change keeps every pinned denylist entry's
        # count in the file and adds no unpinned entry, so the gate passes it (the review of
        # changes to covered files is what catches it).
        expect("documented residual: with entries 1 and 2 pinned once each under a matches list,"
               " swapping the two names between lines 1 and 2 passes", EXIT_PASS,
               ["%s: PASS" % GATE, "3 finding(s), each covered by the carve-out"],
               run_gate("residual-reciprocal-swap", carve_out=FIXTURE_CARVE_OUT.replace(
                   "matches = [[1, 2]]", "matches = [[1, 1], [2, 1]]"),
                   files={"docs/pinned.md": b"otherterm one\nfixtureterm two\n"}))
        expect("documented residual: moving a pinned entry's finding to another line under a"
               " matches list passes", EXIT_PASS,
               ["%s: PASS" % GATE, "covered by the carve-out"],
               run_gate("residual-move", files={
                   "docs/pinned.md": b"fixtureterm one\nplain\nplain\nfixtureterm two\n"}))
        expect("documented residual: replacing a name with other text matching the same denylist"
               " entry under a matches list passes", EXIT_PASS,
               ["%s: PASS" % GATE, "covered by the carve-out"],
               run_gate("residual-same-entry", files={
                   "docs/pinned.md": b"FixtureTerm one\nfixtureterm two\n"}))
        expect("documented residual: another match of a pinned entry on a line where that entry"
               " is already reported keeps the count under a matches list and passes", EXIT_PASS,
               ["%s: PASS" % GATE, "3 finding(s), each covered by the carve-out"],
               run_gate("residual-another-match", files={
                   "docs/pinned.md": b"fixtureterm one and fixtureterm again\nfixtureterm two\n"}))
        # The lines residual: the fixture denylist gives 3 covered findings (the green case); a
        # second denylist entry matching only the listed line adds a fourth, on that unchanged
        # line, and the gate still passes.
        expect("documented residual: a denylist change that adds a finding on an unchanged listed"
               " line passes", EXIT_PASS,
               ["%s: PASS" % GATE, "4 finding(s), each covered by the carve-out"],
               run_gate("residual-lines-denylist",
                        denylist_text=FIXTURE_DENYLIST + "fixtureterm anchor\n"))
        expect("documented residual: a scan that reports no finding leaves a wrong match pin"
               " unchecked and passes", EXIT_PASS,
               ["%s: PASS" % GATE, "names scan: no finding"],
               run_gate("residual-no-finding", carve_out=FIXTURE_CARVE_OUT.replace(
                   "matches = [[1, 2]]", "matches = [[1, 5]]"),
                   denylist_text=FIXTURE_NO_MATCH_DENYLIST))
        write_file(repo, CARVE_OUT_REL, b"format-version = 99\n")
        expect("an uncommitted carve-out edit does not change the verdict (the record is read"
               " from HEAD)", EXIT_PASS, ["%s: PASS" % GATE], run_gate("uncommitted"))
        write_file(repo, CARVE_OUT_REL, FIXTURE_CARVE_OUT.encode("ascii"))
        expect("an unavailable denylist cannot evaluate, as the names gate does", EXIT_CANNOT,
               ["CANNOT-EVALUATE", "CANNOT EVALUATE"], run_gate("no-denylist",
                                                                with_denylist=False))
        expect("an edited listed line is named by its content pin even when the names scan"
               " cannot evaluate", EXIT_CANNOT,
               ["[carve-out-content]", "docs/covered.md:1", "CANNOT-EVALUATE", "CANNOT EVALUATE"],
               run_gate("cannot-content", with_denylist=False,
                        files={"docs/covered.md": b"the otherterm anchor\n"}))
        expect("--ci runs the checks that need no denylist", EXIT_PASS,
               ["%s: PASS" % GATE, "local-only"], run_gate("ci", args=["--ci"],
                                                           with_denylist=False))
        write_file(repo, "docs/uncovered.md", b"another fixtureterm\n")
        setup(repo, "add", "docs/uncovered.md")
        setup(repo, "commit", "-q", "-m", "uncovered")
        expect("an uncovered name fails the gate", EXIT_FAIL,
               ["[names]", "docs/uncovered.md"], run_gate("uncovered"),
               absent=["docs/covered.md:"])
        write_file(repo, "__pycache__/skipped.txt", b"skipped\n")
        setup(repo, "add", "__pycache__/skipped.txt")
        setup(repo, "commit", "-q", "-m", "skipped")
        expect("a tracked path the names scan skips is caught", EXIT_FAIL,
               ["[scan-census]", "__pycache__/skipped.txt"], run_gate("census"))
        # A skip name other than the default ones: the gate reads the skip list from the
        # scanner's SKIP_DIRS assignment at HEAD, so a name added there is enforced too.
        names_custom, added = SKIP_DIRS_LINE.subn(
            lambda match: "SKIP_DIRS = {\"fixtureskip\", " + match.group(1).lstrip("{"),
            fixture_names_bytes().decode("utf-8"), count=1)
        report(added == 1 and "{\"fixtureskip\", " in names_custom,
               "the fixture scanner's SKIP_DIRS assignment gains the skip name fixtureskip",
               "the SKIP_DIRS assignment of tools/check_names.py was not found")
        write_file(repo, NAMES_REL, names_custom.encode("utf-8"))
        write_file(repo, "fixtureskip/held.txt", b"held\n")
        setup(repo, "add", "-A")
        setup(repo, "commit", "-q", "-m", "custom skip name")
        expect("a tracked path under a skip name added to the scanner's SKIP_DIRS is caught",
               EXIT_FAIL, ["[scan-census]", "fixtureskip/held.txt"], run_gate("census-custom"))

        # In-process cases: the skip-list read and the lines pin format fail closed.
        def expect_cannot(label, func, data, fragment):
            try:
                func(data)
            except CannotEvaluate as exc:
                report(fragment in str(exc), label,
                       "expected CANNOT EVALUATE with %r, got: %s" % (fragment, exc))
                return
            report(False, label, "expected CANNOT EVALUATE with %r, got a result" % fragment)

        skip_cases = (
            ("no SKIP_DIRS assignment", b"OTHER = {\".git\"}\n", "holds 0 top-level"),
            ("two SKIP_DIRS assignments",
             b"SKIP_DIRS = {\".git\"}\nSKIP_DIRS = {\"__pycache__\"}\n", "holds 2 top-level"),
            ("a non-literal SKIP_DIRS value", b"SKIP_DIRS = set(NAMES)\n", "not a literal"),
            ("a SKIP_DIRS literal spread over several lines",
             b"SKIP_DIRS = {\n    \".git\",\n}\n", "not a literal"),
            ("a SKIP_DIRS literal that is not a set", b"SKIP_DIRS = {}\n", "non-empty set"),
            ("a SKIP_DIRS set holding a non-string", b"SKIP_DIRS = {\".git\", 1}\n",
             "non-empty set"),
            ("a scanner that is not UTF-8", b"SKIP_DIRS = {\"\xff\"}\n", "not UTF-8"),
        )
        for what, data, fragment in skip_cases:
            expect_cannot("the skip-list read fails closed on " + what, scan_skip_dirs, data,
                          fragment)
        try:
            parsed = scan_skip_dirs(b"SKIP_DIRS = {\".git\", \"vendored\"}\n")
        except CannotEvaluate as exc:
            parsed = exc
        report(parsed == frozenset({".git", "vendored"}),
               "the skip-list read returns a non-default skip name", "got %r" % (parsed,))
        record = FIXTURE_CARVE_OUT.replace(FIXTURE_LINES, "%s")
        not_a_pin = "not a [line, sha256] pair"
        lines_cases = (
            ("a [line, count] pair (the earlier format)", "lines = [[1, 1]]", not_a_pin),
            ("a pin that is not 64 hexadecimal digits", "lines = [[1, \"abc\"]]", not_a_pin),
            ("an uppercase hexadecimal pin", FIXTURE_LINES.upper().replace("LINES", "lines"),
             not_a_pin),
            ("a line pinned twice", FIXTURE_LINES.replace("]]", "], " + FIXTURE_LINES[9:-1]
                                                          + "]"), "pins line 1 twice"),
        )
        for what, lines_value, fragment in lines_cases:
            expect_cannot("the carve-out record fails closed on " + what, load_carve_out,
                          (record % lines_value).encode("ascii"), fragment)

        unred = [kind for kind in FINDING_KINDS if kind not in red_kinds]
        report(not unred, "every finding kind is red, with exit 1, in at least one case",
               "kinds not shown red: " + (", ".join(unred) or "none"))

    if failures:
        print("FAIL: %s self-test (%d checks, %d failures)" % (GATE, total, failures))
        return EXIT_FAIL
    print("PASS: %s self-test (%d checks, 0 failures)" % (GATE, total))
    return EXIT_PASS


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Check the public export against the committed HEAD.")
    parser.add_argument("--root", default=None,
                        help="repository root (default: the parent of this tool's directory)")
    parser.add_argument("--ci", action="store_true",
                        help="hosted mode: the names scan runs only the checks that need no "
                             "denylist")
    parser.add_argument("--self-test", action="store_true",
                        help="build fixture repositories in a temporary directory and check them")
    args = parser.parse_args(argv)
    if args.self_test and (args.root is not None or args.ci):
        parser.error("--self-test does not take --root or --ci")
    try:
        if args.self_test:
            return self_test()
        code, lines = check(args.root if args.root is not None else default_root(), args.ci)
    except Exception as exc:
        print("%s: CANNOT EVALUATE (unexpected error: %s: %s)" % (GATE, type(exc).__name__, exc),
              file=sys.stderr)
        return EXIT_CANNOT
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(main())
