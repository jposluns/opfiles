"""Check the vendored AIQT rule trees against .aiqt/pin.toml.

Usage:
  python3 tools/check_aiqt_vendored.py [--root PATH]
  python3 tools/check_aiqt_vendored.py --self-test

The vendored set is fixed in this tool, not read from the pin: the trees .claude/rules/aiqt and
.claude/rules/security, and the single file .claude/RULES-INDEX.md. The pin must list exactly that
set, so an edit to the pin alone cannot narrow what is checked. A change that removes a vendored
file and its pin entry together passes; only review of the update PR catches it.

The gate is offline. It opens the root once and resolves every path beneath that directory
descriptor, one component at a time, so no symlink is followed at any level. It opens each file
with O_NOFOLLOW and O_NONBLOCK and confirms with fstat that it is a regular file before reading.

Exit status:
  0  every vendored file matches its pinned SHA-256, nothing is missing or extra, the licence
     file matches LICENCE_SHA256, and NOTICE names the vendored set, the Apache License 2.0,
     and the pinned commit;
  1  a check failed: a vendored file is missing, differs from its pin, or is a symlink or not a
     regular file; a vendored path, the licence file, or NOTICE was replaced while being
     checked; a vendored tree holds a file the pin does not list, or nests more than 8 levels
     deep; the pin's [vendored] lists differ from the fixed set; a pinned path is absolute,
     contains "..", is not normalized, overlaps .claude/rules/opfiles, or lies outside the
     vendored set; [sha256] is empty; [source] lacks name, commit, pack_version, local_patches
     or licence, or names another source or licence; LICENSES/Apache-2.0.txt is missing or its
     SHA-256 is not LICENCE_SHA256; or NOTICE is missing or does not name every vendored path,
     the Apache License 2.0, and the pinned commit;
  2  the check cannot be evaluated: the root cannot be opened as a directory; the pin is absent,
     a symlink, replaced while being checked, unreadable, not UTF-8 or not valid TOML; a
     vendored directory vanished while being checked; a file cannot be read; an unexpected
     error occurs; the command line is invalid; or Python is older than 3.14.

The gate never scans .claude/rules/opfiles/ or anything else outside the vendored set, the
licence file and NOTICE. The default root is the parent of this tool's directory, resolved with
os.path.realpath. Only the standard library is used.
"""

import sys

MIN_PYTHON = (3, 14)
GATE = "aiqt-vendored"


def python_ok(version_info):
    return tuple(version_info[:2]) >= MIN_PYTHON


def refuse_old_python(version_info, stream):
    """Write the floor message to stream and return 2 when the version is too old, else 0."""
    if python_ok(version_info):
        return 0
    print("check_aiqt_vendored: cannot evaluate: needs Python 3.14 or newer; this is Python %d.%d"
          % (version_info[0], version_info[1]), file=stream)
    return 2


# The floor is checked at load, as the OPF tools in tools/ check theirs, so the only test of
# __name__ is the entry block at the end of the file.
if not python_ok(sys.version_info):
    import os
    try:
        refuse_old_python(sys.version_info, sys.stderr)
        sys.stderr.flush()
    except BaseException:
        pass
    os._exit(2)

import argparse
import contextlib
import errno
import hashlib
import io
import os
import posixpath
import re
import signal
import stat
import subprocess
import tempfile
import threading
import tomllib

PIN_REL = ".aiqt/pin.toml"
OWN_ZONE = ".claude/rules/opfiles"
EXPECTED_ROOTS = (".claude/rules/aiqt", ".claude/rules/security")
EXPECTED_FILES = (".claude/RULES-INDEX.md",)
EXPECTED_SOURCE = "guardrails"
EXPECTED_LICENCE = "Apache-2.0"
LICENCE_FILE = "LICENSES/Apache-2.0.txt"
# The SHA-256 of the Apache License 2.0 text in LICENCE_FILE. The self-test replaces it with the
# digest of its fixture text.
LICENCE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
NOTICE_FILE = "NOTICE"
NOTICE_LICENCE = "Apache License 2.0"
SOURCE_KEYS = ("name", "commit", "pack_version", "local_patches", "licence")
MAX_DEPTH = 8
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
ROOT_FLAGS = os.O_RDONLY | _DIRECTORY | _CLOEXEC
DIR_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
READ_FLAGS = os.O_RDONLY | _NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _CLOEXEC

# The self-test replaces this to inject races and read errors; everything else uses os.open.
_open = os.open


class CannotEvaluate(Exception):
    """Raised when the check cannot reach a verdict."""


def error_text(exc):
    """Return an OSError's message; strerror is None for some errors."""
    return str(exc.strerror or exc)


def path_problem(rel):
    """Return why a pinned path is not acceptable, or None when it is."""
    if not isinstance(rel, str) or rel == "":
        return "is not a nonempty string"
    if rel.startswith("/") or "\\" in rel or re.match(r"[A-Za-z]:", rel):
        return "is absolute"
    parts = rel.split("/")
    if ".." in parts:
        return "contains '..'"
    if "" in parts or "." in parts or posixpath.normpath(rel) != rel:
        return "is not a normalized relative path"
    if rel == OWN_ZONE or rel.startswith(OWN_ZONE + "/") or OWN_ZONE.startswith(rel + "/"):
        return "overlaps the repository's own rule zone " + OWN_ZONE
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


def lookup(root_fd, rel):
    """Classify rel beneath root_fd without following any symlink.

    Return (kind, where): kind is "file", "dir", "other", "missing", "symlink" or "replaced";
    where is the relative path of the entry that decided it.
    """
    parts = split_rel(rel)
    fd, stop = descend(root_fd, parts[:-1])
    if stop is not None:
        return stop
    try:
        mode = os.lstat(parts[-1], dir_fd=fd).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return "missing", rel
    except OSError as exc:
        raise CannotEvaluate(rel + ": cannot inspect: " + error_text(exc)) from exc
    finally:
        os.close(fd)
    if stat.S_ISLNK(mode):
        return "symlink", rel
    if stat.S_ISREG(mode):
        return "file", rel
    if stat.S_ISDIR(mode):
        return "dir", rel
    return "other", rel


def read_entry(root_fd, rel):
    """Read rel beneath root_fd and return (kind, where, data).

    kind is "file" with the bytes, or "missing", "symlink", "dir" or "other" with None.
    O_NOFOLLOW refuses a symlink swapped in after the lookup, O_NONBLOCK keeps a swapped-in FIFO
    from blocking the open, and fstat confirms a regular file before any byte is read.
    """
    kind, where = lookup(root_fd, rel)
    if kind != "file":
        return kind, where, None
    parts = split_rel(rel)
    fd, stop = descend(root_fd, parts[:-1])
    if stop is not None:
        return stop + (None,)
    try:
        try:
            file_fd = _open(parts[-1], READ_FLAGS, dir_fd=fd)
        except FileNotFoundError:
            return "missing", rel, None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return "symlink", rel, None
            raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            return "other", rel, None
        chunks = []
        while True:
            chunk = os.read(file_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return "file", rel, b"".join(chunks)
    except OSError as exc:
        raise CannotEvaluate(rel + ": cannot read: " + error_text(exc)) from exc
    finally:
        os.close(file_fd)


def load_pin(root_fd):
    kind, where, data = read_entry(root_fd, PIN_REL)
    if kind == "missing":
        raise CannotEvaluate(PIN_REL + ": pin not found")
    if kind == "symlink":
        raise CannotEvaluate(where + ": is a symlink; the pin is not followed")
    if kind == "replaced":
        raise CannotEvaluate(where + ": replaced while being checked")
    if kind != "file":
        raise CannotEvaluate(PIN_REL + ": is not a regular file")
    try:
        return tomllib.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CannotEvaluate(PIN_REL + ": is not UTF-8: " + str(exc)) from exc
    except tomllib.TOMLDecodeError as exc:
        raise CannotEvaluate(PIN_REL + ": is not valid TOML: " + str(exc)) from exc


def string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def walk_root(root_fd, top, found, fails):
    """List every entry under top, iteratively and without following symlinks.

    A directory nested more than MAX_DEPTH levels below top is reported and not entered, which
    bounds the work and the descriptors held.
    """
    pending = [(top, 0)]
    while pending:
        rel, depth = pending.pop()
        fd, stop = descend(root_fd, split_rel(rel))
        if stop is not None:
            kind, where = stop
            if kind == "symlink":
                fails.append(where + ": symlink in the vendored set")
                continue
            if kind == "replaced":
                fails.append(where + ": replaced while being checked")
                continue
            raise CannotEvaluate(where + ": vanished while being checked")
        try:
            try:
                names = sorted(os.listdir(fd))
            except OSError as exc:
                raise CannotEvaluate(rel + ": cannot list: " + error_text(exc)) from exc
            subdirs = []
            for name in names:
                child = rel + "/" + name
                try:
                    mode = os.lstat(name, dir_fd=fd).st_mode
                except OSError as exc:
                    raise CannotEvaluate(child + ": cannot inspect: " + error_text(exc)) from exc
                if stat.S_ISLNK(mode):
                    fails.append(child + ": symlink in the vendored set")
                elif stat.S_ISDIR(mode):
                    if depth >= MAX_DEPTH:
                        fails.append(child + ": nesting exceeds " + str(MAX_DEPTH)
                                     + " levels below " + top)
                    else:
                        subdirs.append((child, depth + 1))
                elif stat.S_ISREG(mode):
                    found.add(child)
                else:
                    fails.append(child + ": not a regular file in the vendored set")
            pending.extend(reversed(subdirs))
        finally:
            os.close(fd)


def check_source(pin, fails):
    source = pin.get("source")
    if not isinstance(source, dict):
        fails.append(PIN_REL + ": [source] table is missing")
        source = {}
    for key in SOURCE_KEYS:
        value = source.get(key)
        if not isinstance(value, str) or value == "":
            fails.append(PIN_REL + ": [source] lacks " + key)
    name = source.get("name")
    if isinstance(name, str) and name and name != EXPECTED_SOURCE:
        fails.append(PIN_REL + ": [source] name must be " + repr(EXPECTED_SOURCE)
                     + ", not " + repr(name))
    licence = source.get("licence")
    if isinstance(licence, str) and licence and licence != EXPECTED_LICENCE:
        fails.append(PIN_REL + ": [source] licence must be " + repr(EXPECTED_LICENCE)
                     + ", not " + repr(licence))
    commit = source.get("commit")
    if isinstance(commit, str) and commit and not COMMIT_RE.fullmatch(commit):
        fails.append(PIN_REL + ": [source] commit is not 40 lowercase hex characters")


def check_vendored_lists(pin, fails):
    """Require the pin's [vendored] lists to equal the fixed set, so the pin cannot narrow it."""
    vendored = pin.get("vendored")
    if not isinstance(vendored, dict):
        fails.append(PIN_REL + ": [vendored] table is missing")
        vendored = {}
    for key, expected in (("roots", EXPECTED_ROOTS), ("files", EXPECTED_FILES)):
        value = vendored.get(key)
        if not string_list(value):
            fails.append(PIN_REL + ": [vendored] " + key + " is not a list of strings")
            continue
        for rel in value:
            problem = path_problem(rel)
            if problem:
                fails.append(PIN_REL + ": pinned " + key[:-1] + " " + repr(rel) + " " + problem)
        if sorted(value) != sorted(expected):
            fails.append(PIN_REL + ": [vendored] " + key + " must be exactly "
                         + ", ".join(expected) + "; the pin lists "
                         + (", ".join(value) or "nothing"))


def pinned_digests(pin, fails):
    digests = pin.get("sha256")
    if not isinstance(digests, dict):
        fails.append(PIN_REL + ": [sha256] table is missing")
        return {}, {}
    if not digests:
        fails.append(PIN_REL + ": [sha256] table is empty")
    pinned = {}
    for rel in sorted(digests):
        problem = path_problem(rel)
        if problem:
            fails.append(PIN_REL + ": pinned path " + repr(rel) + " " + problem)
            continue
        inside = rel in EXPECTED_FILES or any(rel.startswith(top + "/") for top in EXPECTED_ROOTS)
        if not inside:
            fails.append(PIN_REL + ": pinned path " + repr(rel)
                         + " lies outside the vendored set")
            continue
        digest = digests[rel]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            fails.append(PIN_REL + ": pinned digest for " + repr(rel)
                         + " is not 64 lowercase hex characters")
            continue
        pinned[rel] = digest
    for rel in EXPECTED_FILES:
        if rel not in digests:
            fails.append(PIN_REL + ": pinned file " + repr(rel) + " has no sha256 entry")
    return digests, pinned


def check_licence(root_fd, pin, fails):
    """Require the Apache License 2.0 text and a NOTICE that names every vendored path, the
    licence, and the pinned commit."""
    kind, where, data = read_entry(root_fd, LICENCE_FILE)
    if kind == "missing":
        fails.append(LICENCE_FILE + ": licence file is missing")
    elif kind == "symlink":
        fails.append(where + ": symlink where the licence file should be")
    elif kind == "replaced":
        fails.append(where + ": replaced while being checked")
    elif kind != "file":
        fails.append(LICENCE_FILE + ": licence file is not a regular file")
    elif hashlib.sha256(data).hexdigest() != LICENCE_SHA256:
        fails.append(LICENCE_FILE + ": does not hold the Apache License 2.0 text (sha256 "
                     + hashlib.sha256(data).hexdigest() + ", expected " + LICENCE_SHA256 + ")")
    kind, where, data = read_entry(root_fd, NOTICE_FILE)
    if kind == "missing":
        fails.append(NOTICE_FILE + ": missing; it must carry the vendored rules' attribution")
    elif kind == "symlink":
        fails.append(where + ": symlink where NOTICE should be")
    elif kind == "replaced":
        fails.append(where + ": replaced while being checked")
    elif kind != "file":
        fails.append(NOTICE_FILE + ": is not a regular file")
    else:
        for rel in EXPECTED_ROOTS + EXPECTED_FILES:
            if rel.encode("utf-8") not in data:
                fails.append(NOTICE_FILE + ": does not name " + rel)
        if NOTICE_LICENCE.encode("utf-8") not in data:
            fails.append(NOTICE_FILE + ": does not name the " + NOTICE_LICENCE)
        source = pin.get("source")
        commit = source.get("commit") if isinstance(source, dict) else None
        if isinstance(commit, str) and COMMIT_RE.fullmatch(commit) and (
                commit.encode("ascii") not in data):
            fails.append(NOTICE_FILE + ": does not name the pinned commit " + commit)


def evaluate(root_fd):
    pin = load_pin(root_fd)
    fails = []
    check_source(pin, fails)
    check_vendored_lists(pin, fails)
    digests, pinned = pinned_digests(pin, fails)

    matched = 0
    for rel in sorted(pinned):
        kind, where, data = read_entry(root_fd, rel)
        if kind == "missing":
            fails.append(rel + ": pinned file is missing")
        elif kind == "symlink":
            fails.append(where + ": symlink in the vendored set")
        elif kind == "replaced":
            fails.append(where + ": replaced while being checked")
        elif kind != "file":
            fails.append(rel + ": not a regular file in the vendored set")
        else:
            actual = hashlib.sha256(data).hexdigest()
            if actual != pinned[rel]:
                fails.append(rel + ": sha256 " + actual + " differs from pin " + pinned[rel])
            else:
                matched += 1

    found = set()
    for top in EXPECTED_ROOTS:
        kind, where = lookup(root_fd, top)
        if kind == "missing":
            fails.append(top + ": vendored root is missing")
        elif kind == "symlink":
            fails.append(where + ": symlink in the vendored set")
        elif kind == "replaced":
            fails.append(where + ": replaced while being checked")
        elif kind != "dir":
            fails.append(top + ": vendored root is not a directory")
        else:
            walk_root(root_fd, top, found, fails)
    for rel in sorted(found):
        if rel not in digests:
            fails.append(rel + ": extra file not listed in the pin")

    check_licence(root_fd, pin, fails)

    lines = ["FAIL: " + item for item in fails]
    if fails:
        lines.append(GATE + ": FAIL (" + plural(len(fails), "problem") + ")")
        return 1, lines
    lines.append(GATE + ": PASS (" + plural(matched, "pinned file") + " match; "
                 + plural(len(EXPECTED_ROOTS), "root") + " and "
                 + plural(len(EXPECTED_FILES), "single file") + " checked; "
                 + "licence file and NOTICE present)")
    return 0, lines


def cannot(message):
    return 2, ["ERROR: " + message, GATE + ": CANNOT EVALUATE (1 error)"]


def check(root):
    """Return (exit_code, lines) for the tree at root."""
    try:
        root_fd = os.open(root, ROOT_FLAGS)
    except OSError as exc:
        return cannot("--root is not a directory: " + (root or "(empty path)")
                      + " (" + error_text(exc) + ")")
    try:
        return evaluate(root_fd)
    except CannotEvaluate as exc:
        return cannot(str(exc))
    finally:
        os.close(root_fd)


def plural(count, noun):
    return str(count) + " " + noun + ("" if count == 1 else "s")


# Self-test fixtures.

FIXTURE = {
    ".claude/RULES-INDEX.md": b"# Index\n",
    ".claude/rules/aiqt/00-apex.md": b"apex rule\n",
    ".claude/rules/aiqt/10-other.md": b"other rule\n",
    ".claude/rules/security/SECI-one.md": b"security rule\n",
}
FIXTURE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
FIXTURE_LICENCE = b"Apache License\nVersion 2.0, January 2004\n(fixture text)\n"
FIXTURE_LICENCE_SHA256 = hashlib.sha256(FIXTURE_LICENCE).hexdigest()
FIXTURE_NOTICE = (b"Fixture NOTICE covering .claude/rules/aiqt/, .claude/rules/security/ and "
                  b".claude/RULES-INDEX.md, copied from commit " + FIXTURE_COMMIT.encode("ascii")
                  + b" under the Apache License 2.0.\n")
CASE_SECONDS = 10


def toml_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def good_digests():
    return {rel: hashlib.sha256(data).hexdigest() for rel, data in FIXTURE.items()}


def good_source():
    return {"name": "guardrails", "commit": FIXTURE_COMMIT, "pack_version": "1.0.0",
            "local_patches": "none", "licence": "Apache-2.0"}


def write_pin(root, digests=None, source=None, roots=None, files=None, raw=None):
    if raw is None:
        digests = good_digests() if digests is None else digests
        source = good_source() if source is None else source
        roots = list(EXPECTED_ROOTS) if roots is None else roots
        files = list(EXPECTED_FILES) if files is None else files
        out = ["[source]"]
        out += [key + " = " + toml_string(value) for key, value in source.items()]
        out += ["", "[vendored]",
                "roots = [" + ", ".join(toml_string(item) for item in roots) + "]",
                "files = [" + ", ".join(toml_string(item) for item in files) + "]",
                "", "[sha256]"]
        out += [toml_string(rel) + " = " + toml_string(digests[rel]) for rel in sorted(digests)]
        raw = "\n".join(out) + "\n"
    write_file(os.path.join(root, PIN_REL), raw.encode("utf-8"))


def make_tree(base, name):
    root = os.path.join(base, name)
    for rel, data in FIXTURE.items():
        write_file(os.path.join(root, rel), data)
    write_file(os.path.join(root, OWN_ZONE, "README.md"), b"own zone\n")
    write_file(os.path.join(root, LICENCE_FILE), FIXTURE_LICENCE)
    write_file(os.path.join(root, NOTICE_FILE), FIXTURE_NOTICE)
    return root


def swap_at_open(name, want_dir, swap, restore):
    """Return an opener that runs swap() just before opening name and restore() just after.

    It stands in for _open, so a fixture can change the tree between the gate's lookup and its
    open, as a racing writer would. want_dir selects directory opens or file opens.
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


def case_match(base):
    root = make_tree(base, "match")
    write_pin(root)
    return root


def case_changed_byte(base):
    root = make_tree(base, "changed")
    write_pin(root)
    write_file(os.path.join(root, ".claude/rules/aiqt/00-apex.md"), b"apex rulE\n")
    return root


def case_missing_file(base):
    root = make_tree(base, "missing")
    write_pin(root)
    os.unlink(os.path.join(root, ".claude/rules/security/SECI-one.md"))
    return root


def case_missing_index(base):
    root = make_tree(base, "missing-index")
    write_pin(root)
    os.unlink(os.path.join(root, ".claude/RULES-INDEX.md"))
    return root


def case_extra_file(base):
    root = make_tree(base, "extra")
    write_pin(root)
    write_file(os.path.join(root, ".claude/rules/aiqt/99-extra.md"), b"extra\n")
    return root


def case_extra_nested(base):
    root = make_tree(base, "extra-nested")
    write_pin(root)
    write_file(os.path.join(root, ".claude/rules/security/sub/deep.md"), b"deep\n")
    return root


def case_too_deep(base):
    root = make_tree(base, "too-deep")
    write_pin(root)
    nested = "/".join("d%d" % level for level in range(MAX_DEPTH + 2))
    write_file(os.path.join(root, ".claude/rules/security", nested, "deep.md"), b"deep\n")
    return root


def case_symlink_in_root(base):
    root = make_tree(base, "symlink")
    write_pin(root)
    os.symlink("00-apex.md", os.path.join(root, ".claude/rules/aiqt/link.md"))
    return root


def case_pinned_file_symlink(base):
    root = make_tree(base, "symlink-pinned")
    write_pin(root)
    target = os.path.join(root, ".claude/rules/aiqt/10-other.md")
    outside = os.path.join(base, "symlink-pinned-outside.md")
    write_file(outside, FIXTURE[".claude/rules/aiqt/10-other.md"])
    os.unlink(target)
    os.symlink(outside, target)
    return root


def case_symlinked_parent(base):
    root = make_tree(base, "symlink-parent")
    write_pin(root)
    real = os.path.join(base, "symlink-parent-real")
    os.rename(os.path.join(root, ".claude/rules/security"), real)
    os.symlink(real, os.path.join(root, ".claude/rules/security"))
    return root


def case_dotdot_in_pin(base):
    # The escaping entry names an existing file outside the root and carries its true digest,
    # so only the path check can reject it.
    root = make_tree(base, "dotdot")
    escape = b"outside the root\n"
    write_file(os.path.join(base, "escape.md"), escape)
    digests = good_digests()
    digests[".claude/rules/aiqt/../../../../escape.md"] = hashlib.sha256(escape).hexdigest()
    write_pin(root, digests=digests)
    return root


def case_absolute_in_pin(base):
    root = make_tree(base, "absolute")
    digests = good_digests()
    digests["/etc/hostname"] = "0" * 64
    write_pin(root, digests=digests)
    return root


def case_outside_roots(base):
    root = make_tree(base, "outside")
    digests = good_digests()
    digests[LICENCE_FILE] = hashlib.sha256(FIXTURE_LICENCE).hexdigest()
    write_pin(root, digests=digests)
    return root


def case_root_overlaps_own_zone(base):
    root = make_tree(base, "overlap")
    write_pin(root, roots=list(EXPECTED_ROOTS) + [OWN_ZONE])
    return root


def case_emptied_pin(base):
    root = make_tree(base, "emptied")
    write_pin(root, digests={}, roots=[], files=[])
    for rel in FIXTURE:
        os.unlink(os.path.join(root, rel))
    return root


def case_dropped_root(base):
    root = make_tree(base, "dropped-root")
    digests = good_digests()
    del digests[".claude/rules/security/SECI-one.md"]
    write_pin(root, digests=digests, roots=[".claude/rules/aiqt"])
    write_file(os.path.join(root, ".claude/rules/security/SECI-one.md"), b"changed\n")
    write_file(os.path.join(root, ".claude/rules/security/SECI-two.md"), b"added\n")
    return root


def case_dropped_file(base):
    root = make_tree(base, "dropped-file")
    write_pin(root, files=[])
    return root


def case_empty_digests(base):
    root = make_tree(base, "empty-digests")
    write_pin(root, digests={})
    return root


def case_other_source(base):
    root = make_tree(base, "other-source")
    source = good_source()
    source["name"] = "elsewhere"
    write_pin(root, source=source)
    return root


def case_licence_key_missing(base):
    root = make_tree(base, "no-licence-key")
    source = good_source()
    del source["licence"]
    write_pin(root, source=source)
    return root


def case_other_licence(base):
    root = make_tree(base, "other-licence")
    source = good_source()
    source["licence"] = "MIT"
    write_pin(root, source=source)
    return root


def case_licence_file_missing(base):
    root = make_tree(base, "no-licence-file")
    write_pin(root)
    os.unlink(os.path.join(root, LICENCE_FILE))
    return root


def case_licence_file_wrong(base):
    root = make_tree(base, "wrong-licence-file")
    write_pin(root)
    write_file(os.path.join(root, LICENCE_FILE), b"MIT License\n")
    return root


def case_licence_file_truncated(base):
    root = make_tree(base, "truncated-licence-file")
    write_pin(root)
    write_file(os.path.join(root, LICENCE_FILE), FIXTURE_LICENCE.rsplit(b"\n", 2)[0] + b"\n")
    return root


def case_notice_missing(base):
    root = make_tree(base, "no-notice")
    write_pin(root)
    os.unlink(os.path.join(root, NOTICE_FILE))
    return root


def case_notice_incomplete(base):
    root = make_tree(base, "notice-incomplete")
    write_pin(root)
    write_file(os.path.join(root, NOTICE_FILE), b"Covers .claude/rules/aiqt/ and "
                                                b".claude/rules/security/ only.\n")
    return root


def case_notice_without_licence(base):
    root = make_tree(base, "notice-no-licence")
    write_pin(root)
    write_file(os.path.join(root, NOTICE_FILE),
               FIXTURE_NOTICE.replace(NOTICE_LICENCE.encode("utf-8"), b"a licence"))
    return root


def case_notice_without_commit(base):
    root = make_tree(base, "notice-no-commit")
    write_pin(root)
    write_file(os.path.join(root, NOTICE_FILE),
               FIXTURE_NOTICE.replace(FIXTURE_COMMIT.encode("ascii"), b"another commit"))
    return root


def case_bad_commit(base):
    root = make_tree(base, "bad-commit")
    source = good_source()
    source["commit"] = "ABC123"
    write_pin(root, source=source)
    return root


def case_source_key_missing(base):
    root = make_tree(base, "no-patches")
    source = good_source()
    del source["local_patches"]
    write_pin(root, source=source)
    return root


def case_file_without_digest(base):
    root = make_tree(base, "no-digest")
    digests = good_digests()
    del digests[".claude/RULES-INDEX.md"]
    write_pin(root, digests=digests)
    return root


def case_own_zone_ignored(base):
    root = make_tree(base, "own-zone")
    write_pin(root)
    write_file(os.path.join(root, OWN_ZONE, "local-rule.md"), b"local\n")
    os.symlink("README.md", os.path.join(root, OWN_ZONE, "link.md"))
    return root


def case_missing_pin(base):
    return make_tree(base, "no-pin")


def case_invalid_toml(base):
    root = make_tree(base, "bad-toml")
    write_pin(root, raw="[source\nname = \n")
    return root


def case_duplicate_key(base):
    root = make_tree(base, "dup-key")
    write_pin(root, raw='[source]\nname = "a"\nname = "b"\n')
    return root


def case_symlinked_pin(base):
    root = make_tree(base, "symlink-pin")
    outside = os.path.join(base, "symlink-pin-outside.toml")
    write_pin(root)
    os.rename(os.path.join(root, PIN_REL), outside)
    os.symlink(outside, os.path.join(root, PIN_REL))
    return root


def case_root_not_directory(base):
    path = os.path.join(base, "not-a-directory")
    write_file(path, b"plain file\n")
    return path


def case_race_fifo(base):
    """A FIFO replaces a pinned file between the lookup and the open."""
    root = make_tree(base, "race-fifo")
    write_pin(root)
    target = os.path.join(root, ".claude/rules/aiqt/10-other.md")
    aside = os.path.join(base, "race-fifo-aside.md")

    def swap():
        os.rename(target, aside)
        os.mkfifo(target)

    def restore():
        os.unlink(target)
        os.rename(aside, target)

    return root, swap_at_open("10-other.md", False, swap, restore)


def case_race_file_symlink(base):
    """A symlink to an identical file replaces a pinned file between the lookup and the open."""
    root = make_tree(base, "race-symlink")
    write_pin(root)
    target = os.path.join(root, ".claude/rules/aiqt/10-other.md")
    aside = os.path.join(base, "race-symlink-aside.md")
    outside = os.path.join(base, "race-symlink-outside.md")
    write_file(outside, FIXTURE[".claude/rules/aiqt/10-other.md"])

    def swap():
        os.rename(target, aside)
        os.symlink(outside, target)

    def restore():
        os.unlink(target)
        os.rename(aside, target)

    return root, swap_at_open("10-other.md", False, swap, restore)


def _swap_directory(root, base, label, outside_files):
    """Return swap and restore functions that replace .claude/rules/aiqt with a symlink."""
    real = os.path.join(root, ".claude/rules/aiqt")
    aside = os.path.join(base, label + "-aside")
    outside = os.path.join(base, label + "-outside")
    for name, data in outside_files.items():
        write_file(os.path.join(outside, name), data)

    def swap():
        os.rename(real, aside)
        os.symlink(outside, real)

    def restore():
        os.unlink(real)
        os.rename(aside, real)

    return swap, restore


def case_race_directory_symlink(base):
    """A symlink to an identical copy replaces a vendored directory just before it is opened."""
    root = make_tree(base, "race-dir")
    write_pin(root)
    copy = {rel.rsplit("/", 1)[1]: data for rel, data in FIXTURE.items()
            if rel.startswith(".claude/rules/aiqt/")}
    swap, restore = _swap_directory(root, base, "race-dir", copy)
    return root, swap_at_open("aiqt", True, swap, restore)


def case_race_parent_after_open(base):
    """The parent directory becomes a symlink to tampered copies after it was opened."""
    root = make_tree(base, "race-parent")
    write_pin(root)
    tampered = {"10-other.md": b"tampered rule\n"}
    swap, restore = _swap_directory(root, base, "race-parent", tampered)
    return root, swap_at_open("10-other.md", False, swap, restore)


def case_read_error_without_strerror(base):
    """An OSError that carries no strerror still yields a cannot-evaluate message."""
    root = make_tree(base, "read-error")
    write_pin(root)

    def opener(path, flags, mode=0o777, *, dir_fd=None):
        if os.path.basename(path) == "10-other.md":
            raise OSError("injected error without strerror")
        return os.open(path, flags, mode, dir_fd=dir_fd)

    return root, opener


# Each case: label, fixture builder, expected exit, and text that some output line must contain
# (or a tuple of texts, one of which must appear).
CASES = (
    ("matching tree", case_match, 0, "PASS (4 pinned files match"),
    ("changed byte", case_changed_byte, 1, "00-apex.md: sha256"),
    ("missing file in a root", case_missing_file, 1, "SECI-one.md: pinned file is missing"),
    ("missing pinned file", case_missing_index, 1, "RULES-INDEX.md: pinned file is missing"),
    ("extra file in a root", case_extra_file, 1, "99-extra.md: extra file not listed"),
    ("extra file in a nested directory", case_extra_nested, 1, "deep.md: extra file not listed"),
    ("nesting deeper than the bound", case_too_deep, 1, "nesting exceeds 8 levels"),
    ("symlink in a root", case_symlink_in_root, 1, "link.md: symlink in the vendored set"),
    ("pinned file replaced by a symlink", case_pinned_file_symlink, 1,
     "10-other.md: symlink in the vendored set"),
    ("symlinked root directory", case_symlinked_parent, 1,
     ".claude/rules/security: symlink in the vendored set"),
    ("path with '..' in the pin", case_dotdot_in_pin, 1, "contains '..'"),
    ("absolute path in the pin", case_absolute_in_pin, 1, "is absolute"),
    ("pinned path outside the vendored set", case_outside_roots, 1,
     "lies outside the vendored set"),
    ("root overlapping the own rule zone", case_root_overlaps_own_zone, 1,
     "overlaps the repository's own rule zone"),
    ("emptied pin and trees", case_emptied_pin, 1, "[vendored] roots must be exactly"),
    ("security root dropped from the pin", case_dropped_root, 1,
     "SECI-two.md: extra file not listed"),
    ("index dropped from [vendored] files", case_dropped_file, 1,
     "[vendored] files must be exactly"),
    ("empty [sha256] table", case_empty_digests, 1, "[sha256] table is empty"),
    ("[source] names another source", case_other_source, 1, "[source] name must be"),
    ("[source] lacks licence", case_licence_key_missing, 1, "[source] lacks licence"),
    ("[source] names another licence", case_other_licence, 1, "[source] licence must be"),
    ("licence file missing", case_licence_file_missing, 1, "licence file is missing"),
    ("licence file not Apache 2.0", case_licence_file_wrong, 1,
     "does not hold the Apache License 2.0 text"),
    ("licence file truncated", case_licence_file_truncated, 1,
     "does not hold the Apache License 2.0 text"),
    ("NOTICE missing", case_notice_missing, 1, "NOTICE: missing"),
    ("NOTICE does not name the index", case_notice_incomplete, 1,
     "NOTICE: does not name .claude/RULES-INDEX.md"),
    ("NOTICE does not name the licence", case_notice_without_licence, 1,
     "NOTICE: does not name the Apache License 2.0"),
    ("NOTICE does not name the pinned commit", case_notice_without_commit, 1,
     "NOTICE: does not name the pinned commit"),
    ("commit not 40 lowercase hex", case_bad_commit, 1, "commit is not 40 lowercase hex"),
    ("[source] lacks local_patches", case_source_key_missing, 1, "[source] lacks local_patches"),
    ("pinned file without a digest", case_file_without_digest, 1, "has no sha256 entry"),
    ("own rule zone is not scanned", case_own_zone_ignored, 0, "PASS (4 pinned files match"),
    ("FIFO swapped in before the open", case_race_fifo, 1,
     "10-other.md: not a regular file in the vendored set"),
    ("symlink swapped in before the open", case_race_file_symlink, 1,
     "10-other.md: symlink in the vendored set"),
    # Linux refuses O_DIRECTORY|O_NOFOLLOW on a symlink with ENOTDIR ("replaced"); a platform
    # that returns ELOOP reports "symlink". Either message fails the swapped directory.
    ("directory symlink swapped in before the open", case_race_directory_symlink, 1,
     (".claude/rules/aiqt: replaced while being checked",
      ".claude/rules/aiqt: symlink in the vendored set")),
    ("parent swapped after it was opened", case_race_parent_after_open, 0,
     "PASS (4 pinned files match"),
    ("read error without strerror", case_read_error_without_strerror, 2,
     "10-other.md: cannot read: injected error without strerror"),
    ("missing pin", case_missing_pin, 2, "pin not found"),
    ("invalid TOML", case_invalid_toml, 2, "is not valid TOML"),
    ("duplicate TOML key", case_duplicate_key, 2, "is not valid TOML"),
    ("symlinked pin", case_symlinked_pin, 2, "is a symlink; the pin is not followed"),
    ("root is not a directory", case_root_not_directory, 2, "--root is not a directory"),
)


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


def case_symlinked_tools(base, source):
    """A repository whose tools/ directory is reached through a symlink elsewhere."""
    root = case_match(base)
    write_file(os.path.join(root, "tools", "check_aiqt_vendored.py"), source)
    os.mkdir(os.path.join(base, "elsewhere"))
    link = os.path.join(base, "elsewhere", "tools")
    os.symlink(os.path.join(root, "tools"), link)
    return os.path.join(link, "check_aiqt_vendored.py")


def fixture_tool_source(real_digest):
    """Return this tool's source with LICENCE_SHA256 set to the fixture licence digest."""
    with open(os.path.realpath(__file__), "rb") as handle:
        source = handle.read()
    line = b'LICENCE_SHA256 = "%s"\n'
    old = line % real_digest.encode("ascii")
    if source.count(old) != 1:
        raise CannotEvaluate("cannot find the LICENCE_SHA256 line in " + __file__)
    return source.replace(old, line % FIXTURE_LICENCE_SHA256.encode("ascii"))


def self_test():
    """Run the built-in fixtures, with the fixture licence digest in place of LICENCE_SHA256.

    Return 0 pass, 1 a failed case, 2 cannot evaluate. An unexpected error is reported as main()
    reports one and returns 2, so the entry block can exit with this value directly.
    """
    global LICENCE_SHA256
    real_digest = LICENCE_SHA256
    LICENCE_SHA256 = FIXTURE_LICENCE_SHA256
    try:
        return run_self_test(real_digest)
    except Exception as exc:
        print(GATE + ": CANNOT EVALUATE (unexpected error: " + type(exc).__name__ + ": "
              + str(exc) + ")", file=sys.stderr)
        return 2
    finally:
        LICENCE_SHA256 = real_digest


def run_self_test(real_digest):
    global _open
    failures = 0
    total = 0

    def report(ok, label, detail):
        nonlocal failures, total
        total += 1
        if not ok:
            failures += 1
        print(("PASS: " if ok else "FAIL: ") + label + " (" + detail + ")")

    def outcome(expected, got, needle, text):
        detail = "expected exit " + str(expected) + ", got " + str(got)
        needles = needle if isinstance(needle, tuple) else (needle,)
        found = needle is None or any(item in text for item in needles)
        if not found:
            detail += "; no output contains " + repr(needle)
        return got == expected and found, detail

    try:
        with tempfile.TemporaryDirectory(prefix="aiqt-vendored-") as tmp:
            for index, (label, build, expected, needle) in enumerate(CASES):
                base = os.path.join(tmp, "case%02d" % index)
                os.mkdir(base)
                built = build(base)
                root, opener = built if isinstance(built, tuple) else (built, None)
                if opener is not None:
                    _open = opener
                try:
                    code, lines = with_deadline(CASE_SECONDS, lambda: check(root))
                except Exception as exc:
                    report(False, label, "raised " + type(exc).__name__ + ": " + str(exc))
                    continue
                finally:
                    _open = os.open
                ok, detail = outcome(expected, code, needle, "\n".join(lines))
                report(ok, label, detail)

            for label, version, expected, needle in (
                ("Python 3.13 is refused on stderr", (3, 13, 9), 2, "needs Python 3.14 or newer"),
                ("Python 3.14 is accepted", (3, 14, 0), 0, None),
                ("Python 3.15 is accepted", (3, 15, 1), 0, None),
            ):
                err = io.StringIO()
                got = refuse_old_python(version, err)
                ok, detail = outcome(expected, got, needle, err.getvalue())
                if needle is None and err.getvalue():
                    ok, detail = False, detail + "; unexpected output " + repr(err.getvalue())
                report(ok, label, detail)

            base = os.path.join(tmp, "unexpected")
            os.mkdir(base)
            try:
                got, text = main_with_failing_check(base)
                ok, detail = outcome(2, got, "unexpected error", text)
            except Exception as exc:
                ok, detail = False, "raised " + type(exc).__name__ + ": " + str(exc)
            report(ok, "unexpected error exits 2", detail)

            # The path check rejects '..' first; this calls the reader directly to show that the
            # component-wise resolver refuses it too.
            base = os.path.join(tmp, "unsafe-component")
            os.mkdir(base)
            root = case_dotdot_in_pin(base)
            root_fd = os.open(root, ROOT_FLAGS)
            try:
                kind, where, _ = read_entry(root_fd, ".claude/rules/aiqt/../../../../escape.md")
                ok, detail = False, "read " + kind + " at " + where
            except CannotEvaluate as exc:
                ok, detail = "unsafe path component" in str(exc), str(exc)
            finally:
                os.close(root_fd)
            report(ok, "resolver refuses an unsafe path component", detail)

            # Run the tool as a separate process to cover argument handling and the exit status.
            # The fixtures hold a short stand-in for the licence text, so the process runs a copy
            # of this tool whose LICENCE_SHA256 is the stand-in's digest.
            source = fixture_tool_source(real_digest)
            tool = os.path.join(tmp, "check_aiqt_vendored.py")
            write_file(tool, source)
            cli_cases = [
                ("command line, matching tree", case_match, [], 0, "aiqt-vendored: PASS"),
                ("command line, changed byte", case_changed_byte, [], 1, "aiqt-vendored: FAIL"),
                ("command line, root not a directory", case_root_not_directory, [], 2,
                 "CANNOT EVALUATE"),
                ("command line, unknown option", case_match, ["--unknown"], 2,
                 "unrecognized arguments"),
                ("command line, --self-test with --root", case_match, ["--self-test"], 2,
                 "--self-test does not take --root"),
            ]
            for index, (label, build, extra, expected, needle) in enumerate(cli_cases):
                base = os.path.join(tmp, "cli%02d" % index)
                os.mkdir(base)
                root = build(base)
                command = [sys.executable, "-I", "-B", tool, "--root", root] + extra
                proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                      timeout=60)
                text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode(
                    "utf-8", "replace")
                ok, detail = outcome(expected, proc.returncode, needle, text)
                report(ok, label, detail)

            base = os.path.join(tmp, "cli-symlinked-tools")
            os.mkdir(base)
            linked_tool = case_symlinked_tools(base, source)
            proc = subprocess.run([sys.executable, "-I", "-B", linked_tool],
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
            text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            ok, detail = outcome(0, proc.returncode, "aiqt-vendored: PASS", text)
            report(ok, "command line, default root through a symlinked tools directory", detail)
    except (OSError, subprocess.SubprocessError, CannotEvaluate) as exc:
        print(GATE + " self-test: CANNOT EVALUATE (" + str(exc) + ")")
        return 2

    if failures:
        print(GATE + " self-test: FAIL (" + str(failures) + " of " + str(total) + " cases failed)")
        return 1
    print(GATE + " self-test: PASS (" + str(total) + " of " + str(total) + " cases)")
    return 0


def default_root():
    """Return the parent of this tool's directory, resolved with os.path.realpath."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_aiqt_vendored",
        description="Check the vendored AIQT rule trees against " + PIN_REL + ".")
    parser.add_argument("--root", default=None,
                        help="repository root (default: the parent of this tool's directory)")
    parser.add_argument("--self-test", action="store_true",
                        help="run the built-in fixtures and exit")
    args = parser.parse_args(argv)
    if args.self_test and args.root is not None:
        parser.error("--self-test does not take --root")
    try:
        if args.self_test:
            return self_test()
        code, lines = check(args.root if args.root is not None else default_root())
    except Exception as exc:
        print(GATE + ": CANNOT EVALUATE (unexpected error: " + type(exc).__name__ + ": "
              + str(exc) + ")", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(main())
