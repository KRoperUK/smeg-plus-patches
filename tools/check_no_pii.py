#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Refuse to commit personal data.

This repository is public, and the things that get pasted into it are exactly the things
that carry someone's details: a screenshot of a settings screen, a transcribed log, a
manifest with a local path in it, a note about which car was tested. The `no-firmware`
hook guards against shipping vendor binaries; this one guards against shipping *yourself*.

It looks for the patterns that identify a person in the UK, which is where this project's
units live:

    UK mobile number  07xxx xxxxxx, +44 7xxx xxxxxx
    UK postcode       the outward + inward pair, which is the address, not just the area
    email address     anything that looks like one
    NI number         the two-letter six-digit form

Deliberately **not** checked:

  * A bare `~/` or `/Users/<name>/` home path. The committed `builds/*.json` manifests are
    local build recipes and already carry one, and the docs say so. Blocking it would fail
    on files that are working as intended.
  * Car registrations. The current-format pattern (`AB12 CDE`) collides with ordinary
    uppercase tokens in disassembly notes and patch descriptions, so it would cry wolf.

A line is skipped when it contains `pii-ok`, which is the escape hatch for a deliberate
example — a documented test value, a hook message. Use it next to the hit, not at the top
of the file, so the exception stays visible when the line is read.

No dependencies, so this runs from the hooks with nothing installed.

usage:
    python3 tools/check_no_pii.py FILE [FILE ...]     # as a pre-commit hook
    python3 tools/check_no_pii.py $(git ls-files)     # over the whole tree
"""

import re
import sys
from pathlib import Path

PATTERNS = (
    ("UK mobile number", re.compile(r"(?<!\d)(?:\+44\s?7|07)\d{3}[\s\-.]?\d{3}[\s\-.]?\d{3}(?!\d)")),
    ("UK postcode", re.compile(r"(?<![A-Z0-9])[A-Z]{1,2}\d{1,2}[A-Z]? \d[A-Z]{2}(?![A-Z])")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("NI number", re.compile(r"(?<![A-Z])[A-Z]{2} ?\d{2} ?\d{2} ?\d{2} ?[A-D](?![A-Z])")),
)

# Not personal, and the docs would otherwise be unable to show an example address.
SAFE = ("example.com", "example.org", "example.net", "noreply@", "users.noreply.github.com")

# Reading these as text is pointless and can be slow.
BINARY_SUFFIX = (
    ".bin", ".out", ".mot", ".crc", ".rcc", ".pkg", ".wav", ".sqlite", ".ttf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".gz", ".7z", ".pdf",
)

MARKER = "pii-ok"


def scan(path):
    """Yield (line number, what, the matched text) for one file."""
    if Path(path).suffix.lower() in BINARY_SUFFIX:
        return
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return  # binary, or gone — nothing to judge
    for lineno, line in enumerate(text.splitlines(), 1):
        if MARKER in line:
            continue
        for what, rx in PATTERNS:
            for m in rx.finditer(line):
                if any(safe in m.group() for safe in SAFE):
                    continue
                yield lineno, what, m.group()


def main(argv):
    findings = []
    for path in argv[1:]:
        for lineno, what, hit in scan(path):
            findings.append((path, lineno, what, hit))

    if not findings:
        return 0

    print("personal data found in files about to be committed:\n")
    for path, lineno, what, hit in findings:
        print("  %s:%d  %s  %r" % (path, lineno, what, hit))
    print(
        "\nThis repository is public. Remove the detail, or — if the match is a deliberate\n"
        "example rather than a real one — put `%s` on that line." % MARKER
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
