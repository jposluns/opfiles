#!/usr/bin/env python3
"""Self-test for the vendored-Marko CommonMark heading adapter (opf/tools/_commonmark_headings.py).

These are the change-carries-a-check artefacts for the adapter: targeted hostile fixtures that pin the
direct-H2 selection, plus the fail-closed paths (parser exception, missing span, oversized input, wrong
import origin, manifest drift, a manifest that is not the one recorded beside the wheel pin, and a
manifest that is not the one the import record holds). Judged on the adapter's returned values / raised
errors, never by grepping output. Reports the count of checks actually run. Runs as:

    python3 -I -B opf/tools/selftest_commonmark_headings.py

Exit 0 clean, 1 on a failed check, 2 on a fail-closed harness error (the vendored marko cannot load). The
full CommonMark 0.31.2 conformance replay lives in opf/tools/selftest_commonmark_conformance.py; this suite is
the targeted / adversarial complement to it.
"""
import sys

if tuple(sys.version_info[:2]) < (3, 14):
    import os
    try:
        sys.stderr.write(
            "error: selftest_commonmark_headings.py requires Python 3.14 or newer; this is Python %d.%d.%d (%s). "
            "Nothing was run (cannot evaluate).\n"
            % (tuple(sys.version_info[:3]) + (sys.executable or "unknown interpreter",)))
        sys.stderr.flush()
    except BaseException:
        pass
    os._exit(2)

import os
import tempfile
import hashlib
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _commonmark_headings as ch        # noqa: E402  the adapter under test


def _entries(text):
    """Return the adapter's boundaries as a list of (kind, payload, entry_slice) in document order, where
    entry_slice is the heading-start-to-next-heading-or-EOF slice the caller would freeze."""
    scan = ch.scan_entry_headings(text)
    starts = [h.start for h in scan.headings]
    out = []
    for i, h in enumerate(scan.headings):
        end = starts[i + 1] if i + 1 < len(starts) else len(scan.normalized_text)
        out.append((h.kind, h.payload, scan.normalized_text[h.start:end]))
    return out


def _payloads(text):
    return [payload for _kind, payload, _slice in _entries(text)]


def _raises(reason, fn, *args, **kwargs):
    """True when calling fn raises HeadingScanError with the given .reason."""
    try:
        fn(*args, **kwargs)
    except ch.HeadingScanError as exc:
        return exc.reason == reason
    except Exception:
        return False
    return False


def _value(fn, *args, **kwargs):
    """fn's return value, or the HeadingScanError it raised, so a row whose call is refused is recorded as
    a named failed check rather than ending the suite with a traceback."""
    try:
        return fn(*args, **kwargs)
    except ch.HeadingScanError as exc:
        return exc


def self_test():
    # Fail closed if the vendored marko cannot load at all: without it this suite cannot run, and a green
    # exit would be a false pass (verifier-delivery-completeness / check-fails-closed-on-unreadable).
    try:
        ch._load_marko()
    except ch.HeadingScanError as exc:
        print("COMMONMARK-HEADINGS SELF-TEST ERROR: vendored marko unavailable ({}: {}); fail-closed".format(
            exc.reason, exc), file=sys.stderr)
        return 2

    failures = []
    checked = 0

    def check(name, cond):
        nonlocal checked
        checked += 1
        if not cond:
            failures.append(name)

    # --- ATX / setext selection ----------------------------------------------------------------------
    check("atx-h2-is-boundary", _payloads("## 1.0.0 (2026-06-01)\n\n- x\n") == ["1.0.0 (2026-06-01)"])
    check("h1-not-boundary", _payloads("# Title\n\n- x\n") == [])
    check("h3-not-boundary", _payloads("### 1.0.0\n\n- x\n") == [])
    check("setext-h2-is-boundary",
          _entries("1.0.0 (2026-06-01)\n---\n\n- x\n") == [(ch.KIND_SETEXT, "1.0.0 (2026-06-01)",
                                                            "1.0.0 (2026-06-01)\n---\n\n- x\n")])
    check("setext-h1-not-boundary", _payloads("Title\n===\n\n- x\n") == [])
    check("multiline-setext-keeps-newline",
          _payloads("1.0.0\ntrailing title\n---\n") == ["1.0.0\ntrailing title"])
    check("atx-with-3-space-indent-is-boundary", _payloads("   ## 1.0.0\n") == ["1.0.0"])
    check("atx-empty-payload-is-boundary-with-empty-token", _payloads("##\n\n- x\n") == [""])
    check("atx-closing-hashes-stripped", _payloads("## 1.0.0 ##\n") == ["1.0.0"])

    # --- thematic-break ambiguity --------------------------------------------------------------------
    check("thematic-break-alone-not-a-heading", _payloads("- x\n\n---\n\n- y\n") == [])
    check("dashes-after-text-are-setext", _payloads("1.0.0\n---\n") == ["1.0.0"])

    # --- fences: a "##" inside a fence is not a boundary ---------------------------------------------
    check("backtick-fence-hides-hash",
          _payloads("## real\n\n```\n## not-a-heading\n```\n") == ["real"])
    check("tilde-fence-hides-hash",
          _payloads("## real\n\n~~~\n## not-a-heading\n~~~\n") == ["real"])
    check("info-string-fence-hides-hash",
          _payloads("## real\n\n```python\n## not-a-heading\n```\n") == ["real"])
    check("unterminated-fence-hides-trailing-hash",
          _payloads("## real\n\n```\n## not-a-heading\n") == ["real"])

    # --- indented code: a 4-space "##" is code; a 4-space fence does not hide a later "##" ------------
    check("indented-code-hash-not-a-boundary",
          _payloads("para\n\n    ## not-a-heading\n") == [])
    check("indented-fence-does-not-hide-later-heading",
          _payloads("## real\n\n    ```\n## 9.9.9\n") == ["real", "9.9.9"])

    # --- HTML blocks: a "##" inside any HTML-block category is not a boundary -------------------------
    # Assert the fenced/embedded tokens do not surface as payloads, and a real H2 after the block does.
    check("html-type1-pre-hides-hash",
          "## inside" not in "".join(_payloads("<pre>\n## inside\n</pre>\n\n## real\n"))
          and "real" in _payloads("<pre>\n## inside\n</pre>\n\n## real\n"))
    check("html-type2-comment-blanklines-hides-hash",
          _payloads("<!--\n## inside\n\n## still inside\n-->\n\n## real\n") == ["real"])
    check("html-type3-instruction-hides-hash",
          _payloads("<?php\n## inside\n?>\n\n## real\n") == ["real"])
    check("html-type4-declaration-hides-hash",
          _payloads("<!X\n## inside\n>\n\n## real\n") == ["real"])
    check("html-type5-cdata-hides-hash",
          _payloads("<![CDATA[\n## inside\n]]>\n\n## real\n") == ["real"])
    check("html-type6-block-tag-hides-hash",
          _payloads("<div>\n## inside\n\n## real\n") == ["real"])
    check("html-type7-complete-tag-hides-hash",
          _payloads('<a href="/x">\n## inside\n\n## real\n') == ["real"])

    # --- nested containers: a "##" inside a quote or list is not a top-level boundary -----------------
    check("blockquote-hash-not-a-boundary", _payloads("> ## not-a-heading\n\n## real\n") == ["real"])
    check("list-hash-not-a-boundary", _payloads("- item\n  ## not-a-heading\n\n## real\n") == ["real"])

    # --- CR/CRLF and NUL: normalized, offsets aligned, no crash --------------------------------------
    crlf = "## 1.1.0 (2026-06-15)\r\n\r\n- second\r\n\r\n## 1.0.0 (2026-06-01)\r\n\r\n- first\r\n"
    check("crlf-normalized-slices",
          _entries(crlf)[0] == (ch.KIND_ATX, "1.1.0 (2026-06-15)",
                                "## 1.1.0 (2026-06-15)\n\n- second\n\n"))
    lone_cr = "## 1.0.0 (2026-06-01)\r\r- first\r"
    check("lone-cr-normalized", _payloads(lone_cr) == ["1.0.0 (2026-06-01)"])
    nul = "## has\x00nul\n\n- x\n"
    scan_nul = ch.scan_entry_headings(nul)
    check("nul-preserved-in-normalized-text", "\x00" in scan_nul.normalized_text)
    check("nul-heading-still-recognized", _payloads(nul) == ["has\x00nul"])

    # --- digest boundary: the slice runs to the NEXT direct H2, not to EOF ----------------------------
    two = "## 1.1.0 (2026-06-15)\n\n- second release\n\n## 1.0.0 (2026-06-01)\n\n- first release\n"
    check("nonfinal-entry-slice-ends-at-next-h2",
          _entries(two)[0][2] == "## 1.1.0 (2026-06-15)\n\n- second release\n\n")
    check("final-entry-slice-runs-to-eof",
          _entries(two)[1][2] == "## 1.0.0 (2026-06-01)\n\n- first release\n")

    # --- FAIL-CLOSED: oversized input ----------------------------------------------------------------
    oversized = "#" * (ch.MAX_CHANGELOG_BYTES + 1)
    check("oversized-fails-closed", _raises(ch.REASON_OVERSIZED, ch.scan_entry_headings, oversized))
    at_ceiling = "## x\n" + "y\n" * ((ch.MAX_CHANGELOG_BYTES - 5) // 2)
    check("at-ceiling-does-not-fail-closed", len(at_ceiling.encode("utf-8")) <= ch.MAX_CHANGELOG_BYTES
          and ch.scan_entry_headings(at_ceiling) is not None)

    # --- FAIL-CLOSED: parser exception ---------------------------------------------------------------
    saved_new_parser = ch._new_parser

    class _Boom:
        def parse(self, _text):
            raise RuntimeError("simulated parser fault")

    ch._new_parser = lambda _marko: _Boom()
    try:
        check("parser-exception-fails-closed", _raises(ch.REASON_PARSER, ch.scan_entry_headings, "## x\n"))
    finally:
        ch._new_parser = saved_new_parser

    # --- FAIL-CLOSED: missing / invalid source span --------------------------------------------------
    marko = ch._load_marko()

    class _NoSpanHeading(marko.block.Heading):
        pass

    class _FakeDoc:
        def __init__(self, norm):
            self.source_span = (0, len(norm))
            bad = _NoSpanHeading.__new__(_NoSpanHeading)
            bad.level = 2
            bad.source_span = None        # a level-2 heading with no usable span
            self.children = [bad]

    class _FakeParser:
        def parse(self, text):
            return _FakeDoc(ch._normalize_lf(text))

    ch._new_parser = lambda _marko: _FakeParser()
    try:
        check("missing-span-fails-closed", _raises(ch.REASON_INVALID_SPAN, ch.scan_entry_headings, "## x\n"))
    finally:
        ch._new_parser = saved_new_parser

    # --- FAIL-CLOSED: structurally-degenerate parse result (F2) --------------------------------------
    class _NoChildrenDoc:
        def __init__(self, norm):
            self.source_span = (0, len(norm))   # a document with NO children attribute at all

    class _NoChildrenParser:
        def parse(self, text):
            return _NoChildrenDoc(ch._normalize_lf(text))

    ch._new_parser = lambda _marko: _NoChildrenParser()
    try:
        check("no-children-fails-closed", _raises(ch.REASON_PARSER, ch.scan_entry_headings, "## x\n"))
    finally:
        ch._new_parser = saved_new_parser

    class _NoLevelHeading(marko.block.Heading):
        pass

    class _NoLevelDoc:
        def __init__(self, norm):
            self.source_span = (0, len(norm))
            bad = _NoLevelHeading.__new__(_NoLevelHeading)
            bad.source_span = (0, 4)
            bad.level = None              # a heading node with no integer level is a malformed structure
            self.children = [bad]

    class _NoLevelParser:
        def parse(self, text):
            return _NoLevelDoc(ch._normalize_lf(text))

    ch._new_parser = lambda _marko: _NoLevelParser()
    try:
        check("no-level-heading-fails-closed", _raises(ch.REASON_PARSER, ch.scan_entry_headings, "## x\n"))
    finally:
        ch._new_parser = saved_new_parser

    # --- FAIL-CLOSED: wrong import origin / version --------------------------------------------------
    class _FakeModule:
        pass

    outside = _FakeModule()
    outside.__version__ = ch.MARKO_VERSION
    outside.__file__ = "/usr/lib/python3/dist-packages/marko/__init__.py"   # outside the vendored tree
    check("wrong-import-origin-fails-closed",
          _raises(ch.REASON_PROVENANCE, ch._verify_marko_provenance, outside, ch._VENDOR_DIR))

    wrong_version = _FakeModule()
    wrong_version.__version__ = "2.2.3"
    wrong_version.__file__ = os.path.join(ch._VENDOR_DIR, "marko", "__init__.py")
    check("wrong-version-fails-closed",
          _raises(ch.REASON_PROVENANCE, ch._verify_marko_provenance, wrong_version, ch._VENDOR_DIR))

    # The genuine vendored module passes provenance (positive control that the check is not always-fail).
    check("genuine-provenance-passes", (lambda: (ch._verify_marko_provenance(marko, ch._VENDOR_DIR), True)[1])())

    # --- FAIL-CLOSED: a submodule resolved outside the vendored tree (F6) ----------------------------
    check("submodule-origin-outside-fails-closed",
          _raises(ch.REASON_PROVENANCE, ch._verify_module_origin, outside, ch._VENDOR_DIR))
    no_file = _FakeModule()
    no_file.__name__ = "marko.parser"
    check("submodule-origin-nofile-fails-closed",
          _raises(ch.REASON_PROVENANCE, ch._verify_module_origin, no_file, ch._VENDOR_DIR))
    check("genuine-submodule-origin-passes",
          (lambda: (ch._verify_module_origin(marko.block, ch._VENDOR_DIR),
                    ch._verify_module_origin(marko.parser, ch._VENDOR_DIR), True)[2])())

    # --- FAIL-CLOSED: manifest drift over a synthetic vendored tree ----------------------------------
    tmp = tempfile.mkdtemp(prefix="commonmark-headings-selftest-")
    try:
        pkg = os.path.join(tmp, "marko")
        os.makedirs(pkg)
        f_init = os.path.join(pkg, "__init__.py")
        f_parser = os.path.join(pkg, "parser.py")
        with open(f_init, "wb") as fh:
            fh.write(b"# init\n")
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser\n")

        def sha(path):
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()

        manifest_path = os.path.join(tmp, ch.MANIFEST_NAME)
        provenance_path = os.path.join(tmp, ch.PROVENANCE_NAME)
        inventory_path = os.path.join(tmp, ch.INVENTORY_NAME)
        wheel_sha = ch.MARKO_WHEEL_SHA256      # the synthetic record holds the pinned wheel sha256

        def read_bytes(path):
            with open(path, "rb") as fh:
                return fh.read()

        def write_bytes(path, data):
            with open(path, "wb") as fh:
                fh.write(data)

        def write_provenance(manifest_sha, version=ch.MARKO_VERSION, wheel=wheel_sha, extra=""):
            with open(provenance_path, "w", encoding="utf-8") as fh:
                fh.write('[package]\nversion = "{}"\n\n[artifacts.wheel]\nsha256 = "{}"\n{}'.format(
                    version, wheel, extra))
                if manifest_sha is not None:
                    fh.write('manifest_sha256 = "{}"\n'.format(manifest_sha))

        def import_entry(imported_manifest, rel=ch.MANIFEST_NAME):
            # The entry a synthetic import record holds for a manifest whose bytes as imported (with the
            # opf/ prefix put back) are `imported_manifest`.
            as_imported = ch.as_imported_manifest(imported_manifest)
            return {"blob": ch.git_blob_id(as_imported), "mode": "100644", "path": rel,
                    "sha256": hashlib.sha256(as_imported).hexdigest()}

        def write_inventory(entries):
            with open(inventory_path, "w", encoding="utf-8") as fh:
                json.dump({"deviations": [], "entries": entries}, fh, indent=1, sort_keys=True)

        def write_manifest(entries, rebind=True, reimport=True):
            # rebind=True re-pins the synthetic provenance record to the new manifest and reimport=True
            # re-anchors the synthetic import record to it, so rows that test the per-file check are not
            # masked by either; rebind=False or reimport=False keeps the old record.
            with open(manifest_path, "w", encoding="utf-8") as fh:
                for digest, rel in entries:
                    fh.write("{}  {}\n".format(digest, rel))
            if rebind:
                write_provenance(sha(manifest_path))
            if reimport:
                write_inventory([import_entry(read_bytes(manifest_path))])

        good = [(sha(f_init), "marko/__init__.py"), (sha(f_parser), "marko/parser.py")]
        write_manifest(good)
        good_manifest = read_bytes(manifest_path)
        check("manifest-clean-verifies", _value(ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp) == 2)
        # F7: the REAL committed manifest (repo-root-relative paths) verifies against the real vendored tree
        # under DEFAULT arguments -- exercising the standing per-push wiring, not only synthetic trees. This
        # includes the check of the real manifest against the real provenance record and the real import
        # record (PROVENANCE-inventory.json).
        check("real-vendored-tree-verifies", _value(ch.verify_vendor_manifest) == 26)

        # --- manifest checked against the provenance record (TODO 313) --------------------------------
        # RED: a vendored file and its manifest row edited together, with the provenance record (version,
        # wheel sha256 and manifest_sha256) unchanged. The per-file check alone accepts this; the binding
        # refuses it. The synthetic import record is re-anchored to the edit, so only the binding decides.
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser EDITED WITH ITS ROW\n")
        write_manifest([(sha(f_init), "marko/__init__.py"), (sha(f_parser), "marko/parser.py")], rebind=False)
        check("manifest-row-changed-same-pin-refused",
              _raises(ch.REASON_MANIFEST_UNBOUND, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # Residual of the binding alone: the same edit with manifest_sha256 rewritten, the version and the
        # wheel sha256 unchanged, passes verify_manifest_binding.
        write_provenance(sha(manifest_path))
        check("manifest-row-changed-with-rewritten-digest-passes-binding-residual",
              isinstance(_value(ch.verify_manifest_binding, read_bytes(manifest_path), provenance_path),
                         tuple))
        # --- manifest anchored to the import record (review MAJOR 1) ---------------------------------
        # RED: that same-pin edit (file, row and manifest_sha256 together) is refused by the import anchor
        # while the import record still holds the manifest as imported.
        write_inventory([import_entry(good_manifest)])
        check("manifest-row-changed-with-rewritten-digest-not-imported-refused",
              _raises(ch.REASON_MANIFEST_NOT_IMPORTED, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # Residual of the anchor: the same edit with a forged import record (its entry rewritten) passes.
        write_inventory([import_entry(read_bytes(manifest_path))])
        check("manifest-row-changed-with-forged-import-record-passes-residual",
              _value(ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp) == 2)
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser\n")
        write_manifest(good)
        # RED: a changed import entry (its blob is not the clean manifest's) refuses the clean tree.
        write_inventory([import_entry(good_manifest + b"# another manifest\n")])
        check("manifest-import-entry-changed-refused",
              _raises(ch.REASON_MANIFEST_NOT_IMPORTED, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # The rebuild of the imported bytes: opf/ goes back after the two spaces of each row and nowhere else.
        check("manifest-as-imported-prefixes-each-row",
              ch.as_imported_manifest(b"# note  x\n" + b"a" * 64 + b"  x/y\n" + b"b" * 64 + b"  z\n")
              == b"# note  x\n" + b"a" * 64 + b"  opf/x/y\n" + b"b" * 64 + b"  opf/z\n")
        # The import record must be readable UTF-8 JSON with exactly one usable entry for the manifest.
        os.remove(inventory_path)
        check("manifest-import-record-absent-refused",
              _raises(ch.REASON_VENDOR_UNREADABLE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # Each malformed record below except not-json holds a usable entry for the manifest (or, for
        # no-entries-list, entries-not-a-list and not-an-object, has nothing a later step can iterate), so
        # only the guard each row is named for refuses it: with that guard removed, the record is accepted
        # or a later step raises an error that is not a HeadingScanError, and the row fails. The row
        # entries-not-a-list also fails when the entries-list guard is weakened to a None check, because a
        # number is not None and cannot be iterated. The control row shows the raw entry bytes themselves
        # are accepted.
        entry_json = json.dumps(import_entry(good_manifest), sort_keys=True).encode("utf-8")
        write_bytes(inventory_path, b'{"entries": [' + entry_json + b"]}")
        check("manifest-import-record-raw-control-verifies",
              _value(ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp) == 2)
        for name, raw in (("not-json", b'{"entries": ['),
                          ("not-utf8", b'{"entries": [' + entry_json + b'], "x": "\xff"}'),
                          ("duplicate-key", b'{"entries": [], "entries": [' + entry_json + b"]}"),
                          ("nan", b'{"entries": [' + entry_json + b'], "x": NaN}'),
                          ("no-entries-list", b"{}"),
                          ("entries-not-a-list", b'{"entries": 5}'),
                          ("not-an-object", b"[]")):
            write_bytes(inventory_path, raw)
            check("manifest-import-record-{}-refused".format(name),
                  _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_inventory([import_entry(good_manifest, rel="elsewhere/" + ch.MANIFEST_NAME)])
        check("manifest-import-record-no-entry-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_inventory([import_entry(good_manifest), import_entry(good_manifest)])
        check("manifest-import-record-two-entries-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        upper = import_entry(good_manifest)
        upper["blob"] = upper["blob"].upper()
        write_inventory([upper])
        check("manifest-import-record-bad-blob-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_manifest(good)

        # RED: one byte of the REAL committed manifest changed (a digest row's first hex digit), checked
        # against the REAL provenance record and the REAL import record: each refuses it.
        try:
            with open(os.path.join(ch._VENDOR_DIR, ch.MANIFEST_NAME), "rb") as fh:
                real_manifest = fh.read()
        except OSError:
            real_manifest = b""           # the real-manifest rows below then fail, by name
        real_provenance = os.path.join(ch._VENDOR_DIR, ch.PROVENANCE_NAME)
        real_root = os.path.dirname(os.path.dirname(ch._VENDOR_DIR))
        real_inventory = os.path.join(real_root, ch.INVENTORY_NAME)
        real_rel = os.path.relpath(os.path.join(ch._VENDOR_DIR, ch.MANIFEST_NAME), real_root)
        real_rel = real_rel.replace(os.sep, "/")
        one_byte = (b"0" if real_manifest[:1] != b"0" else b"1") + real_manifest[1:]
        check("real-manifest-one-byte-change-refused",
              len(one_byte) == len(real_manifest)
              and _raises(ch.REASON_MANIFEST_UNBOUND, ch.verify_manifest_binding, one_byte, real_provenance))
        bound = _value(ch.verify_manifest_binding, real_manifest, real_provenance)
        check("real-manifest-binding-verifies", isinstance(bound, tuple) and bound[0] == ch.MARKO_VERSION)
        check("real-manifest-one-byte-change-not-imported-refused",
              len(one_byte) == len(real_manifest)
              and _raises(ch.REASON_MANIFEST_NOT_IMPORTED, ch.verify_manifest_import, one_byte,
                          real_inventory, real_rel))
        anchored = _value(ch.verify_manifest_import, real_manifest, real_inventory, real_rel)
        check("real-manifest-import-anchor-verifies", isinstance(anchored, str) and len(anchored) == 40)
        # Malformed, missing or unpinned pin fields fail closed as provenance errors; a missing record is
        # unreadable.
        write_provenance(None)
        check("manifest-binding-missing-digest-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_provenance(sha(manifest_path), version="2.2.3")
        check("manifest-binding-wrong-version-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_provenance(sha(manifest_path), wheel="AB" * 32)
        check("manifest-binding-bad-wheel-sha-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_provenance(sha(manifest_path), wheel="cd" * 32)
        check("manifest-binding-other-wheel-sha-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        with open(provenance_path, "wb") as fh:
            fh.write(b"[package\n")
        check("manifest-binding-not-toml-refused",
              _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # A record without [package], without [artifacts.wheel], or whose artifacts is not a table is
        # refused with a reason, not a crash.
        pin_lines = 'sha256 = "{}"\nmanifest_sha256 = "{}"\n'.format(wheel_sha, sha(manifest_path))
        for name, text in (("no-package", "[artifacts.wheel]\n" + pin_lines),
                           ("no-wheel-table", '[package]\nversion = "{}"\n'.format(ch.MARKO_VERSION)),
                           ("artifacts-not-a-table",
                            'artifacts = "wheel"\n\n[package]\nversion = "{}"\n'.format(ch.MARKO_VERSION))):
            write_bytes(provenance_path, text.encode("utf-8"))
            check("manifest-binding-{}-refused".format(name),
                  _raises(ch.REASON_PROVENANCE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        os.remove(provenance_path)
        check("manifest-binding-record-absent-refused",
              _raises(ch.REASON_VENDOR_UNREADABLE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        # A manifest that is not UTF-8, bound in the record and anchored in the import record so both
        # checks pass, is refused when it is decoded.
        write_bytes(manifest_path, good_manifest + b"\xff\n")
        write_provenance(sha(manifest_path))
        write_inventory([import_entry(read_bytes(manifest_path))])
        check("manifest-not-utf8-refused",
              _raises(ch.REASON_MANIFEST_DRIFT, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
        write_manifest(good)

        # A drifted file (bytes differ from the recorded digest).
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser CHANGED\n")
        check("manifest-drift-fails-closed",
              _raises(ch.REASON_MANIFEST_DRIFT, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))

        # A missing recorded file.
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser\n")        # restore bytes so only the removal matters
        os.remove(f_parser)
        check("manifest-missing-file-fails-closed",
              _raises(ch.REASON_MANIFEST_DRIFT, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))

        # An extra, unlisted vendored file (bidirectional reconciliation).
        with open(f_parser, "wb") as fh:
            fh.write(b"# parser\n")
        write_manifest([(sha(f_init), "marko/__init__.py")])   # omit parser.py from the manifest
        check("manifest-extra-file-fails-closed",
              _raises(ch.REASON_MANIFEST_DRIFT, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))

        # A missing manifest is unreadable, not "nothing to check".
        os.remove(manifest_path)
        check("manifest-absent-fails-closed",
              _raises(ch.REASON_VENDOR_UNREADABLE, ch.verify_vendor_manifest, vendor_dir=tmp, root=tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("COMMONMARK-HEADINGS SELF-TEST: FAIL ({} of {} checks failed)".format(len(failures), checked))
        for name in failures:
            print("  FAILED: {}".format(name))
        return 1
    print("COMMONMARK-HEADINGS SELF-TEST: PASS ({} heading-selection and fail-closed checks)".format(checked))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(self_test())
