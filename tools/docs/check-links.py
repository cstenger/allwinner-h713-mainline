#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Verify every relative link in docs/ resolves. RUNS ON THE HOST, no board.

An index is only worth having if its links work, and this repo's docs are now
heavily cross-linked -- 525 relative links across 115 files. A dead link in
docs/README.md or register-index.md is worse than no entry, because it asserts
something exists.

CODE BLOCKS ARE SKIPPED, and that is not an optimisation. Disassembly listings
here contain things like `handler[+0x14](word)`, which is valid MIPS commentary
and a perfect impostor for markdown link syntax. Scanning raw text reports it as
a broken link to a file named "word". That was the only "failure" the first
version of this script found.

Anchors (`#section`) are checked for FILE existence only. Heading anchors are
not verified: headings here are long and full of punctuation, so reimplementing
GitHub's slug rules would produce false failures that train people to ignore the
gate.

    usage: tools/docs/check-links.py [--quiet]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "ftp://")


def links_in(text):
    """Yield link targets outside fenced and indented code blocks."""
    fenced = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced:
            continue
        # Indented code block. Markdown needs 4 spaces; disassembly dumps here
        # are indented well past that.
        if line.startswith("    ") or line.startswith("\t"):
            continue
        for m in LINK.finditer(line):
            yield m.group(1)


def main():
    quiet = "--quiet" in sys.argv
    broken, checked = [], 0
    for path in sorted(DOCS.rglob("*.md")):
        for target in links_in(path.read_text(errors="replace")):
            if target.startswith(SKIP_SCHEMES) or target.startswith("#"):
                continue
            checked += 1
            dest = (path.parent / target.split("#", 1)[0]).resolve()
            if not dest.exists():
                broken.append((path.relative_to(ROOT), target))

    if broken:
        print(f"BROKEN LINKS: {len(broken)} of {checked}", file=sys.stderr)
        for src, target in broken:
            print(f"  {src} -> {target}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"links: {checked} relative targets, all resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
