#!/usr/bin/env python3
"""Line-width gate: refuse a changed or added line wider than its file's width at the base.

Usage:
  python3 tools/check_line_width.py [--root PATH] [--base REV]
  python3 tools/check_line_width.py --self-test

Three passes. The gate compares the git repository at the root with a base commit in three passes,
and fails when any finds a line too wide:
  HEAD: the committed content of HEAD (git diff BASE HEAD, every line read from git's objects), so
    a PASS attests the commit that would be pushed, whatever the index or the work tree holds;
  the index: the staged content (git diff --cached BASE, every line read from the index's blobs),
    so a staged change is checked even when the work tree no longer holds it;
  the work tree: the tracked files as the work tree holds them (git diff BASE; an untracked file
    is not looked at, and a path marked assume-unchanged is read from the index, as git commit -a
    reads it), so a change not yet staged is checked too.
Each pass checks each line changed or added since the base in a Python, shell, Markdown or TOML
file, and each finding names the passes that saw it (HEAD, the index, the work tree, or several).

Files. A file is checked when its path ends in .py, .pyi, .sh, .bash, .md, .markdown or .toml
(in any letter case), or, with none of those suffixes, when the first line of the bytes the pass
reads (its blob at HEAD or in the index, or its work-tree file) is a shebang (#!) naming python,
sh, bash, dash, ksh or zsh. A symlink, a submodule and a deleted file are not checked.

Text and binary. Only content git stores and diffs decides whether a file is text: its blob at the
base, and its new content as git diffs it (its blob at HEAD or in the index, or the clean form git
makes of the work-tree file). The work-tree bytes never decide it, and no attribute does (the diff
runs with -a). Content is binary when it holds a NUL byte. A file that was text at the base is
checked whatever it holds now. A file that was not text at the base (binary there, not a regular
file there, or new since the base) and whose new content is binary is never skipped when its
suffix names it as checked, since no Python, shell, Markdown or TOML file holds a NUL byte: the
NUL byte is itself a finding, and its lines are checked as well. Only a file checked for its
shebang alone is skipped as binary in that case, and the PASS line counts the files skipped.

Width. A line's width is its number of columns after UTF-8 decoding, without its line ending (LF,
or CR LF): every character counts as one column (an undecodable byte too), except a tab, which
advances to the next multiple of 8. A file's width at the base is the largest width of any of its
lines at the base, but never less than 100: the maximum, not a percentile, so one wide line at the
base lets every changed line of that file be as wide. A file new since the base (added, or at the
base a symlink, a submodule or a binary file) may have lines up to 120 wide. A file git pairs as a
rename (its rename detection at the default similarity, forced on with -M) keeps the width its old
path had at the base; a file moved and rewritten past that similarity is new, so each of its lines
is checked against 120.

Changed lines. git diff between the base and HEAD, the index or the work tree, with no context
lines (-U0 and --inter-hunk-context=0, or the whole file as context when its new content must be
read whole to decide whether it is binary), -a so that no attribute hides a file's lines, -M, and
no external diff or textconv, names the added lines. Only those are checked: a line that is the
same at the base and now, in a file that keeps its path or that git pairs as a rename, is never
flagged. An existing long line can therefore stay, and an edit to it may keep it as wide as it
was, because that line itself sets the file's width. A type change (a symlink or a submodule at
the base, a regular file now) is diffed as a deletion and an addition, and the addition is
checked. Every context line, an empty one too, advances the line number.

Missing files. In the work-tree pass, a checked file that git lists as changed with a regular mode
but that is missing from the work tree, or is not a regular file there (a skip-worktree or sparse
entry, for example), is a finding, since the gate cannot read the bytes it would check.

Base. --base REV names the base commit. Without it the base is the merge base of HEAD with
origin/main (refs/remotes/origin/main): the commit the branch was cut from, so the gate checks
exactly what the branch changes, and a commit that reached main after the branch was cut is
neither checked as the branch's own nor used as the width a branch line is held to. The default
refuses a shallow repository, whose truncated history may not hold the merge base; a base named
with --base must be a commit the repository holds.

git's environment. git runs with PATH and HOME from the caller and no other variable of the
caller's environment: GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_CONFIG_*, GIT_ATTR_SOURCE, the
locale and every other variable are dropped. git reads neither its system nor its global
configuration (GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL=/dev/null), nor the system or user
attributes file (GIT_ATTR_NOSYSTEM=1, core.attributesFile=/dev/null); it ignores replace refs
(GIT_NO_REPLACE_OBJECTS=1), does not fetch a missing object in a partial clone
(GIT_NO_LAZY_FETCH=1), writes its messages in the C locale (LC_ALL=C), consults no fsmonitor
(core.fsmonitor=false), writes an empty context line with its leading space, so that its line
number is counted (diff.suppressBlankEmpty=false), expands a sparse index in memory, so that the
diff of a file in a sparse directory entry is read (index.sparse=false), and does not refresh or
write the index (diff.autoRefreshIndex=false). So the work-tree pass also lists a stat-dirty file
(one whose stat data the index does not match), even when its content equals the base; such a
file diffs to nothing, and is neither checked nor counted. The repository's own configuration
and attributes still apply, except where these settings override them. A safe.directory set in
the global configuration does not apply, so run the gate as the owner of the clone.

Writes. The gate writes no file of the work tree, and it does not refresh or rewrite the index
file: .git/index stays byte-identical with the same mtime. It takes no lock (no .git/index.lock),
and nothing under .git changes but what the two cases below describe (seen with git 2.53.0),
which git itself writes while it reads the index; the gate's settings do not stop these writes.
R11 pins this in a plain repository. R13 and R14 run the two cases and fail on any change to a
path's mtime or a file's bytes that unexplained() does not allow, and unexplained() allows each
write below and some others:
  a sparse index: expanding the index in memory (index.sparse=false) makes git write the tree
    objects of the index's directories. A tree the object store lacks (that of a directory
    holding a staged change, for example) is added as a new loose object in its fan-out
    directory under .git/objects, which gets a new mtime (and .git/objects too, when git creates
    that directory); no commit names it, and git gc prunes it in time. A tree the store already
    holds keeps its bytes but gets a new mtime: the loose object's, or, where the objects are
    packed, the pack file's;
  a split index (core.splitIndex): reading the index renews the mtime of its shared index file
    (.git/sharedindex.*), whose bytes stay the same.
--self-test writes only in the temporary directory where it builds its repositories.

Fails closed. Exit 2 (CANNOT EVALUATE), never a pass: when git cannot be run or fails; when the
root has no git history (it is not in a git work tree, as in a copy without .git, or HEAD has no
commit); when the root is not the top of its work tree; when the base cannot be resolved to a
commit (no origin/main, no merge base, a shallow repository for the default, a REV that is not a
commit or starts with -); when a path is unmerged (git ls-files -u lists it); when a file's base
bytes or its diff cannot be read, or its diff holds a line of no known kind (an empty line inside
a hunk, for example); when the diff of a file that HEAD or the index changed has no file section,
so its lines would go unchecked (a sparse index entry git did not expand, for example); when a
work-tree file cannot be read; and when a checked file the work-tree pass lists (changed there,
or only stat-dirty, since the index is not refreshed) has a filter or working-tree-encoding
attribute, whose conversion would make the content git diffs differ from the work-tree bytes.
For a file git lists with no content id (a stat-dirty one, whose stat data does not match the
index, as after a fresh copy or a cache restore, or one added with git add -N), git has not hashed
it, and only that conversion could tell whether it changed: a refresh would run it, and the gate
does not refresh. The message says so, and names the remedy for an unchanged file not added with
git add -N: git update-index -q --refresh, which runs the conversion and updates the index.

Runner. tools/run_all_checks.sh registers the gate as line-width in local mode only: the hosted
Quality job checks out the pull request head alone, a depth-1 clone with no origin/main, so the
default base cannot be found there and --ci lists the gate as NOT RUN. Its self-test,
line-width-self-test, builds its own repositories and runs in both modes. In a copy with no git
history, or with no origin/main, the gate exits 2 with the reason, and the full local run lists
line-width as CANNOT-EVALUATE (exit 2) among its FAILED GATES and fails: run the full local run in
a git clone that has origin/main.

Residuals. Settings in the repository's own configuration that change which lines a diff calls
added (diff.algorithm, for example) apply. Widths are counted in characters and tab stops, not in
the columns a terminal draws, so a wide East Asian character or a combining mark counts as one. A
file checked for its shebang alone, not text at the base, whose new content holds a NUL byte is
skipped as binary. The width at the base is the maximum, not a percentile (see Width). Line
numbers are those of the content git diffs.

Exit: 0 pass, 1 one or more lines too wide, a checked file missing from the work tree, or a file
whose suffix names it as checked holding a NUL byte where it would otherwise be skipped as binary
(each named), 2 cannot evaluate.
Standard library only; Python 3.14 or newer.
"""

import sys

MIN_PYTHON = (3, 14)
TOOL = "check_line_width"
GATE = "line-width"


def python_gate(version):
    """Return 2 when the given version is older than the floor, else 0."""
    return 2 if tuple(version[:2]) < MIN_PYTHON else 0


# The floor is checked at load, as the other gates in tools/ check theirs, so the only test of
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
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2
GIT = "git"
GIT_TIMEOUT = 300
UPSTREAM = "refs/remotes/origin/main"
WIDTH_FLOOR = 100
NEW_FILE_WIDTH = 120
TAB = 8
# The context a diff gets when a file's new content must be read whole: more lines than any file.
WHOLE = 1 << 30
SUFFIXES = (".py", ".pyi", ".sh", ".bash", ".md", ".markdown", ".toml")
SHEBANG = re.compile(
    rb"#![ \t]*(?:[^ \t]*/)?(?:env[ \t]+(?:-[^ \t]*[ \t]+)*)?"
    rb"(?:python[0-9.]*|sh|bash|dash|ksh|zsh)(?:[ \t].*)?\r?")
REGULAR = ("100644", "100755")
NO_BLOB = re.compile(r"0+")
HUNK = re.compile(rb"@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,[0-9]+)? @@")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
HEAD_PASS, INDEX_PASS, WORK_PASS = "HEAD", "the index", "the work tree"
# git's environment: of the caller's variables only these are kept, and GIT_ENV_SET is added, so
# no variable can point git at another repository, index, object store, configuration or
# attribute source, or replace its diff.
GIT_ENV_KEEP = ("PATH", "HOME")
GIT_ENV_SET = {"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
               "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
# The configuration every git call gets on its command line.
GIT_CONFIG = ("-c", "core.quotePath=false", "-c", "core.fsmonitor=false",
              "-c", "diff.suppressBlankEmpty=false", "-c", "index.sparse=false",
              "-c", "diff.autoRefreshIndex=false", "-c", "core.attributesFile=" + os.devnull)
# Attributes that make the content git diffs differ from the work-tree bytes.
CONVERSIONS = ("filter", "working-tree-encoding")


class CannotEvaluate(Exception):
    """Raised when the gate cannot reach a verdict."""


class GitFailed(CannotEvaluate):
    """Raised when git ran and exited with a failure status."""


def git_env(source=None):
    """Return the environment git runs in: GIT_ENV_KEEP of source (default os.environ), and
    GIT_ENV_SET."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items() if key in GIT_ENV_KEEP}
    env.update(GIT_ENV_SET)
    return env


def run_git(git, root, env, args, what):
    """Run git in root and return its standard output, or raise CannotEvaluate naming what."""
    command = [git, "-C", root, *GIT_CONFIG]
    try:
        proc = subprocess.run(command + list(args), stdin=subprocess.DEVNULL,
                              capture_output=True, env=env, timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate("git could not be run to %s (%s: %s)"
                             % (what, type(exc).__name__, exc)) from None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitFailed("git could not %s (exit %d%s)" % (
            what, proc.returncode, (": " + detail[0]) if detail else ""))
    return proc.stdout


def display(text):
    """Return text with each character that is not printable escaped, for one output line."""
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in text)


def work_tree(git, root, env):
    """Return the real path of root, which must be the top of a git work tree."""
    real = os.path.realpath(root)
    try:
        out = run_git(git, real, env, ["rev-parse", "--show-toplevel"], "find the work tree")
    except GitFailed as exc:
        raise CannotEvaluate(
            "%s has no git history: it is not in a git work tree (a copy without .git, for "
            "example), so there is no base to compare it with; run the gate in a git clone that "
            "has origin/main, or pass --base in one [%s]" % (display(real), exc)) from None
    top = out.decode("utf-8", "surrogateescape").rstrip("\n")
    if not top or os.path.realpath(top) != real:
        raise CannotEvaluate("%s is not the top of a git work tree (git names %s)"
                             % (display(real), display(top) or "none"))
    return real


def commit_id(git, root, env, rev, what):
    """Return the full id of the commit rev names, or None when git says it names none."""
    try:
        out = run_git(git, root, env, ["rev-parse", "--verify", "--quiet", rev + "^{commit}"],
                      what)
    except GitFailed:
        return None
    sha = out.decode("ascii", "replace").strip()
    if not SHA.fullmatch(sha):
        raise CannotEvaluate("git resolved %s to %s, not a commit id" % (display(rev),
                                                                        display(sha)))
    return sha


def head_commit(git, root, env):
    """Return the full id of HEAD's commit, or raise CannotEvaluate when there is none."""
    sha = commit_id(git, root, env, "HEAD", "resolve HEAD")
    if sha is None:
        raise CannotEvaluate("HEAD has no commit, so the repository has no git history to "
                             "compare with a base; commit first, or run the gate in a clone")
    return sha


def resolve_base(git, root, env, base):
    """Return the full id of the base commit: base, or the merge base of HEAD with origin/main."""
    if base is None:
        shallow = run_git(git, root, env, ["rev-parse", "--is-shallow-repository"],
                          "tell whether the repository is shallow").strip()
        if shallow != b"false":
            raise CannotEvaluate("the repository is shallow, so it may not hold the merge base of "
                                 "HEAD with origin/main; fetch the full history or pass --base")
        if commit_id(git, root, env, UPSTREAM, "resolve origin/main") is None:
            raise CannotEvaluate("there is no origin/main (%s), so the default base, the merge "
                                 "base of HEAD with origin/main, cannot be found; fetch "
                                 "origin/main or pass --base" % UPSTREAM)
        out = run_git(git, root, env, ["merge-base", "HEAD", UPSTREAM],
                      "find the merge base of HEAD with origin/main")
        rev = out.decode("ascii", "replace").strip()
    else:
        if not base or base.startswith("-"):
            raise CannotEvaluate("--base %s is not a revision" % display(repr(base)))
        rev = base
    sha = commit_id(git, root, env, rev, "resolve the base %s" % display(rev))
    if sha is None:
        raise CannotEvaluate("git could not resolve the base %s to a commit" % display(rev))
    return sha


def refuse_unmerged(git, root, env):
    """Raise CannotEvaluate when the index holds an unmerged path."""
    out = run_git(git, root, env, ["ls-files", "-u", "-z"], "list the unmerged paths")
    if out:
        first = out.split(b"\0", 1)[0].split(b"\t", 1)[-1].decode("utf-8", "surrogateescape")
        raise CannotEvaluate("%s is unmerged (a merge, rebase or cherry-pick is in progress); "
                             "resolve it first" % display(first))


def changed_pairs(raw):
    """Parse git diff --raw -z output into a list of dicts, one per changed path."""
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    pairs, index = [], 0
    while index < len(fields):
        head = fields[index].decode("ascii", "replace")
        parts = head.split(" ")
        if not head.startswith(":") or len(parts) != 5 or not parts[4]:
            raise CannotEvaluate("unexpected git diff --raw record %s" % display(head[:80]))
        letter = parts[4][0]
        count = 2 if letter in ("R", "C") else 1
        paths = [path.decode("utf-8", "surrogateescape")
                 for path in fields[index + 1:index + 1 + count]]
        if len(paths) != count:
            raise CannotEvaluate("git diff --raw output ends inside a record")
        pairs.append({"status": letter, "old_mode": parts[0][1:], "new_mode": parts[1],
                      "old_sha": parts[2], "new_sha": parts[3], "old": paths[0],
                      "new": paths[-1]})
        index += 1 + count
    return pairs


def added_lines(patch, sections=1, required=None):
    """Return ([(line number, bytes)] of the added lines, whether the new side holds a NUL byte).

    A context line (which a merged hunk, or a diff with the whole file as context, may hold)
    advances the line number and is not returned, but counts toward the NUL test. A patch whose
    number of file sections is not sections, or with a hunk line of no known kind (an empty line
    inside a hunk, which diff.suppressBlankEmpty would make of an empty context line, among them),
    raises CannotEvaluate. With two sections (a type change: a deletion, then an addition), the
    first must add nothing, and the second is the one returned. A patch with no file section
    returns no line, unless required names the file and pass whose diff must hold one: then it
    raises CannotEvaluate naming them.
    """
    found, number, in_hunk = [], 0, False
    lines = patch.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for line in lines:
        if line.startswith(b"diff "):
            found.append([[], False])
            in_hunk = False
            continue
        if line.startswith(b"@@"):
            match = HUNK.match(line)
            if match is None:
                raise CannotEvaluate("unexpected hunk header %s"
                                     % display(line[:80].decode("utf-8", "replace")))
            number, in_hunk = int(match.group(1)), True
            continue
        if not in_hunk or line.startswith((b"-", b"\\")):
            continue
        if line.startswith((b"+", b" ")):
            if line.startswith(b"+"):
                found[-1][0].append((number, line[1:]))
            found[-1][1] = found[-1][1] or b"\0" in line
            number += 1
        else:
            raise CannotEvaluate("unexpected patch line %s"
                                 % display(line[:80].decode("utf-8", "replace")))
    if required is not None and not found:
        raise CannotEvaluate("the diff of %s has no file section, though git lists it as changed "
                             "since the base (a sparse index entry git did not expand, for "
                             "example), so its lines cannot be read" % required)
    if len(found) > sections or (found and len(found) != sections):
        raise CannotEvaluate("the diff of one file has %d file sections" % len(found))
    if sections == 2 and found[0][0]:
        raise CannotEvaluate("the first file section of a type change adds lines")
    return (found[-1][0], found[-1][1]) if found else ([], False)


def width(line):
    """Return the width of one line's bytes, without a final CR: a tab advances to the next stop."""
    if line.endswith(b"\r"):
        line = line[:-1]
    decoded = line.decode("utf-8", "surrogateescape")
    if "\t" not in decoded:
        return len(decoded)
    column = 0
    for char in decoded:
        column += TAB - column % TAB if char == "\t" else 1
    return column


def file_width(data):
    """Return the largest width of any line of data."""
    return max((width(line) for line in data.split(b"\n")), default=0)


def named(path):
    """Return whether path ends in one of the checked suffixes."""
    return path.rsplit("/", 1)[-1].lower().endswith(SUFFIXES)


def checked(path, data):
    """Return whether path, with the bytes data, is a Python, shell, Markdown or TOML file."""
    if named(path):
        return True
    return data is not None and SHEBANG.fullmatch(data.split(b"\n", 1)[0]) is not None


def read_work_file(root, rel):
    """Return the bytes of the regular file rel beneath root, or None when it is not one."""
    path = os.path.join(root, rel)
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CannotEvaluate("%s cannot be read (%s)" % (display(rel), exc.strerror)) from None


def read_blob(git, root, env, sha, what):
    """Return the bytes of the blob sha."""
    return run_git(git, root, env, ["cat-file", "blob", sha], what)


def refuse_conversions(git, root, env, pairs):
    """Raise CannotEvaluate when a filter or working-tree-encoding attribute applies to the new
    path of one of pairs, the work-tree pass's checked files.

    A pair whose new id is null names a file git has not hashed: its stat data does not match the
    index, which the gate does not refresh, or it was added with git add -N. Only the conversion
    could tell whether such a file changed, so the message says that, and how to clear it when the
    file is unchanged and was not added with git add -N.
    """
    if not pairs:
        return
    paths = [pair["new"] for pair in pairs]
    unhashed = {pair["new"] for pair in pairs if NO_BLOB.fullmatch(pair["new_sha"])}
    out = run_git(git, root, env, ["check-attr", "-z", *CONVERSIONS, "--", *paths],
                  "read the attributes of the changed files")
    fields = out.split(b"\0")
    for index in range(0, len(fields) - 2, 3):
        path, name, value = (field.decode("utf-8", "surrogateescape")
                             for field in fields[index:index + 3])
        if value in ("unspecified", "unset"):
            continue
        if path in unhashed:
            raise CannotEvaluate(
                "%s has the %s attribute (%s), and git lists it with no content id (its stat data "
                "does not match the index, or it was added with git add -N), so git has not "
                "hashed it: only that conversion could tell whether it changed, and the gate does "
                "not refresh the index, which would run it; the gate does not check a file whose "
                "content git diffs through a conversion. If it was not added with git add -N and "
                "its content is unchanged (a fresh copy or a cache restore renews stat data), git "
                "update-index -q --refresh clears this: it runs the conversion and updates the "
                "index"
                % (display(path), name, display(value)))
        raise CannotEvaluate(
            "%s has the %s attribute (%s), so the content git diffs is not its work-tree "
            "bytes; the gate does not check such a file" % (display(path), name, display(value)))


def diff_args(whole):
    """Return the options of one file's diff."""
    context = ["-U%d" % WHOLE] if whole else ["-U0", "--inter-hunk-context=0"]
    return ["diff", *context, "-a", "-M", "--no-color", "--no-relative", "--no-ext-diff",
            "--no-textconv", "--ignore-submodules=all"]


def check_file(git, root, env, revs, pair, record, where):
    """Check the added lines of one changed file in the pass where; record adds each finding and
    counts it."""
    status, new = pair["status"], pair["new"]
    limit, why, whole = NEW_FILE_WIDTH, "a file new since the base", True
    if status != "A" and pair["old_mode"] in REGULAR:
        old = read_blob(git, root, env, pair["old_sha"], "read %s at the base"
                        % display(pair["old"]))
        if b"\0" not in old:
            limit, why, whole = max(WIDTH_FLOOR, file_width(old)), "its width at the base", False
    specs = [":(literal)" + path for path in dict.fromkeys((pair["old"], new))]
    patch = run_git(git, root, env, diff_args(whole) + revs + ["--"] + specs,
                    "diff %s against the base" % display(new))
    # A file HEAD or the index changed has two blob ids, so its diff must have a file section; an
    # empty diff would check nothing. The work-tree pass is exempt: since git does not refresh the
    # index (diff.autoRefreshIndex=false), its raw listing names every stat-dirty file, and one
    # whose work-tree content equals the base diffs to nothing. Such a file is not counted. Only an
    # empty diff is skipped: a work-tree diff that deletes lines and adds none is still checked for
    # a NUL byte and counted (R15).
    required = None
    if where != WORK_PASS and pair["old_sha"] != pair["new_sha"]:
        required = "%s in %s" % (display(new), where)
    added, nul = added_lines(patch, 2 if status == "T" else 1, required)
    if where == WORK_PASS and not patch:
        return
    if whole and nul:
        # A NUL byte exempts only a file checked for its shebang alone: no Python, shell, Markdown
        # or TOML file holds one, so for a file its suffix names the NUL byte is a finding, and
        # its lines are checked too.
        if not named(new):
            record("binary", new)
            return
        record("nul", new)
    record("files", 1)
    record("lines", len(added))
    for number, content in added:
        size = width(content)
        if size > limit:
            record("finding", (new, number, size, limit, why))


def pass_revs(where, base, head):
    """Return the revisions the pass where diffs: base against HEAD, the index or the work tree."""
    if where == HEAD_PASS:
        return [base, head]
    if where == INDEX_PASS:
        return ["--cached", base]
    return [base]


def run_pass(git, root, env, base, where, head, record):
    """Check one pass, where (HEAD_PASS, INDEX_PASS or WORK_PASS); head is HEAD's commit id."""
    revs = pass_revs(where, base, head)
    raw = run_git(git, root, env, ["diff", "--raw", "-z", "--no-abbrev", "-M", "--no-relative",
                                   "--ignore-submodules=all", "--no-ext-diff", "--no-textconv",
                                   *revs, "--"],
                  "list the files changed since the base in %s" % where)
    pending = []
    for pair in changed_pairs(raw):
        status, new = pair["status"], pair["new"]
        if status == "D":
            continue
        if status not in ("A", "M", "T", "R", "C"):
            raise CannotEvaluate("%s has status %s (unknown)" % (display(new), status))
        if pair["new_mode"] not in REGULAR:
            continue
        stored = not NO_BLOB.fullmatch(pair["new_sha"])
        if where == WORK_PASS:
            data = read_work_file(root, new)
            if data is None:
                blob = (read_blob(git, root, env, pair["new_sha"], "read %s" % display(new))
                        if stored and not named(new) else None)
                if checked(new, blob):
                    record("missing", new)
                continue
        else:
            data = None if named(new) else read_blob(git, root, env, pair["new_sha"],
                                                    "read %s in %s" % (display(new), where))
        if checked(new, data):
            pending.append(pair)
    if where == WORK_PASS:
        refuse_conversions(git, root, env, pending)
    for pair in pending:
        check_file(git, root, env, revs, pair, record, where)


def evaluate(root, base=None, git=GIT, env=None):
    """Return a dict with the base, the findings and the counts, or raise CannotEvaluate.

    Each finding is (path, line number, width, allowed width, why that width, where), where names
    the passes that saw it, as passes() joins them: "HEAD", "the index and the work tree", or
    "HEAD, the index and the work tree", for example. Each entry of "nul" is (path, where), for a
    file its suffix names as checked whose new content holds a NUL byte where it would otherwise
    be skipped as binary. git runs in git_env(env): env (default os.environ) reduced to
    GIT_ENV_KEEP, with GIT_ENV_SET added.
    """
    env = git_env(env)
    root = work_tree(git, root, env)
    head = head_commit(git, root, env)
    sha = resolve_base(git, root, env, base)
    refuse_unmerged(git, root, env)
    seen, nul, counts, binary, missing = {}, {}, {}, set(), []
    for name in (HEAD_PASS, INDEX_PASS, WORK_PASS):
        counts[name] = {"lines": 0, "files": 0}

        def record(kind, value, name=name):
            if kind == "finding":
                seen.setdefault(value, []).append(name)
            elif kind == "nul":
                nul.setdefault(value, []).append(name)
            elif kind == "binary":
                binary.add(value)
            elif kind == "missing":
                missing.append(value)
            elif kind == "lines":
                counts[name]["lines"] += value
            else:
                counts[name]["files"] += value

        run_pass(git, root, env, sha, name, head, record)
    findings = sorted(key + (passes(names),) for key, names in seen.items())
    return {"base": sha, "head": head, "findings": findings, "missing": sorted(missing),
            "nul": sorted((path, passes(names)) for path, names in nul.items()),
            "counts": counts, "binary": sorted(binary)}


def passes(names):
    """Return the pass names joined for one line: "A", "A and B", or "A, B and C"."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def plural(count, noun):
    """Return count and noun, with an s when count is not one."""
    return "%d %s%s" % (count, noun, "" if count == 1 else "s")


def check(root, base=None, git=GIT, env=None):
    """Return (exit, output lines) for the repository at root."""
    try:
        result = evaluate(root, base, git, env)
    except CannotEvaluate as exc:
        return EXIT_CANNOT, ["%s: CANNOT EVALUATE (%s)" % (GATE, exc)]
    short = result["base"][:12]
    findings, missing, nul = result["findings"], result["missing"], result["nul"]
    if findings or missing or nul:
        parts = ([plural(len(findings), "line") + " wider than allowed"] if findings else []) + (
            [plural(len(nul), "checked file") + " holding a NUL byte"] if nul else []) + (
            [plural(len(missing), "checked file") + " missing from the work tree"]
            if missing else [])
        out = ["%s: FAIL (%s, against base %s)" % (GATE, "; ".join(parts), short)]
        for path, number, size, limit, why, where in findings:
            out.append("  %s:%d: %d columns, wider than %d (%s; in %s)"
                       % (display(path), number, size, limit, why, where))
        for path, where in nul:
            out.append("  %s: holds a NUL byte, which no Python, shell, Markdown or TOML file "
                       "holds, so it is not skipped as binary (in %s)" % (display(path), where))
        for path in missing:
            out.append("  %s: changed since the base, but missing from the work tree or not a "
                       "regular file there, so it cannot be read" % display(path))
        return EXIT_FAIL, out
    counts = result["counts"]
    return EXIT_PASS, ["%s: PASS (%s; checked against base %s; %s)" % (
        GATE, "; ".join("%s: %s changed or added in %s" % (
            name, plural(counts[name]["lines"], "line"), plural(counts[name]["files"], "file"))
            for name in (HEAD_PASS, INDEX_PASS, WORK_PASS)), short,
        plural(len(result["binary"]), "binary file") + " skipped")]


def default_root():
    """Return the parent of this tool's directory, resolved with os.path.realpath."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# The self-test. Every repository it builds is in a temporary directory, with git's global and
# system configuration switched off, so no hook, signing or user setting of the host applies.
# Fixtures are built with fixture_git, which runs git without the gate's own options, so a
# fixture can set up what those options must defeat.

def hermetic_env(home):
    """Return a git environment with no variable of the host but PATH, and a fixed identity."""
    stamp = "2026-01-01T00:00:00Z"
    return {"PATH": os.environ.get("PATH", os.defpath), "HOME": home, "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "line-width self-test", "GIT_AUTHOR_EMAIL": "self-test@invalid",
            "GIT_COMMITTER_NAME": "line-width self-test",
            "GIT_COMMITTER_EMAIL": "self-test@invalid", "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp, "GIT_TERMINAL_PROMPT": "0"}


def fixture_git(env):
    """Return setup(repo, *args), which runs git in repo for a fixture and returns its output."""
    def setup(repo, *args):
        try:
            proc = subprocess.run([GIT, "-C", repo, "-c", "commit.gpgsign=false"] + list(args),
                                  stdin=subprocess.DEVNULL, capture_output=True, env=env,
                                  timeout=GIT_TIMEOUT, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise CannotEvaluate("git could not be run to set up a fixture (%s)" % exc) from None
        if proc.returncode != 0:
            raise CannotEvaluate("git %s failed setting up a fixture (exit %d: %s)" % (
                args[0], proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))
        return proc.stdout
    return setup


def write(root, rel, data):
    """Write data to rel beneath root, creating its directory."""
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def text(*lines):
    """Return the LF-terminated bytes of lines."""
    return "".join(line + "\n" for line in lines).encode("utf-8")


def snapshot(root):
    """Return each path beneath root, .git included: a directory's mtime, a file's mtime and bytes.

    A file created and removed again beneath a directory (a lock file, for example) changes the
    directory's mtime, so it shows too.
    """
    state = {}
    for top, _dirs, files in os.walk(root):
        state[top] = os.lstat(top).st_mtime_ns
        for name in files:
            path = os.path.join(top, name)
            with open(path, "rb") as handle:
                state[path] = (os.lstat(path).st_mtime_ns, handle.read())
    return state


def changed_paths(root, before, after):
    """Return the paths beneath root, relative to it, that differ between two snapshots."""
    return sorted(os.path.relpath(path, root) for path in set(before) | set(after)
                  if before.get(path) != after.get(path))


def unexplained(root, before, after, setup):
    """Return the paths beneath root, relative to it, whose change between two snapshots is not
    one listed below. The list holds every change the Writes paragraph allows git while the gate
    reads the index, and some that the Writes paragraph does not describe.

    Allowed, and nothing else: a new mtime for .git/objects and for a fan-out directory under it
    (two hexadecimal digits); a new mtime, with the same bytes, for a file under .git/objects or
    a .git/sharedindex.* file; a new fan-out directory; and a new file in a fan-out directory,
    when the directory's name and the file's name joined are a full object id (40 or 64 lowercase
    hexadecimal digits) that git cat-file -t reports as a tree (git reads only the type, from a
    pack or from the header of a loose file, the new one included, and nothing checks that the
    new file's bytes hash to that name). Anything else, the mtime of .git (a lock file taken and
    released changes it) or of any other file there, the index changing at all, a work-tree path
    changing, or any path removed, is returned, except that CannotEvaluate is raised, so the
    self-test cannot evaluate, when git cat-file -t fails on such a full object id.
    """
    git_dir = os.path.join(root, ".git")
    objects = os.path.join(git_dir, "objects")
    odd = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        parent = os.path.dirname(path)
        fan_out = parent == objects and re.fullmatch("[0-9a-f]{2}", os.path.basename(path))
        if isinstance(new, int):
            if isinstance(old, int) and (path == objects or fan_out) or old is None and fan_out:
                continue
        elif isinstance(old, tuple) and isinstance(new, tuple):
            if old[1] == new[1] and (path.startswith(objects + os.sep) or parent == git_dir
                                     and os.path.basename(path).startswith("sharedindex.")):
                continue
        elif old is None and new is not None:
            sha = os.path.basename(parent) + os.path.basename(path)
            if os.path.dirname(parent) == objects and re.fullmatch(
                    "[0-9a-f]{2}", os.path.basename(parent)) and SHA.fullmatch(sha) and setup(
                    root, "cat-file", "-t", sha).strip() == b"tree":
                continue
        odd.append(os.path.relpath(path, root))
    return odd


def build_branch_repo(repo, setup):
    """Build the main fixture: a base commit, main moved on, and a branch with changes.

    Returns (base commit, origin/main commit).
    """
    os.makedirs(repo)
    setup(repo, "init", "-q", "-b", "main")
    write(repo, "a.py", text("# a", "a" * 110, "b" * 20, "c" * 20))
    write(repo, "long.md", text("L" * 200, "short"))
    write(repo, "floor.sh", text("#!/bin/sh", "echo hi"))
    write(repo, "moved.toml", text("k = 1", *(letter * 300 for letter in "vuxyz")))
    write(repo, "gone.py", text("g" * 150))
    write(repo, "img", b"#!/bin/sh\n\0" + b"z" * 500 + b"\n")
    write(repo, "base_binary.md", b"\0binary\n")
    setup(repo, "add", "-A")
    setup(repo, "commit", "-q", "-m", "base")
    base = setup(repo, "rev-parse", "HEAD").decode("ascii").strip()
    # main moves on after the branch is cut: a.py gets a 200-character line there.
    write(repo, "a.py", text("# a", "a" * 200, "b" * 20, "c" * 20))
    setup(repo, "commit", "-q", "-a", "-m", "main moves on")
    upstream = setup(repo, "rev-parse", "HEAD").decode("ascii").strip()
    setup(repo, "update-ref", UPSTREAM, upstream)
    setup(repo, "checkout", "-q", "-b", "work", base)
    # Committed on the branch.
    write(repo, "a.py", text("# a", "a" * 110, "B" * 111, "c" * 20))
    write(repo, "long.md", text("L" * 200, "s" * 150, "t" * 201))
    write(repo, "floor.sh", text("#!/bin/sh", "echo hi", "e" * 100, "f" * 101))
    setup(repo, "mv", "moved.toml", "renamed.toml")
    write(repo, "renamed.toml", text("k = 1", *(letter * 300 for letter in "vuxyz"), "w" * 301))
    setup(repo, "rm", "-q", "gone.py")
    write(repo, "img", b"#!/bin/sh\n\0\0" + b"z" * 600 + b"\n")
    write(repo, "base_binary.md", text("q" * 121, "q" * 120))
    write(repo, "new.toml", text("n" * 120, "N" * 121))
    write(repo, "blob", b"#!/bin/sh\nbin\0" + b"z" * 500 + b"\n")
    write(repo, "data.json", text("j" * 500))
    write(repo, "tool", text("#!/usr/bin/env bash", "t" * 130))
    write(repo, "notes", text("n" * 130))
    write(repo, "crlf.py", ("r" * 120 + "\r\n" + "r" * 120 + "\r\n" + "R" * 121 + "\r\n").encode())
    os.symlink("a" * 150, os.path.join(repo, "link.md"))
    setup(repo, "add", "-A")
    setup(repo, "commit", "-q", "-m", "branch changes")
    # Staged only, uncommitted, and untracked.
    write(repo, "staged.md", text("s" * 121))
    setup(repo, "add", "staged.md")
    write(repo, "a.py", text("# a", "a" * 110, "B" * 111, "C" * 112, "D" * 110))
    write(repo, "untracked.py", text("u" * 500))
    return base, upstream


ALL = "HEAD, the index and the work tree"
STAGED = "the index and the work tree"
COMMITTED = "HEAD and the index"
EXPECTED = [
    ("a.py", 3, 111, 110, "its width at the base", ALL),
    ("a.py", 4, 112, 110, "its width at the base", "the work tree"),
    ("base_binary.md", 1, 121, 120, "a file new since the base", ALL),
    ("crlf.py", 3, 121, 120, "a file new since the base", ALL),
    ("floor.sh", 4, 101, 100, "its width at the base", ALL),
    ("long.md", 3, 201, 200, "its width at the base", ALL),
    ("new.toml", 2, 121, 120, "a file new since the base", ALL),
    ("renamed.toml", 7, 301, 300, "its width at the base", ALL),
    ("staged.md", 1, 121, 120, "a file new since the base", STAGED),
    ("tool", 2, 130, 120, "a file new since the base", ALL),
]


def small_repo(tmp, name, setup, files):
    """Build a repository with one base commit of files, origin/main at it, and branch work."""
    repo = os.path.join(tmp, name)
    os.makedirs(repo)
    setup(repo, "init", "-q", "-b", "main")
    for rel, data in files.items():
        write(repo, rel, data)
    setup(repo, "add", "-A")
    setup(repo, "commit", "-q", "-m", "base")
    setup(repo, "update-ref", UPSTREAM, "HEAD")
    setup(repo, "checkout", "-q", "-b", "work")
    return repo


def commit_all(repo, setup, message="change"):
    """Stage everything in repo and commit it."""
    setup(repo, "add", "-A")
    setup(repo, "commit", "-q", "-m", message)


def finding(path, number, size, limit, why, where):
    """Return the output line of one finding."""
    return "  %s:%d: %d columns, wider than %d (%s; in %s)" % (path, number, size, limit, why,
                                                                where)


def self_test():
    """Run every case; return 0 when all pass, 1 when any fails, 2 when it cannot evaluate."""
    total = failures = 0

    def report(ok, label, detail=""):
        nonlocal total, failures
        total += 1
        if not ok:
            failures += 1
            print("  FAIL  %s%s" % (label, (": " + detail) if detail else ""))

    def expect(label, code, needles, result, absent=()):
        got, out = result
        joined = "\n".join(out)
        needles = [needles] if isinstance(needles, str) else needles
        report(got == code and all(needle in joined for needle in needles)
               and not any(item in joined for item in absent), label,
               "expected exit %d with %r and without %r, got exit %d: %s"
               % (code, needles, list(absent), got, joined))

    for version, expected in (((3, 13, 9), 2), ((3, 14, 0), 0), ((3, 15, 1), 0)):
        report(python_gate(version) == expected, "Python %d.%d.%d floor" % version)

    report(width(b"x" * 7 + b"\r") == 7, "a final CR is not counted")
    report(width(b"\xff\xfeab") == 4, "an undecodable byte counts as one character")
    report(width("été".encode()) == 3, "a character, not a byte, is one unit")
    report(width(b"\t") == 8 and width(b"abc\td") == 9 and width(b"12345678\tx") == 17,
           "a tab advances to the next multiple of 8")
    report(file_width(text("ab", "abcd", "")) == 4, "a file's width is its widest line")
    for path, data, want in (("x.PY", b"", True), ("d/x.toml", b"", True), ("x.md", b"", True),
                             ("x.json", b"{}\n", False), ("x.cgi", b"#!/bin/sh\n", True),
                             ("run", b"#!/bin/sh\n", True), ("run", b"#!/bin/shell\n", False),
                             ("run", b"#!/usr/bin/env -S python3 -I\n", True),
                             ("run", b"#!/usr/bin/python3.14\r\n", True),
                             ("run", b"#!/usr/bin/env node\n", False), ("run", b"plain\n", False),
                             ("run", None, False)):
        report(checked(path, data) is want, "classification of %s %r" % (path, (data or b"")[:30]))
    merged = (b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -2,3 +2,4 @@ ctx\n-old\n+new\n"
              b" same\n+added\n\\ No newline at end of file\n@@ -9,0 +10 @@\n+tail\n")
    report(added_lines(merged) == ([(2, b"new"), (4, b"added"), (10, b"tail")], False),
           "a merged hunk's context line advances the line number and is not checked",
           repr(added_lines(merged)))
    report(added_lines(b"diff --git a/x b/x\n@@ -1 +1,2 @@\n \0ctx\n+new\n")[1] is True,
           "a context line holding a NUL makes the new side binary")
    typed = (b"diff --git a/x b/x\ndeleted file mode 120000\n@@ -1 +0,0 @@\n-target\n"
             b"diff --git a/x b/x\nnew file mode 100644\n@@ -0,0 +1 @@\n+line\n")
    report(added_lines(typed, 2) == ([(1, b"line")], False),
           "a type change's addition section is the one checked", repr(added_lines(typed, 2)))
    for label, patch, sections in (
            ("two file sections", b"diff --git a/x b/x\ndiff --git a/y b/y\n", 1),
            ("one file section for a type change", b"diff --git a/x b/x\n@@ -1 +1 @@\n+x\n", 2),
            ("a type change whose first section adds",
             b"diff --git a/x b/x\n@@ -0,0 +1 @@\n+x\ndiff --git a/x b/x\n", 2),
            ("an unknown hunk line", b"@@ -1 +1 @@\n?odd\n", 1),
            ("an empty line inside a hunk",
             b"diff --git a/x b/x\n@@ -1,2 +1,3 @@\n\n+x\n same\n", 1),
            ("a malformed hunk header", b"@@ -x +1 @@\n", 1)):
        try:
            added_lines(patch, sections)
            report(False, "a patch with %s cannot be evaluated" % label)
        except CannotEvaluate:
            report(True, label)
    report(added_lines(b"") == ([], False), "an empty patch adds no line when none is required")
    try:
        added_lines(b"", 1, "x.md in the index")
        report(False, "an empty patch where a file section is required cannot be evaluated")
    except CannotEvaluate as exc:
        report("x.md in the index" in str(exc),
               "an empty patch where a file section is required cannot be evaluated", str(exc))
    caller = {"PATH": "/p", "HOME": "/h", "GIT_DIR": "/d", "GIT_WORK_TREE": "/w",
              "GIT_INDEX_FILE": "/i", "GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_COUNT": "1",
              "GIT_CONFIG_KEY_0": "diff.external", "GIT_CONFIG_VALUE_0": "true",
              "GIT_ATTR_SOURCE": "HEAD", "GIT_EXTERNAL_DIFF": "true", "LANG": "de_DE.UTF-8",
              "LC_ALL": "de_DE.UTF-8", "XDG_CONFIG_HOME": "/x"}
    want = {"PATH": "/p", "HOME": "/h", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
    # The fixtures test what GIT_CONFIG_GLOBAL, GIT_CONFIG_NOSYSTEM, GIT_NO_LAZY_FETCH and
    # GIT_NO_REPLACE_OBJECTS do. GIT_ATTR_NOSYSTEM is pinned by this exact comparison alone: git
    # reads the system attributes file from a path fixed when git is built, which no variable
    # moves, so a fixture could not set one up without writing outside its temporary directory.
    report(git_env(caller) == want, "git's environment keeps only PATH and HOME of the caller's",
           repr(git_env(caller)))

    try:
        with tempfile.TemporaryDirectory(prefix="line-width-self-test.") as tmp:
            env = hermetic_env(tmp)
            setup = fixture_git(env)

            repo = os.path.join(tmp, "repo")
            base, upstream = build_branch_repo(repo, setup)

            result = evaluate(repo, None, GIT, env)
            report(result["base"] == base, "the default base is the merge base with origin/main",
                   "got %s, want %s" % (result["base"], base))
            report(result["findings"] == EXPECTED,
                   "the findings: long changed lines, new files, a rename, the floor, committed, "
                   "staged and unstaged changes", repr(result["findings"]))
            report(result["binary"] == ["blob", "img"],
                   "binary files checked for their shebang alone are skipped",
                   repr(result["binary"]))
            report(result["nul"] == [], "no file named as checked holds a NUL byte",
                   repr(result["nul"]))
            flagged = {found[:2] for found in result["findings"]}
            for path, number, label in (
                    ("long.md", 1, "a long unchanged line"),
                    ("renamed.toml", 2, "an unchanged long line of a renamed file"),
                    ("a.py", 5, "a changed line exactly as wide as the file's width"),
                    ("floor.sh", 3, "a changed line exactly at the 100 floor"),
                    ("new.toml", 1, "a new file's line exactly 120 wide"),
                    ("crlf.py", 1, "a CRLF line 120 wide")):
                report((path, number) not in flagged, label + " is not flagged")
            for path in ("blob", "img", "data.json", "notes", "untracked.py", "link.md",
                         "gone.py"):
                report(all(found[0] != path for found in result["findings"]),
                       "%s is not checked" % path)
            report(result["counts"] == {HEAD_PASS: {"lines": 15, "files": 8},
                                        INDEX_PASS: {"lines": 16, "files": 9},
                                        WORK_PASS: {"lines": 18, "files": 9}},
                   "every added line of every checked file is counted in each pass",
                   repr(result["counts"]))
            explicit = evaluate(repo, base, GIT, env)
            report(explicit["findings"] == EXPECTED, "--base with the fork commit gives the same")
            moved = evaluate(repo, "refs/remotes/origin/main", GIT, env)
            report([found for found in moved["findings"] if found[0] == "a.py"] == []
                   and moved["base"] == upstream,
                   "against origin/main itself, a.py's base width is the 200 main gave it",
                   repr(moved["findings"]))
            expect("the branch fails", EXIT_FAIL,
                   finding("a.py", 3, 111, 110, "its width at the base", ALL),
                   check(repo, None, GIT, env))

            clean = os.path.join(tmp, "clean")
            os.makedirs(clean)
            setup(clean, "init", "-q", "-b", "main")
            write(clean, "c.py", text("x" * 130))
            setup(clean, "add", "-A")
            setup(clean, "commit", "-q", "-m", "only")
            expect("no origin/main: the default base cannot be found", EXIT_CANNOT,
                   "there is no origin/main", check(clean, None, GIT, env))
            setup(clean, "update-ref", UPSTREAM, "HEAD")
            expect("a clean branch passes", EXIT_PASS,
                   "line-width: PASS (HEAD: 0 lines changed or added in 0 files; the index: 0 "
                   "lines changed or added in 0 files; the work tree: 0 lines",
                   check(clean, None, GIT, env))
            write(clean, "c.py", text("x" * 130, "y" * 130))
            expect("an added line as wide as the file's long line passes", EXIT_PASS,
                   "the index: 0 lines changed or added in 0 files; the work tree: 1 line changed "
                   "or added in 1 file", check(clean, None, GIT, env))

            blob = setup(repo, "rev-parse", "HEAD:a.py").decode("ascii").strip()
            for label, rev, needle in (
                    ("an unknown --base", "no-such-revision", "resolve the base"),
                    ("a --base that starts with -", "-n", "is not a revision"),
                    ("an empty --base", "", "is not a revision"),
                    ("a --base that names a blob", blob, "resolve the base")):
                expect(label + " cannot be evaluated", EXIT_CANNOT, needle,
                       check(repo, rev, GIT, env))
            plain = os.path.join(tmp, "plain")
            os.makedirs(plain)
            expect("a directory with no git history", EXIT_CANNOT,
                   ["has no git history", "not in a git work tree"],
                   check(plain, None, GIT, env))
            unborn = os.path.join(tmp, "unborn")
            os.makedirs(unborn)
            setup(unborn, "init", "-q", "-b", "main")
            write(unborn, "u.md", text("u"))
            setup(unborn, "add", "-A")
            expect("a repository with no commit", EXIT_CANNOT, "HEAD has no commit",
                   check(unborn, None, GIT, env))
            subdirectory = os.path.join(repo, "sub")
            os.makedirs(subdirectory)
            expect("a subdirectory of a work tree", EXIT_CANNOT, "not the top of a git work tree",
                   check(subdirectory, None, GIT, env))
            expect("git that cannot be run", EXIT_CANNOT, "git could not be run",
                   check(repo, None, os.path.join(tmp, "no-such-git"), env))

            shallow = os.path.join(tmp, "shallow")
            setup(tmp, "clone", "-q", "--depth", "1", "--no-local", "file://" + repo, shallow)
            expect("a shallow clone with the default base", EXIT_CANNOT, "shallow",
                   check(shallow, None, GIT, env))

            broken = os.path.join(tmp, "broken")
            shutil.copytree(repo, broken, symlinks=True)
            old = setup(broken, "rev-parse", base + ":a.py").decode("ascii").strip()
            os.unlink(os.path.join(broken, ".git", "objects", old[:2], old[2:]))
            expect("a base whose blob cannot be read", EXIT_CANNOT, "git could not",
                   check(broken, None, GIT, env))

            fixtures(tmp, env, setup, report, expect)

            tool = os.path.abspath(__file__)
            decoy = dict(env, GIT_DIR=os.path.join(clean, ".git"), GIT_WORK_TREE=clean,
                         GIT_INDEX_FILE=os.path.join(clean, ".git", "index"),
                         GIT_EXTERNAL_DIFF="true", GIT_CONFIG_PARAMETERS="'diff.external'='true'")
            for label, args, code, needle, run_env in (
                    ("command line, a failing branch", ["--root", repo], EXIT_FAIL,
                     "a.py:4: 112 columns", env),
                    ("command line, caller variables pointing git at a decoy repository are "
                     "dropped", ["--root", repo], EXIT_FAIL, "a.py:4: 112 columns", decoy),
                    ("command line, a passing branch", ["--root", clean], EXIT_PASS, "PASS", env),
                    ("command line, an unknown base", ["--root", repo, "--base", "nope"],
                     EXIT_CANNOT, "CANNOT EVALUATE", env),
                    ("command line, --self-test with --base", ["--self-test", "--base", "x"],
                     EXIT_CANNOT, "does not take", env)):
                proc = subprocess.run([sys.executable, "-I", "-B", tool] + args, env=run_env,
                                      stdin=subprocess.DEVNULL, capture_output=True,
                                      timeout=GIT_TIMEOUT)
                out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
                report(proc.returncode == code and needle in out, label,
                       "exit %d: %s" % (proc.returncode, out.strip()))
    except (OSError, subprocess.SubprocessError, CannotEvaluate) as exc:
        print("%s self-test: CANNOT EVALUATE (%s)" % (GATE, exc))
        return EXIT_CANNOT

    if failures:
        print("%s self-test: FAIL (%d of %d checks failed)" % (GATE, failures, total))
        return EXIT_FAIL
    print("%s self-test: PASS (%d of %d checks)" % (GATE, total, total))
    return EXIT_PASS


def fixtures(tmp, env, setup, report, expect):
    """The fixtures for the controls that the main repository cannot observe."""
    at_base = "its width at the base"
    new_file = "a file new since the base"
    wide = text("# doc", "x" * 300)

    # A NUL byte does not make a file that was text at the base binary, committed or not. A file
    # its suffix names as checked that was not text at the base and holds a NUL now is a finding,
    # and its lines are checked against 120: a new file (N1), a staged new file, and a file binary
    # at the base whose NUL line is unchanged. Only a file checked for its shebang alone is skipped:
    # a staged new one, and one binary at the base whose NUL line is unchanged, which only a diff
    # with the whole file as context shows.
    repo = small_repo(tmp, "nul", setup, {
        "doc.md": text("# doc"), "work.md": text("# work"), "kept.md": b"\0\nkeep\n",
        "run-kept": b"#!/bin/sh\n\0\nkeep\n"})
    write(repo, "doc.md", b"# doc\n<!-- \0 -->\n" + b"x" * 300 + b"\n")
    write(repo, "new.md", b"# new\n<!-- \0 -->\n" + b"x" * 300 + b"\n")
    write(repo, "kept.md", b"\0\nkeep\n" + b"k" * 130 + b"\n")
    write(repo, "run-kept", b"#!/bin/sh\n\0\nkeep\n" + b"k" * 130 + b"\n")
    commit_all(repo, setup)
    write(repo, "work.md", b"# work\n<!-- \0 -->\n" + b"y" * 300 + b"\n")
    write(repo, "newbin.md", b"\0" + b"n" * 300 + b"\n")
    write(repo, "run-new", b"#!/bin/sh\n\0" + b"n" * 300 + b"\n")
    setup(repo, "add", "newbin.md", "run-new")
    result = evaluate(repo, None, GIT, env)
    report(result["findings"] == [("doc.md", 3, 300, 100, at_base, ALL),
                                  ("kept.md", 3, 130, 120, new_file, ALL),
                                  ("new.md", 3, 300, 120, new_file, ALL),
                                  ("newbin.md", 1, 301, 120, new_file, STAGED),
                                  ("work.md", 3, 300, 100, at_base, "the work tree")],
           "a NUL byte exempts no line of a file named as checked", repr(result["findings"]))
    report(result["nul"] == [("kept.md", ALL), ("new.md", ALL), ("newbin.md", STAGED)],
           "a file named as checked holding a NUL byte is a finding", repr(result["nul"]))
    report(result["binary"] == ["run-kept", "run-new"],
           "a file checked for its shebang alone holding a NUL byte is skipped as binary, even "
           "when its NUL line is unchanged", repr(result["binary"]))
    expect("N1: a new Markdown file holding a NUL byte fails", EXIT_FAIL,
           ["new.md: holds a NUL byte", finding("new.md", 3, 300, 120, new_file, ALL),
            "3 checked files holding a NUL byte"],
           check(repo, None, GIT, env), absent=["run-kept", "run-new", "doc.md: holds"])

    # A NUL byte is a failure on its own: a new Markdown file holding one, every line narrow (R1).
    repo = small_repo(tmp, "nul-only", setup, {"doc.md": text("# doc")})
    write(repo, "narrow.md", b"# n\n<!-- \0 -->\nshort\n")
    commit_all(repo, setup)
    expect("R1: a NUL byte fails a new Markdown file whose lines are all narrow", EXIT_FAIL,
           ["narrow.md: holds a NUL byte", "1 checked file holding a NUL byte"],
           check(repo, None, GIT, env), absent=["wider than allowed"])

    # A committed working-tree-encoding attribute makes the work tree UTF-16, but does not exempt
    # the file: the gate cannot evaluate it.
    repo = small_repo(tmp, "encoding", setup, {"doc.md": text("# doc")})
    write(repo, ".gitattributes", text("doc.md working-tree-encoding=UTF-16LE"))
    write(repo, "doc.md", wide.decode("ascii").encode("utf-16-le"))
    commit_all(repo, setup)
    expect("a committed working-tree-encoding attribute does not exempt a file", EXIT_CANNOT,
           "doc.md has the working-tree-encoding attribute", check(repo, None, GIT, env))

    # The HEAD pass: a long line committed on the branch fails, whatever the work tree holds.
    repo = small_repo(tmp, "committed", setup, {"doc.md": text("# doc")})
    write(repo, "doc.md", wide)
    commit_all(repo, setup)
    head_only = finding("doc.md", 2, 300, 100, at_base, COMMITTED)
    os.unlink(os.path.join(repo, "doc.md"))
    expect("a committed long line, the work-tree file deleted", EXIT_FAIL, head_only,
           check(repo, None, GIT, env))
    write(repo, "doc.md", text("# doc"))
    expect("a committed long line, the work tree reverted to the base", EXIT_FAIL, head_only,
           check(repo, None, GIT, env))
    write(repo, "doc.md", wide)
    setup(repo, "update-index", "--skip-worktree", "doc.md")
    os.unlink(os.path.join(repo, "doc.md"))
    expect("a committed long line, the file skip-worktree and absent", EXIT_FAIL,
           [head_only, "doc.md: changed since the base, but missing from the work tree"],
           check(repo, None, GIT, env))

    # Replace refs are ignored: a replacement of the committed blob does not hide its line.
    repo = small_repo(tmp, "replace", setup, {"doc.md": text("# doc")})
    write(repo, "doc.md", wide)
    commit_all(repo, setup)
    long_blob = setup(repo, "rev-parse", "HEAD:doc.md").decode("ascii").strip()
    short_blob = setup(repo, "rev-parse", "HEAD~1:doc.md").decode("ascii").strip()
    setup(repo, "replace", long_blob, short_blob)
    write(repo, "doc.md", text("# doc"))
    expect("a replace ref does not hide a committed line", EXIT_FAIL, head_only,
           check(repo, None, GIT, env))

    # The index pass: a long line staged, then the work tree reverted to the base text (N26).
    repo = small_repo(tmp, "staged", setup, {"doc.md": text("# doc")})
    write(repo, "doc.md", wide)
    setup(repo, "add", "doc.md")
    write(repo, "doc.md", text("# doc"))
    expect("N26: a staged long line the work tree no longer holds fails", EXIT_FAIL,
           finding("doc.md", 2, 300, 100, at_base, "the index"), check(repo, None, GIT, env))

    # The gate does not refresh the index (diff.autoRefreshIndex=false), so the work-tree pass
    # lists every stat-dirty file. A long line staged, the work tree reverted to the base text, and
    # an unchanged tracked file made stat-dirty: both diff to nothing in the work tree, which is
    # exempt from the empty-diff guard, so the index finding stands alone and no file is counted
    # in the work tree (R10). In this repository (no sparse or split index) the run changes no
    # path: the index is byte-identical with the same mtime, and no other path beneath the root
    # changes (R11).
    repo = small_repo(tmp, "stat-dirty", setup, {"doc.md": text("# doc"), "t.md": text("t")})
    write(repo, "doc.md", wide)
    setup(repo, "add", "doc.md")
    write(repo, "doc.md", text("# doc"))
    os.utime(os.path.join(repo, "t.md"), (1, 1))
    listed = setup(repo, "-c", "diff.autoRefreshIndex=false", "diff", "--name-only", "-z",
                   UPSTREAM, "--")
    report(listed.split(b"\0") == [b"doc.md", b"t.md", b""],
           "R10: without a refresh, the work tree lists the reverted and the stat-dirty file",
           repr(listed))
    index = os.path.join(repo, ".git", "index")
    before = snapshot(repo)
    expect("R10: a stat-dirty file and a reverted file diff to nothing in the work tree",
           EXIT_FAIL, finding("doc.md", 2, 300, 100, at_base, "the index"),
           check(repo, None, GIT, env), absent=["CANNOT EVALUATE", "in the work tree"])
    after = snapshot(repo)
    report(after[index] == before[index],
           "R11: a run leaves .git/index byte-identical with the same mtime",
           "mtime %d to %d, bytes %s" % (before[index][0], after[index][0],
                                         "same" if after[index][1] == before[index][1]
                                         else "changed"))
    report(after == before, "R11: a run writes no path beneath the root",
           repr(changed_paths(repo, before, after)))
    counts = evaluate(repo, None, GIT, env)["counts"]
    report(counts[WORK_PASS] == {"lines": 0, "files": 0} and
           counts[INDEX_PASS] == {"lines": 1, "files": 1},
           "R10: a file that diffs to nothing in the work tree is not counted there",
           repr(counts))

    # The work-tree skip fires for an empty diff only, not for a diff that adds no line (R15). A
    # Markdown file binary at the base that loses a line in the work tree alone still holds its
    # NUL byte, which is a finding there; a file whose work-tree change only deletes a line is
    # counted, with no line.
    repo = small_repo(tmp, "work-delete", setup, {"bin.md": b"\0one\ntwo\nthree\n",
                                                   "del.md": text("one", "two", "three")})
    write(repo, "bin.md", b"\0one\nthree\n")
    write(repo, "del.md", text("one", "three"))
    expect("R15: a work-tree diff that adds no line to a file holding a NUL byte fails",
           EXIT_FAIL, ["  bin.md: holds a NUL byte, which no Python, shell, Markdown or TOML file "
                       "holds, so it is not skipped as binary (in the work tree)",
                       "1 checked file holding a NUL byte"],
           check(repo, None, GIT, env), absent=["wider than allowed"])
    result = evaluate(repo, None, GIT, env)
    report(result["nul"] == [("bin.md", "the work tree")]
           and result["counts"][WORK_PASS] == {"lines": 0, "files": 2},
           "R15: a work-tree diff that only deletes lines is checked and counted",
           repr((result["nul"], result["counts"])))

    # The work-tree pass: a changed file missing from the work tree, or not a regular file there,
    # named as checked or checked for its shebang alone (N33).
    repo = small_repo(tmp, "sparse", setup, {"doc.md": text("# doc"), "keep.md": text("k"),
                                              "run": text("#!/bin/sh", "echo a")})
    write(repo, "doc.md", text("# doc", "more"))
    write(repo, "run", text("#!/bin/sh", "echo a", "echo b"))
    setup(repo, "add", "doc.md", "run")
    setup(repo, "update-index", "--skip-worktree", "doc.md", "run")
    os.unlink(os.path.join(repo, "doc.md"))
    os.unlink(os.path.join(repo, "run"))
    missing = "doc.md: changed since the base, but missing from the work tree"
    expect("a staged change to a skip-worktree file missing from the work tree", EXIT_FAIL,
           [missing, "run: changed since the base, but missing from the work tree",
            "2 checked files missing"], check(repo, None, GIT, env))
    os.symlink("keep.md", os.path.join(repo, "doc.md"))
    expect("a staged change to a skip-worktree file that is a symlink in the work tree",
           EXIT_FAIL, missing, check(repo, None, GIT, env))

    # Tabs advance to the next multiple of 8.
    repo = small_repo(tmp, "tabs", setup, {"x.py": text("x = 0")})
    write(repo, "x.py", text("x = 0", "\t" * 60 + "x = 1"))
    commit_all(repo, setup)
    expect("a line of 60 tabs is 485 columns", EXIT_FAIL,
           finding("x.py", 2, 485, 100, at_base, ALL), check(repo, None, GIT, env))

    # Type changes: a symlink or a submodule at the base, a regular file now. One such file
    # holds a NUL byte (N2): it is a finding, not skipped.
    repo = os.path.join(tmp, "types")
    os.makedirs(repo)
    setup(repo, "init", "-q", "-b", "main")
    os.symlink("t" * 150, os.path.join(repo, "link.md"))
    os.symlink("link.md", os.path.join(repo, "nul-link.md"))
    setup(repo, "add", "-A")
    setup(repo, "update-index", "--add", "--cacheinfo", "160000,%s,sub.md" % ("1" * 40))
    setup(repo, "commit", "-q", "-m", "base")
    setup(repo, "update-ref", UPSTREAM, "HEAD")
    setup(repo, "checkout", "-q", "-b", "work")
    os.unlink(os.path.join(repo, "link.md"))
    write(repo, "link.md", text("l" * 130))
    os.unlink(os.path.join(repo, "nul-link.md"))
    write(repo, "nul-link.md", b"# new\n<!-- \0 -->\n" + b"x" * 300 + b"\n")
    setup(repo, "rm", "-q", "--cached", "sub.md")
    write(repo, "sub.md", text("s" * 121))
    commit_all(repo, setup)
    expect("a symlink or a submodule at the base, a regular file now, is a new file", EXIT_FAIL,
           [finding("link.md", 1, 130, 120, new_file, ALL),
            finding("sub.md", 1, 121, 120, new_file, ALL),
            finding("nul-link.md", 3, 300, 120, new_file, ALL),
            "nul-link.md: holds a NUL byte"], check(repo, None, GIT, env))

    # An unmerged path: git diff reports it as M, so git ls-files -u decides.
    repo = small_repo(tmp, "unmerged", setup, {"m.md": text("a")})
    setup(repo, "checkout", "-q", "-b", "other")
    write(repo, "m.md", text("b"))
    commit_all(repo, setup)
    setup(repo, "checkout", "-q", "work")
    write(repo, "m.md", text("c"))
    commit_all(repo, setup)
    try:
        setup(repo, "merge", "-q", "other")
    except CannotEvaluate:
        pass
    expect("an unmerged path cannot be evaluated", EXIT_CANNOT, "m.md is unmerged",
           check(repo, None, GIT, env))

    # A file named *.md next to a.md: each pathspec is literal.
    repo = small_repo(tmp, "literal", setup, {"a.md": text("a"), "*.md": text("star")})
    write(repo, "a.md", text("a", "a" * 130))
    write(repo, "*.md", text("star", "s" * 130))
    commit_all(repo, setup)
    expect("a file named *.md is diffed alone", EXIT_FAIL,
           [finding("*.md", 2, 130, 100, at_base, ALL),
            finding("a.md", 2, 130, 100, at_base, ALL)], check(repo, None, GIT, env))

    # diff.renames=false in the repository: -M still pairs the rename.
    repo = small_repo(tmp, "renames", setup,
                      {"m.toml": text("k = 1", *(letter * 300 for letter in "vuxyz"))})
    setup(repo, "config", "diff.renames", "false")
    setup(repo, "mv", "m.toml", "n.toml")
    write(repo, "n.toml", text("k = 1", *(letter * 300 for letter in "vuxyz"), "w" * 301))
    commit_all(repo, setup)
    expect("diff.renames=false does not stop rename detection", EXIT_FAIL,
           finding("n.toml", 7, 301, 300, at_base, ALL), check(repo, None, GIT, env),
           absent=["n.toml:2:"])

    # diff.suppressBlankEmpty=true in the repository would write an empty context line without
    # its leading space; the gate turns it off, so line numbers stay right (N3). Without the
    # setting, an empty context line before the wide line advances the line number too (N3b).
    for name, suppress in (("suppress-blank", True), ("blank-context", False)):
        repo = small_repo(tmp, name, setup, {"x.md": b"\0\n\nkeep\n"})
        if suppress:
            setup(repo, "config", "diff.suppressBlankEmpty", "true")
        write(repo, "x.md", b"\n\nkeep\n" + b"w" * 130 + b"\n")
        commit_all(repo, setup)
        expect("%s: an empty context line advances the line number"
               % ("N3, diff.suppressBlankEmpty=true" if suppress else "N3b"), EXIT_FAIL,
               finding("x.md", 4, 130, 120, new_file, ALL), check(repo, None, GIT, env),
               absent=["x.md:3:"])

    # A repository-local external diff and textconv driver that would hide every line.
    repo = small_repo(tmp, "drivers", setup, {"hidden.md": text("h"), "plain.md": text("p")})
    setup(repo, "config", "diff.external", "true")
    setup(repo, "config", "diff.hide.textconv", "true")
    write(repo, ".git/info/attributes", text("hidden.md diff=hide"))
    write(repo, "hidden.md", text("h", "h" * 130))
    write(repo, "plain.md", text("p", "p" * 130))
    commit_all(repo, setup)
    expect("an external diff and a textconv driver hide no line", EXIT_FAIL,
           [finding("hidden.md", 2, 130, 100, at_base, ALL),
            finding("plain.md", 2, 130, 100, at_base, ALL)], check(repo, None, GIT, env))

    # An fsmonitor hook that reports no change would hide an unstaged edit.
    repo = small_repo(tmp, "fsmonitor", setup, {"doc.md": text("# doc")})
    hook = os.path.join(tmp, "fsmonitor-hook")
    write(tmp, "fsmonitor-hook", b"#!/bin/sh\nprintf 'token\\0'\n")
    os.chmod(hook, 0o755)
    setup(repo, "config", "core.fsmonitor", hook)
    setup(repo, "config", "core.fsmonitorHookVersion", "2")
    setup(repo, "update-index", "--fsmonitor")
    setup(repo, "status", "--porcelain")
    write(repo, "doc.md", wide)
    expect("an fsmonitor hook does not hide an unstaged edit", EXIT_FAIL,
           finding("doc.md", 2, 300, 100, at_base, "the work tree"), check(repo, None, GIT, env))

    # A filter attribute on a changed checked file: the gate cannot evaluate it.
    repo = small_repo(tmp, "filter", setup, {"doc.md": text("# doc")})
    setup(repo, "config", "filter.cut.clean", "cut -c1-50")
    write(repo, ".git/info/attributes", text("*.md filter=cut"))
    write(repo, "doc.md", wide)
    expect("a clean filter on a changed checked file cannot be evaluated", EXIT_CANNOT,
           "doc.md has the filter attribute", check(repo, None, GIT, env))

    # An unchanged checked file with a filter attribute that is only stat-dirty (R16). git has not
    # hashed it, and only the filter could tell whether it changed, so the gate cannot evaluate
    # it; the message names that cause and the remedy. After git update-index -q --refresh the
    # file is no longer listed, and the gate passes.
    repo = small_repo(tmp, "filter-stat-dirty", setup,
                      {"a.md": text("# a"), ".gitattributes": text("*.md filter=noop")})
    setup(repo, "config", "filter.noop.clean", "cat")
    setup(repo, "config", "filter.noop.smudge", "cat")
    os.utime(os.path.join(repo, "a.md"), (1, 1))
    expect("R16: an unchanged, stat-dirty file with a filter names the cause and the remedy",
           EXIT_CANNOT, ["a.md has the filter attribute (noop), and git lists it with no content "
                         "id (its stat data does not match the index, or it was added with git "
                         "add -N), so git has not hashed it",
                         "If it was not added with git add -N and its content is unchanged",
                         "git update-index -q --refresh clears this"],
           check(repo, None, GIT, env), absent=["is not its work-tree bytes"])
    setup(repo, "update-index", "-q", "--refresh")
    expect("R16: after git update-index -q --refresh, the unchanged file with a filter passes",
           EXIT_PASS, "line-width: PASS", check(repo, None, GIT, env))

    # A file with a filter attribute that git has hashed (R18): a wide line staged, the work tree
    # equal to the index, and the index refreshed, so git lists the file with its content id. The
    # message names the conversion, not stat data.
    repo = small_repo(tmp, "filter-hashed", setup,
                      {"a.md": text("# a"), ".gitattributes": text("*.md filter=noop")})
    setup(repo, "config", "filter.noop.clean", "cat")
    setup(repo, "config", "filter.noop.smudge", "cat")
    write(repo, "a.md", wide)
    setup(repo, "add", "a.md")
    setup(repo, "update-index", "-q", "--refresh")
    expect("R18: a hashed file with a filter is refused for the conversion, not its stat data",
           EXIT_CANNOT, "a.md has the filter attribute (noop), so the content git diffs is not "
           "its work-tree bytes", check(repo, None, GIT, env), absent=["stat data does not match"])

    # A file with a filter attribute added with git add -N (R19): git lists it with no content id
    # whatever its stat data, so git update-index -q --refresh does not clear it. The message
    # names that cause, and scopes the remedy to a file not added with git add -N.
    repo = small_repo(tmp, "filter-intent-to-add", setup,
                      {"a.md": text("# a"), ".gitattributes": text("*.md filter=noop")})
    setup(repo, "config", "filter.noop.clean", "cat")
    setup(repo, "config", "filter.noop.smudge", "cat")
    write(repo, "n.md", text("# n"))
    setup(repo, "add", "-N", "n.md")
    intent = ["n.md has the filter attribute (noop), and git lists it with no content id (its "
              "stat data does not match the index, or it was added with git add -N)",
              "If it was not added with git add -N"]
    expect("R19: a file with a filter added with git add -N names that cause", EXIT_CANNOT,
           intent, check(repo, None, GIT, env))
    setup(repo, "update-index", "-q", "--refresh")
    expect("R19: git update-index -q --refresh does not clear a file added with git add -N",
           EXIT_CANNOT, intent, check(repo, None, GIT, env))

    # The user's attributes file (HOME/.config/git/attributes) is not read.
    repo = small_repo(tmp, "home-attributes", setup, {"doc.md": text("# doc")})
    setup(repo, "config", "filter.cut.clean", "cut -c1-50")
    home = os.path.join(tmp, "home")
    write(home, os.path.join(".config", "git", "attributes"), text("*.md filter=cut"))
    write(repo, "doc.md", wide)
    expect("the user's attributes file is not read", EXIT_FAIL,
           finding("doc.md", 2, 300, 100, at_base, "the work tree"),
           check(repo, None, GIT, dict(env, HOME=home)))

    # git reads neither the global nor the system configuration. The configuration below holds
    # P10's clean filter and attributes file, then a malformed line, so every git command fails if
    # it reads the file at all. A command-line run points HOME's .gitconfig and the caller's
    # GIT_CONFIG_GLOBAL at it (GIT_CONFIG_GLOBAL=/dev/null defeats both); a wrapper points
    # GIT_CONFIG_SYSTEM at it, as a host's git finds /etc/gitconfig (GIT_CONFIG_NOSYSTEM=1
    # defeats it).
    repo = small_repo(tmp, "host-config", setup, {"doc.md": text("# doc")})
    write(repo, "doc.md", wide)
    host = os.path.join(tmp, "host-home")
    write(host, "attributes", text("*.md filter=cut"))
    config = os.path.join(host, ".gitconfig")
    write(host, ".gitconfig", text('[filter "cut"]', "\tclean = cut -c1-50", "[core]",
                                   "\tattributesFile = " + os.path.join(host, "attributes"),
                                   "[malformed"))
    work_line = finding("doc.md", 2, 300, 100, at_base, "the work tree")
    proc = subprocess.run([sys.executable, "-I", "-B", os.path.abspath(__file__), "--root", repo],
                          env=dict(env, HOME=host, GIT_CONFIG_GLOBAL=config),
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=GIT_TIMEOUT)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    report(proc.returncode == EXIT_FAIL and work_line in out,
           "command line, the global configuration (HOME and GIT_CONFIG_GLOBAL) is not read",
           "exit %d: %s" % (proc.returncode, out.strip()))
    real = shutil.which(GIT, path=env["PATH"]) or GIT
    system_git = os.path.join(tmp, "system-git")
    write(tmp, "system-git", (
        "#!%s -I\nimport os, sys\nos.environ['GIT_CONFIG_SYSTEM'] = %r\n"
        "os.execv(%r, [%r] + sys.argv[1:])\n" % (sys.executable, config, real, real)).encode())
    os.chmod(system_git, 0o755)
    expect("the system configuration is not read", EXIT_FAIL, work_line,
           check(repo, None, system_git, env))

    # A partial clone that lacks the base blob: git does not fetch it from the promisor remote
    # (GIT_NO_LAZY_FETCH=1), so the gate cannot evaluate rather than reach out to fetch it.
    source = small_repo(tmp, "promisor", setup, {"doc.md": text("# doc", "o" * 150)})
    write(source, "doc.md", text("# doc", "o" * 150, "p" * 151))
    commit_all(source, setup)
    setup(source, "config", "uploadpack.allowFilter", "true")
    partial = os.path.join(tmp, "partial")
    setup(tmp, "clone", "-q", "--filter=blob:none", "--no-local", "-b", "work",
          "file://" + source, partial)
    expect("a base blob a partial clone lacks is not fetched", EXIT_CANNOT,
           "read doc.md at the base", check(partial, None, GIT, env))

    # A git that resolves a revision to something that is not a commit id.
    fake = os.path.join(tmp, "fake-git")
    write(tmp, "fake-git", (
        "#!%s -I\nimport os, sys\nargs = sys.argv[1:]\n"
        "if 'rev-parse' in args and '--verify' in args:\n    print('HEAD')\n    sys.exit(0)\n"
        "os.execv(%r, [%r] + args)\n" % (sys.executable, real, real)).encode())
    os.chmod(fake, 0o755)
    expect("a revision git resolves to no commit id cannot be evaluated", EXIT_CANNOT,
           "not a commit id", check(repo, None, fake, env))

    # A cone sparse checkout with a sparse index: out/ is one directory entry of the index, so a
    # diff of out/b.md that does not expand it is empty. The gate expands it (index.sparse=false),
    # so the index pass reads the staged line: committed (R8), then with HEAD reset to the base
    # (R9). A git that drops that setting gives the empty diff, which cannot be evaluated.
    repo = small_repo(tmp, "sparse-index", setup, {"in/a.md": text("# a"),
                                                    "out/b.md": text("# b")})
    write(repo, "out/b.md", wide)
    commit_all(repo, setup)
    setup(repo, "sparse-checkout", "init", "--cone", "--sparse-index")
    setup(repo, "sparse-checkout", "set", "in")
    out_missing = "out/b.md: changed since the base, but missing from the work tree"
    expect("R8: a committed line in a sparse index directory is read in HEAD and the index",
           EXIT_FAIL, [finding("out/b.md", 2, 300, 100, at_base, COMMITTED), out_missing],
           check(repo, None, GIT, env))
    setup(repo, "reset", "-q", "--soft", UPSTREAM)
    # A stat-dirty file in the cone, and no staged change whose directory's tree the object store
    # lacks. The run leaves the sparse index byte-identical with the same mtime; in this state
    # the only other change is git's own: expanding the sparse index renews the mtime of tree
    # objects the repository holds, without changing their bytes (R12). R13 stages a change in
    # the cone, where git adds tree objects too.
    os.utime(os.path.join(repo, "in", "a.md"), (1, 1))
    index = os.path.join(repo, ".git", "index")
    objects = os.path.join(repo, ".git", "objects") + os.sep
    before = snapshot(repo)
    expect("R9: a staged line in a sparse index directory is read in the index", EXIT_FAIL,
           [finding("out/b.md", 2, 300, 100, at_base, "the index"), out_missing],
           check(repo, None, GIT, env))
    after = snapshot(repo)
    report(after[index] == before[index],
           "R12: a run leaves a sparse .git/index byte-identical with the same mtime",
           "mtime %d to %d" % (before[index][0], after[index][0]))
    renewed = [path for path in set(before) | set(after) if before.get(path) != after.get(path)]
    report(all(path.startswith(objects) and isinstance(before.get(path), tuple)
               and isinstance(after.get(path), tuple) and before[path][1] == after[path][1]
               for path in renewed),
           "R12: with every tree stored, a sparse-index run changes only existing objects' mtime",
           repr(changed_paths(repo, before, after)))
    dense = setup(repo, "ls-files", "-s", "--sparse", "out").decode("utf-8", "replace")
    report(dense.startswith("040000 "), "the gate leaves the sparse index on disk sparse", dense)
    unexpanded = os.path.join(tmp, "unexpanded-git")
    write(tmp, "unexpanded-git", (
        "#!%s -I\nimport os, sys\nargs = sys.argv[1:]\n"
        "for at in range(len(args) - 1):\n"
        "    if args[at:at + 2] == ['-c', 'index.sparse=false']:\n"
        "        del args[at:at + 2]\n        break\n"
        "os.execv(%r, [%r] + args)\n" % (sys.executable, real, real)).encode())
    os.chmod(unexpanded, 0o755)
    expect("an empty diff of a file the index changed cannot be evaluated", EXIT_CANNOT,
           "the diff of out/b.md in the index has no file section",
           check(repo, None, unexpanded, env))

    # unexplained(), the oracle of R13 and R14, returns each change below that the Writes paragraph
    # does not allow (R17). Each change below is made alone between two snapshots, with the mtimes
    # of .git and .git/objects set back first so that a change to either shows: each but the last
    # is returned, and a new tree object, with its fan-out directory, is not.
    repo = small_repo(tmp, "unexplained", setup, {"a.md": text("# a")})
    git_dir = os.path.join(repo, ".git")
    empty = setup(repo, "hash-object", "--stdin").decode("ascii").strip()
    blob = setup(repo, "rev-parse", "HEAD:a.md").decode("ascii").strip()
    write(tmp, "unexplained-tree", b"100644 b.md\0" + bytes.fromhex(blob))

    def lock():
        write(repo, ".git/index.lock", b"")
        os.remove(os.path.join(git_dir, "index.lock"))

    loose = os.path.join(".git", "objects", blob[:2], blob[2:])

    def flip():
        os.chmod(os.path.join(repo, loose), 0o644)
        with open(os.path.join(repo, loose), "r+b") as handle:
            first = handle.read(1)
            handle.seek(0)
            handle.write(bytes([first[0] ^ 1]))

    # A loose tree copied to the path that splits its id after four hexadecimal digits, not two:
    # the directory is made before the first snapshot, so that only the copy is the change.
    tree = setup(repo, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    stray = os.path.join(".git", "objects", tree[:4], tree[4:])
    os.mkdir(os.path.join(repo, os.path.dirname(stray)))

    for label, change, want in (
            ("a work-tree file's new bytes", lambda: write(repo, "a.md", text("# b")), ["a.md"]),
            ("a work-tree file's new mtime", lambda: os.utime(os.path.join(repo, "a.md"), (1, 1)),
             ["a.md"]),
            (".git/index's new mtime", lambda: os.utime(os.path.join(git_dir, "index"), (1, 1)),
             [".git/index"]),
            ("a path removed under .git", lambda: os.remove(os.path.join(git_dir, "description")),
             [".git", ".git/description"]),
            ("a lock taken and released", lock, [".git"]),
            ("a new .git/index.lock", lambda: write(repo, ".git/index.lock", b""),
             [".git", ".git/index.lock"]),
            (".git/config's new mtime", lambda: os.utime(os.path.join(git_dir, "config"), (1, 1)),
             [".git/config"]),
            ("a loose object's new bytes", flip, [loose]),
            ("a new directory under .git/objects that is not a fan-out",
             lambda: os.mkdir(os.path.join(git_dir, "objects", "zz")),
             [os.path.join(".git", "objects", "zz")]),
            ("a loose tree's copy in a directory under .git/objects that is not a fan-out",
             lambda: shutil.copyfile(os.path.join(git_dir, "objects", tree[:2], tree[2:]),
                                     os.path.join(repo, stray)),
             [os.path.dirname(stray), stray]),
            (".git/objects/pack's new mtime",
             lambda: os.utime(os.path.join(git_dir, "objects", "pack"), (1, 1)),
             [os.path.join(".git", "objects", "pack")]),
            ("a new blob", lambda: setup(repo, "hash-object", "-w", "--stdin"),
             [os.path.join(".git", "objects", empty[:2], empty[2:])]),
            ("a new tree", lambda: setup(repo, "hash-object", "-w", "-t", "tree",
                                         os.path.join(tmp, "unexplained-tree")), [])):
        os.utime(git_dir, (1, 1))
        os.utime(os.path.join(git_dir, "objects"), (1, 1))
        before = snapshot(repo)
        change()
        odd = unexplained(repo, before, snapshot(repo), setup)
        report(odd == want, "R17: unexplained() %s %s" % ("returns" if want else "allows", label),
               "expected %r, got %r" % (want, odd))

    # A sparse index with a change staged in the cone and a stat-dirty file there (R13). git may
    # add the tree objects of the staged directories when it expands the index (see Writes); the
    # gate leaves the index byte-identical with the same mtime and changes no path's mtime and no
    # file's bytes, in the work tree or under .git, but what unexplained() allows (a superset of
    # Writes). The mtime of .git is set back first, as in R17, so that a lock taken and released
    # shows.
    repo = small_repo(tmp, "sparse-staged", setup, {"in/a.md": text("# a"), "in/z.md": text("z"),
                                                     "out/b.md": text("# b")})
    setup(repo, "sparse-checkout", "init", "--cone", "--sparse-index")
    setup(repo, "sparse-checkout", "set", "in")
    write(repo, "in/a.md", wide)
    setup(repo, "add", "in/a.md")
    os.utime(os.path.join(repo, "in", "z.md"), (1, 1))
    index = os.path.join(repo, ".git", "index")
    os.utime(os.path.join(repo, ".git"), (1, 1))
    before = snapshot(repo)
    expect("R13: a change staged in the cone of a sparse index is read", EXIT_FAIL,
           finding("in/a.md", 2, 300, 100, at_base, STAGED), check(repo, None, GIT, env))
    after = snapshot(repo)
    report(after[index] == before[index],
           "R13: with a staged change in the cone, a run leaves a sparse .git/index byte-identical "
           "with the same mtime", "mtime %d to %d" % (before[index][0], after[index][0]))
    odd = unexplained(repo, before, after, setup)
    report(odd == [], "R13: with a sparse index and a staged change, a run changes no mtime or "
           "bytes that unexplained() does not allow", repr(odd))

    # A split index (core.splitIndex) with a staged change and a stat-dirty file (R14). git may
    # renew the mtime of the shared index file when it reads the index (see Writes); the gate
    # leaves .git/index byte-identical with the same mtime, and the shared index byte-identical.
    repo = small_repo(tmp, "split-index", setup, {"a.md": text("# a"), "t.md": text("t")})
    setup(repo, "config", "core.splitIndex", "true")
    setup(repo, "update-index", "--split-index")
    write(repo, "a.md", wide)
    setup(repo, "add", "a.md")
    os.utime(os.path.join(repo, "t.md"), (1, 1))
    git_dir = os.path.join(repo, ".git")
    index = os.path.join(git_dir, "index")
    shared = [os.path.join(git_dir, name) for name in sorted(os.listdir(git_dir))
              if name.startswith("sharedindex.")]
    report(bool(shared), "R14: the split-index fixture has a shared index file",
           repr(sorted(os.listdir(git_dir))))
    os.utime(git_dir, (1, 1))
    before = snapshot(repo)
    expect("R14: a staged change in a split index is read", EXIT_FAIL,
           finding("a.md", 2, 300, 100, at_base, STAGED), check(repo, None, GIT, env))
    after = snapshot(repo)
    report(after[index] == before[index]
           and all(after.get(path, (0, None))[1] == before[path][1] for path in shared),
           "R14: with a split index, a run leaves .git/index byte-identical with the same mtime, "
           "and the shared index byte-identical", repr(changed_paths(repo, before, after)))
    odd = unexplained(repo, before, after, setup)
    report(odd == [], "R14: with a split index, a run changes no mtime or bytes "
           "that unexplained() does not allow", repr(odd))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Refuse a changed or added line wider than its file's width at the base.")
    parser.add_argument("--root", default=None,
                        help="repository root (default: the parent of this tool's directory)")
    parser.add_argument("--base", default=None,
                        help="base revision (default: the merge base of HEAD with origin/main)")
    parser.add_argument("--self-test", action="store_true",
                        help="build fixture repositories in a temporary directory and check them")
    args = parser.parse_args(argv)
    if args.self_test and (args.root is not None or args.base is not None):
        parser.error("--self-test does not take --root or --base")
    try:
        if args.self_test:
            return self_test()
        code, lines = check(args.root if args.root is not None else default_root(), args.base)
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
