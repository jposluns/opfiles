"""Check the handover addendum record PROVENANCE-addendum.json against its SHA256SUMS and the files.

Usage:
  python3 tools/check_provenance_addendum.py [--root PATH]
  python3 tools/check_provenance_addendum.py --self-test

PROVENANCE-addendum.json records the files the source guardrails repository handed over after the
import (PROVENANCE.md, "Handover addendum"). It is an object with exactly the keys files,
source_commit, source_commit_note and source_repository. source_commit is the source commit as the
handover names it (7 to 40 lowercase hex digits) and source_commit_note says how complete that id
is. Each record of "files" names one handed-over file by its source path and the SHA-256 the
handover lists for it (source_sha256), and its disposition: landed (byte for byte), landed-adapted
or already-present, each with the path where it is in this repository (landed_path) and the SHA-256
of the bytes there (landed_sha256); or declined, with the reason (decline_reason). A record holds
exactly those fields for its disposition. PROVENANCE-addendum.SHA256SUMS, committed beside it, is
the handover's SHA256SUMS byte for byte: one "<64 hex>  <path>" line per handed-over file.

The gate requires the records to be sorted by source path with no path twice, each record's
source_sha256 to equal the SHA256SUMS line for its source path, every SHA256SUMS line to have a
record, and each landed_sha256 to equal the SHA-256 of the regular file at its landed_path. So a
landed file changed after it landed fails the gate until its record is updated with the change.
Each disposition's own claim is held as well: a landed record's landed_sha256 must equal its
source_sha256 (byte for byte), and an already-present record's landed_sha256 must equal the sha256
of the PROVENANCE-inventory.json entry for its landed_path (the bytes the import brought, which the
handed-over file equals once adapted). PROVENANCE-inventory.json is read only when a record is
already-present.

Residual: the gate cannot see the source repository or the handover itself. An edit that rewrites
a SHA256SUMS line and the matching source_sha256 together passes, as does one that rewrites a
landed-adapted file and its landed_sha256 together. The same edit to a landed file fails
[landed-not-identical] unless its source_sha256 and SHA256SUMS line are rewritten too, and to an
already-present file fails [present-not-imported] unless its inventory entry is rewritten too, which
changes the inventory SHA-256 that PROVENANCE.md pins (tools/check_provenance_deviations.py). Treat
any change to these files as a change to the provenance record and review it against the handover.
PROVENANCE.md cannot pin these files' digests, because its value rule
(tools/check_provenance_deviations.py) refuses every 40 or 64 hex run outside its import lines.

Every path is resolved beneath the root's directory descriptor one component at a time, so no
symlink is followed at any level; each file is opened with O_NOFOLLOW and O_NONBLOCK, and fstat
confirms a regular file before any byte is read. The JSON reader refuses a duplicate key and the
constants NaN and Infinity.

Exit status:
  0  every record has the right form, is sorted and matches SHA256SUMS and its landed file, and
     every SHA256SUMS line has a record;
  1  a finding, each named on its own line with its kind in brackets: a top-level key is missing
     or not defined [keys]; source_commit has the wrong form, or source_commit_note or
     source_repository is not a nonempty string [bad-commit]; a record is not an object, lacks a
     field or has one its disposition does not define, or has a field of the wrong form
     [bad-record]; the records are not sorted by source path [unsorted] or name one twice
     [duplicate-record]; a record's source path has no SHA256SUMS line [not-in-sums]; a SHA256SUMS
     line has no record [unrecorded-sum]; a source_sha256 differs from its SHA256SUMS line
     [sums-mismatch]; a landed file is missing [landed-missing], is a symlink, not a regular file or
     was replaced while being read [not-regular], or its SHA-256 differs from landed_sha256
     [landed-mismatch]; a landed record's landed_sha256 differs from its source_sha256
     [landed-not-identical]; an already-present record's landed_path has no
     PROVENANCE-inventory.json entry, or its landed_sha256 differs from that entry's sha256
     [present-not-imported];
  2  the check cannot be evaluated: the root cannot be opened as a directory; either file, or
     PROVENANCE-inventory.json where a record is already-present, is missing, a symlink or not a
     regular file; the record or the inventory is not UTF-8, not valid JSON (a duplicate key, NaN
     or Infinity included) or not an object; the record has no files list; the inventory has no
     entries list, an entry that is not an object with a nonempty string path and a 64 lowercase
     hex sha256, or names a path twice; a SHA256SUMS line is not "<64 lowercase hex>  <normalized
     relative path>", the file does not end with a newline or names a path twice; a file cannot be
     read for a reason other than absence; an unexpected error occurs; the command line is
     invalid; or Python is older than 3.14.

The default root is the parent of this tool's directory, resolved with os.path.realpath. Only the
standard library is used.
"""

import sys

MIN_PYTHON = (3, 14)
TOOL = "check_provenance_addendum"
GATE = "provenance-addendum"


def python_gate(version):
    """Return 2 when the given version is older than the floor, else 0."""
    return 2 if tuple(version[:2]) < MIN_PYTHON else 0


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
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

RECORD = "PROVENANCE-addendum.json"
SUMS = "PROVENANCE-addendum.SHA256SUMS"
INVENTORY = "PROVENANCE-inventory.json"
TOP_KEYS = ("files", "source_commit", "source_commit_note", "source_repository")
LANDED_FIELDS = ("disposition", "landed_path", "landed_sha256", "source_path", "source_sha256")
DECLINED_FIELDS = ("decline_reason", "disposition", "source_path", "source_sha256")
DISPOSITIONS = {
    "landed": LANDED_FIELDS,
    "landed-adapted": LANDED_FIELDS,
    "already-present": LANDED_FIELDS,
    "declined": DECLINED_FIELDS,
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")
SUMS_LINE = re.compile(r"([0-9a-f]{64})  (.+)")
FINDING_KINDS = (
    "keys",
    "bad-commit",
    "bad-record",
    "unsorted",
    "duplicate-record",
    "not-in-sums",
    "unrecorded-sum",
    "sums-mismatch",
    "landed-missing",
    "not-regular",
    "landed-mismatch",
    "landed-not-identical",
    "present-not-imported",
)
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CANNOT = 2
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
ROOT_FLAGS = os.O_RDONLY | _DIRECTORY | _CLOEXEC
DIR_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
READ_FLAGS = os.O_RDONLY | _NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _CLOEXEC


class CannotEvaluate(Exception):
    """Raised when the check cannot reach a verdict."""


def error_text(exc):
    return str(exc.strerror or exc)


def path_problem(rel):
    """Return why rel is not a normalized relative POSIX path, or None when it is one."""
    if not isinstance(rel, str) or rel == "":
        return "is not a nonempty string"
    if rel.startswith("/") or "\\" in rel or "\0" in rel or "\r" in rel or "\n" in rel:
        return "is not a relative POSIX path"
    parts = rel.split("/")
    if ".." in parts or "" in parts or "." in parts or posixpath.normpath(rel) != rel:
        return "is not a normalized relative path"
    return None


def read_regular(root_fd, rel):
    """Read rel beneath root_fd without following any symlink; return (kind, data).

    kind is "file" with the bytes, or "missing", "symlink", "replaced" or "other" with None.
    """
    parts = rel.split("/")
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                mode = os.lstat(part, dir_fd=fd).st_mode
            except (FileNotFoundError, NotADirectoryError):
                return "missing", None
            except OSError as exc:
                raise CannotEvaluate(rel + ": cannot inspect: " + error_text(exc)) from exc
            if stat.S_ISLNK(mode):
                return "symlink", None
            if not stat.S_ISDIR(mode):
                return "missing", None
            try:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    return "symlink", None
                if exc.errno in (errno.ENOTDIR, errno.ENOENT):
                    return "replaced", None
                raise CannotEvaluate(rel + ": cannot open: " + error_text(exc)) from exc
            os.close(fd)
            fd = child
        try:
            mode = os.lstat(parts[-1], dir_fd=fd).st_mode
        except (FileNotFoundError, NotADirectoryError):
            return "missing", None
        except OSError as exc:
            raise CannotEvaluate(rel + ": cannot inspect: " + error_text(exc)) from exc
        if stat.S_ISLNK(mode):
            return "symlink", None
        if not stat.S_ISREG(mode):
            return "other", None
        try:
            file_fd = os.open(parts[-1], READ_FLAGS, dir_fd=fd)
        except FileNotFoundError:
            return "replaced", None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return "symlink", None
            raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            return "replaced", None
        chunks = []
        while True:
            chunk = os.read(file_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return "file", b"".join(chunks)
    except OSError as exc:
        raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(file_fd)


def read_required(root_fd, rel):
    """Return the bytes of a file the check cannot do without, or raise CannotEvaluate."""
    kind, data = read_regular(root_fd, rel)
    if kind != "file":
        raise CannotEvaluate(rel + ": " + {"missing": "is missing", "symlink": "is a symlink",
                                           "replaced": "was replaced while being read"}.get(
                                               kind, "is not a regular file"))
    return data


def _refuse_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key " + repr(key))
        seen[key] = value
    return seen


def _refuse_constant(name):
    raise ValueError("the constant " + name + " is not JSON")


def load_json_object(root_fd, rel):
    """Return the JSON object in rel, read strictly, or raise CannotEvaluate."""
    data = read_required(root_fd, rel)
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_refuse_duplicates,
                            parse_constant=_refuse_constant)
    except UnicodeDecodeError as exc:
        raise CannotEvaluate(rel + ": is not UTF-8: " + str(exc)) from exc
    except ValueError as exc:
        raise CannotEvaluate(rel + ": is not valid JSON: " + str(exc)) from exc
    if not isinstance(parsed, dict):
        raise CannotEvaluate(rel + ": the top level is not an object")
    return parsed


def load_record(root_fd):
    parsed = load_json_object(root_fd, RECORD)
    if not isinstance(parsed.get("files"), list):
        raise CannotEvaluate(RECORD + ": has no files list")
    return parsed


def load_inventory(root_fd):
    """Return a dict of path to imported SHA-256 from PROVENANCE-inventory.json's entries, or raise
    CannotEvaluate."""
    parsed = load_json_object(root_fd, INVENTORY)
    entries = parsed.get("entries")
    if not isinstance(entries, list):
        raise CannotEvaluate(INVENTORY + ": has no entries list")
    imported = {}
    for index, entry in enumerate(entries):
        path = entry.get("path") if isinstance(entry, dict) else None
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not (isinstance(path, str) and path and isinstance(digest, str)
                and SHA256_RE.fullmatch(digest)):
            raise CannotEvaluate(INVENTORY + ": entries[%d] is not an object with a nonempty "
                                 "string path and a 64 lowercase hex sha256" % index)
        if path in imported:
            raise CannotEvaluate(INVENTORY + ": entries[%d] repeats the path %s" % (index, path))
        imported[path] = digest
    return imported


def load_sums(root_fd):
    """Return a dict of path to SHA-256 from the committed SHA256SUMS, or raise CannotEvaluate."""
    data = read_required(root_fd, SUMS)
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CannotEvaluate(SUMS + ": is not ASCII: " + str(exc)) from exc
    if not text.endswith("\n"):
        raise CannotEvaluate(SUMS + ": does not end with a newline")
    sums = {}
    for number, line in enumerate(text[:-1].split("\n"), 1):
        match = SUMS_LINE.fullmatch(line)
        if match is None or path_problem(match.group(2)) is not None:
            raise CannotEvaluate(SUMS + ": line %d %s is not '<64 lowercase hex>  <normalized "
                                 "relative path>'" % (number, ascii(line)))
        if match.group(2) in sums:
            raise CannotEvaluate(SUMS + ": line %d repeats the path %s" % (number, match.group(2)))
        sums[match.group(2)] = match.group(1)
    return sums


def record_problems(record):
    """Return a list of messages for one record's shape; empty when it has the right form."""
    if not isinstance(record, dict):
        return ["is not an object"]
    disposition = record.get("disposition")
    if disposition not in DISPOSITIONS:
        return ["disposition %s is not one of %s"
                % (json.dumps(disposition), ", ".join(sorted(DISPOSITIONS)))]
    fields = DISPOSITIONS[disposition]
    problems = ["lacks the field " + field for field in fields if field not in record]
    problems += ["has the field %s, which a %s record does not define" % (field, disposition)
                 for field in sorted(set(record) - set(fields))]
    for field in ("source_path", "landed_path"):
        if field in record and field in fields and path_problem(record[field]) is not None:
            problems.append(field + " " + path_problem(record[field]))
    for field in ("source_sha256", "landed_sha256"):
        value = record.get(field)
        if field in record and field in fields and not (
                isinstance(value, str) and SHA256_RE.fullmatch(value)):
            problems.append(field + " is not 64 lowercase hex")
    reason = record.get("decline_reason")
    if "decline_reason" in record and not (isinstance(reason, str) and reason.strip()):
        problems.append("decline_reason is not a nonempty string")
    return problems


def evaluate(root_fd):
    """Return (exit, lines) for the repository open at root_fd; raise CannotEvaluate."""
    parsed = load_record(root_fd)
    sums = load_sums(root_fd)
    findings = []

    def find(where, message, kind):
        findings.append("FAIL: %s: %s [%s]" % (where, message, kind))

    for key in TOP_KEYS:
        if key not in parsed:
            find(RECORD, "lacks the top-level key " + key, "keys")
    for key in sorted(set(parsed) - set(TOP_KEYS)):
        find(RECORD, "has the top-level key %s, which the format does not define" % key, "keys")
    commit = parsed.get("source_commit")
    if "source_commit" in parsed and not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        find(RECORD, "source_commit is not 7 to 40 lowercase hex", "bad-commit")
    for key in ("source_commit_note", "source_repository"):
        value = parsed.get(key)
        if key in parsed and not (isinstance(value, str) and value.strip()):
            find(RECORD, key + " is not a nonempty string", "bad-commit")

    previous = None
    recorded = set()
    landed = 0
    imported = None
    for index, record in enumerate(parsed["files"]):
        source = record.get("source_path") if isinstance(record, dict) else None
        label = ("record " + source) if isinstance(source, str) else "files[%d]" % index
        problems = record_problems(record)
        for message in problems:
            find(label, message, "bad-record")
        if not isinstance(source, str):
            continue
        if previous is not None and source == previous:
            find(label, "repeats the source path of the record before it", "duplicate-record")
        elif previous is not None and source < previous:
            find(label, "is out of order: it sorts before %s, the record before it" % previous,
                 "unsorted")
        previous = source
        recorded.add(source)
        if problems:
            continue
        if source not in sums:
            find(label, "its source path has no line in " + SUMS, "not-in-sums")
        elif record["source_sha256"] != sums[source]:
            find(label, "source_sha256 %s differs from %s, which lists %s"
                 % (record["source_sha256"], SUMS, sums[source]), "sums-mismatch")
        if record["disposition"] == "declined":
            continue
        path = record["landed_path"]
        if record["disposition"] == "landed" and record["landed_sha256"] != record["source_sha256"]:
            find(label, "is landed byte for byte, but its landed_sha256 %s differs from its "
                 "source_sha256 %s; a landed file that differs from the handed-over bytes is "
                 "landed-adapted" % (record["landed_sha256"], record["source_sha256"]),
                 "landed-not-identical")
        if record["disposition"] == "already-present":
            if imported is None:
                imported = load_inventory(root_fd)
            if path not in imported:
                find(label, "is already-present, but %s has no entry for its landed path %s"
                     % (INVENTORY, path), "present-not-imported")
            elif record["landed_sha256"] != imported[path]:
                find(label, "is already-present, but its landed_sha256 %s differs from the "
                     "imported sha256 %s of %s in %s" % (record["landed_sha256"], imported[path],
                                                         path, INVENTORY), "present-not-imported")
        kind, data = read_regular(root_fd, path)
        if kind == "missing":
            find(label, "its landed file %s is missing" % path, "landed-missing")
        elif kind != "file":
            find(label, "its landed file %s is %s" % (path, {
                "symlink": "a symlink; it is not followed",
                "replaced": "replaced while being read"}.get(kind, "not a regular file")),
                "not-regular")
        else:
            digest = hashlib.sha256(data).hexdigest()
            if digest != record["landed_sha256"]:
                find(label, "landed_sha256 %s differs from the sha256 %s of %s"
                     % (record["landed_sha256"], digest, path), "landed-mismatch")
            else:
                landed += 1
    for path in sorted(set(sums) - recorded):
        find(SUMS, "its line for %s has no record in %s" % (path, RECORD), "unrecorded-sum")

    lines = list(findings)
    if findings:
        lines.append("%s: FAIL (%s)" % (GATE, plural(len(findings), "finding")))
        return EXIT_FAIL, lines
    lines.append("%s: PASS (%s, each matching %s; %d landed and matching its file)"
                 % (GATE, plural(len(parsed["files"]), "handed-over file"), SUMS, landed))
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


# Self-test fixtures: a handover of four files, one landed byte for byte, one landed adapted at
# another path, one declined and one already present (adapted, it equals the imported bytes that
# the fixture inventory lists).

SOURCE = {
    "a/one.py": b"ONE = 1\n",
    "b/two.md": b"# Two\n",
    "c/three.txt": b"three\n",
    "d/present.py": b"PRESENT = 1\n# as the source names it\n",
}
LANDED = {"tools/one.py": b"ONE = 1\n", "docs/two.md": b"# Two, adapted\n",
          "tools/present.py": b"PRESENT = 1\n"}
APPENDED = LANDED["tools/one.py"] + b"# one appended line\n"


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def fixture_records():
    return [
        {"disposition": "landed", "landed_path": "tools/one.py",
         "landed_sha256": sha256_of(LANDED["tools/one.py"]), "source_path": "a/one.py",
         "source_sha256": sha256_of(SOURCE["a/one.py"])},
        {"disposition": "landed-adapted", "landed_path": "docs/two.md",
         "landed_sha256": sha256_of(LANDED["docs/two.md"]), "source_path": "b/two.md",
         "source_sha256": sha256_of(SOURCE["b/two.md"])},
        {"decline_reason": "Fixture decline.", "disposition": "declined",
         "source_path": "c/three.txt", "source_sha256": sha256_of(SOURCE["c/three.txt"])},
        {"disposition": "already-present", "landed_path": "tools/present.py",
         "landed_sha256": sha256_of(LANDED["tools/present.py"]), "source_path": "d/present.py",
         "source_sha256": sha256_of(SOURCE["d/present.py"])},
    ]


def fixture_sums():
    return "".join("%s  %s\n" % (sha256_of(data), path)
                   for path, data in sorted(SOURCE.items())).encode("ascii")


def fixture_inventory(entries=None):
    """Return inventory bytes: entries replaces the entry list (the default lists the imported
    tools/present.py and one other file)."""
    if entries is None:
        entries = [{"path": "README.md", "sha256": "3" * 64},
                   {"path": "tools/present.py", "sha256": sha256_of(LANDED["tools/present.py"])}]
    return json.dumps({"entries": entries}, indent=1, sort_keys=True).encode()


def fixture(edit=None, raw=None, sums=None, landed=None, post=None, inventory=None):
    """Return a case builder: edit changes the parsed record in place, raw replaces its bytes,
    sums replaces the SHA256SUMS bytes, landed maps a landed path to new bytes (None removes it),
    inventory replaces the inventory bytes (False writes none) and post edits the written tree."""
    def build(base):
        root = os.path.join(base, "repo")
        os.makedirs(root)
        files = dict(LANDED)
        files.update(landed or {})
        for path, data in sorted(files.items()):
            if data is not None:
                write_file(os.path.join(root, path), data)
        parsed = {"files": fixture_records(), "source_commit": "0123abcd",
                  "source_commit_note": "Fixture prefix.", "source_repository": "fixture"}
        if edit is not None:
            edit(parsed)
        data = raw if raw is not None else json.dumps(parsed, indent=1, sort_keys=True).encode()
        write_file(os.path.join(root, RECORD), data)
        if sums is not False:
            write_file(os.path.join(root, SUMS), fixture_sums() if sums is None else sums)
        if inventory is not False:
            write_file(os.path.join(root, INVENTORY),
                       fixture_inventory() if inventory is None else inventory)
        if post is not None:
            post(root)
        return root

    return build


def _set(index, field, value):
    def edit(parsed):
        if value is _REMOVE:
            del parsed["files"][index][field]
        else:
            parsed["files"][index][field] = value

    return edit


_REMOVE = object()


def _top(key, value):
    def edit(parsed):
        if value is _REMOVE:
            del parsed[key]
        else:
            parsed[key] = value

    return edit


def _files(change):
    def edit(parsed):
        parsed["files"] = change(parsed["files"])

    return edit


def _symlink_landed(root):
    target = os.path.join(root, "tools", "one.py")
    outside = root + "-outside.py"
    write_file(outside, LANDED["tools/one.py"])
    os.unlink(target)
    os.symlink(outside, target)


def _symlink_dir(root):
    tools = os.path.join(root, "tools")
    outside = root + "-tools"
    os.rename(tools, outside)
    os.symlink(outside, tools)


def _directory_landed(root):
    os.unlink(os.path.join(root, "tools", "one.py"))
    os.mkdir(os.path.join(root, "tools", "one.py"))


def _symlink_record(root):
    target = os.path.join(root, RECORD)
    outside = root + "-record.json"
    os.rename(target, outside)
    os.symlink(outside, target)


def _cases():
    """Return (label, builder, expected exit, a text one output line must hold)."""
    sums = fixture_sums()
    one_byte = b"ONE = 2\n"
    return [
        ("clean fixture", fixture(), EXIT_PASS, GATE + ": PASS"),
        ("one-byte change to a landed file", fixture(landed={"tools/one.py": one_byte}),
         EXIT_FAIL, "[landed-mismatch]"),
        ("one-byte change to an adapted landed file",
         fixture(landed={"docs/two.md": b"# Two, adapteD\n"}), EXIT_FAIL, "[landed-mismatch]"),
        ("landed file missing", fixture(landed={"tools/one.py": None}), EXIT_FAIL,
         "[landed-missing]"),
        ("landed file a symlink to identical bytes", fixture(post=_symlink_landed), EXIT_FAIL,
         "[not-regular]"),
        ("landed file under a symlinked directory", fixture(post=_symlink_dir), EXIT_FAIL,
         "[not-regular]"),
        ("landed file a directory", fixture(post=_directory_landed), EXIT_FAIL,
         "[not-regular]"),
        ("source sha256 differs from SHA256SUMS", fixture(_set(0, "source_sha256", "0" * 64)),
         EXIT_FAIL, "[sums-mismatch]"),
        ("declined source sha256 differs from SHA256SUMS",
         fixture(_set(2, "source_sha256", "1" * 64)), EXIT_FAIL, "[sums-mismatch]"),
        ("SHA256SUMS line changed", fixture(sums=sums.replace(sums[:1], b"f" if sums[:1] != b"f"
                                                              else b"e", 1)),
         EXIT_FAIL, "[sums-mismatch]"),
        ("record for a path not in SHA256SUMS", fixture(_files(lambda files: files + [
            {"decline_reason": "x", "disposition": "declined", "source_path": "d/four",
             "source_sha256": "2" * 64}])), EXIT_FAIL, "[not-in-sums]"),
        ("SHA256SUMS line with no record", fixture(_files(lambda files: files[:2])), EXIT_FAIL,
         "[unrecorded-sum]"),
        ("records unsorted", fixture(_files(lambda files: [files[1], files[0], files[2]])),
         EXIT_FAIL, "[unsorted]"),
        ("record repeated", fixture(_files(lambda files: [files[0], files[0]] + files[1:])),
         EXIT_FAIL, "[duplicate-record]"),
        ("unknown disposition", fixture(_set(0, "disposition", "imported")), EXIT_FAIL,
         "[bad-record]"),
        ("landed record lacks landed_sha256", fixture(_set(0, "landed_sha256", _REMOVE)),
         EXIT_FAIL, "[bad-record]"),
        ("landed record carries a decline reason", fixture(_set(0, "decline_reason", "x")),
         EXIT_FAIL, "[bad-record]"),
        ("declined record carries a landed path", fixture(_set(2, "landed_path", "c/three.txt")),
         EXIT_FAIL, "[bad-record]"),
        ("declined record with an empty reason", fixture(_set(2, "decline_reason", " ")),
         EXIT_FAIL, "[bad-record]"),
        ("landed sha256 in upper case", fixture(_set(0, "landed_sha256", sha256_of(
            LANDED["tools/one.py"]).upper())), EXIT_FAIL, "[bad-record]"),
        ("landed path escapes the root", fixture(_set(0, "landed_path", "../one.py")), EXIT_FAIL,
         "[bad-record]"),
        ("record not an object", fixture(_files(lambda files: files + ["x"])), EXIT_FAIL,
         "[bad-record]"),
        ("top-level key missing", fixture(_top("source_repository", _REMOVE)), EXIT_FAIL,
         "[keys]"),
        ("top-level key extra", fixture(_top("extra", 1)), EXIT_FAIL, "[keys]"),
        ("source commit not hex", fixture(_top("source_commit", "main")), EXIT_FAIL,
         "[bad-commit]"),
        ("source commit note empty", fixture(_top("source_commit_note", "")), EXIT_FAIL,
         "[bad-commit]"),
        ("source repository empty", fixture(_top("source_repository", " ")), EXIT_FAIL,
         "[bad-commit]"),
        # A landed record holds its file to the handed-over bytes: one line appended to the landed
        # file with only landed_sha256 refreshed (the file and the record agree) is still red.
        ("landed file differs from the handed-over bytes, landed_sha256 refreshed",
         fixture(_set(0, "landed_sha256", sha256_of(APPENDED)), landed={"tools/one.py": APPENDED}),
         EXIT_FAIL, "[landed-not-identical]"),
        # Mutant-style: an adapted record relabelled landed, every digest left true.
        ("landed-adapted record relabelled landed", fixture(_set(1, "disposition", "landed")),
         EXIT_FAIL, "[landed-not-identical]"),
        ("already-present file differs from its imported bytes, landed_sha256 refreshed",
         fixture(_set(3, "landed_sha256", sha256_of(APPENDED)),
                 landed={"tools/present.py": APPENDED}), EXIT_FAIL, "[present-not-imported]"),
        ("already-present path with no inventory entry",
         fixture(inventory=fixture_inventory([{"path": "README.md", "sha256": "3" * 64}])),
         EXIT_FAIL, "[present-not-imported]"),
        # Mutant-style: a landed-adapted record relabelled already-present (its bytes are not the
        # imported ones, and its path has no inventory entry).
        ("landed-adapted record relabelled already-present",
         fixture(_set(1, "disposition", "already-present")), EXIT_FAIL, "[present-not-imported]"),
        ("inventory missing where a record is already-present", fixture(inventory=False),
         EXIT_CANNOT, INVENTORY + ": is missing"),
        ("inventory not needed without an already-present record",
         fixture(_files(lambda files: files[:3]), sums=b"".join(
             line + b"\n" for line in fixture_sums().split(b"\n")[:3]), inventory=False),
         EXIT_PASS, GATE + ": PASS"),
        ("inventory with a duplicate key", fixture(inventory=b'{"entries": [], "entries": []}'),
         EXIT_CANNOT, "duplicate key"),
        ("inventory without an entries list", fixture(inventory=b'{"entries": {}}'), EXIT_CANNOT,
         "no entries list"),
        ("inventory entry with an upper-case sha256", fixture(inventory=fixture_inventory(
            [{"path": "tools/present.py",
              "sha256": sha256_of(LANDED["tools/present.py"]).upper()}])),
         EXIT_CANNOT, "64 lowercase hex sha256"),
        ("inventory repeats a path", fixture(inventory=fixture_inventory(
            [{"path": "tools/present.py", "sha256": sha256_of(LANDED["tools/present.py"])}] * 2)),
         EXIT_CANNOT, "repeats the path tools/present.py"),
        ("record missing", fixture(raw=None, post=lambda root: os.unlink(
            os.path.join(root, RECORD))), EXIT_CANNOT, RECORD + ": is missing"),
        ("record a symlink", fixture(post=_symlink_record), EXIT_CANNOT, "is a symlink"),
        ("record with a duplicate key", fixture(raw=b'{"files": [], "files": []}'), EXIT_CANNOT,
         "duplicate key"),
        ("record with NaN", fixture(raw=b'{"files": [], "source_commit": NaN}'), EXIT_CANNOT,
         "NaN"),
        ("record top level not an object", fixture(raw=b"[]"), EXIT_CANNOT, "not an object"),
        ("record without a files list", fixture(raw=b'{"files": {}}'), EXIT_CANNOT,
         "no files list"),
        ("SHA256SUMS missing", fixture(sums=False), EXIT_CANNOT, SUMS + ": is missing"),
        ("SHA256SUMS without a final newline", fixture(sums=sums[:-1]), EXIT_CANNOT,
         "does not end with a newline"),
        ("SHA256SUMS line with one space", fixture(sums=sums.replace(b"  ", b" ", 1)),
         EXIT_CANNOT, "is not '<64 lowercase hex>"),
        ("SHA256SUMS line with CRLF", fixture(sums=sums.replace(b"\n", b"\r\n", 1)),
         EXIT_CANNOT, "is not '<64 lowercase hex>"),
        ("SHA256SUMS repeats a path", fixture(sums=sums + sums.split(b"\n")[0] + b"\n"),
         EXIT_CANNOT, "repeats the path"),
        ("SHA256SUMS empty line", fixture(sums=sums + b"\n"), EXIT_CANNOT,
         "is not '<64 lowercase hex>"),
    ]


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


def self_test():
    """Run the self-test and return its exit status: 0 pass, 1 a failed case, 2 cannot evaluate."""
    try:
        return run_self_test()
    except Exception as exc:
        print("%s: CANNOT EVALUATE (unexpected error: %s: %s)" % (GATE, type(exc).__name__, exc),
              file=sys.stderr)
        return EXIT_CANNOT


def run_self_test():
    failures = 0
    total = 0
    red = set()

    def report(ok, label, detail):
        nonlocal failures, total
        total += 1
        failures += 0 if ok else 1
        print("%s %s: %s" % ("PASS" if ok else "FAIL", label, detail))

    def outcome(expected, got, needle, text):
        found = any(needle in line for line in text.splitlines())
        detail = "expected exit %d, got %d" % (expected, got)
        if not found:
            detail += "; no line contains %r" % needle
        return got == expected and found, detail

    try:
        with tempfile.TemporaryDirectory(prefix="provenance-addendum-") as tmp:
            for index, (label, build, expected, needle) in enumerate(_cases()):
                base = os.path.join(tmp, "case%02d" % index)
                os.mkdir(base)
                root = build(base)
                code, lines = check(root)
                ok, detail = outcome(expected, code, needle, "\n".join(lines))
                if ok and expected == EXIT_FAIL:
                    red.update(kind for kind in FINDING_KINDS if needle == "[" + kind + "]")
                report(ok, label, detail)

            unred = [kind for kind in FINDING_KINDS if kind not in red]
            report(not unred, "every finding kind is red, with exit 1, in at least one case",
                   "kinds not shown red: " + (", ".join(unred) or "none"))

            for version, expected in (((3, 13, 9), 2), ((3, 14, 0), 0), ((3, 15, 1), 0)):
                got = python_gate(version)
                report(got == expected, "Python %d.%d.%d gate" % version,
                       "expected exit %d, got %d" % (expected, got))

            base = os.path.join(tmp, "unexpected")
            os.mkdir(base)
            got, text = main_with_failing_check(base)
            ok, detail = outcome(EXIT_CANNOT, got, "unexpected error", text)
            report(ok, "unexpected error exits 2", detail)

            base = os.path.join(tmp, "not-a-directory")
            write_file(base, b"x\n")
            got, lines = check(base)
            ok, detail = outcome(EXIT_CANNOT, got, "cannot be opened as a directory",
                                 "\n".join(lines))
            report(ok, "a root that is a regular file exits 2", detail)

            tool = os.path.realpath(__file__)
            cli_cases = [
                ("command line, clean fixture", fixture(), [], EXIT_PASS, GATE + ": PASS"),
                ("command line, one-byte change to a landed file",
                 fixture(landed={"tools/one.py": b"ONE = 3\n"}), [], EXIT_FAIL, GATE + ": FAIL"),
                ("command line, unknown option", fixture(), ["--unknown"], EXIT_CANNOT,
                 "unrecognized arguments"),
                ("command line, --self-test with --root", fixture(), ["--self-test"],
                 EXIT_CANNOT, "--self-test does not take --root"),
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
    except (OSError, subprocess.SubprocessError) as exc:
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
        description="Check " + RECORD + " against " + SUMS + " and the landed files.",
    )
    parser.add_argument("--root", default=None,
                        help="repository root (default: the parent of this tool's directory)")
    parser.add_argument("--self-test", action="store_true",
                        help="build fixtures in a temporary directory and check every exit path")
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
