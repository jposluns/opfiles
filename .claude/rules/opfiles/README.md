# Rules for this repository

This directory is this repository's own rule zone. Rules written for this repository go here.

The aiqt/ and security/ trees beside it, and .claude/RULES-INDEX.md, are vendored from the guardrails repository. They are pinned in .aiqt/pin.toml, checked by tools/check_aiqt_vendored.py, and never edited by hand.

They change only through a dedicated update PR that replaces both trees and the index wholesale and rewrites the pin.

The generation note in .claude/RULES-INDEX.md describes the guardrails repository, where the index is generated; here the index and both rule trees are vendored verbatim, pinned in .aiqt/pin.toml, and checked by tools/check_aiqt_vendored.py.
