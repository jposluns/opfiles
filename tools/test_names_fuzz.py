#!/usr/bin/env python3
"""Fuzz test of the names gate (tools/check_names.py) against GNU grep.

The names gate translates each denylist entry, a POSIX extended regular
expression (ERE), into a Python regular expression and must then decide every
line as the fleet pre-push hook's grep does. This test generates entries from a
small ERE grammar (literals, bracket expressions with ranges, negation, POSIX
classes and [=c=] and [.c.], intervals, alternation, groups, back-references,
the anchors ^ and $, and the GNU escapes the gate supports: \\w \\W \\s \\S \\b
\\B \\< \\> \\` \\'), and test lines built from them (ASCII, Latin-1 bytes,
UTF-8 multibyte characters and NUL bytes). For each entry and line it compares
the gate's decision with GNU grep, run as

    grep -E -i -q -a -e ENTRY

with LC_ALL=C and the line's bytes on its standard input.

The rules:
  - The gate may be stricter than grep: an entry the gate refuses (it would
    report CANNOT-EVALUATE) and grep accepts is counted, not failed.
  - The gate must never be weaker: for an entry the gate accepts, the gate
    must match a line exactly where grep -a matches it. The one documented
    exception is the NUL superset: for a line that holds a NUL byte, the gate
    may also match a part of the line between NUL bytes, which grep -a does
    not search on its own. An entry the gate accepts and grep refuses is
    counted, not failed (grep then matches nothing that the gate could miss).
  - For a sample of generated paths, masked() must print as asterisks every
    path component that a match reported by grep -E -i -o -b -a overlaps.
  - A run that compares too little never passes: when the stricter count is
    more than half of all generated entries, when fewer than half of the
    (entry, line) pairs were compared with grep, or when no compared line or
    sampled path is one grep matches, the run reports CANNOT-EVALUATE and exits
    2, so a gate that refuses almost every entry cannot pass.

A failure is printed as the entry index and the line or path index (each
counted from 1 in the order they are generated) with the seed, never as the
entry, the line or the path. The same seed and case count generate the same
entries, lines and paths, so a failure is reproduced with --seed.

The test reads no denylist and imports tools/check_names.py by path, with
bytecode writing turned off. It uses only the standard library.

Usage: test_names_fuzz.py [--seed N] [--cases N] [--self-test]
  --seed N     the seed of the generator (default 1729)
  --cases N    the number of (entry, line) pairs (default 2000)
  --self-test  check that each part of the coverage rule above, on its own,
               refuses a thin run (the gate refuses more than half the
               entries, fewer than half the pairs are compared, or no compared
               line or sampled path is one grep matches), then run the fuzz
               loop against three deliberately weakened stubs of the gate (one
               that matches case-sensitively, one whose masked() never masks,
               and one that refuses every entry) and pass only when the first
               two are caught as failures and the run of the third ends with
               the exit code 2 that main gives it. The self-test
               detects these weakenings only; it does not show that the
               fuzz catches every weakening, since a sampled run with a fixed
               seed can miss any weakening it does not happen to generate.
               tools/run_all_checks.sh runs it as the local-only gate
               names-fuzz-self-test.

Exit: 0 every case agreed (or, with --self-test, the coverage rule held and
every stub was caught), 1 a weaker case or a masking failure (or, with
--self-test, the coverage rule let a thin run pass or a stub was not caught),
2 cannot evaluate (Python older than 3.14, GNU grep missing, the gate cannot be
loaded, or the run compared too little) or a usage error.
"""
import sys

if sys.version_info < (3, 14):
    print("CANNOT-EVALUATE: tools/test_names_fuzz.py needs Python 3.14 or newer")
    sys.exit(2)

import argparse
import importlib.util
import random
import re
import shutil
import subprocess
import types
from pathlib import Path

GATE_PATH = Path(__file__).resolve().parent / "check_names.py"
DEFAULT_SEED = 1729
DEFAULT_CASES = 2000
SELF_TEST_CASES = 400
LINES_PER_ENTRY = 4
# One generated path is checked for every MASK_EVERY entries.
MASK_EVERY = 2
MAX_LINE = 40
GREP_TIMEOUT = 30
# grep runs with this environment only, so no inherited locale or option changes its reading.
GREP_ENV = {"LC_ALL": "C"}
BOM_BYTES = b"\xef\xbb\xbf"

LETTERS = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = b"0123456789"
WORD = LETTERS + DIGITS + b"_"
# Characters that are literal outside a bracket expression, and those that must be escaped to be.
PLAIN = b" !\"#%&',-/:;<=>@_`~"
SPECIAL = b".[]()*+?{}|^$\\"
HIGH = bytes(range(0x80, 0x100))
MULTIBYTE = tuple(chr(point).encode("utf-8") for point in (0xE9, 0xC5, 0xFF, 0x3B1, 0x416, 0x20AC, 0x1F600))
ASSERTIONS = (b"^", b"$", b"\\b", b"\\B", b"\\<", b"\\>", b"\\`", b"\\'")
# (text, lowest count, highest count or None for no bound)
QUANTIFIERS = ((b"*", 0, None), (b"+", 1, None), (b"?", 0, 1), (b"{2}", 2, 2), (b"{1,}", 1, None),
               (b"{0,2}", 0, 2), (b"{,2}", 0, 2), (b"{1,3}", 1, 3), (b"{0}", 0, 0))
PRINTABLE = bytes(range(0x20, 0x7F))
POSIX_MEMBERS = {
    b"alnum": LETTERS + DIGITS,
    b"alpha": LETTERS,
    b"blank": b" \t",
    b"cntrl": bytes(range(0x00, 0x20)) + b"\x7f",
    b"digit": DIGITS,
    b"graph": bytes(range(0x21, 0x7F)),
    b"lower": LETTERS[:26],
    b"print": PRINTABLE,
    b"punct": bytes(byte for byte in range(0x21, 0x7F) if byte not in LETTERS + DIGITS),
    b"space": b" \t\n\r\x0b\x0c",
    b"upper": LETTERS[26:],
    b"xdigit": DIGITS + b"abcdefABCDEF",
}
CLASS_NAMES = tuple(POSIX_MEMBERS)
# Single members of a bracket expression: never ] [ - or ^, which have a meaning there.
BRACKET_SINGLE = LETTERS + DIGITS + b" _!#%&,/;<>@~.*+?(){}|$\\" + b"\xc3\xa9\xe9\xff\x80"
RANGE_POOL = bytes(byte for byte in range(0x21, 0x7F) if byte not in b"]-[^")
PRESET_RANGES = ((ord("a"), ord("z")), (ord("A"), ord("Z")), (ord("0"), ord("9")), (ord("a"), ord("f")),
                 (ord("C"), ord("X")), (ord("A"), ord("z")), (ord("_"), ord("a")), (ord("!"), ord("/")))
ESCAPE_WITNESS = {ord("w"): WORD, ord("W"): b" -./@\xe9\x80", ord("s"): b" \t\x0b\x0c\r", ord("S"): b"aZ9_-\xe9"}
# Bytes a line may hold besides the witness of an entry: never a newline, which ends a line.
NOISE = PRINTABLE + b"\t" + HIGH


class CannotEvaluate(Exception):
    """The run cannot compare the gate with grep."""


# ---------------------------------------------------------------------------------------------
# The grammar. A node is a tuple whose first member names its kind:
#   ("lit", byte, escaped)          one byte, written with a backslash when escaped
#   ("any",)                        .
#   ("bracket", text, members)      a bracket expression and the bytes it is meant to match
#   ("esc", letter)                 \w \W \s \S
#   ("assert", text)                ^ $ \b \B \< \> \` \'
#   ("backref", number)             \1 to \9
#   ("group", number, alternation)  ( ... )
#   ("alt", [concatenation, ...])   a|b
#   ("cat", [node, ...])            ab
#   ("rep", node, text, low, high)  a*, a{1,3} and so on
# ---------------------------------------------------------------------------------------------


def render(node):
    """The ERE text of a node, as bytes."""
    kind = node[0]
    if kind == "lit":
        return (b"\\" if node[2] else b"") + bytes([node[1]])
    if kind == "any":
        return b"."
    if kind == "bracket":
        return node[1]
    if kind == "esc":
        return b"\\" + bytes([node[1]])
    if kind == "assert":
        return node[1]
    if kind == "backref":
        return b"\\" + str(node[1]).encode("ascii")
    if kind == "group":
        return b"(" + render(node[2]) + b")"
    if kind == "alt":
        return b"|".join(render(branch) for branch in node[1])
    if kind == "cat":
        return b"".join(render(piece) for piece in node[1])
    if kind == "rep":
        return render(node[1]) + node[2]
    raise AssertionError(f"unknown node kind {kind}")


def witness(node, rng, groups):
    """Bytes the node is meant to match. This is a guide for building lines likely to match, not a
    claim: grep decides every line."""
    kind = node[0]
    if kind == "lit":
        return bytes([node[1]])
    if kind == "any":
        return bytes([rng.choice(NOISE)])
    if kind == "bracket":
        return bytes([rng.choice(node[2])]) if node[2] else b"?"
    if kind == "esc":
        return bytes([rng.choice(ESCAPE_WITNESS[node[1]])])
    if kind == "assert":
        return b""
    if kind == "backref":
        return groups.get(node[1], b"")
    if kind == "group":
        text = witness(node[2], rng, groups)
        groups[node[1]] = text
        return text
    if kind == "alt":
        return witness(rng.choice(node[1]), rng, groups)
    if kind == "cat":
        return b"".join(witness(piece, rng, groups) for piece in node[1])
    if kind == "rep":
        low, high = node[3], node[4]
        count = rng.randint(low, low + 2 if high is None else high)
        return b"".join(witness(node[1], rng, groups) for _ in range(count))
    raise AssertionError(f"unknown node kind {kind}")


class Generator:
    """Entries, lines and paths from one seeded random source, so a seed reproduces a run."""

    def __init__(self, rng):
        self.rng = rng
        self.groups = 0
        self.closed = []

    def entry(self):
        """(node, entry bytes): an entry the denylist file could hold, never empty, never a comment, and
        never holding a newline, a carriage return, a NUL or a byte order mark."""
        while True:
            self.groups = 0
            self.closed = []
            node = self.alternation(0)
            text = render(node)
            if text and not text.startswith(b"#") and BOM_BYTES not in text:
                return node, text

    def alternation(self, depth):
        count = self.rng.choices((1, 2, 3), (7, 2, 1))[0]
        return ("alt", [self.concatenation(depth) for _ in range(count)])

    def concatenation(self, depth):
        pieces = []
        for _ in range(self.rng.randint(1, 4)):
            pieces.extend(self.piece(depth))
        return ("cat", pieces)

    def piece(self, depth):
        rng = self.rng
        roll = rng.random()
        if roll < 0.06:
            # A UTF-8 multibyte character: one literal for each byte, never repeated as a whole.
            return [("lit", byte, False) for byte in rng.choice(MULTIBYTE)]
        if roll < 0.14:
            return [("assert", rng.choice(ASSERTIONS))]
        if roll < 0.17 and self.closed:
            node = ("backref", rng.choice(self.closed))
        elif roll < 0.27 and depth < 3:
            self.groups += 1
            number = self.groups
            inner = self.alternation(depth + 1)
            if number <= 9:
                self.closed.append(number)
            node = ("group", number, inner)
        elif roll < 0.43:
            node = self.bracket()
        elif roll < 0.49:
            node = ("any",)
        elif roll < 0.56:
            node = ("esc", rng.choice(b"wWsS"))
        else:
            node = self.literal()
        if rng.random() < 0.3:
            text, low, high = rng.choice(QUANTIFIERS)
            node = ("rep", node, text, low, high)
            if rng.random() < 0.08:
                # A stacked repetition, such as a*+ or a{2}{1,3}.
                text, low, high = rng.choice(QUANTIFIERS)
                node = ("rep", node, text, low, high)
        return [node]

    def literal(self):
        rng = self.rng
        roll = rng.random()
        if roll < 0.6:
            return ("lit", rng.choice(LETTERS), False)
        if roll < 0.7:
            return ("lit", rng.choice(DIGITS), False)
        if roll < 0.82:
            return ("lit", rng.choice(PLAIN), rng.random() < 0.1)
        if roll < 0.92:
            return ("lit", rng.choice(SPECIAL), True)
        return ("lit", rng.choice(HIGH), False)

    def range_ends(self):
        rng = self.rng
        roll = rng.random()
        if roll < 0.5:
            return rng.choice(PRESET_RANGES)
        if roll < 0.7:
            low = rng.choice(RANGE_POOL)
            return low, rng.choice([byte for byte in RANGE_POOL if byte >= low])
        if roll < 0.82:
            low = rng.randint(0x80, 0xFF)
            return low, rng.randint(low, 0xFF)
        if roll < 0.9:
            return rng.choice(RANGE_POOL), rng.randint(0x80, 0xFF)
        # Any order, so some ranges are refused by both, such as [Z-a] or [z-a].
        return rng.choice(RANGE_POOL), rng.choice(RANGE_POOL)

    def bracket(self):
        rng = self.rng
        negate = rng.random() < 0.3
        items = []
        members = set()
        if rng.random() < 0.1:
            items.append(b"]")
            members.add(ord("]"))
        for _ in range(rng.randint(1, 3)):
            roll = rng.random()
            if roll < 0.35:
                byte = rng.choice(BRACKET_SINGLE)
                items.append(bytes([byte]))
                members.add(byte)
            elif roll < 0.65:
                low, high = self.range_ends()
                items.append(bytes([low]) + b"-" + bytes([high]))
                members.update(range(low, high + 1))
            elif roll < 0.88:
                name = rng.choice(CLASS_NAMES)
                items.append(b"[:" + name + b":]")
                members.update(POSIX_MEMBERS[name])
            else:
                kind = rng.choice(b".=")
                byte = rng.choice(LETTERS + DIGITS + b".=-")
                items.append(bytes([ord("["), kind, byte, kind, ord("]")]))
                members.add(byte)
        if rng.random() < 0.1:
            items.append(b"-")
            members.add(ord("-"))
        if negate:
            members = set(range(0x01, 0x100)) - members
        members.discard(ord("\n"))
        text = b"[" + (b"^" if negate else b"") + b"".join(items) + b"]"
        return ("bracket", text, bytes(sorted(members)))

    def noise(self, low, high):
        rng = self.rng
        parts = []
        for _ in range(rng.randint(low, high)):
            if rng.random() < 0.15:
                parts.append(rng.choice(MULTIBYTE))
            else:
                parts.append(bytes([rng.choice(NOISE)]))
        return b"".join(parts)

    def swap_case(self, data):
        return bytes(byte ^ 0x20 if byte in LETTERS and self.rng.random() < 0.5 else byte for byte in data)

    def mutate(self, data):
        rng = self.rng
        data = bytearray(data)
        for _ in range(rng.randint(1, 2)):
            roll = rng.random()
            position = rng.randint(0, len(data))
            if roll < 0.3:
                data[position:position] = bytes([rng.choice(NOISE)])
            elif roll < 0.5:
                data[position:position] = b"\0"
            elif data and roll < 0.75:
                del data[min(position, len(data) - 1)]
            elif data:
                data[min(position, len(data) - 1)] = rng.choice(NOISE)
        return bytes(data)

    def random_line(self, node):
        rng = self.rng
        kind = rng.choice(("ascii", "latin-1", "utf-8", "nul", "nul"))
        if kind == "ascii":
            return bytes(rng.choice(PRINTABLE) for _ in range(rng.randint(0, 20)))
        if kind == "latin-1":
            return bytes(rng.choice(HIGH + LETTERS) for _ in range(rng.randint(0, 20)))
        if kind == "utf-8":
            return b"".join(rng.choice(MULTIBYTE + tuple(bytes([byte]) for byte in LETTERS))
                            for _ in range(rng.randint(0, 12)))
        # A line with NUL bytes, which grep -a reads as text and the gate also splits at each NUL.
        text = witness(node, rng, {})
        if rng.random() < 0.5:
            return self.noise(0, 3) + b"\0" + text + b"\0" + self.noise(0, 3)
        position = rng.randint(0, len(text))
        return text[:position] + b"\0" + text[position:]

    def lines(self, node):
        """LINES_PER_ENTRY lines for one entry."""
        rng = self.rng
        built = [
            self.noise(0, 4) + witness(node, rng, {}) + self.noise(0, 4),
            self.swap_case(witness(node, rng, {})),
            self.mutate(self.swap_case(witness(node, rng, {}))),
            self.random_line(node),
        ]
        return [line.replace(b"\n", b" ")[:MAX_LINE] for line in built]

    def component(self):
        rng = self.rng
        pool = LETTERS + DIGITS + b"._-" + b"\xe9\xc3\xa9"
        return bytes(rng.choice(pool) for _ in range(rng.randint(1, 6)))

    def path(self, node):
        """A relative path whose middle component holds a witness of the entry."""
        rng = self.rng
        parts = [self.component() for _ in range(rng.randint(0, 2))]
        parts.append(self.noise(0, 2) + witness(node, rng, {}) + self.noise(0, 2))
        parts += [self.component() for _ in range(rng.randint(0, 2))]
        path = b"/".join(parts).replace(b"\0", b"_").replace(b"\n", b"_")[:MAX_LINE]
        return path or b"x"


# ---------------------------------------------------------------------------------------------
# grep and the gate
# ---------------------------------------------------------------------------------------------


def find_grep():
    """The path of GNU grep; raise CannotEvaluate when grep is missing or is not GNU grep."""
    grep = shutil.which("grep")
    if not grep:
        raise CannotEvaluate("grep is not on PATH")
    try:
        result = subprocess.run([grep, "--version"], capture_output=True, env=GREP_ENV,
                                timeout=GREP_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate(f"grep --version could not run ({exc.__class__.__name__})") from exc
    first = result.stdout.split(b"\n", 1)[0]
    if result.returncode != 0 or b"GNU grep" not in first:
        raise CannotEvaluate("the grep on PATH is not GNU grep")
    return grep


def run_grep(arguments, data):
    try:
        return subprocess.run(arguments, input=data + b"\n", capture_output=True, env=GREP_ENV,
                              timeout=GREP_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotEvaluate(f"grep could not run ({exc.__class__.__name__})") from exc


def grep_status(grep, entry, data):
    """0 grep -a matches the line, 1 it does not, 2 grep refuses the entry."""
    result = run_grep([grep, "-E", "-i", "-q", "-a", "-e", entry], data)
    if result.returncode not in (0, 1, 2):
        raise CannotEvaluate(f"grep exited {result.returncode}")
    return result.returncode


def grep_spans(grep, entry, data):
    """The [start, end) byte spans of the non-empty matches grep -o -b reports, or None when grep
    refuses the entry."""
    result = run_grep([grep, "-E", "-i", "-o", "-b", "-a", "-e", entry], data)
    if result.returncode == 2:
        return None
    if result.returncode not in (0, 1):
        raise CannotEvaluate(f"grep exited {result.returncode}")
    spans = []
    for row in result.stdout.split(b"\n"):
        if not row:
            continue
        offset, _, text = row.partition(b":")
        start = int(offset)
        spans.append((start, start + len(text)))
    return spans


def load_gate():
    """tools/check_names.py, imported by path, with no bytecode written."""
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("check_names_under_fuzz", GATE_PATH)
        if spec is None or spec.loader is None:
            raise CannotEvaluate("tools/check_names.py cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except CannotEvaluate:
        raise
    except Exception as exc:  # any failure to load the gate means nothing can be compared
        raise CannotEvaluate(f"tools/check_names.py cannot be loaded ({exc.__class__.__name__})") from exc
    for name in ("compile_entry", "line_matches", "masked", "translate_ere", "BOM"):
        if not hasattr(module, name):
            raise CannotEvaluate(f"tools/check_names.py has no {name}")
    return module


def gate_pattern(gate, entry):
    """The gate's compiled pattern for an entry, or None when the gate refuses it, as load_denylist
    does: a line with a carriage return or byte order mark, or one that cannot be translated or
    compiled. The entry is given to the gate as its bytes, one character for each byte (Latin-1)."""
    text = entry.decode("latin-1")
    if "\r" in text or gate.BOM in text:
        return None
    try:
        return gate.compile_entry(text)
    except ValueError:
        return None


def mask_hides(gate, pattern, path, spans):
    """Whether masked() prints as asterisks, one for each byte, every non-empty component of path that
    a span overlaps."""
    rel = path.decode("utf-8", "surrogateescape")
    shown = gate.masked(rel, [pattern]).encode("utf-8", "surrogateescape")
    parts = path.split(b"/")
    shown_parts = shown.split(b"/")
    if len(parts) != len(shown_parts):
        return False
    offset = 0
    for part, out in zip(parts, shown_parts):
        end = offset + len(part)
        if part and any(start < end and stop > offset for start, stop in spans):
            if out != b"*" * len(part):
                return False
        offset = end + 1
    return True


# ---------------------------------------------------------------------------------------------
# The fuzz loop
# ---------------------------------------------------------------------------------------------


def fuzz(gate, grep, seed, cases):
    """Compare the gate with grep on cases (entry, line) pairs. Return (tally, failures), where each
    failure is (kind, entry index, line or path index or None), indices counted from 1."""
    generator = Generator(random.Random(seed))
    tally = dict.fromkeys(("entries", "pairs", "compared", "agreed", "grep matched", "stricter",
                           "both refused", "grep refused", "nul superset", "paths", "paths with a match"), 0)
    failures = []
    line_number = 0
    path_number = 0
    entry_number = 0
    while tally["pairs"] < cases:
        entry_number += 1
        node, entry = generator.entry()
        lines = generator.lines(node)[:cases - tally["pairs"]]
        path = generator.path(node) if entry_number % MASK_EVERY == 1 else None
        first_line = line_number + 1
        line_number += len(lines)
        tally["entries"] += 1
        tally["pairs"] += len(lines)
        if path is not None:
            path_number += 1
        try:
            pattern = gate_pattern(gate, entry)
        except Exception as exc:  # a crash of the gate is a failure, never a pass
            failures.append(("error", entry_number, exc.__class__.__name__))
            continue
        if pattern is None:
            refused = grep_status(grep, entry, b"") == 2
            tally["both refused" if refused else "stricter"] += 1
            continue
        if grep_status(grep, entry, lines[0]) == 2:
            tally["grep refused"] += 1
            continue
        for number, line in enumerate(lines, first_line):
            status = grep_status(grep, entry, line)
            text = line.decode("latin-1")
            try:
                found = bool(gate.line_matches(pattern, text))
                whole = bool(pattern.search(text))
            except Exception as exc:  # a crash of the gate is a failure, never a pass
                failures.append(("error", entry_number, exc.__class__.__name__))
                break
            tally["compared"] += 1
            if status == 0:
                tally["grep matched"] += 1
                if found:
                    tally["agreed"] += 1
                else:
                    failures.append(("missed", entry_number, number))
            elif whole:
                failures.append(("extra", entry_number, number))
            elif found:
                tally["nul superset"] += 1
            else:
                tally["agreed"] += 1
        if path is not None:
            spans = grep_spans(grep, entry, path)
            if spans is not None:
                tally["paths"] += 1
                if spans:
                    tally["paths with a match"] += 1
                try:
                    hidden = mask_hides(gate, pattern, path, spans)
                except Exception as exc:  # a crash of the gate is a failure, never a pass
                    failures.append(("error", entry_number, exc.__class__.__name__))
                    continue
                if not hidden:
                    failures.append(("mask", entry_number, path_number))
    return tally, failures


def describe(failure, seed):
    kind, entry, other = failure
    if kind == "missed":
        return f"entry {entry} line {other}: grep -a matches the line and the gate does not (seed {seed})"
    if kind == "extra":
        return (f"entry {entry} line {other}: the gate matches the whole line and grep -a does not, "
                f"outside the NUL superset (seed {seed})")
    if kind == "mask":
        return (f"entry {entry} path {other}: masked() prints a component that a match reported by "
                f"grep -o -b overlaps (seed {seed})")
    return f"entry {entry}: the gate raised {other} (seed {seed})"


def shortfall(tally):
    """Why a run with no failure still compared too little to pass, or None when it compared enough:
    the entries the gate refuses and grep accepts (stricter) are more than half of all generated
    entries, fewer than half of the (entry, line) pairs were compared with grep, or no compared line
    or sampled path is one grep matches. Each reason holds only counts."""
    if tally["stricter"] * 2 > tally["entries"]:
        return (f"the gate refused {tally['stricter']} entries that grep accepts, more than half of the "
                f"{tally['entries']} entries, so the run compared too little")
    if tally["compared"] * 2 < tally["pairs"]:
        return (f"only {tally['compared']} of {tally['pairs']} (entry, line) pairs were compared with grep, "
                f"fewer than half, so the run compared too little")
    if not tally["grep matched"] or not tally["paths with a match"]:
        return "the run compared no line or path that grep matches, so it proves nothing"
    return None


def run_outcome(tally, failures):
    """The exit code main gives a fuzz run with these counts and failures: 1 when there is a failure, 2
    when shortfall finds that the run compared too little, 0 otherwise. The self-test applies it to a
    stub's run, so the self-test checks the decision main makes, not a copy of it."""
    if failures:
        return 1
    return 2 if shortfall(tally) is not None else 0


# ---------------------------------------------------------------------------------------------
# The self-test: each part of the coverage rule must refuse a thin run, and three deliberately
# weakened stubs of the gate must each be caught.
# ---------------------------------------------------------------------------------------------


def stub(gate, **overrides):
    """A stand-in for the gate with the functions the fuzz loop uses, some of them replaced."""
    members = {name: getattr(gate, name) for name in ("compile_entry", "line_matches", "masked", "BOM")}
    members.update(overrides)
    return types.SimpleNamespace(**members)


def case_sensitive_stub(gate):
    """The gate, except that entries are compiled without IGNORECASE."""
    def compile_entry(text):
        try:
            return re.compile(gate.translate_ere(text), re.ASCII | re.MULTILINE)
        except (re.error, OverflowError, RecursionError) as exc:
            raise ValueError("cannot compile") from exc
    return stub(gate, compile_entry=compile_entry)


def unmasking_stub(gate):
    """The gate, except that masked() never masks."""
    return stub(gate, masked=lambda rel, patterns, everything=False: rel)


def refusing_stub(gate):
    """The gate, except that it refuses every entry, as a gate that reports CANNOT-EVALUATE for any
    denylist would."""
    def compile_entry(text):
        raise ValueError("refused")
    return stub(gate, compile_entry=compile_entry)


def catch_stubs(gate, grep, seed):
    """Run the fuzz loop against the three weakened stubs; return 0 when the case-sensitive stub and
    the unmasking stub are caught as failures and run_outcome gives the run of the refusing stub exit
    2, else 1."""
    _, weak_case = fuzz(case_sensitive_stub(gate), grep, seed, SELF_TEST_CASES)
    _, weak_mask = fuzz(unmasking_stub(gate), grep, seed, SELF_TEST_CASES)
    refusing_tally, refusing_failures = fuzz(refusing_stub(gate), grep, seed, SELF_TEST_CASES)
    missed = sum(1 for failure in weak_case if failure[0] in ("missed", "extra"))
    unmasked = sum(1 for failure in weak_mask if failure[0] == "mask")
    refusing_exit = run_outcome(refusing_tally, refusing_failures)
    print(f"self-test (seed {seed}, {SELF_TEST_CASES} cases for each stub):")
    print(f"  a stub that matches case-sensitively: {missed} weaker case(s) caught")
    print(f"  a stub whose masked() never masks: {unmasked} masking failure(s) caught")
    print(f"  a stub that refuses every entry: its run exits {refusing_exit} (2 wanted)")
    if missed and unmasked and refusing_exit == 2:
        print("PASS: names fuzz self-test (every weakened gate stub was caught)")
        return 0
    print("FAIL: names fuzz self-test (a weakened gate stub was not caught)")
    return 1


# Counts of runs with no failure, and whether shortfall must refuse each. Each thin run breaks one part
# of the coverage rule and meets every other part, so each part is shown to refuse a run on its own: a
# gate that refuses more than half the entries, a run that compares fewer than half its pairs, and a
# run with no line or no path that grep matches must never pass.
COVERAGE_CASES = (
    ("a gate that refuses 51 of 100 entries (300 of 400 pairs compared)",
     {"entries": 100, "stricter": 51, "pairs": 400, "compared": 300}, True),
    ("a run that compares 199 of 400 pairs", {"entries": 100, "stricter": 10, "pairs": 400, "compared": 199},
     True),
    ("a run with no compared line that grep matches",
     {"entries": 100, "stricter": 10, "pairs": 400, "compared": 300, "grep matched": 0}, True),
    ("a run with no sampled path that grep matches",
     {"entries": 100, "stricter": 10, "pairs": 400, "compared": 300, "paths with a match": 0}, True),
    ("a run at both bounds (50 of 100 entries refused, 200 of 400 pairs compared)",
     {"entries": 100, "stricter": 50, "pairs": 400, "compared": 200}, False),
)


def coverage_caught():
    """Apply shortfall to the counts of COVERAGE_CASES, each with lines and paths grep matched unless
    the case sets those counts; return True when it refuses every thin run and accepts the run at the
    bounds."""
    held = True
    print("self-test of the coverage rule:")
    for label, counts, thin in COVERAGE_CASES:
        tally = {"grep matched": 50, "paths with a match": 10, **counts}
        refused = shortfall(tally) is not None
        print(f"  {label}: {'refused' if refused else 'accepted'}")
        held = held and refused == thin
    return held


def run_self_test(seed):
    """Check the coverage rule, then find GNU grep, load the gate and run catch_stubs with seed;
    return 1 when the coverage rule fails, and 2 when the stubs cannot be evaluated."""
    if not coverage_caught():
        print("FAIL: names fuzz self-test (the coverage rule let a thin run pass, or refused a run at its bounds)")
        return 1
    try:
        grep = find_grep()
        gate = load_gate()
        return catch_stubs(gate, grep, seed)
    except CannotEvaluate as exc:
        print(f"CANNOT-EVALUATE: {exc}")
        return 2


def self_test():
    """The self-test with the default seed: 0 the coverage rule held and every stub was caught, 1 the
    coverage rule failed or a stub was not caught, 2 cannot evaluate. main() runs it with --seed
    instead."""
    return run_self_test(DEFAULT_SEED)


# ---------------------------------------------------------------------------------------------


def positive(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"not a positive integer: {text}")
    return value


def main(argv):
    parser = argparse.ArgumentParser(prog="test_names_fuzz.py", allow_abbrev=False,
                                     description="Fuzz test of the names gate against GNU grep.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"generator seed (default {DEFAULT_SEED})")
    parser.add_argument("--cases", type=positive, default=DEFAULT_CASES,
                        help=f"number of (entry, line) pairs (default {DEFAULT_CASES})")
    parser.add_argument("--self-test", action="store_true",
                        help="check the coverage rule, and that three deliberately weakened gate stubs "
                             "are caught")
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test(args.seed)
    try:
        grep = find_grep()
        gate = load_gate()
        tally, failures = fuzz(gate, grep, args.seed, args.cases)
    except CannotEvaluate as exc:
        print(f"CANNOT-EVALUATE: {exc}")
        return 2
    print(f"names fuzz: seed {args.seed}, {tally['pairs']} (entry, line) pairs from {tally['entries']} entries, "
          f"{tally['paths']} sampled paths")
    print(f"  pairs compared with grep: {tally['compared']}")
    print(f"  pairs that agreed: {tally['agreed']} (grep -a matched {tally['grep matched']})")
    print(f"  NUL-split matches only the gate reports (the documented superset): {tally['nul superset']}")
    print(f"  entries the gate refuses and grep accepts (stricter, counted): {tally['stricter']}")
    print(f"  entries both refuse: {tally['both refused']}")
    print(f"  entries the gate accepts and grep refuses (counted): {tally['grep refused']}")
    print(f"  sampled paths where grep -o -b reports a match: {tally['paths with a match']}")
    outcome = run_outcome(tally, failures)
    if outcome == 1:
        for failure in failures:
            print(f"  FAIL  {describe(failure, args.seed)}")
        print(f"FAIL: names fuzz ({len(failures)} failure(s); rerun with --seed {args.seed} "
              f"--cases {args.cases} to reproduce)")
        return 1
    if outcome == 2:
        print(f"CANNOT-EVALUATE: {shortfall(tally)}")
        return 2
    print(f"PASS: names fuzz (seed {args.seed}, {tally['pairs']} pairs, no weaker case, no masking failure)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(main(sys.argv[1:]))
