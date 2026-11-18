"""Check the post-import deviation records of PROVENANCE-inventory.json against the files.

Usage:
  python3 tools/check_provenance_deviations.py [--root PATH]
  python3 tools/check_provenance_deviations.py --self-test

PROVENANCE-inventory.json is an object with exactly the keys deviations, entries, files,
source_commit and source_opf_tree. Each item of "entries" names one imported file by its path, git
mode, blob id and SHA-256 as imported. Each record of "deviations" names an imported file changed
since the import by its path, the reason, the blob id and SHA-256 of its current bytes, and its
imported SHA-256 (sha256_imported). The gate reads only the repository: it recomputes the SHA-256
and the git blob id of every imported file from its current bytes, compares them with both lists,
compares each file's owner executable bit with its entry's mode, and checks that PROVENANCE.md pins
the SHA-256 of the inventory's current bytes on its "- Per-file inventory:
`PROVENANCE-inventory.json`" line, which must end with "sha256 <digest>".

The entries list is anchored to the import: the gate recomputes the git tree id of the imported
tree from the entries (mode, path and blob, with git's tree format and order) and requires it to
equal both the inventory's source_opf_tree and the 40-hex id on PROVENANCE.md's "- Source `opf/`
tree object:" line. It also requires files to equal the entry count, PROVENANCE.md's "- Imported
files: N (E executable)" line to match the entry count and the 100755 count, and source_commit to
equal the 40-hex id on PROVENANCE.md's "- Source commit:" line. Each of these PROVENANCE.md lines,
and the pin line, is found by its marker in any letter case, so a second line in another case is
a finding. A value rule that does not depend on spelling backs the markers. Every run of exactly
40 or 64 hex digits in PROVENANCE.md, in any letter case, must be the value of the Source commit
line, the source tree line or the pin line, each in its exact form. Every count pair (digits, "("
and digits, with any Unicode digits and spaces) must be the counts of the Imported files line in
its exact form. Any other such value is a finding, so a second line that differs from one of those
lines only in an invisible or look-alike character is seen when it holds such a value.

Residual: the gate cannot see the source repository. An edit that rewrites entries to match the
current files, together with source_opf_tree, the PROVENANCE.md tree line and the pin (and, when
the edit changes the number of entries or of 100755 entries, files and the Imported files line to
match; and, for a file with a deviation record whose entry it rewrites or drops, that record
dropped) passes, so it can hide a change to an imported file. So does a matching edit of
source_commit and the Source commit line. Treat any change to those values as a re-import and
review it against the source repository: git rev-parse <source_commit>:opf must print the tree id.
The entries' sha256 values are not part of the tree id, so only the SHA-1 blob id ties an
unchanged file to the import. This SHA-1 has no collision detection, so a file built to collide
with its imported blob passes once its entry's sha256 and the pin are rewritten and any deviation
record for it is dropped. The value rule matches by shape only. It sees a run of exactly 40 or 64
ASCII hex digits, in any letter case, with no ASCII hex digit on either side, so a hex value is not
seen when every run of ASCII hex digits that holds a part of it has another length, as when other
hex digits extend it to another length or when characters that are not ASCII hex digits, look-alike
or invisible, break it into runs of other lengths. It sees a count pair as an ASCII "(" whose
nearest characters that are not Unicode whitespace, on each side, are Unicode decimal digits, so a
pair whose "(" is a look-alike character, or that has any other character, such as an invisible one
or a look-alike digit that is not a Unicode decimal digit, such as a superscript digit, between a
count and its "(", is not seen. A copy that drops executable bits, such as an archive or a snapshot,
fails with [mode-changed].

The root is opened once and every path is resolved beneath that directory descriptor, one component
at a time, so no symlink is followed at any level. Each file is opened with O_NOFOLLOW and
O_NONBLOCK, and fstat confirms a regular file before any byte is read. The JSON reader refuses a
duplicate key and the constants NaN and Infinity.

Exit status:
  0  every imported file is a regular file whose bytes equal its imported SHA-256 (with a matching
     entry blob id) or are recorded by exactly one deviation record, and whose executable bit
     matches its entry's mode; every record has exactly the fields path, reason, blob, sha256 and
     sha256_imported in the right form, names an imported file that differs from its imported
     bytes, and matches the file and the entry; the records are sorted by path; the entries, the
     inventory's top-level keys and counts and PROVENANCE.md's import lines agree as above;
     PROVENANCE.md pins the inventory's current SHA-256 once; and PROVENANCE.md holds no run of
     exactly 40 or 64 hex digits and no count pair outside the values of those lines;
  1  a finding, each named on its own line with its kind in brackets: the git tree id of the
     entries differs from source_opf_tree [entries-tree]; PROVENANCE.md has no single "- Source
     `opf/` tree object:" line naming that tree id [source-tree]; files is not the entry count
     [file-count]; PROVENANCE.md has no single "- Imported files:" line with the entry and
     executable counts [imported-count]; the inventory lacks a top-level key or has one the format
     does not define [inventory-keys]; source_commit differs from PROVENANCE.md's single "- Source
     commit:" line [source-commit]; an imported file's executable bit differs from its entry's
     mode [mode-changed]; an imported file changed with no deviation record
     [unrecorded-change]; a record's sha256 [stale-sha256] or blob
     [stale-blob] does not match the file; its sha256_imported does not match the entry
     [wrong-imported-sha256]; it names a file equal to its imported bytes [unchanged-file] or a path
     that is not an entry [not-an-entry]; the records are not sorted by path [unsorted] or name a
     path twice [duplicate-record]; a record lacks a field [missing-field], has a field the format
     does not define [unexpected-field], or has a field of the wrong form or is not an object
     [bad-field]; an imported file is missing [missing-file], or it or PROVENANCE.md is a symlink,
     not a regular file or replaced while being checked [not-regular]; an unchanged file's blob id
     differs from its entry [entry-blob]; PROVENANCE.md is missing or has no pin [pin-missing],
     pins another SHA-256 [pin-stale], or has more than one line that pins an inventory digest,
     whatever its form or letter case [pin-duplicate]; or a PROVENANCE.md line holds a run of
     exactly 40 or 64 hex digits that is not the value of the Source commit, source tree or pin
     line in its exact form [stray-digest], or a count pair that is not the counts of the
     Imported files line in its exact form [stray-count];
  2  the check cannot be evaluated: the root cannot be opened as a directory; the inventory is
     missing, a symlink, not a regular file, not UTF-8, not valid JSON (a duplicate key, NaN or
     Infinity included), or its entries or deviations is missing or not a list; an entry is not an
     object with exactly path, mode, blob and sha256 in the right form, its path is not a
     normalized relative path, two entries name one path, or one entry's path is a directory of
     another's; a file cannot be read for a reason other than absence; PROVENANCE.md is not UTF-8;
     an unexpected error occurs; the command line is invalid; or Python is older than 3.14.

A deviation record holds no mode, so any change to an imported file's executable bit is a finding:
the git mode of an imported file is not a post-import change this format can record. The gate does
not look for files the inventory does not list: an addition is not a deviation. The default root is
the parent of this tool's directory, resolved with os.path.realpath, as in
tools/check_aiqt_vendored.py. Only the standard library is used.
"""

import sys

MIN_PYTHON = (3, 14)
TOOL = "check_provenance_deviations"
GATE = "provenance-deviations"


def python_gate(version):
    """Return 2 when the given version is older than the floor, else 0."""
    return 2 if tuple(version[:2]) < MIN_PYTHON else 0


# The floor is checked at load, as the OPF tools in tools/ check theirs, so the only test of
# __name__ is the entry block at the end of the file.
if python_gate(sys.version_info) != 0:
    import os
    try:
        sys.stderr.write(
            "%s: Python 3.14 or newer is required; this is Python %d.%d\n"
            % (TOOL, sys.version_info[0], sys.version_info[1])
        )
        sys.stderr.flush()
    except BaseException:
        pass
    os._exit(2)

import argparse  # noqa: E402
import contextlib  # noqa: E402
import errno  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import posixpath  # noqa: E402
import re  # noqa: E402
import signal  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402

INVENTORY = "PROVENANCE-inventory.json"
PROVENANCE = "PROVENANCE.md"
PIN_PREFIX = "- Per-file inventory: `PROVENANCE-inventory.json`"
PIN_DIGEST = re.compile(r"sha256 ([0-9a-f]{64})$")
# A line that pins an inventory digest in any form: it starts with PIN_PREFIX, or it names the
# inventory and holds "sha256 " with 64 hex digits, each compared in any letter case. Exactly one
# such line is allowed, and it must start with PIN_PREFIX exactly.
PIN_MARKERS = ("Per-file inventory", INVENTORY)
PIN_ANY_DIGEST = re.compile(r"sha256 [0-9a-f]{64}", re.IGNORECASE)
# The import facts of PROVENANCE.md: (marker, the line form, its description, finding kind). Every
# line holding the marker in any letter case counts, and exactly one is allowed, which must match
# the form exactly.
SOURCE_COMMIT_LINE = ("Source commit", re.compile(r"- Source commit: ([0-9a-f]{40})(?: .*)?"),
                      "- Source commit: <40 hex>", "source-commit")
SOURCE_TREE_LINE = ("tree object", re.compile(r"- Source `opf/` tree object: ([0-9a-f]{40})"),
                    "- Source `opf/` tree object: <40 hex>", "source-tree")
IMPORTED_LINE = ("Imported files",
                 re.compile(r"- Imported files: ([1-9][0-9]*|0) \(([1-9][0-9]*|0) executable\)"
                            r"(?:;.*)?"),
                 "- Imported files: <N> (<E> executable)", "imported-count")
# The value rule, which does not depend on how a line is spelt: a run of exactly 40 or 64 hex
# digits in any letter case (a commit, tree or blob id, or a SHA-256) may appear in PROVENANCE.md
# only as the value of the Source commit, source tree or pin line in its exact form, and a count
# pair (digits, "(" and digits, with any Unicode digits and spaces) only as the counts of the
# Imported files line in its exact form. A count pair may start only at the first digit of a run
# and ends at the first digit after "(", so a long run of digits is scanned in linear time;
# check_stray_values compares only where each pair starts.
HEX_RUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{64}|[0-9A-Fa-f]{40})(?![0-9A-Fa-f])")
COUNT_RUN = re.compile(r"(?<!\d)\d+\s*\(\s*\d")
TOP_KEYS = ("deviations", "entries", "files", "source_commit", "source_opf_tree")
ENTRY_FIELDS = ("blob", "mode", "path", "sha256")
RECORD_FIELDS = ("path", "reason", "blob", "sha256", "sha256_imported")
MODES = ("100644", "100755")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
BLOB_RE = re.compile(r"[0-9a-f]{40}")
# Every kind of finding; the self-test fails unless each one is red in at least one case.
FINDING_KINDS = (
    "entries-tree",
    "source-tree",
    "file-count",
    "imported-count",
    "inventory-keys",
    "source-commit",
    "mode-changed",
    "unrecorded-change",
    "stale-sha256",
    "stale-blob",
    "wrong-imported-sha256",
    "unchanged-file",
    "not-an-entry",
    "unsorted",
    "duplicate-record",
    "missing-field",
    "unexpected-field",
    "bad-field",
    "missing-file",
    "not-regular",
    "entry-blob",
    "pin-missing",
    "pin-stale",
    "pin-duplicate",
    "stray-digest",
    "stray-count",
)
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CANNOT = 2
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
ROOT_FLAGS = os.O_RDONLY | _DIRECTORY | _CLOEXEC
DIR_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
# O_NOFOLLOW refuses a symlink swapped in after lstat; O_NONBLOCK keeps a swapped-in FIFO from
# blocking the open. Neither changes how a regular file is read.
READ_FLAGS = os.O_RDONLY | _NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _CLOEXEC
CASE_SECONDS = 10

# The self-test replaces this to inject races and read errors; everything else uses os.open.
_open = os.open


class CannotEvaluate(Exception):
    """Raised when the check cannot reach a verdict."""


def error_text(exc):
    """Return an OSError's message; strerror is None for some errors."""
    return str(exc.strerror or exc)


def path_problem(rel):
    """Return why an inventory path is not acceptable, or None when it is."""
    if not isinstance(rel, str) or rel == "":
        return "is not a nonempty string"
    if rel.startswith("/") or "\\" in rel or "\0" in rel:
        return "is not a relative POSIX path"
    try:
        rel.encode("utf-8")
    except UnicodeEncodeError:
        return "is not encodable as UTF-8"
    parts = rel.split("/")
    if ".." in parts or "" in parts or "." in parts or posixpath.normpath(rel) != rel:
        return "is not a normalized relative path"
    return None


def split_rel(rel):
    """Split a relative path, refusing any component that could leave its parent."""
    parts = rel.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise CannotEvaluate(rel + ": unsafe path component " + repr(part))
    return parts


def descend(root_fd, parts):
    """Open the directory that parts name beneath root_fd, one component at a time.

    Return (fd, None) with a new descriptor that the caller closes, or (None, (kind, where)) when
    a component is missing or not a directory ("missing"), is a symlink ("symlink"), or was
    replaced between its lstat and its open ("replaced"). An lstat classifies each component;
    O_NOFOLLOW with O_DIRECTORY refuses a symlink or non-directory swapped in after it.
    """
    fd = os.dup(root_fd)
    try:
        for index, part in enumerate(parts):
            where = "/".join(parts[: index + 1])
            try:
                mode = os.lstat(part, dir_fd=fd).st_mode
            except (FileNotFoundError, NotADirectoryError):
                return None, ("missing", where)
            except OSError as exc:
                raise CannotEvaluate(where + ": cannot inspect: " + error_text(exc)) from exc
            if stat.S_ISLNK(mode):
                return None, ("symlink", where)
            if not stat.S_ISDIR(mode):
                return None, ("missing", where)
            try:
                child = _open(part, DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    return None, ("symlink", where)
                if exc.errno == errno.ENOTDIR:
                    return None, ("replaced", where)
                if exc.errno == errno.ENOENT:
                    return None, ("missing", where)
                raise CannotEvaluate(where + ": cannot open: " + error_text(exc)) from exc
            os.close(fd)
            fd = child
        result, fd = fd, -1
        return result, None
    finally:
        if fd >= 0:
            os.close(fd)


def read_entry(root_fd, rel):
    """Read rel beneath root_fd without following any symlink; return (kind, where, data, mode).

    kind is "file" with the bytes and the st_mode from fstat of the open file, or "missing",
    "symlink", "replaced" or "other" with None and None; where is the relative path of the entry
    that decided it. O_NOFOLLOW refuses a symlink swapped in after the lstat, O_NONBLOCK keeps a
    swapped-in FIFO from blocking the open, and fstat confirms a regular file before any byte is
    read.
    """
    parts = split_rel(rel)
    fd, stop = descend(root_fd, parts[:-1])
    if stop is not None:
        return stop + (None, None)
    try:
        try:
            mode = os.lstat(parts[-1], dir_fd=fd).st_mode
        except (FileNotFoundError, NotADirectoryError):
            return "missing", rel, None, None
        except OSError as exc:
            raise CannotEvaluate(rel + ": cannot inspect: " + error_text(exc)) from exc
        if stat.S_ISLNK(mode):
            return "symlink", rel, None, None
        if not stat.S_ISREG(mode):
            return "other", rel, None, None
        try:
            file_fd = _open(parts[-1], READ_FLAGS, dir_fd=fd)
        except FileNotFoundError:
            return "missing", rel, None, None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return "symlink", rel, None, None
            raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(fd)
    try:
        file_mode = os.fstat(file_fd).st_mode
        if not stat.S_ISREG(file_mode):
            return "other", rel, None, None
        chunks = []
        while True:
            chunk = os.read(file_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return "file", rel, b"".join(chunks), file_mode
    except OSError as exc:
        raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(file_fd)


def git_blob(data):
    """Return the git blob id (SHA-1 of the blob header and the bytes) of data."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tree_id(entries):
    """Return the git tree id of the tree that entries (path to entry) describe.

    Each directory's children are sorted by name as bytes, with a directory's name compared as the
    name followed by "/"; a file is "<mode> <name>\\0" and its 20-byte blob id, a directory is
    "40000 <name>\\0" and its 20-byte tree id, and a tree id is the SHA-1 of "tree <length>\\0"
    and the body. Raise CannotEvaluate when one entry's path is a directory of another's.
    """
    root = {}
    for path, entry in entries.items():
        parts = path.split("/")
        node = root
        for index, part in enumerate(parts[:-1]):
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                raise CannotEvaluate(INVENTORY + ": the entries name "
                                     + "/".join(parts[: index + 1])
                                     + " as both a file and a directory")
            node = child
        if parts[-1] in node:
            raise CannotEvaluate(INVENTORY + ": the entries name " + path
                                 + " as both a file and a directory")
        node[parts[-1]] = (entry["mode"], entry["blob"])

    def build(node):
        items = []
        for name, value in node.items():
            raw = name.encode("utf-8")
            if isinstance(value, dict):
                items.append((raw + b"/", b"40000 " + raw + b"\0" + bytes.fromhex(build(value))))
            else:
                mode, blob = value
                items.append((raw, mode.encode("ascii") + b" " + raw + b"\0"
                              + bytes.fromhex(blob)))
        body = b"".join(line for _key, line in sorted(items))
        return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()

    return build(root)


def not_a_file(kind, where, rel):
    """Return the message for rel, which read_entry did not read as a regular file."""
    if kind == "missing":
        return "missing" if where == rel else where + " is missing or not a directory"
    if kind == "symlink":
        return where + " is a symlink; it is not followed"
    if kind == "replaced":
        return where + " was replaced while being checked"
    return where + " is not a regular file"


def _refuse_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key " + repr(key))
        seen[key] = value
    return seen


def _refuse_constant(name):
    raise ValueError("the constant " + name + " is not JSON")


def load_inventory(root_fd):
    """Return (bytes, parsed object) of the inventory, or raise CannotEvaluate."""
    kind, where, data, _mode = read_entry(root_fd, INVENTORY)
    if kind != "file":
        raise CannotEvaluate(INVENTORY + ": " + not_a_file(kind, where, INVENTORY))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CannotEvaluate(INVENTORY + ": is not UTF-8: " + str(exc)) from exc
    try:
        inventory = json.loads(
            text, object_pairs_hook=_refuse_duplicates, parse_constant=_refuse_constant)
    except ValueError as exc:
        raise CannotEvaluate(INVENTORY + ": is not valid JSON: " + str(exc)) from exc
    if not isinstance(inventory, dict):
        raise CannotEvaluate(INVENTORY + ": the top level is not an object")
    for key in ("entries", "deviations"):
        if not isinstance(inventory.get(key), list):
            raise CannotEvaluate(INVENTORY + ": has no " + key + " list")
    return data, inventory


def parse_entries(items):
    """Return a dict of path to entry for the entries list, or raise CannotEvaluate."""
    entries = {}
    for index, item in enumerate(items):
        label = INVENTORY + ": entries[%d]" % index
        if not isinstance(item, dict) or set(item) != set(ENTRY_FIELDS):
            raise CannotEvaluate(label + " is not an object with exactly the fields "
                                 + ", ".join(ENTRY_FIELDS))
        problem = path_problem(item["path"])
        if problem is not None:
            raise CannotEvaluate(label + " path " + problem)
        if item["mode"] not in MODES:
            raise CannotEvaluate(label + " mode is not one of " + ", ".join(MODES))
        if not isinstance(item["blob"], str) or not BLOB_RE.fullmatch(item["blob"]):
            raise CannotEvaluate(label + " blob is not 40 lowercase hex")
        if not isinstance(item["sha256"], str) or not SHA256_RE.fullmatch(item["sha256"]):
            raise CannotEvaluate(label + " sha256 is not 64 lowercase hex")
        if item["path"] in entries:
            raise CannotEvaluate(label + " repeats the path " + item["path"])
        entries[item["path"]] = item
    return entries


def record_problems(index, record):
    """Return (label, findings) for one deviation record: its shape, field by field."""
    if not isinstance(record, dict):
        return "deviations[%d]" % index, [("is not an object", "bad-field")]
    path = record.get("path")
    label = "deviation " + path if isinstance(path, str) else "deviations[%d]" % index
    problems = []
    for field in RECORD_FIELDS:
        if field not in record:
            problems.append(("lacks the field " + field, "missing-field"))
    for field in sorted(set(record) - set(RECORD_FIELDS)):
        problems.append(("has the field " + field + ", which the format does not define",
                         "unexpected-field"))
    forms = (
        ("path", lambda value: isinstance(value, str) and value != "", "a nonempty string"),
        ("reason", lambda value: isinstance(value, str) and value.strip() != "",
         "a nonempty string"),
        ("blob", lambda value: isinstance(value, str) and BLOB_RE.fullmatch(value),
         "40 lowercase hex"),
        ("sha256", lambda value: isinstance(value, str) and SHA256_RE.fullmatch(value),
         "64 lowercase hex"),
        ("sha256_imported", lambda value: isinstance(value, str) and SHA256_RE.fullmatch(value),
         "64 lowercase hex"),
    )
    for field, good, form in forms:
        if field in record and not good(record[field]):
            problems.append((field + " is not " + form, "bad-field"))
    return label, problems


def read_provenance(root_fd, digest, find):
    """Return the lines of PROVENANCE.md, or None after reporting why it cannot be checked."""
    kind, where, data, _mode = read_entry(root_fd, PROVENANCE)
    if kind == "missing" and where == PROVENANCE:
        find(PROVENANCE, "missing; it must pin the inventory sha256 " + digest, "pin-missing")
        return None
    if kind != "file":
        find(PROVENANCE, not_a_file(kind, where, PROVENANCE), "not-regular")
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CannotEvaluate(PROVENANCE + ": is not UTF-8: " + str(exc)) from exc
    return [line.rstrip("\r") for line in text.split("\n")]


def provenance_fact(lines, fact, find):
    """Return the match of the one PROVENANCE.md line for fact, or None after a finding.

    fact is (marker, form, description, kind). Every line holding the marker in any letter case
    counts, so a second line in another form or case is not overlooked; exactly one is allowed,
    and it must match the form.
    """
    marker, form, description, kind = fact
    folded = marker.casefold()
    hits = [line for line in lines if folded in line.casefold()]
    if not hits:
        find(PROVENANCE, "has no line %s" % description, kind)
        return None
    if len(hits) > 1:
        find(PROVENANCE, "has %d lines holding %r in any letter case; exactly one line %s is "
             "allowed" % (len(hits), marker, description), kind)
        return None
    match = form.fullmatch(hits[0])
    if match is None:
        find(PROVENANCE, "its line %r is not in the form %s" % (hits[0], description), kind)
    return match


def check_pin(lines, digest, find):
    """Check that PROVENANCE.md pins digest on exactly one inventory line.

    A pin line is one that starts with PIN_PREFIX, or one in any other form that names the
    inventory and holds "sha256 " with 64 hex digits, each compared in any letter case; exactly
    one is allowed, and it must start with PIN_PREFIX exactly.
    """
    prefix = PIN_PREFIX.casefold()
    markers = [marker.casefold() for marker in PIN_MARKERS]
    pins = [line for line in lines if line.casefold().startswith(prefix)
            or (any(marker in line.casefold() for marker in markers)
                and PIN_ANY_DIGEST.search(line))]
    if not pins:
        find(PROVENANCE, "has no line starting %s; it must pin the inventory sha256 %s"
             % (PIN_PREFIX, digest), "pin-missing")
        return
    if len(pins) > 1:
        find(PROVENANCE, "has %d inventory pin lines; exactly one is allowed" % len(pins),
             "pin-duplicate")
        return
    if not pins[0].startswith(PIN_PREFIX):
        find(PROVENANCE, "its inventory pin line %r does not start with %s; it must pin %s"
             % (pins[0], PIN_PREFIX, digest), "pin-missing")
        return
    match = PIN_DIGEST.search(pins[0])
    if match is None:
        find(PROVENANCE, "its inventory line does not end with sha256 and a digest; it must pin "
             + digest, "pin-missing")
    elif match.group(1) != digest:
        find(PROVENANCE, "pins the inventory sha256 %s, but the inventory's sha256 is %s"
             % (match.group(1), digest), "pin-stale")


def canonical_values(line):
    """Return (hex spans, count starts): the values line may hold as a canonical line.

    A line is canonical when it matches the Source commit or source tree form exactly, starts with
    PIN_PREFIX exactly and ends with "sha256 <digest>", or matches the Imported files form exactly;
    it may hold only its own value. Any other line may hold no value.
    """
    for fact in (SOURCE_COMMIT_LINE, SOURCE_TREE_LINE):
        match = fact[1].fullmatch(line)
        if match is not None:
            return {match.span(1)}, set()
    if line.startswith(PIN_PREFIX):
        match = PIN_DIGEST.search(line)
        if match is not None:
            return {match.span(1)}, set()
    match = IMPORTED_LINE[1].fullmatch(line)
    if match is not None:
        return set(), {match.start(1)}
    return set(), set()


def check_stray_values(lines, find):
    """Report each PROVENANCE.md line that holds a value outside the canonical lines' own values.

    A value is a run of exactly 40 or 64 hex digits (HEX_RUN) or a count pair (COUNT_RUN). The rule
    does not read the markers, so a second line that differs from a canonical line only in an
    invisible or look-alike character is a finding whatever its spelling. The line is shown with
    ascii(), so every character that is not ASCII is escaped and visible in the message.
    """
    for number, line in enumerate(lines, 1):
        hex_ok, count_ok = canonical_values(line)
        stray = [match for match in HEX_RUN.finditer(line) if match.span() not in hex_ok]
        if stray:
            find(PROVENANCE, "line %d %s holds a run of 40 or 64 hex digits that is not the value "
                 "of the Source commit, source tree or pin line in its exact form"
                 % (number, ascii(line)), "stray-digest")
        counts = [match for match in COUNT_RUN.finditer(line) if match.start() not in count_ok]
        if counts:
            find(PROVENANCE, "line %d %s holds a count pair that is not the counts of the "
                 "Imported files line in its exact form" % (number, ascii(line)), "stray-count")


def evaluate(root_fd):
    """Return (exit, lines) for the repository open at root_fd; raise CannotEvaluate."""
    data, inventory = load_inventory(root_fd)
    entries = parse_entries(inventory["entries"])
    tree = tree_id(entries)
    findings = []

    def find(where, message, kind):
        findings.append("FAIL: %s: %s [%s]" % (where, message, kind))

    for key in TOP_KEYS:
        if key not in inventory:
            find(INVENTORY, "lacks the top-level key " + key, "inventory-keys")
    for key in sorted(set(inventory) - set(TOP_KEYS)):
        find(INVENTORY, "has the top-level key %s, which the format does not define" % key,
             "inventory-keys")
    if "source_opf_tree" in inventory and inventory["source_opf_tree"] != tree:
        find(INVENTORY, "the git tree id of the entries is %s, but source_opf_tree is %s"
             % (tree, json.dumps(inventory["source_opf_tree"])), "entries-tree")
    files = inventory.get("files")
    if "files" in inventory and (type(files) is not int or files != len(entries)):
        find(INVENTORY, "files is %s, but the entries list has %d entries"
             % (json.dumps(files), len(entries)), "file-count")

    current = {}
    for path, entry in entries.items():
        kind, where, content, mode = read_entry(root_fd, path)
        if kind == "file":
            current[path] = (hashlib.sha256(content).hexdigest(), git_blob(content))
            executable = bool(mode & stat.S_IXUSR)
            if executable != (entry["mode"] == "100755"):
                find(path, "its executable bit is %s, but its entry's mode is %s"
                     % ("set" if executable else "clear", entry["mode"]), "mode-changed")
        elif kind == "missing" and where == path:
            find(path, "imported file is missing", "missing-file")
        elif kind == "missing":
            find(path, "imported file is missing: " + not_a_file(kind, where, path),
                 "missing-file")
        else:
            find(path, "imported file: " + not_a_file(kind, where, path), "not-regular")

    records = []
    previous = None
    recorded = set()
    for index, record in enumerate(inventory["deviations"]):
        label, problems = record_problems(index, record)
        for message, kind in problems:
            find(label, message, kind)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            continue
        path = record["path"]
        if previous is not None and path == previous:
            find(label, "repeats the path of the record before it", "duplicate-record")
        elif previous is not None and path < previous:
            find(label, "is out of order: it sorts before %s, the record before it" % previous,
                 "unsorted")
        previous = path
        recorded.add(path)
        if not problems:
            records.append(record)

    changed = 0
    for path, entry in entries.items():
        if path not in current:
            continue
        sha256, blob = current[path]
        if sha256 == entry["sha256"]:
            if blob != entry["blob"]:
                find(path, "its bytes equal the imported sha256, but their blob id %s differs "
                     "from the entry's blob %s" % (blob, entry["blob"]), "entry-blob")
            continue
        changed += 1
        if path not in recorded:
            find(path, "changed since the import (sha256 %s, imported %s) with no deviation record"
                 % (sha256, entry["sha256"]), "unrecorded-change")

    for record in records:
        path = record["path"]
        label = "deviation " + path
        entry = entries.get(path)
        if entry is None:
            find(label, "names a path that is not an imported entry", "not-an-entry")
            continue
        if record["sha256_imported"] != entry["sha256"]:
            find(label, "sha256_imported %s does not match the entry's sha256 %s"
                 % (record["sha256_imported"], entry["sha256"]), "wrong-imported-sha256")
        if path not in current:
            continue
        sha256, blob = current[path]
        if sha256 == entry["sha256"]:
            find(label, "names a file whose bytes equal its imported sha256 %s; drop the record"
                 % sha256, "unchanged-file")
            continue
        if record["sha256"] != sha256:
            find(label, "sha256 %s does not match the file's sha256 %s"
                 % (record["sha256"], sha256), "stale-sha256")
        if record["blob"] != blob:
            find(label, "blob %s does not match the file's blob id %s" % (record["blob"], blob),
                 "stale-blob")

    digest = hashlib.sha256(data).hexdigest()
    provenance = read_provenance(root_fd, digest, find)
    if provenance is not None:
        check_pin(provenance, digest, find)
        match = provenance_fact(provenance, SOURCE_TREE_LINE, find)
        if match is not None and match.group(1) != tree:
            find(PROVENANCE, "names the source tree object %s, but the git tree id of the entries "
                 "is %s" % (match.group(1), tree), "source-tree")
        match = provenance_fact(provenance, SOURCE_COMMIT_LINE, find)
        if (match is not None and "source_commit" in inventory
                and inventory["source_commit"] != match.group(1)):
            find(PROVENANCE, "names the source commit %s, but the inventory's source_commit is %s"
                 % (match.group(1), json.dumps(inventory["source_commit"])), "source-commit")
        match = provenance_fact(provenance, IMPORTED_LINE, find)
        executables = sum(1 for entry in entries.values() if entry["mode"] == "100755")
        if match is not None and (int(match.group(1)), int(match.group(2))) != (
                len(entries), executables):
            find(PROVENANCE, "says %s imported files (%s executable), but the entries list has %d "
                 "(%d executable)" % (match.group(1), match.group(2), len(entries), executables),
                 "imported-count")
        check_stray_values(provenance, find)

    lines = list(findings)
    if findings:
        lines.append("%s: FAIL (%s)" % (GATE, plural(len(findings), "finding")))
        return EXIT_FAIL, lines
    lines.append(
        "%s: PASS (%s checked, %d changed since the import and each recorded; the entries hash to "
        "the source tree %s; %s pins the inventory sha256 %s)"
        % (GATE, plural(len(entries), "imported file"), changed, tree, PROVENANCE, digest))
    return EXIT_PASS, lines


def cannot(message):
    return EXIT_CANNOT, ["ERROR: " + message, GATE + ": CANNOT EVALUATE (1 error)"]


def check(root):
    """Return (exit, lines) for the repository at root."""
    try:
        root_fd = os.open(root, ROOT_FLAGS)
    except OSError as exc:
        return cannot("the root cannot be opened as a directory: " + (root or "(empty path)")
                      + " (" + error_text(exc) + ")")
    try:
        return evaluate(root_fd)
    except CannotEvaluate as exc:
        return cannot(str(exc))
    finally:
        os.close(root_fd)


def plural(count, noun):
    return "%d %s%s" % (count, noun, "" if count == 1 else "s")


# Self-test fixtures. The imported tree has four files; a case changes the current files, the
# deviation records, the inventory or PROVENANCE.md, and the fixture writes them all. tools.sh
# sits beside tools/ because git's order differs from a plain byte order there: git compares a
# directory's name as "tools/", which sorts after "tools.sh", while "tools" sorts before it.

FIXTURE_FILES = {
    "README.md": (b"# Fixture\n", "100644"),
    "tools.sh": (b"echo tools\n", "100644"),
    "tools/lib/helper.py": (b"VALUE = 1\n", "100644"),
    "tools/run.sh": (b"#!/usr/bin/env bash\necho run\n", "100755"),
}
FIXTURE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
# The git tree id of FIXTURE_FILES, computed by git itself and not by tree_id: the four files were
# written with those bytes and modes into a new repository, staged with
# "git -c core.fileMode=true -c core.autocrlf=false add README.md tools.sh tools/lib/helper.py
# tools/run.sh", and "git write-tree" printed this id (git 2.53.0). The self-test requires
# tree_id to reproduce it, and the fixtures pin it as the source tree.
FIXTURE_TREE = "53a81efe18410b40be0aa429b190a155adca9e54"


def write_file(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def fixture_entries():
    """Return the entries list of the fixture's import, sorted by path."""
    return [
        {"blob": git_blob(data), "mode": mode, "path": path, "sha256": sha256_of(data)}
        for path, (data, mode) in sorted(FIXTURE_FILES.items())
    ]


def fixture_tree():
    """Return the git tree id of the fixture's import, computed by the gate's own helper.

    The self-test requires it to equal FIXTURE_TREE, which git computed.
    """
    return tree_id({entry["path"]: entry for entry in fixture_entries()})


def provenance_text(digest, tree=FIXTURE_TREE, commit=FIXTURE_COMMIT,
                    imported="4 (1 executable)"):
    """Return the fixture's PROVENANCE.md text, pinning digest."""
    return (
        "# Provenance\n\n"
        "- Source commit: %s (main, fixture)\n"
        "- Source `opf/` tree object: %s\n"
        "- Imported files: %s; no symlinks\n"
        "- Per-file inventory: `PROVENANCE-inventory.json` (path, git mode, blob id, SHA-256 of "
        "bytes), sha256 %s\n"
        "- Post-import changes: the deviations list.\n"
    ) % (commit, tree, imported, digest)


def _provenance(**fields):
    """Return a provenance builder for the fixture text with fields changed."""
    return lambda digest: provenance_text(digest, **fields).encode("utf-8")


def _provenance_lines(edit):
    """Return a provenance builder that passes the fixture's lines through edit."""
    def build(digest):
        lines = edit(provenance_text(digest).splitlines())
        return "".join(line + "\n" for line in lines).encode("utf-8")

    return build


def record_for(path, data, reason="Fixture change."):
    """Return a correct deviation record for path with the current bytes data."""
    return {
        "blob": git_blob(data),
        "path": path,
        "reason": reason,
        "sha256": sha256_of(data),
        "sha256_imported": sha256_of(FIXTURE_FILES[path][0]),
    }


def fixture(changes=None, records=None, inventory=None, raw=None, provenance=None, post=None):
    """Return a case builder for a fixture repository.

    changes maps a path to its current bytes (None removes it); records is the deviations list
    (the default is a correct record for each change, sorted by path); inventory edits the parsed
    inventory in place; raw replaces the inventory bytes; provenance maps the pinned digest to the
    PROVENANCE.md bytes (None leaves the file out); post edits the written tree.
    """
    changes = changes or {}

    def build(base):
        root = os.path.join(base, "repo")
        current = {path: data for path, (data, _mode) in FIXTURE_FILES.items()}
        current.update(changes)
        for path, data in sorted(current.items()):
            if data is None:
                continue
            os.makedirs(os.path.join(root, os.path.dirname(path)), exist_ok=True)
            write_file(os.path.join(root, path), data)
            executable = FIXTURE_FILES[path][1] == "100755"
            os.chmod(os.path.join(root, path), 0o755 if executable else 0o644)
        os.makedirs(root, exist_ok=True)
        entries = fixture_entries()
        if records is None:
            deviations = [record_for(path, data) for path, data in sorted(changes.items())
                          if data is not None]
        else:
            deviations = records
        parsed = {"deviations": deviations, "entries": entries, "files": len(entries),
                  "source_commit": FIXTURE_COMMIT, "source_opf_tree": FIXTURE_TREE}
        if inventory is not None:
            inventory(parsed)
        if raw is not None:
            data = raw
        else:
            data = json.dumps(parsed, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
        write_file(os.path.join(root, INVENTORY), data)
        text = (provenance_text(sha256_of(data)).encode("utf-8") if provenance is None
                else provenance(sha256_of(data)))
        if text is not None:
            write_file(os.path.join(root, PROVENANCE), text)
        if post is not None:
            result = post(root)
            if result is not None:
                return result
        return root

    return build


CHANGED = b"VALUE = 2\n"
CHANGED_RUN = b"#!/usr/bin/env bash\necho changed\n"


def _edit_record(field, value):
    """Return a records list with one correct record whose field is set to value (or removed)."""
    record = record_for("tools/lib/helper.py", CHANGED)
    if value is _REMOVE:
        del record[field]
    else:
        record[field] = value
    return [record]


_REMOVE = object()


def _symlink_file(path):
    """Replace path with a symlink to a copy of its own bytes outside the root."""
    def post(root):
        target = os.path.join(root, path)
        outside = root + "-symlink-target"
        with open(target, "rb") as handle:
            write_file(outside, handle.read())
        os.unlink(target)
        os.symlink(outside, target)

    return post


def _symlink_parent(root):
    """Make tools/lib a symlink to a copy of itself outside the root."""
    lib = os.path.join(root, "tools", "lib")
    outside = root + "-lib-outside"
    os.rename(lib, outside)
    os.symlink(outside, lib)


def _directory_in_place(root):
    os.unlink(os.path.join(root, "README.md"))
    os.mkdir(os.path.join(root, "README.md"))


def _swap_at_open(name, want_dir, swap, restore):
    """Return an opener that runs swap() just before opening name and restore() just after.

    It stands in for _open, so a fixture can change the tree between the lstat and the open, as a
    racing writer would. want_dir selects directory opens (O_DIRECTORY) or file opens.
    """
    def opener(path, flags, mode=0o777, *, dir_fd=None):
        hit = os.path.basename(path) == name and bool(flags & _DIRECTORY) == want_dir
        if hit:
            swap()
        try:
            return os.open(path, flags, mode, dir_fd=dir_fd)
        finally:
            if hit:
                restore()

    return opener


def _race(kind):
    """Replace README.md with a FIFO or a symlink to identical bytes between lstat and open."""
    def post(root):
        target = os.path.join(root, "README.md")
        aside = root + "-aside.md"
        outside = root + "-outside.md"
        write_file(outside, FIXTURE_FILES["README.md"][0])

        def swap():
            os.rename(target, aside)
            if kind == "fifo":
                os.mkfifo(target)
            else:
                os.symlink(outside, target)

        def restore():
            os.unlink(target)
            os.rename(aside, target)

        return root, _swap_at_open("README.md", False, swap, restore)

    return post


TAMPERED = b"VALUE = 9\n"


def _race_directory(at_directory_open):
    """Swap tools/lib for a symlink to a copy whose helper.py is tampered.

    With at_directory_open, the swap comes just before tools/lib is opened, so only O_NOFOLLOW on
    the directory open keeps the gate from reading the tampered copy. Otherwise it comes just
    before helper.py is opened, after the gate opened tools/lib, so the gate keeps reading the
    directory it opened and sees the imported bytes.
    """
    def post(root):
        lib = os.path.join(root, "tools", "lib")
        aside = root + "-lib-aside"
        tampered = root + "-lib-tampered"
        os.mkdir(tampered)
        write_file(os.path.join(tampered, "helper.py"), TAMPERED)

        def swap():
            os.rename(lib, aside)
            os.symlink(tampered, lib)

        def restore():
            os.unlink(lib)
            os.rename(aside, lib)

        if at_directory_open:
            return root, _swap_at_open("lib", True, swap, restore)
        return root, _swap_at_open("helper.py", False, swap, restore)

    return post


def _chmod(path, mode):
    def post(root):
        os.chmod(os.path.join(root, path), mode)

    return post


def _raise_eacces_on(name):
    def opener(path, flags, mode=0o777, *, dir_fd=None):
        if os.path.basename(path) == name:
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return os.open(path, flags, mode, dir_fd=dir_fd)

    return opener


def _with_opener(opener):
    def post(root):
        return root, opener

    return post


def _root_is_file(base):
    write_file(os.path.join(base, "not-a-directory"), b"x\n")
    return os.path.join(base, "not-a-directory")


def _drop(key):
    def edit(parsed):
        del parsed[key]

    return edit


def _entry_edit(field, value):
    def edit(parsed):
        parsed["entries"][0][field] = value

    return edit


def _duplicate_entry(parsed):
    parsed["entries"].append(dict(parsed["entries"][0]))


def _entry_blob_wrong(parsed):
    parsed["entries"][0]["blob"] = "0" * 40


def _two_pins(digest):
    text = provenance_text(digest)
    pin = next(line for line in text.splitlines() if line.startswith(PIN_PREFIX))
    return (text + pin + "\n").encode()


def _add_lines(*added):
    """Return a provenance builder that appends added lines to the fixture text."""
    return _provenance_lines(lambda lines: lines + list(added))


def _drop_lines(marker):
    """Return a provenance builder whose fixture text lacks every line holding marker."""
    return _provenance_lines(lambda lines: [line for line in lines if marker not in line])


def _drop_entry(path):
    def edit(parsed):
        parsed["entries"] = [entry for entry in parsed["entries"] if entry["path"] != path]

    return edit


def _entry_to(path, data):
    """Return an inventory edit that rewrites path's entry digests to data, as P2 does."""
    def edit(parsed):
        for entry in parsed["entries"]:
            if entry["path"] == path:
                entry["sha256"], entry["blob"] = sha256_of(data), git_blob(data)

    return edit


def _set(key, value):
    def edit(parsed):
        parsed[key] = value

    return edit


def _rewrite_entries_and_tree(parsed):
    """Rewrite README.md's entry to changed bytes and source_opf_tree to match the new entries."""
    _entry_to("README.md", b"changed\n")(parsed)
    parsed["source_opf_tree"] = tree_id({entry["path"]: entry for entry in parsed["entries"]})


INNER_ENTRY = {"blob": "1" * 40, "mode": "100644", "path": "README.md/inner", "sha256": "1" * 64}


def _file_and_directory(parsed):
    parsed["entries"].append(dict(INNER_ENTRY))


def _directory_and_file(parsed):
    parsed["entries"].insert(0, dict(INNER_ENTRY))


def _indent_line(marker):
    """Return a provenance builder whose one line holding marker is indented by two spaces."""
    return _provenance_lines(lambda lines: ["  " + line if marker in line else line
                                            for line in lines])


def _good_records_two():
    return [record_for("tools/lib/helper.py", CHANGED), record_for("tools/run.sh", CHANGED_RUN)]


def _cases():
    """Return the cases: label, builder, expected exit, and the needle: a text one output line
    must hold, a tuple of texts one output line must hold together, or a list of such needles
    of which one must match."""
    helper = {"tools/lib/helper.py": CHANGED}
    both = {"tools/lib/helper.py": CHANGED, "tools/run.sh": CHANGED_RUN}
    good = record_for("tools/lib/helper.py", CHANGED)
    stale = record_for("tools/lib/helper.py", b"VALUE = 3\n")
    stray = dict(good, path="tools/absent.py")
    imported = sha256_of(FIXTURE_FILES["tools/lib/helper.py"][0])
    tree = FIXTURE_TREE
    zero_tree = "0" * 40
    lower_pin = _provenance_lines(
        lambda lines: [line.replace(PIN_PREFIX, PIN_PREFIX.lower()) for line in lines])
    return [
        ("unchanged import, no records", fixture(), EXIT_PASS, "PASS (4 imported files checked, 0"),
        ("changed file with a matching record", fixture(helper), EXIT_PASS,
         "1 changed since the import and each recorded"),
        ("two changed files with sorted records", fixture(both), EXIT_PASS,
         "2 changed since the import and each recorded"),
        ("PROVENANCE.md with CRLF line ends", fixture(
            provenance=lambda digest: provenance_text(digest).replace("\n", "\r\n").encode()),
         EXIT_PASS, "PASS"),
        ("the entries hash to the pinned source tree", fixture(), EXIT_PASS,
         "the entries hash to the source tree %s;" % tree),
        ("entry dropped", fixture(inventory=_drop_entry("README.md")), EXIT_FAIL,
         ("FAIL: PROVENANCE-inventory.json: the git tree id of the entries is ",
          "but source_opf_tree is \"%s\" [entries-tree]" % tree)),
        ("entry digests rewritten to edited bytes", fixture(
            {"README.md": b"changed\n"}, records=[],
            inventory=_entry_to("README.md", b"changed\n")), EXIT_FAIL, "[entries-tree]"),
        ("source_opf_tree edited", fixture(inventory=_set("source_opf_tree", zero_tree)),
         EXIT_FAIL,
         "the git tree id of the entries is %s, but source_opf_tree is \"%s\" [entries-tree]"
         % (tree, zero_tree)),
        ("entries and source_opf_tree rewritten together", fixture(
            {"README.md": b"changed\n"}, records=[], inventory=_rewrite_entries_and_tree),
         EXIT_FAIL, ("FAIL: PROVENANCE.md: names the source tree object %s, but the git tree id "
                     "of the entries is " % tree, "[source-tree]")),
        ("PROVENANCE.md source tree line edited", fixture(provenance=_provenance(tree=zero_tree)),
         EXIT_FAIL, "names the source tree object %s, but the git tree id of the entries is %s "
         "[source-tree]" % (zero_tree, tree)),
        ("PROVENANCE.md without the source tree line", fixture(
            provenance=_drop_lines("tree object")), EXIT_FAIL,
         "PROVENANCE.md: has no line - Source `opf/` tree object: <40 hex> [source-tree]"),
        ("PROVENANCE.md with a second source tree line", fixture(
            provenance=_add_lines("  - Source `opf/` tree object: " + zero_tree)), EXIT_FAIL,
         "has 2 lines holding 'tree object' in any letter case; exactly one line - Source `opf/` "
         "tree object: <40 hex> is allowed [source-tree]"),
        ("PROVENANCE.md with a second source tree line in another letter case", fixture(
            provenance=_add_lines("- source `opf/` Tree Object: " + zero_tree)), EXIT_FAIL,
         "has 2 lines holding 'tree object' in any letter case; exactly one line - Source `opf/` "
         "tree object: <40 hex> is allowed [source-tree]"),
        ("an indented sole source tree line", fixture(provenance=_indent_line("tree object")),
         EXIT_FAIL, "its line '  - Source `opf/` tree object: %s' is not in the form - Source "
         "`opf/` tree object: <40 hex> [source-tree]" % tree),
        ("files count edited", fixture(inventory=_set("files", 1)), EXIT_FAIL,
         "FAIL: PROVENANCE-inventory.json: files is 1, but the entries list has 4 entries "
         "[file-count]"),
        ("files not an integer", fixture(inventory=_set("files", "4")), EXIT_FAIL,
         "files is \"4\", but the entries list has 4 entries [file-count]"),
        ("files is 4.0", fixture(inventory=_set("files", 4.0)), EXIT_FAIL,
         "files is 4.0, but the entries list has 4 entries [file-count]"),
        ("PROVENANCE.md Imported files count edited", fixture(
            provenance=_provenance(imported="7 (1 executable)")), EXIT_FAIL,
         "FAIL: PROVENANCE.md: says 7 imported files (1 executable), but the entries list has 4 "
         "(1 executable) [imported-count]"),
        ("PROVENANCE.md executable count edited", fixture(
            provenance=_provenance(imported="4 (0 executable)")), EXIT_FAIL,
         "says 4 imported files (0 executable), but the entries list has 4 (1 executable) "
         "[imported-count]"),
        ("PROVENANCE.md with a second Imported files line in lower case", fixture(
            provenance=_add_lines("- imported files: 7 (1 executable)")), EXIT_FAIL,
         "has 2 lines holding 'Imported files' in any letter case; exactly one line - Imported "
         "files: <N> (<E> executable) is allowed [imported-count]"),
        ("PROVENANCE.md Imported files line without counts", fixture(
            provenance=_provenance(imported="three")), EXIT_FAIL,
         ("its line '- Imported files: three; no symlinks' is not in the form",
          "[imported-count]")),
        ("PROVENANCE.md without the Imported files line", fixture(
            provenance=_drop_lines("Imported files")), EXIT_FAIL,
         "has no line - Imported files: <N> (<E> executable) [imported-count]"),
        ("inventory with an unknown top-level key", fixture(inventory=_set("note", "x")),
         EXIT_FAIL, "FAIL: PROVENANCE-inventory.json: has the top-level key note, which the format "
         "does not define [inventory-keys]"),
        ("inventory without source_commit", fixture(inventory=_drop("source_commit")), EXIT_FAIL,
         "PROVENANCE-inventory.json: lacks the top-level key source_commit [inventory-keys]"),
        ("inventory without source_opf_tree", fixture(inventory=_drop("source_opf_tree")),
         EXIT_FAIL,
         "PROVENANCE-inventory.json: lacks the top-level key source_opf_tree [inventory-keys]"),
        ("inventory source_commit edited", fixture(inventory=_set("source_commit", "1" * 40)),
         EXIT_FAIL, "FAIL: PROVENANCE.md: names the source commit %s, but the inventory's "
         "source_commit is \"%s\" [source-commit]" % (FIXTURE_COMMIT, "1" * 40)),
        ("PROVENANCE.md source commit line edited", fixture(provenance=_provenance(
            commit="2" * 40)), EXIT_FAIL,
         "names the source commit %s, but the inventory's source_commit is \"%s\" "
         "[source-commit]" % ("2" * 40, FIXTURE_COMMIT)),
        ("PROVENANCE.md without the source commit line", fixture(
            provenance=_drop_lines("Source commit")), EXIT_FAIL,
         "has no line - Source commit: <40 hex> [source-commit]"),
        ("PROVENANCE.md with a second source commit line in lower case", fixture(
            provenance=_add_lines("- source commit: " + "0" * 40)), EXIT_FAIL,
         "has 2 lines holding 'Source commit' in any letter case; exactly one line - Source "
         "commit: <40 hex> is allowed [source-commit]"),
        ("executable imported file loses its executable bit", fixture(
            post=_chmod("tools/run.sh", 0o644)), EXIT_FAIL,
         "FAIL: tools/run.sh: its executable bit is clear, but its entry's mode is 100755 "
         "[mode-changed]"),
        ("non-executable imported file gains an executable bit", fixture(
            post=_chmod("README.md", 0o744)), EXIT_FAIL,
         "FAIL: README.md: its executable bit is set, but its entry's mode is 100644 "
         "[mode-changed]"),
        ("changed file with no record", fixture(helper, records=[]), EXIT_FAIL,
         "FAIL: tools/lib/helper.py: changed since the import (sha256 %s, imported %s) with no "
         "deviation record [unrecorded-change]" % (sha256_of(CHANGED), imported)),
        ("record from an earlier edit of the file", fixture(helper, records=[stale]), EXIT_FAIL,
         "deviation tools/lib/helper.py: sha256 %s does not match the file's sha256 %s "
         "[stale-sha256]" % (sha256_of(b"VALUE = 3\n"), sha256_of(CHANGED))),
        ("record whose blob does not match", fixture(helper, records=_edit_record(
            "blob", git_blob(b"other\n"))), EXIT_FAIL, "[stale-blob]"),
        ("record whose sha256_imported does not match the entry", fixture(
            helper, records=_edit_record("sha256_imported", sha256_of(b"other\n"))), EXIT_FAIL,
         "[wrong-imported-sha256]"),
        ("record for a file equal to its imported bytes", fixture(records=[good]), EXIT_FAIL,
         "deviation tools/lib/helper.py: names a file whose bytes equal its imported sha256 %s; "
         "drop the record [unchanged-file]" % imported),
        ("record for a path that is not an entry", fixture(helper, records=[good, stray]),
         EXIT_FAIL,
         "deviation tools/absent.py: names a path that is not an imported entry [not-an-entry]"),
        ("records out of path order", fixture(both, records=list(reversed(_good_records_two()))),
         EXIT_FAIL, "[unsorted]"),
        ("two records for one path", fixture(helper, records=[good, dict(good)]), EXIT_FAIL,
         "[duplicate-record]"),
        ("record without path", fixture(helper, records=_edit_record("path", _REMOVE)), EXIT_FAIL,
         "deviations[0]: lacks the field path [missing-field]"),
        ("record without reason", fixture(helper, records=_edit_record("reason", _REMOVE)),
         EXIT_FAIL, "lacks the field reason [missing-field]"),
        ("record without blob", fixture(helper, records=_edit_record("blob", _REMOVE)), EXIT_FAIL,
         "lacks the field blob [missing-field]"),
        ("record without sha256", fixture(helper, records=_edit_record("sha256", _REMOVE)),
         EXIT_FAIL, "lacks the field sha256 [missing-field]"),
        ("record without sha256_imported", fixture(
            helper, records=_edit_record("sha256_imported", _REMOVE)), EXIT_FAIL,
         "lacks the field sha256_imported [missing-field]"),
        ("record with an undefined field", fixture(helper, records=_edit_record("mode", "100644")),
         EXIT_FAIL, "has the field mode, which the format does not define [unexpected-field]"),
        ("record with an upper-case sha256", fixture(helper, records=_edit_record(
            "sha256", sha256_of(CHANGED).upper())), EXIT_FAIL,
         "sha256 is not 64 lowercase hex [bad-field]"),
        ("record with an empty reason", fixture(helper, records=_edit_record("reason", " ")),
         EXIT_FAIL, "reason is not a nonempty string [bad-field]"),
        ("record that is not an object", fixture(helper, records=["tools/lib/helper.py"]),
         EXIT_FAIL, "deviations[0]: is not an object [bad-field]"),
        ("imported file missing", fixture({"README.md": None}), EXIT_FAIL,
         "README.md: imported file is missing [missing-file]"),
        ("imported file's directory missing", fixture(
            post=lambda root: os.rename(os.path.join(root, "tools", "lib"),
                                        os.path.join(root, "tools", "moved"))), EXIT_FAIL,
         "tools/lib is missing or not a directory [missing-file]"),
        ("imported file a symlink to identical bytes", fixture(post=_symlink_file("README.md")),
         EXIT_FAIL,
         "README.md: imported file: README.md is a symlink; it is not followed [not-regular]"),
        ("imported file's directory a symlink", fixture(post=_symlink_parent), EXIT_FAIL,
         "tools/lib is a symlink; it is not followed [not-regular]"),
        ("imported file a directory", fixture(post=_directory_in_place), EXIT_FAIL,
         "README.md is not a regular file [not-regular]"),
        ("symlink swapped in before the open", fixture(post=_race("symlink")), EXIT_FAIL,
         "README.md is a symlink; it is not followed [not-regular]"),
        ("FIFO swapped in before the open", fixture(post=_race("fifo")), EXIT_FAIL,
         "README.md is not a regular file [not-regular]"),
        # Linux refuses O_DIRECTORY|O_NOFOLLOW on a symlink with ENOTDIR ("replaced"); a platform
        # that returns ELOOP reports "symlink". Either message fails the swapped directory.
        ("directory symlink swapped in before the open", fixture(post=_race_directory(True)),
         EXIT_FAIL,
         ["FAIL: tools/lib/helper.py: imported file: tools/lib was replaced while being checked "
          "[not-regular]",
          "FAIL: tools/lib/helper.py: imported file: tools/lib is a symlink; it is not followed "
          "[not-regular]"]),
        ("parent swapped after it was opened", fixture(post=_race_directory(False)), EXIT_PASS,
         "PASS (4 imported files checked, 0 changed"),
        ("unchanged file whose entry blob is wrong", fixture(inventory=_entry_blob_wrong),
         EXIT_FAIL, "[entry-blob]"),
        ("PROVENANCE.md pins an earlier inventory", fixture(
            provenance=lambda digest: provenance_text("0" * 64).encode()), EXIT_FAIL,
         ("FAIL: PROVENANCE.md: pins the inventory sha256 %s, but the inventory's sha256 is "
          % ("0" * 64), "[pin-stale]")),
        ("PROVENANCE.md without the inventory line", fixture(
            provenance=_drop_lines("Per-file inventory")), EXIT_FAIL,
         ("FAIL: PROVENANCE.md: has no line starting " + PIN_PREFIX, "[pin-missing]")),
        ("PROVENANCE.md with a second pin line in another form", fixture(
            provenance=_add_lines("- Per-file inventory: PROVENANCE-inventory.json sha256 "
                                  + "0" * 64)), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md with a second pin line in lower case", fixture(
            provenance=_add_lines("- per-file inventory: provenance-inventory.json sha256 "
                                  + "0" * 64)), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md with a second pin line in upper case", fixture(
            provenance=_add_lines("- PER-FILE INVENTORY: PROVENANCE-INVENTORY.JSON SHA256 "
                                  + "0" * 64)), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md with a second pin prefix line in lower case and no digest", fixture(
            provenance=_add_lines(PIN_PREFIX.lower())), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md with an indented copy of the pin line", fixture(
            provenance=lambda digest: (provenance_text(digest) + "  " + PIN_PREFIX
                                       + " sha256 " + "1" * 64 + "\n").encode()), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md whose one pin line is in another form", fixture(
            provenance=_provenance_lines(lambda lines: [
                "  " + line if line.startswith(PIN_PREFIX) else line for line in lines])),
         EXIT_FAIL, ("its inventory pin line '  " + PIN_PREFIX, "does not start with",
                     "[pin-missing]")),
        ("PROVENANCE.md whose one pin line is in lower case", fixture(provenance=lower_pin),
         EXIT_FAIL, ("does not start with", "[pin-missing]")),
        ("a lower-case sole pin line holds a stray digest", fixture(provenance=lower_pin),
         EXIT_FAIL, ("line 6 '" + PIN_PREFIX.lower(), "[stray-digest]")),
        # X1 to X4 of the round 3 review: a second line that differs from a canonical line only in
        # an invisible or look-alike character, which no marker finds.
        ("a second source commit line with a no-break space", fixture(
            provenance=_add_lines("- Source\u00a0commit: " + zero_tree)), EXIT_FAIL,
         "line 8 '- Source\\xa0commit: %s' holds a run of 40 or 64 hex digits that is not the "
         "value of the Source commit, source tree or pin line in its exact form [stray-digest]"
         % zero_tree),
        ("a second source tree line with a zero-width space", fixture(
            provenance=_add_lines("- Source `opf/` tree\u200b object: " + zero_tree)), EXIT_FAIL,
         ("line 8 '- Source `opf/` tree\\u200b object: %s' holds a run of 40 or 64 hex digits"
          % zero_tree, "[stray-digest]")),
        ("a second Imported files line with two spaces", fixture(
            provenance=_add_lines("- Imported  files: 7 (1 executable)")), EXIT_FAIL,
         "line 8 '- Imported  files: 7 (1 executable)' holds a count pair that is not the counts "
         "of the Imported files line in its exact form [stray-count]"),
        ("a second pin line with a no-break space and a non-breaking hyphen", fixture(
            provenance=_add_lines("- Per-file\u00a0inventory: PROVENANCE\u2011inventory.json "
                                  "sha256 " + "0" * 64)), EXIT_FAIL,
         ("line 8 '- Per-file\\xa0inventory: PROVENANCE\\u2011inventory.json sha256 " + "0" * 64,
          "[stray-digest]")),
        ("a source commit line that holds a second 40 hex value", fixture(
            provenance=_provenance(commit=FIXTURE_COMMIT + " " + zero_tree)), EXIT_FAIL,
         ("line 3 '- Source commit: %s %s" % (FIXTURE_COMMIT, zero_tree), "[stray-digest]")),
        # MINOR 1 of the round 4 review: the value rule's letter case, Unicode digits and spaces,
        # own-value allowance for counts and exact 40 or 64 boundary.
        ("a second source commit line with an upper-case value", fixture(
            provenance=_add_lines("- Source commit: " + "ABCDEF0123" * 4)), EXIT_FAIL,
         ("line 8 '- Source commit: %s'" % ("ABCDEF0123" * 4), "[stray-digest]")),
        ("a second Imported files line with full-width digits", fixture(
            provenance=_add_lines("- Imported files: \uff17 (\uff11 executable)")), EXIT_FAIL,
         ("line 8 '- Imported files: \\uff17 (\\uff11 executable)'", "[stray-count]")),
        ("a second Imported files line with no-break spaces", fixture(
            provenance=_add_lines("- Imported files: 7\u00a0(\u00a01 executable)")), EXIT_FAIL,
         ("line 8 '- Imported files: 7\\xa0(\\xa01 executable)'", "[stray-count]")),
        ("an Imported files line with a second count pair", fixture(
            provenance=_provenance(imported="4 (1 executable); 7 (1 executable)")), EXIT_FAIL,
         ("line 5 '- Imported files: 4 (1 executable); 7 (1 executable); no symlinks'",
          "[stray-count]")),
        ("runs of 41 and 65 hex digits are not values", fixture(
            provenance=_add_lines("- Note: " + "0" * 41, "- Note: " + "0" * 65)), EXIT_PASS,
         "PASS (4 imported files checked, 0"),
        # MINOR 4 of the round 4 review: a count pair is found in linear time, so a long run of
        # digits finishes well within CASE_SECONDS.
        ("a PROVENANCE.md line of 60000 digits", fixture(provenance=_add_lines("7" * 60000)),
         EXIT_PASS, "PASS (4 imported files checked, 0"),
        ("PROVENANCE.md inventory line without a digest", fixture(
            provenance=lambda digest: (PIN_PREFIX + " (path)\n").encode()), EXIT_FAIL,
         ("its inventory line does not end with sha256 and a digest; it must pin ",
          "[pin-missing]")),
        ("PROVENANCE.md missing", fixture(provenance=lambda digest: None), EXIT_FAIL,
         ("FAIL: PROVENANCE.md: missing; it must pin the inventory sha256 ", "[pin-missing]")),
        ("PROVENANCE.md with two inventory lines", fixture(provenance=_two_pins), EXIT_FAIL,
         "has 2 inventory pin lines; exactly one is allowed [pin-duplicate]"),
        ("PROVENANCE.md a symlink", fixture(post=_symlink_file(PROVENANCE)), EXIT_FAIL,
         "FAIL: PROVENANCE.md: PROVENANCE.md is a symlink; it is not followed [not-regular]"),
        ("every problem is named", fixture(
            {"README.md": b"changed\n", "tools/lib/helper.py": CHANGED}, records=[stray],
            provenance=_drop_lines("Per-file inventory"), post=_chmod("tools/run.sh", 0o644),
            inventory=_set("files", 5)), EXIT_FAIL, "FAIL (6 findings)"),
        ("inventory missing", fixture(post=lambda root: os.unlink(os.path.join(root, INVENTORY))),
         EXIT_CANNOT, "PROVENANCE-inventory.json: missing"),
        ("inventory a symlink to identical bytes", fixture(post=_symlink_file(INVENTORY)),
         EXIT_CANNOT, "PROVENANCE-inventory.json is a symlink"),
        ("inventory not JSON", fixture(raw=b"{\"entries\": [\n"), EXIT_CANNOT,
         "is not valid JSON"),
        ("inventory not UTF-8", fixture(raw=b"{\"entries\": [], \"deviations\": [\xff]}"),
         EXIT_CANNOT, "is not UTF-8"),
        ("inventory with a duplicate key", fixture(
            raw=b"{\"entries\": [], \"deviations\": [], \"entries\": []}"), EXIT_CANNOT,
         "duplicate key 'entries'"),
        ("inventory with NaN", fixture(raw=b"{\"entries\": [], \"deviations\": [], \"x\": NaN}"),
         EXIT_CANNOT, "the constant NaN is not JSON"),
        ("inventory a list", fixture(raw=b"[]"), EXIT_CANNOT, "the top level is not an object"),
        ("inventory without entries", fixture(inventory=_drop("entries")), EXIT_CANNOT,
         "has no entries list"),
        ("inventory without deviations", fixture(inventory=_drop("deviations")), EXIT_CANNOT,
         "has no deviations list"),
        ("inventory whose entries is an object", fixture(
            inventory=_set("entries", {"README.md": {}})), EXIT_CANNOT,
         "PROVENANCE-inventory.json: has no entries list"),
        ("inventory whose deviations is a string", fixture(
            inventory=_set("deviations", "tools/lib/helper.py")), EXIT_CANNOT,
         "PROVENANCE-inventory.json: has no deviations list"),
        ("inventory whose deviations is null", fixture(inventory=_set("deviations", None)),
         EXIT_CANNOT, "PROVENANCE-inventory.json: has no deviations list"),
        ("entry with an upper-case blob", fixture(
            inventory=lambda parsed: parsed["entries"][0].update(
                blob=parsed["entries"][0]["blob"].upper())), EXIT_CANNOT,
         "PROVENANCE-inventory.json: entries[0] blob is not 40 lowercase hex"),
        ("entries naming a path as a file and a directory", fixture(
            inventory=_file_and_directory), EXIT_CANNOT,
         "PROVENANCE-inventory.json: the entries name README.md as both a file and a directory"),
        ("entries naming a directory before the same path as a file", fixture(
            inventory=_directory_and_file), EXIT_CANNOT,
         "PROVENANCE-inventory.json: the entries name README.md as both a file and a directory"),
        ("entry without sha256", fixture(inventory=lambda parsed: parsed["entries"][0].pop(
            "sha256")), EXIT_CANNOT, "entries[0] is not an object with exactly the fields"),
        ("entry with an unsafe path", fixture(inventory=_entry_edit("path", "../outside.md")),
         EXIT_CANNOT, "entries[0] path is not a normalized relative path"),
        ("entry with an absolute path", fixture(inventory=_entry_edit("path", "/etc/hostname")),
         EXIT_CANNOT, "entries[0] path is not a relative POSIX path"),
        ("entry with an unknown mode", fixture(inventory=_entry_edit("mode", "120000")),
         EXIT_CANNOT, "entries[0] mode is not one of"),
        ("entry with a short sha256", fixture(inventory=_entry_edit("sha256", "abc")),
         EXIT_CANNOT, "entries[0] sha256 is not 64 lowercase hex"),
        ("two entries for one path", fixture(inventory=_duplicate_entry), EXIT_CANNOT,
         "repeats the path README.md"),
        ("PROVENANCE.md not UTF-8", fixture(provenance=lambda digest: b"\xff\n"), EXIT_CANNOT,
         "PROVENANCE.md: is not UTF-8"),
        ("read error on an imported file", fixture(
            post=_with_opener(_raise_eacces_on("helper.py"))), EXIT_CANNOT,
         "tools/lib/helper.py: cannot read: Permission denied"),
        ("read error on the inventory", fixture(post=_with_opener(_raise_eacces_on(INVENTORY))),
         EXIT_CANNOT, "PROVENANCE-inventory.json: cannot read: Permission denied"),
        ("root a regular file", _root_is_file, EXIT_CANNOT,
         "the root cannot be opened as a directory"),
        ("root absent", lambda base: os.path.join(base, "absent"), EXIT_CANNOT,
         "the root cannot be opened as a directory"),
    ]


def with_deadline(seconds, func):
    """Run func, raising TimeoutError if it has not returned within seconds."""
    main_thread = threading.current_thread() is threading.main_thread()
    if not hasattr(signal, "setitimer") or not main_thread:
        return func()

    def expired(signum, frame):
        raise TimeoutError("did not finish within %d seconds" % seconds)

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return func()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main_with_failing_check(root):
    """Run main() while check() raises, and return (exit, output)."""
    global check
    saved = check

    def broken(path):
        raise RuntimeError("injected failure")

    check = broken
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["--root", root])
    finally:
        check = saved
    return code, out.getvalue()


def _symlinked_tools(base):
    """Build a fixture repository whose tools/ directory is reached through a symlink elsewhere."""
    root = fixture()(base)
    with open(os.path.realpath(__file__), "rb") as handle:
        write_file(os.path.join(root, "tools", TOOL + ".py"), handle.read())
    os.mkdir(os.path.join(base, "elsewhere"))
    link = os.path.join(base, "elsewhere", "tools")
    os.symlink(os.path.join(root, "tools"), link)
    return os.path.join(link, TOOL + ".py")


def self_test():
    """Run the self-test and return its exit status: 0 pass, 1 a failed case, 2 cannot evaluate.

    An unexpected error is reported as main() reports one and returns 2, so the entry block can
    exit with this value directly.
    """
    try:
        return run_self_test()
    except Exception as exc:
        print("%s: CANNOT EVALUATE (unexpected error: %s: %s)" % (GATE, type(exc).__name__, exc),
              file=sys.stderr)
        return EXIT_CANNOT


def run_self_test():
    """Build fixtures in a temporary directory; check every pass, fail and cannot-evaluate path."""
    global _open
    failures = 0
    total = 0
    red_kinds = set()

    def report(ok, label, detail):
        nonlocal failures, total
        total += 1
        if not ok:
            failures += 1
        print("%s %s: %s" % ("PASS" if ok else "FAIL", label, detail))

    def alternatives(needle):
        """Return the needle as a list of tuples: one tuple of texts per alternative."""
        options = needle if isinstance(needle, list) else [needle]
        return [option if isinstance(option, tuple) else (option,) for option in options]

    def outcome(expected, got, needle, text):
        detail = "expected exit %d, got %d" % (expected, got)
        found = needle is None or any(all(item in line for item in option)
                                      for option in alternatives(needle)
                                      for line in text.splitlines())
        if not found:
            detail += "; no line contains %r" % (needle,)
        return got == expected and found, detail

    try:
        with tempfile.TemporaryDirectory(prefix="provenance-deviations-") as tmp:
            for index, (label, build, expected, needle) in enumerate(_cases()):
                base = os.path.join(tmp, "case%02d" % index)
                os.mkdir(base)
                built = build(base)
                root, opener = built if isinstance(built, tuple) else (built, None)
                if opener is not None:
                    _open = opener
                try:
                    code, lines = with_deadline(CASE_SECONDS, lambda: check(root))
                except Exception as exc:
                    report(False, label, "raised %s: %s" % (type(exc).__name__, exc))
                    continue
                finally:
                    _open = os.open
                text = "\n".join(lines)
                ok, detail = outcome(expected, code, needle, text)
                if ok and expected == EXIT_FAIL:
                    options = alternatives(needle)
                    # A kind counts as red only when every alternative names it.
                    red_kinds.update(kind for kind in FINDING_KINDS
                                     if all(any(item.endswith("[" + kind + "]") for item in option)
                                            for option in options))
                report(ok, label, detail)

            unred = [kind for kind in FINDING_KINDS if kind not in red_kinds]
            report(not unred, "every finding kind is red, with exit 1, in at least one case",
                   "kinds not shown red: " + (", ".join(unred) or "none"))

            got = fixture_tree()
            report(got == FIXTURE_TREE, "tree_id reproduces the fixture tree id git computed",
                   "expected %s, got %s" % (FIXTURE_TREE, got))

            for version, expected in (((3, 13, 9), 2), ((3, 14, 0), 0), ((3, 15, 1), 0)):
                got = python_gate(version)
                report(got == expected, "Python %d.%d.%d gate" % version,
                       "expected exit %d, got %d" % (expected, got))

            base = os.path.join(tmp, "unexpected")
            os.mkdir(base)
            try:
                got, text = main_with_failing_check(base)
                ok, detail = outcome(EXIT_CANNOT, got, "unexpected error", text)
            except Exception as exc:
                ok, detail = False, "raised %s: %s" % (type(exc).__name__, exc)
            report(ok, "unexpected error exits 2", detail)

            # The entry check refuses '..' first; this calls the reader directly to show that the
            # component-wise resolver refuses it too.
            base = os.path.join(tmp, "unsafe-component")
            os.mkdir(base)
            root = fixture()(base)
            root_fd = os.open(root, ROOT_FLAGS)
            try:
                kind, where, _data, _mode = read_entry(root_fd, "tools/../../escape.md")
                ok, detail = False, "read %s at %s" % (kind, where)
            except CannotEvaluate as exc:
                ok, detail = "unsafe path component" in str(exc), str(exc)
            finally:
                os.close(root_fd)
            report(ok, "resolver refuses an unsafe path component", detail)

            # Run the tool as a separate process to cover argument handling and the exit status.
            tool = os.path.realpath(__file__)
            cli_cases = [
                ("command line, clean fixture", fixture(), [], EXIT_PASS, GATE + ": PASS"),
                ("command line, stale record", fixture(
                    {"tools/lib/helper.py": CHANGED},
                    records=[record_for("tools/lib/helper.py", b"VALUE = 3\n")]), [], EXIT_FAIL,
                 GATE + ": FAIL"),
                ("command line, root a regular file", _root_is_file, [], EXIT_CANNOT,
                 "CANNOT EVALUATE"),
                ("command line, unknown option", fixture(), ["--unknown"], EXIT_CANNOT,
                 "unrecognized arguments"),
                ("command line, --self-test with --root", fixture(), ["--self-test"], EXIT_CANNOT,
                 "--self-test does not take --root"),
            ]
            for index, (label, build, extra, expected, needle) in enumerate(cli_cases):
                base = os.path.join(tmp, "cli%02d" % index)
                os.mkdir(base)
                root = build(base)
                proc = subprocess.run(
                    [sys.executable, "-I", "-B", tool, "--root", root] + extra,
                    stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
                text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode(
                    "utf-8", "replace")
                ok, detail = outcome(expected, proc.returncode, needle, text)
                report(ok, label, detail)

            base = os.path.join(tmp, "cli-symlinked-tools")
            os.mkdir(base)
            linked_tool = _symlinked_tools(base)
            proc = subprocess.run([sys.executable, "-I", "-B", linked_tool],
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
            text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            ok, detail = outcome(EXIT_PASS, proc.returncode, GATE + ": PASS", text)
            report(ok, "command line, default root through a symlinked tools directory", detail)
    except (OSError, subprocess.SubprocessError, CannotEvaluate) as exc:
        print("%s self-test: CANNOT EVALUATE (%s)" % (GATE, exc))
        return EXIT_CANNOT

    if failures:
        print("%s self-test: FAIL (%d of %d cases failed)" % (GATE, failures, total))
        return EXIT_FAIL
    print("%s self-test: PASS (%d of %d cases)" % (GATE, total, total))
    return EXIT_PASS


def default_root():
    """Return the parent of this tool's directory, resolved with os.path.realpath."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Check the deviation records of " + INVENTORY + " against the files.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (default: the parent of this tool's directory)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="build fixtures in a temporary directory and check every exit path",
    )
    args = parser.parse_args(argv)
    if args.self_test and args.root is not None:
        parser.error("--self-test does not take --root")
    try:
        if args.self_test:
            return self_test()
        code, lines = check(args.root if args.root is not None else default_root())
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
