#!/usr/bin/env python3
"""Names gate: no account, employer, workplace or personal name in the repository.

The denylist is private and is never stored in the repository. It is the
maintainer's protected-terms file, in the format the fleet pre-push hook reads:
one POSIX extended regular expression (ERE) per line, matched
case-insensitively. The file is the one named by OPFILES_NAMES_DENYLIST or,
when that variable is unset or empty, ~/.config/protected-terms/terms.regex;
either way it must live outside the repository. Empty lines and lines whose
first character is # are ignored; every other line is an entry, used exactly
as written (no whitespace is trimmed). Entries are numbered from 1 in file
order, counting only entries.

Each entry is translated from POSIX ERE to a Python regular expression:
bracket expressions (with the classes [:alnum:] [:alpha:] [:blank:] [:cntrl:]
[:digit:] [:graph:] [:lower:] [:print:] [:punct:] [:space:] [:upper:]
[:xdigit:], read with their C-locale (ASCII) members, ranges, and a backslash
that is literal inside brackets), anchors, groups, alternation, the * + ? and
{m,n} repetitions, the GNU escapes \\w \\W \\s \\S \\b \\B \\< \\>, and the GNU
buffer anchors \\` (start, translated to \\A) and \\' (end, translated to \\Z);
each line and each path is searched as a separate string, so these anchor at
the start and end of that line or path, as in the hook's grep. An escaped
special character is that character. A line that cannot be translated (for
example an unknown class, an unbalanced parenthesis or bracket, a repetition
with nothing to repeat, an escape that ERE does not define, such as \\d, a
back-reference such as \\1, a collating element [.c.] or an equivalence class
[=c=] (grep decides a line with one matcher but reads an entry that holds one
of these three with a second matcher, whose case folding and interval reading
differ; the gate refuses them rather than approximate either matcher), a
range whose end point sorts before its start point, or one whose end point
sorts before its start point once a to z are read as A to Z, which grep -E -i
in the C locale also refuses, such as [Z-a], a repetition of a group whose
body is not of one fixed length, such as (a*)* or (a|ab)+, whose backtracking
has no practical bound (a repeated group of fixed-length pieces, such as
(ab){2}, is kept), a repetition stacked on a repeated group, a repetition
stacked on a repetition whose count is not fixed, groups nested more than 100
deep, or repetitions stacked so deep that the translation nests more than 200
deep), that Python cannot compile, or that holds a carriage return or a byte
order mark (the UTF-8 bytes EF BB BF, as a file saved with CRLF line endings
or a BOM would) makes the gate report CANNOT-EVALUATE and exit 2, naming only
the line number, never the line. Since such a line could name any term, every
component of every path printed by the checks that need no denylist is then
printed as asterisks; the same holds when the denylist file cannot be resolved
or read, or is inside the repository.

Matching follows the C locale, the locale decided for this gate, and works on
bytes as grep in the C locale does. Every file, the denylist included, is read
as bytes and split into lines at each newline byte only (a carriage return
alone does not end a line), and each line is decoded as Latin-1, so that one
byte is one character; a file that is not valid UTF-8 is read in the same way.
Each entry is used as those bytes, and each path is turned into its UTF-8
bytes in the same way before it is used. A line of a file that holds a NUL
byte is a finding when an entry matches the whole line or any part of it
between NUL bytes, so the gate reports whatever grep reports, whether grep
reads the file as text or treats each NUL as the end of a line, as it does
for a file it takes to be binary. Every entry is compiled with re.ASCII
together with re.IGNORECASE, so the POSIX classes hold only their ASCII
members, \\w \\W \\b \\B \\< \\> treat only ASCII letters, digits and the
underscore as word characters (a byte outside ASCII is not one), only ASCII
letters match either case, and . \\W \\S and a negated bracket expression match
one byte, even one byte of a multibyte UTF-8 character, and a range or a
bracket expression that holds a character outside ASCII is read byte by byte,
as grep reads it.

Matching is case-insensitive and is not limited to whole words: an entry
carries its own boundaries. Each entry is searched in every line of every file
(a line is the text between two newline characters, as the hook's grep sees
it) and in every file path. A finding names the file, the line and the entry
number, never the entry or the matched text. In a printed file path, every
whole path component (the text between two slashes) that overlaps a match of
any entry is printed as asterisks, one for each byte. Each component is tested
once for each entry that matches the path: it is masked when any match, at any
start and of any alternative or length, starts before the component ends and
ends after it starts (the end is tested with the rest of the path still
visible after it, so an assertion such as \\b, \\B or \\< that closes the match
sees the byte that follows, as in grep), so no part of a protected term is
printed whichever alternative or length a pattern prefers. The text grep
reports for a match comes from its second matcher, which folds case inside a
bracket expression by upper-casing both the members and the searched byte, a
reading that can differ from the one that decides the line; each entry
therefore also carries a widened pattern whose bracket expressions hold the
union of the two readings (each complemented first when the bracket is
negated), and masking searches the widened pattern, so a component is masked
whichever reading grep reports. Masking more of a path than the deciding
pattern matches is safe; printing less never is. When the length of a path in
bytes multiplied by the number of entries that match the path is above a fixed
bound, every component of that printed path is masked without any further
search. That bound limits the number of searches masking runs, not the cost of
each search.

The refusals above remove only some causes of heavy backtracking. An entry the
gate accepts, such as one with several unbounded repetitions in a row, can
still make Python's matcher backtrack heavily on a long line or path, in line
matching and in masking alike. So denylist matching (the search of every path
and line and the masking of every path printed in a local run with a usable
denylist) runs in one worker process, started with the multiprocessing spawn
start method, one file at a time. Each file has a time budget of
MATCH_BUDGET_SECONDS (60 seconds). When the worker has not finished a file
within its budget, the worker is stopped and the gate reports CANNOT-EVALUATE
and exits 2, naming only that file, printed with every path component as
asterisks; every component of every other printed path is then masked too, and
no denylist finding is printed. The same holds, with no file named, when the
worker does not start within WORKER_START_SECONDS (60 seconds, not counted in
any file's budget) or fails. The worker's standard output and standard error
are the null device, so nothing the worker prints, such as a traceback of a
failed start, which could name an absolute path under the home directory,
reaches the gate's output: the gate prints only its own CANNOT-EVALUATE line,
which holds the class name of a failure and never a path, an entry or matched
text. The compiled entries reach the worker as its first message, after it
reports that it has started, so a stalled start is bounded by
WORKER_START_SECONDS too. When the gate receives SIGTERM while the worker
runs, it stops the worker, reports CANNOT-EVALUATE and exits 2. A worker whose
gate was killed without that chance, as by SIGKILL, ends by its own alarm at
most MATCH_BUDGET_SECONDS plus ORPHAN_GRACE_SECONDS (60 seconds) after it
received a file. Otherwise the output, the exit code and the
masking are those of matching in the gate's own process. The budget bounds one
file, not the whole run: a run with many slow files can still reach the
per-gate timeout of tools/run_all_checks.sh, which also fails closed, since the
runner reports the gate as timed out and counts that as a failure.

In a git checkout the gate reads the tracked files and the untracked files
that .gitignore does not exclude, so an ignored machine-local file is never
read; outside a git checkout it reads every file under the root.

Two checks need no denylist and always run: email addresses and
home-directory paths (under /home or /Users), which carry an account or
personal name. The SSH user git@github.com is not a personal address, and
an address at a name RFC 2606 or RFC 6761 reserves for documentation and
testing (example, example.com, example.net and example.org with their
subdomains, and any name under the .example, .invalid, .test or .localhost
top-level names) cannot name a real account, so both are allowed in every
file. The email check also skips the exact paths in EMAIL_EXEMPT below,
each with its reason: the vendored third-party tree under tools/_vendor/
(upstream attribution kept as imported), the published site's own security
contact file, and the three imported tools whose self-tests carry synthetic
non-reserved fixture addresses. The home-directory check has no exception:
it runs on every file.

Modes:
  local (the default): the denylist is required. When the denylist file does
    not exist, is inside the repository, cannot be read, holds no entry, or
    holds a line that cannot be translated or compiled or that holds a carriage
    return or byte order mark, or when matching a file runs past its time
    budget, or the matching worker fails, or the gate receives SIGTERM while
    the worker runs, the gate reports
    CANNOT-EVALUATE and exits 2. A denylist that is not valid UTF-8 is still
    read, as bytes.
  CI (the --ci argument; tools/run_all_checks.sh --ci passes it): no denylist
    is available on a hosted runner, so the gate runs only the checks that
    need no denylist and prints that it did so. Only that argument selects
    this mode; no environment variable does, so an inherited setting such as
    GITHUB_ACTIONS=true cannot skip the denylist checks of a local run.

Exit: 0 pass, 1 finding, 2 cannot evaluate or a usage error.
"""
import functools
import math
import multiprocessing
import os
import re
import signal
import string
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__"}
ENV = "OPFILES_NAMES_DENYLIST"
# Printed as written, never expanded, so no output names the account's home directory.
DEFAULT_DENYLIST = "~/.config/protected-terms/terms.regex"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ALLOWED_ADDRESSES = {"git@github.com"}
HOME_PATH = re.compile(r"(?<![A-Za-z0-9_.])/(?:home|Users)/[A-Za-z0-9._-]+")
# The names RFC 2606 and RFC 6761 reserve for documentation and testing. An address at one of
# these, or at any of their subdomains, cannot name a real account, so it is allowed everywhere.
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
RESERVED_TOP_LEVEL = ("example", "invalid", "test", "localhost")
# The email check's path exceptions (see the module docstring). An entry that ends with "/" is a
# path prefix; any other entry is one exact file. tools/_vendor/ keeps its upstream attribution as
# imported, site/.well-known/security.txt is the published site's own security contact, and the
# three tools carry synthetic non-reserved fixture addresses in their self-tests.
EMAIL_EXEMPT = (
    "site/.well-known/security.txt",
    "tools/_opf_check.py",
    "tools/_opf_views.py",
    "tools/_vendor/",
    "tools/check_opf_homes.py",
)


def exempt(rel, exemptions):
    """True when rel is one of the exemptions, or lies under an exemption that ends with "/"."""
    return any(rel == entry or (entry.endswith("/") and rel.startswith(entry))
               for entry in exemptions)


def reserved_address(address):
    """True when the address's domain is a name RFC 2606 or RFC 6761 reserves (see
    RESERVED_DOMAINS and RESERVED_TOP_LEVEL), or a subdomain of one. The address is given
    lower-cased."""
    domain = address.rsplit("@", 1)[1]
    labels = domain.split(".")
    if labels[-1] in RESERVED_TOP_LEVEL:
        return True
    return any(domain == name or domain.endswith("." + name) for name in RESERVED_DOMAINS)

# The POSIX character classes, as members of a Python character class, in the C locale.
POSIX_CLASSES = {
    "alnum": "0-9A-Za-z",
    "alpha": "A-Za-z",
    "blank": " \\t",
    "cntrl": "\\x00-\\x1f\\x7f",
    "digit": "0-9",
    "graph": "\\x21-\\x7e",
    "lower": "a-z",
    "print": "\\x20-\\x7e",
    "punct": "\\x21-\\x2f\\x3a-\\x40\\x5b-\\x60\\x7b-\\x7e",
    "space": " \\t\\n\\r\\x0b\\x0c",
    "upper": "A-Z",
    "xdigit": "0-9A-Fa-f",
}
# The same classes as byte sets, for the widened patterns behind masking.
_LOWER = frozenset(range(0x61, 0x7B))
_UPPER = frozenset(range(0x41, 0x5B))
_DIGIT = frozenset(range(0x30, 0x3A))
_ALPHA = _LOWER | _UPPER
_ALNUM = _ALPHA | _DIGIT
CLASS_MEMBERS = {
    "alnum": _ALNUM,
    "alpha": _ALPHA,
    "blank": frozenset({0x20, 0x09}),
    "cntrl": frozenset(range(0x00, 0x20)) | {0x7F},
    "digit": _DIGIT,
    "graph": frozenset(range(0x21, 0x7F)),
    "lower": _LOWER,
    "print": frozenset(range(0x20, 0x7F)),
    "punct": frozenset(range(0x21, 0x7F)) - _ALNUM,
    "space": frozenset({0x20, 0x09, 0x0A, 0x0B, 0x0C, 0x0D}),
    "upper": _UPPER,
    "xdigit": _DIGIT | frozenset(range(0x41, 0x47)) | frozenset(range(0x61, 0x67)),
}
ALL_BYTES = frozenset(range(0x100))
# A repetition interval: {m}, {m,}, {m,n} or the GNU {,n}.
INTERVAL = re.compile(r"\{([0-9]*)(,([0-9]*))?\}")
DUP_MAX = 32767
# The deepest group nesting an entry may have, and the deepest nesting its translation may have. Both
# are far below the depth at which Python's parser fails, so a translated entry, and the one extra
# group masked() adds around it, always compile; a deeper entry is refused with exit 2, not a crash.
MAX_GROUP_DEPTH = 100
MAX_NESTING = 200
# Masking searches a path once for each pattern and once more for each of its components that could
# overlap a match; above this bound on the length of the path in bytes multiplied by the number of
# entries that match the path, every component is masked instead, which is safe. The bound limits the
# number of searches, not the cost of each one: a search that backtracks heavily is stopped by the
# time budget below.
MASK_WORK_CAP = 65536
# The time budget, in seconds, of denylist matching for one file in the worker process (see the module
# docstring); far below the runner's default per-gate bound of 900 seconds, so one slow file is
# reported as CANNOT-EVALUATE before the runner stops the gate.
MATCH_BUDGET_SECONDS = 60
# The time, in seconds, the worker process has to start, outside every file's budget.
WORKER_START_SECONDS = 60
# The worker ends by its own alarm this many seconds after a file's budget, counted from when it received
# the file; the gate stops it at the budget, so the alarm fires only when the gate is gone, as after SIGKILL.
ORPHAN_GRACE_SECONDS = 60
# The UTF-8 byte order mark, one character for each byte (Latin-1).
BOM = b"\xef\xbb\xbf".decode("latin-1")


class Untranslatable(ValueError):
    """An entry that is not a POSIX ERE this gate can translate."""


def literal(char):
    """The Python regular expression, valid inside and outside a character class, for one character."""
    if char.isalnum() or char == "_":
        return char
    if char in string.punctuation:
        return "\\" + char
    return f"\\U{ord(char):08x}"


def upper_ascii(char):
    """The character upper-cased as toupper in the C locale does: only a to z change."""
    return char.upper() if "a" <= char <= "z" else char


def upper_byte(value):
    """One byte value upper-cased as toupper in the C locale does: only a to z change."""
    return value - 32 if 0x61 <= value <= 0x7A else value


def lower_byte(value):
    """One byte value lower-cased as tolower in the C locale does: only A to Z change."""
    return value + 32 if 0x41 <= value <= 0x5A else value


def nesting_depth(regex):
    """The deepest nesting of parentheses in a Python regular expression that translate_entry built;
    an escaped character never opens or closes a group (inside a character class every parenthesis is
    escaped)."""
    depth = deepest = 0
    escaped = False
    for char in regex:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "(":
            depth += 1
            deepest = max(deepest, depth)
        elif char == ")":
            depth -= 1
    return deepest


def rigid_width(kinds):
    """The one length, in characters, of every string a translated span can match, or None when the
    span could match more than one length or in more than one way. The span is given as the shapes
    translate_entry keeps for its pieces: ("atom", width) is one piece that matches exactly width
    characters in exactly one way, ("open",) and ("close",) delimit a group, ("alt",) is a branch
    bar, and ("rep", low, high) repeats the piece before it low to high times (high is None when
    the count is unbounded). An alternation, or a repetition whose count is not fixed, makes the
    width None. A span with a width matches in at most one way from each starting position, so a
    repetition of it never backtracks catastrophically; returning None where a finer reading could
    allow the span is safe, because refusing an entry is always allowed."""
    frames = [[]]
    branched = [False]
    for kind in kinds:
        tag = kind[0]
        if tag == "atom":
            frames[-1].append(kind[1])
        elif tag == "open":
            frames.append([])
            branched.append(False)
        elif tag == "close":
            items = frames.pop()
            frames[-1].append(None if branched.pop() or None in items else sum(items))
        elif tag == "alt":
            branched[-1] = True
        else:  # ("rep", low, high) repeats the piece before it
            width = frames[-1].pop()
            if width is None or kind[2] is None or kind[1] != kind[2]:
                frames[-1].append(None)
            else:
                frames[-1].append(width * kind[1])
    items = frames.pop()
    return None if branched.pop() or None in items else sum(items)


def byte_set_class(members):
    """A pattern piece, one repeatable atom, matching exactly one character whose code is in members."""
    if not members:
        # A bracket no byte is in; the piece must still take a repetition.
        return "(?:(?!))"
    ordered = sorted(members)
    runs = []
    start = prev = ordered[0]
    for value in ordered[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append((start, prev))
        start = prev = value
    runs.append((start, prev))
    parts = []
    for low, high in runs:
        if high - low >= 2:
            parts.append(literal(chr(low)) + "-" + literal(chr(high)))
        else:
            parts.append("".join(literal(chr(value)) for value in range(low, high + 1)))
    return "[" + "".join(parts) + "]"


def wide_bracket(raw, image, negate):
    """The widened byte set of one bracket expression, as a pattern piece. grep decides a line with a
    matcher whose bracket holds the raw members closed over ASCII case, but reports the matched text
    from a second matcher whose bracket holds a byte when its upper-cased value is among the
    upper-cased members (image). Each reading is complemented first when the bracket is negated, and
    the widened set is their union, so masking covers whichever text grep reports."""
    closed = {value for value in ALL_BYTES
              if value in raw or upper_byte(value) in raw or lower_byte(value) in raw}
    located = {value for value in ALL_BYTES if upper_byte(value) in image}
    if negate:
        closed = ALL_BYTES - closed
        located = ALL_BYTES - located
    return byte_set_class(closed | located)


def translate_bracket(ere, index):
    """Translate the bracket expression that starts at ere[index] == '['; return
    (text, widened text, next index): the members as written for the deciding pattern, and the
    widened byte set of wide_bracket for the pattern masked() searches."""
    j = index + 1
    negate = j < len(ere) and ere[j] == "^"
    if negate:
        j += 1
    items = []
    raw = set()
    image = set()
    first = True
    while True:
        if j >= len(ere):
            raise Untranslatable("unterminated bracket expression")
        char = ere[j]
        if char == "]" and not first:
            j += 1
            break
        first = False
        if char == "[" and j + 1 < len(ere) and ere[j + 1] == ":":
            end = ere.find(":]", j + 2)
            if end < 0:
                raise Untranslatable("unterminated character class")
            name = ere[j + 2:end]
            if name not in POSIX_CLASSES:
                raise Untranslatable("unknown character class")
            j = end + 2
            if j + 1 < len(ere) and ere[j] == "-" and ere[j + 1] != "]":
                raise Untranslatable("a character class cannot start a range")
            items.append(POSIX_CLASSES[name])
            raw |= CLASS_MEMBERS[name]
            # grep's second matcher reads [:upper:] and [:lower:] as [:alpha:] when it folds case.
            image |= _ALPHA if name in ("upper", "lower") else CLASS_MEMBERS[name]
            continue
        if char == "[" and j + 1 < len(ere) and ere[j + 1] in ".=":
            raise Untranslatable("a collating element or an equivalence class, "
                                 "which grep reads with its second matcher")
        start, j = char, j + 1
        if j + 1 < len(ere) and ere[j] == "-" and ere[j + 1] != "]":
            j += 1
            if ere[j] == "[" and j + 1 < len(ere) and ere[j + 1] in ".=:":
                raise Untranslatable("a class, a collating element or an equivalence class "
                                     "as a range end point")
            end_char, j = ere[j], j + 1
            if ord(end_char) < ord(start):
                raise Untranslatable("a range whose end point sorts before its start point")
            if ord(upper_ascii(end_char)) < ord(upper_ascii(start)):
                # grep -E -i in the C locale refuses such a range ("Invalid range end"), for example [Z-a].
                raise Untranslatable("a range whose upper-cased end point sorts before its upper-cased start")
            items.append(literal(start) + "-" + literal(end_char))
            raw |= set(range(ord(start), ord(end_char) + 1))
            image |= set(range(upper_byte(ord(start)), upper_byte(ord(end_char)) + 1))
        else:
            items.append(literal(start))
            raw.add(ord(start))
            image.add(upper_byte(ord(start)))
    text = "[" + ("^" if negate else "") + "".join(items) + "]"
    return text, wide_bracket(raw, image, negate), j


def translate_entry(ere):
    """Translate one POSIX extended regular expression to (deciding pattern, widened pattern): two
    Python regular expressions, identical except in bracket expressions, where the widened pattern
    holds the byte set of wide_bracket so that masking covers the text grep's second matcher reports.
    Raise Untranslatable for anything this gate does not translate faithfully, among it a
    back-reference, a collating element and an equivalence class, which grep hands to that second
    matcher (see the module docstring), and for anything whose matching could backtrack with no
    practical bound: a repeated group whose body is not of one fixed length, a repetition stacked
    on a repeated group, and a repetition stacked on a repetition whose count is not fixed."""
    out = []    # (deciding text, widened text) pieces
    kinds = []  # parallel to out: the shape of each piece, read by rigid_width
    atom_start = None  # index in out of the last atom a repetition may apply to
    repeated = False   # whether the last item of out is a repetition
    open_groups = []

    def emit(text, wide=None, kind=("atom", 0)):
        out.append((text, text if wide is None else wide))
        kinds.append(kind)

    def atom(text, wide=None):
        nonlocal atom_start, repeated
        atom_start, repeated = len(out), False
        emit(text, wide, ("atom", 1))

    def anchor(text):
        nonlocal atom_start, repeated
        atom_start, repeated = None, False
        emit(text)

    def repetition(text, low, high):
        nonlocal repeated
        if atom_start is None:
            raise Untranslatable("a repetition with nothing to repeat")
        if repeated:
            # ERE a*+ is (a*)+; Python would read *+ as possessive and +? as lazy. The wrap builds
            # a repeated group, so it is kept only where a repeated group would be kept: never over
            # a repeated group, and over a repeated atom only when the repetition it wraps has a
            # fixed count, so that the wrapped body keeps one fixed length.
            if kinds[atom_start][0] == "open":
                raise Untranslatable("a repetition stacked on a repeated group")
            width = rigid_width(kinds[atom_start:])
            if width is None:
                raise Untranslatable("a repetition stacked on a repetition whose count is not fixed")
            wrapped = ("(?:" + "".join(piece[0] for piece in out[atom_start:]) + ")",
                       "(?:" + "".join(piece[1] for piece in out[atom_start:]) + ")")
            out[atom_start:] = [wrapped]
            kinds[atom_start:] = [("atom", width)]
        elif kinds[atom_start][0] == "open" and rigid_width(kinds[atom_start:]) is None:
            # A repeated group whose body can match more than one length, or in more than one way,
            # can backtrack with no practical bound, as (a*)* or (a|ab)+ can, so the entry is
            # refused; refusing with exit 2 is always allowed. A group whose body is a sequence of
            # fixed-length pieces, as in (ab){2}, matches in at most one way from each starting
            # position, so repeating it never backtracks catastrophically and it is kept.
            raise Untranslatable("a repetition of a group whose body is not of one fixed length")
        emit(text, None, ("rep", low, high))
        repeated = True

    i = 0
    while i < len(ere):
        char = ere[i]
        if char == "\\":
            if i + 1 >= len(ere):
                raise Untranslatable("a trailing backslash")
            escaped = ere[i + 1]
            i += 2
            if escaped in "wWsS":
                atom("\\" + escaped)
            elif escaped in "bB":
                anchor("\\" + escaped)
            elif escaped == "<":
                anchor(r"\b(?=\w)")
            elif escaped == ">":
                anchor(r"\b(?<=\w)")
            elif escaped == "`":
                anchor(r"\A")
            elif escaped == "'":
                anchor(r"\Z")
            elif escaped in "123456789":
                raise Untranslatable("a back-reference, which grep hands to its second matcher")
            elif escaped.isalnum() or escaped == "_" or escaped.isspace() or not escaped.isprintable():
                raise Untranslatable("an escape that POSIX ERE does not define")
            else:
                atom(literal(escaped))
            continue
        if char == "[":
            text, wide, i = translate_bracket(ere, i)
            atom(text, wide)
            continue
        if char == "{":
            match = INTERVAL.match(ere, i)
            if not match or (match.group(1) == "" and match.group(3) in (None, "")):
                raise Untranslatable("a brace that does not start a valid interval")
            low = int(match.group(1) or "0")
            high = low if match.group(2) is None else (None if match.group(3) == "" else int(match.group(3)))
            if low > DUP_MAX or (high is not None and (high > DUP_MAX or high < low)):
                raise Untranslatable("an interval out of range")
            if match.group(2) is None:
                repetition(f"{{{low}}}", low, low)
            else:
                repetition(f"{{{low},{'' if high is None else high}}}", low, high)
            i = match.end()
            continue
        i += 1
        if char == "(":
            if len(open_groups) >= MAX_GROUP_DEPTH:
                raise Untranslatable("groups nested too deeply")
            open_groups.append(len(out))
            emit("(", None, ("open",))
            atom_start, repeated = None, False
        elif char == ")":
            if not open_groups:
                raise Untranslatable("an unmatched closing parenthesis")
            start = open_groups.pop()
            emit(")", None, ("close",))
            atom_start, repeated = start, False
        elif char == "|":
            atom_start, repeated = None, False
            emit("|", None, ("alt",))
        elif char == "*":
            repetition("*", 0, None)
        elif char == "+":
            repetition("+", 1, None)
        elif char == "?":
            repetition("?", 0, 1)
        elif char in "^$":
            anchor(char)
        elif char == ".":
            atom(".")
        else:
            atom(literal(char))
    if open_groups:
        raise Untranslatable("an unmatched opening parenthesis")
    deciding = "".join(piece[0] for piece in out)
    widened = "".join(piece[1] for piece in out)
    if nesting_depth(deciding) > MAX_NESTING or nesting_depth(widened) > MAX_NESTING:
        # Stacked repetitions such as a{2}{2}{2} each add a group around the atom.
        raise Untranslatable("repetitions nested too deeply")
    return deciding, widened


def translate_ere(ere):
    """The deciding pattern of translate_entry, for callers that need only the pattern that decides
    lines."""
    return translate_entry(ere)[0]


def as_bytes(text):
    """Text as its UTF-8 bytes, one character for each byte (Latin-1), as grep in the C locale reads
    it. A surrogate escape stands for the byte it escapes."""
    return text.encode("utf-8", "surrogateescape").decode("latin-1")


def from_bytes(text):
    """The inverse of as_bytes."""
    return text.encode("latin-1").decode("utf-8", "surrogateescape")


class CompiledEntry:
    """One compiled denylist entry: search and match decide lines with the deciding pattern, and mask
    is the compiled widened pattern that masked() searches (see translate_entry)."""

    __slots__ = ("deciding", "mask")

    def __init__(self, deciding, mask):
        self.deciding = deciding
        self.mask = mask

    def search(self, *args, **kwargs):
        return self.deciding.search(*args, **kwargs)

    def match(self, *args, **kwargs):
        return self.deciding.match(*args, **kwargs)

    @property
    def pattern(self):
        return self.deciding.pattern

    @property
    def flags(self):
        return self.deciding.flags


def compile_entry(ere):
    """The compiled, case-insensitive entry, matched against bytes (see as_bytes); raise ValueError
    when it cannot be translated or compiled. The entry is given as its bytes, one character for each
    byte (Latin-1), so it is translated byte by byte as grep in the C locale reads it. ASCII follows
    the C locale decided for this gate; MULTILINE keeps ^ and $ at line ends, as grep reads them. The
    result is a CompiledEntry: its search and match decide as grep decides a line, and its mask member
    is the widened pattern masked() searches."""
    try:
        deciding, widened = translate_entry(ere)
        flags = re.ASCII | re.IGNORECASE | re.MULTILINE
        return CompiledEntry(re.compile(deciding, flags), re.compile(widened, flags))
    except (re.error, OverflowError, RecursionError) as exc:
        raise ValueError("cannot compile") from exc


def listed_paths():
    """Relative POSIX paths of the regular files to read, sorted. In a git checkout: the tracked
    files and the untracked files that .gitignore does not exclude. Otherwise: every file under
    the root."""
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE")}
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, env=env, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0:
        names = {name for name in result.stdout.decode("utf-8", "surrogateescape").split("\0") if name}
    else:
        names = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")}
    return [name for name in sorted(names)
            if not any(part in SKIP_DIRS for part in PurePosixPath(name).parts) and (ROOT / name).is_file()]


def repository_files():
    """(relative path, lines or None) for every listed file, in a fixed order. The lines are those of
    grep_lines on the file's bytes, each decoded as Latin-1 (one character for each byte), whether or
    not the file is valid UTF-8; None means the file could not be read."""
    for rel in listed_paths():
        try:
            data = (ROOT / rel).read_bytes()
        except OSError:
            yield rel, None
            continue
        yield rel, [line.decode("latin-1") for line in grep_lines(data)]


@functools.lru_cache(maxsize=4096)
def reaching_past(pattern, remaining):
    """pattern, made to match only a span that ends fewer than remaining characters before the end of
    the string. The condition is a lookahead, not endpos, so the text after the span stays visible to
    an assertion such as \\b, \\B or \\< that closes the pattern."""
    return re.compile(f"(?:{pattern.pattern})(?!(?s:.){{{remaining}}})", pattern.flags)


def mask_pattern(pattern):
    """The pattern masked() searches with: an entry's widened pattern, or the pattern itself."""
    return getattr(pattern, "mask", pattern)


def masked(rel, patterns, everything=False):
    """The path with every whole component (split on "/") that overlaps a match of any pattern replaced
    by asterisks, one for each byte; with everything set, every component is replaced. The path is
    matched as bytes (see as_bytes). Each pattern is first searched once in the whole path; when the
    length of the path in bytes multiplied by the number of patterns that match it is above
    MASK_WORK_CAP, every component is replaced without any further search: masking more is safe, and
    the number of searches stays bounded (the cost of one search does not; see the module
    docstring). A pattern that matches nowhere in the path does not count towards that bound, so a
    long denylist does not mask a path that only a few of its entries match. Each entry is searched as
    its widened pattern (see
    translate_entry), so a component is also masked when only the matcher grep reports text from
    would match it; masking more is safe. A pattern that matches nowhere in the path is skipped, and
    a component that ends at or before the leftmost position where the pattern matches keeps its text
    without a search of its own; both shortcuts are exact, because every match starts at or after
    that leftmost position. Each other non-empty component, spanning [a, b), is tested once: it is
    masked when some match, at any start and of any alternative or length, starts before b and ends
    after a. Searching the whole path with reaching_past(pattern, len(path) - a) finds the leftmost
    start from which some match ends after a, with the rest of the path visible after that end, so
    the component overlaps a match exactly when that start is before b. No part of a match is
    printed, whichever alternative or length a pattern prefers; an empty match inside a component
    also masks it, which is safe."""
    raw = as_bytes(rel)
    parts = raw.split("/")
    matching = []  # (widened pattern, leftmost start of a match) for each pattern that matches the path
    if not everything:
        for pattern in patterns:
            searched = mask_pattern(pattern)
            first = searched.search(raw)
            if first is not None:
                matching.append((searched, first.start()))
        if len(raw) * len(matching) > MASK_WORK_CAP:
            everything = True
    hidden = [everything] * len(parts)
    for searched, leftmost in [] if everything else matching:
        offset = 0
        for number, part in enumerate(parts):
            end = offset + len(part)
            if part and not hidden[number] and end > leftmost:
                match = reaching_past(searched, len(raw) - offset).search(raw)
                hidden[number] = match is not None and match.start() < end
            offset = end + 1
    return from_bytes("/".join("*" * len(part) if hide else part for part, hide in zip(parts, hidden)))


def structural_labels(rel, lines):
    """The email address and home-directory path labels of one file (see structural_findings)."""
    labels = []
    if lines is None:
        return labels
    email_exempt = exempt(rel, EMAIL_EXEMPT)
    for number, line in enumerate(lines, 1):
        if not email_exempt:
            for match in EMAIL.finditer(line):
                address = match.group(0).lower()
                if address not in ALLOWED_ADDRESSES and not reserved_address(address):
                    labels.append(f"{number}: email address")
        if HOME_PATH.search(line):
            labels.append(f"{number}: home-directory path")
    return labels


def structural_findings(files, patterns, mask_all=False, shown=None):
    """Email addresses and home-directory paths. An address in ALLOWED_ADDRESSES or at a reserved
    name (reserved_address), and a file in EMAIL_EXEMPT, give no email finding; the home-directory
    check runs on every file. Printed paths are masked by patterns, or entirely when mask_all is
    set. When shown is given, it maps a path to its printed form, already masked by patterns (see
    timed_matching), and a path it does not hold is masked entirely, with no search."""
    findings = []
    for rel, lines in files:
        labels = structural_labels(rel, lines)
        if labels:
            if mask_all or shown is None:
                printed = masked(rel, patterns, mask_all)
            else:
                printed = shown.get(rel) or masked(rel, patterns, True)
            findings += [f"{printed}:{label}" for label in labels]
    return findings


def load_denylist():
    """Return (patterns, None, False) when the denylist can be used, or (patterns, reason, mask_all)
    when it cannot. In the second case, patterns holds the entries that did compile (perhaps none),
    which are still used to mask printed paths, and mask_all is True when a line was refused, or the
    file could not be resolved or read, or is inside the repository: such a line or file could name any
    term (a file inside the repository is not read, so none of its terms could mask a path), so every
    component of a printed path is then masked. The file is read as bytes, split by grep_lines, and each
    line is decoded as Latin-1 (one character for each byte), so a file that is not valid UTF-8 is still
    read."""
    value = os.environ.get(ENV, "")
    if value:
        what = f"the file named by {ENV}"
        raw = value
    else:
        what = f"{DEFAULT_DENYLIST} ({ENV} is not set or is empty)"
        raw = DEFAULT_DENYLIST
    try:
        resolved = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return [], f"{what} cannot be resolved ({exc.__class__.__name__})", True
    if not value and not resolved.exists():
        return [], f"{what} does not exist", False
    if resolved == ROOT or ROOT in resolved.parents:
        return [], f"{what} is inside the repository; the denylist must live outside it", True
    try:
        data = resolved.read_bytes()
    except OSError as exc:
        return [], f"{what} cannot be read ({exc.__class__.__name__})", True
    patterns = []
    bad_lines = []
    # Split at each newline byte only, so a CRLF line keeps its carriage return and is refused; a UTF-8
    # byte order mark, read as Latin-1, is the three characters of BOM below.
    for number, line in enumerate((line.decode("latin-1") for line in grep_lines(data)), 1):
        if "\r" in line or BOM in line:
            bad_lines.append(str(number))
            continue
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(compile_entry(line))
        except ValueError:
            bad_lines.append(str(number))
    if bad_lines:
        plural = len(bad_lines) > 1
        return patterns, (f"{what}: line{'s' if plural else ''} {', '.join(bad_lines)} cannot be translated "
                          f"from POSIX ERE or compiled, or {'hold' if plural else 'holds'} a carriage return "
                          f"or byte order mark"), True
    if not patterns:
        return [], f"{what} holds no entry", False
    return patterns, None, False


def grep_lines(data):
    """The lines of data (bytes or text) as grep reads them: split at each newline only, with no empty
    last line after a final newline."""
    lines = data.split(b"\n" if isinstance(data, bytes) else "\n")
    if not lines[-1]:
        lines.pop()
    return lines


def line_matches(pattern, line):
    """Whether pattern matches the line or, when the line holds a NUL byte, any part of it between NUL
    bytes: grep reads such a file as binary and ends a line at each NUL, grep -a reads it as text, and
    a finding is reported for either reading."""
    if pattern.search(line):
        return True
    return "\0" in line and any(pattern.search(part) for part in line.split("\0"))


def denylist_findings(files, patterns):
    """Denylist matches in paths and lines. A printed path is masked by patterns, and is worked out
    only for a file that has a finding."""
    findings = []
    for rel, lines in files:
        labels = []
        path = as_bytes(rel)
        for index, pattern in enumerate(patterns, 1):
            if pattern.search(path):
                labels.append(f" path matches denylist entry {index}")
        for number, line in enumerate(lines or [], 1):
            for index, pattern in enumerate(patterns, 1):
                if line_matches(pattern, line):
                    labels.append(f"{number}: denylist entry {index}")
        if labels:
            shown = masked(rel, patterns)
            findings += [f"{shown}:{label}" for label in labels]
    return findings


class Terminated(BaseException):
    """Raised by the SIGTERM handler that main installs while the worker runs, so that the finally block
    of timed_matching stops the worker before the gate exits. It is not an Exception, so the failure
    handler of timed_matching lets it pass."""


def raise_terminated(signum, frame):
    """The SIGTERM handler of main: ignore any further SIGTERM, so the report of this one is not cut
    short, and raise Terminated."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise Terminated


def match_worker(connection):
    """The worker process of timed_matching. It reports that it is ready, reads the compiled entries as
    its first message, then answers each job (relative path, lines, whether the path needs a masked
    form for a structural finding) with ("done", denylist findings, masked path or None), or ("error",
    exception class name) when the matching raised. It ends when the parent closes its end of the
    connection, and on any other failure, without printing anything (its standard output and standard
    error are the null device; see start_silenced): the parent sees a failure only as a closed
    connection or an error reply, and fails closed. While it matches one file it holds an alarm of the
    file's budget plus ORPHAN_GRACE_SECONDS, whose default action ends the process even in the middle
    of a search; the parent stops the worker at the budget, so the alarm ends it only when the parent
    is gone without having stopped it, as after SIGKILL."""
    try:
        alarm = getattr(signal, "alarm", None)
        if alarm is not None:
            # An ignored SIGALRM would be inherited through exec; the default action ends the process.
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
        connection.send(("ready",))
        patterns = connection.recv()
        while True:
            rel, lines, structural = connection.recv()
            if alarm is not None:
                alarm(math.ceil(MATCH_BUDGET_SECONDS) + ORPHAN_GRACE_SECONDS)
            try:
                reply = ("done", denylist_findings([(rel, lines)], patterns),
                         masked(rel, patterns) if structural else None)
            except Exception as exc:  # reported to the parent, which fails closed
                reply = ("error", exc.__class__.__name__)
            if alarm is not None:
                alarm(0)
            connection.send(reply)
    except BaseException:  # the end of the connection, or any failure: the parent fails closed
        pass
    finally:
        connection.close()


def start_silenced(worker):
    """Start worker with file descriptors 1 and 2 (standard output and standard error) on the null
    device, then restore them. The worker inherits the null device, so nothing it or the interpreter
    running it writes, such as a traceback of a failed start that names an absolute path, perhaps one
    under the home directory, is printed. The descriptors are restored however start ends; an error
    here, such as a closed descriptor, reaches timed_matching, which fails closed."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()
    saved = []
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        for descriptor in (1, 2):
            saved.append((descriptor, os.dup(descriptor)))
        for descriptor, _ in saved:
            os.dup2(null, descriptor)
        worker.start()
    finally:
        for descriptor, copy in saved:
            os.dup2(copy, descriptor)
            os.close(copy)
        os.close(null)


def timed_matching(files, patterns, structural):
    """Denylist matching of every file in one worker process, started with the spawn start method,
    with a time budget of MATCH_BUDGET_SECONDS for each file. structural holds the paths that have a
    structural finding, whose printed form the worker masks by patterns too. Return
    (denylist findings, {path: masked path} for the paths in structural, None) when every file was
    matched, or ([], {}, reason) when the worker did not start within WORKER_START_SECONDS, failed,
    or ran past the budget of a file; that file is then named with every path component masked, and
    no entry, line or matched text is ever part of the reason, which names a failure only by its
    exception class. The worker is started by start_silenced, so it prints nothing, and receives
    patterns only after it reports that it is ready, so a large set of entries cannot stall the start
    outside WORKER_START_SECONDS. The worker loads this file as the main module of the process, so
    the gate must run as a script; loaded under any other module name, the worker cannot start, and
    the reason says that it failed."""
    context = multiprocessing.get_context("spawn")
    ours, theirs = context.Pipe()
    worker = context.Process(target=match_worker, args=(theirs,), daemon=True)
    finished = False
    named, shown = [], {}
    try:
        start_silenced(worker)
        theirs.close()
        if not ours.poll(WORKER_START_SECONDS):
            return [], {}, (f"the denylist matching worker did not start within {WORKER_START_SECONDS:g} "
                            f"seconds, so the denylist checks did not run")
        if ours.recv() != ("ready",):
            return [], {}, "the denylist matching worker did not start, so the denylist checks did not run"
        ours.send(patterns)
        for rel, lines in files:
            ours.send((rel, lines, rel in structural))
            if not ours.poll(MATCH_BUDGET_SECONDS):
                return [], {}, (f"denylist matching of {masked(rel, [], True)} did not finish within "
                                f"{MATCH_BUDGET_SECONDS:g} seconds, so the denylist checks did not complete; "
                                f"an entry whose matching backtracks heavily, such as one with several "
                                f"unbounded repetitions in a row, can cause this")
            reply = ours.recv()
            if reply[0] != "done":
                return [], {}, (f"the denylist matching worker failed ({reply[1]}), "
                                f"so the denylist checks did not complete")
            named += reply[1]
            if reply[2] is not None:
                shown[rel] = reply[2]
        finished = True
        return named, shown, None
    except Exception as exc:  # any failure to start or reach the worker fails closed
        return [], {}, (f"the denylist matching worker failed ({exc.__class__.__name__}), "
                        f"so the denylist checks did not complete")
    finally:
        theirs.close()
        ours.close()
        if worker.pid is not None:
            if finished:
                # The worker ends when it reads the end of the connection closed above.
                worker.join(WORKER_START_SECONDS)
            if worker.is_alive():
                worker.kill()
            worker.join()


def main(argv):
    if argv not in ([], ["--ci"]):
        print("usage: check_names.py [--ci]")
        return 2
    ci = argv == ["--ci"]
    files = list(repository_files())
    patterns, reason, mask_all = ([], None, False) if ci else load_denylist()
    named, shown, stopped = [], None, None
    if not ci and reason is None:
        # Every search with a denylist entry runs in the worker, within a time budget for each file.
        structural = {rel for rel, lines in files if structural_labels(rel, lines)}
        # SIGTERM, such as from a harness that stops only this process, raises Terminated, so the finally
        # block of timed_matching stops the worker before the gate exits.
        previous = signal.signal(signal.SIGTERM, raise_terminated)
        try:
            named, shown, stopped = timed_matching(files, patterns, structural)
        except Terminated:
            print("CANNOT-EVALUATE: the gate received SIGTERM, so the denylist checks did not complete.")
            return 2
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)
        if stopped is not None:
            mask_all = True
    findings = structural_findings(files, patterns, mask_all, shown)
    if findings:
        print(f"FAIL: {len(findings)} email address(es) or home-directory path(s)")
        for finding in findings:
            print(f"  {finding}")
    else:
        print("PASS: no email address or home-directory path (the checks that need no denylist)")
    if ci:
        print("CI mode (--ci): ran only the checks that need no denylist; the denylist checks did not run")
        return 1 if findings else 0
    if reason is not None:
        print(f"CANNOT-EVALUATE: {reason}, so the denylist checks did not run. "
              f"Create {DEFAULT_DENYLIST}, or set {ENV} to a readable file outside the repository, "
              f"with one POSIX extended regular expression per line.")
        return 2
    if stopped is not None:
        print(f"CANNOT-EVALUATE: {stopped}.")
        return 2
    if named:
        print(f"FAIL: {len(named)} denylist match(es)")
        for finding in named:
            print(f"  {finding}")
    else:
        print(f"PASS: no denylist match ({len(patterns)} entries)")
    return 1 if findings or named else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
