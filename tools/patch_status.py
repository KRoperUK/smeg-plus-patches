#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Write each patch set's hardware status into the docs, from `patches/*.json` alone.

Status used to be restated by hand in several pages, and they drifted apart (fixed twice in
review). Now each `patches/<name>.json` carries it:

    "summary": "what it changes, one line of Markdown",
    "status": {"state": "never-flashed", "label": "Never flashed", "note": "..."}

`state` is one of STATES below and picks the pill colour; `label` and `note` are free text.
This regenerates the marked blocks in the docs:

    <!-- patch-status:table -->   ...   <!-- /patch-status:table -->    docs/PATCHES.md
    <!-- patch-status:panel -->   ...   <!-- /patch-status:panel -->    docs/index.md

usage:
    python3 tools/patch_status.py            # rewrite the blocks
    python3 tools/patch_status.py --check    # exit 1 if any block is stale (the test runs this)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCHES = ROOT / "patches"

# state -> (pill class, heading in the landing-page panel)
STATES = {
    "confirmed": ("pill-ok", "Confirmed on hardware"),
    "flashed": ("pill-wip", "Flashed, effect not yet confirmed"),
    "never-flashed": ("pill-wip", "Candidates awaiting a car test"),
    "falsified": ("pill-no", "Falsified on hardware"),
    "diagnostic": ("pill-no", "Diagnostic builds, not for driving"),
}
TARGETS = {
    "table": ROOT / "docs" / "PATCHES.md",
    "panel": ROOT / "docs" / "index.md",
}


def load():
    """[(name, summary, status)] for every patch set, sorted by name; refuses bad entries."""
    out = []
    for path in sorted(PATCHES.glob("*.json")):
        spec = json.loads(path.read_text())
        status, summary = spec.get("status"), spec.get("summary")
        if not isinstance(status, dict) or status.get("state") not in STATES or not summary:
            raise SystemExit(
                '%s: needs "summary" and "status": {"state": one of %s, "label", "note"}'
                % (path.name, ", ".join(STATES))
            )
        out.append((path.stem, summary, status))
    return out


def pill(status):
    return "**%s**{ .pill .%s }" % (status["label"], STATES[status["state"]][0])


def table(entries):
    lines = ["| file | what it changes | status |", "|---|---|---|"]
    for name, summary, status in entries:
        lines.append(
            "| `patches/%s.json` | %s | %s %s |" % (name, summary, pill(status), status["note"])
        )
    return "\n".join(lines)


def panel(entries):
    lines = []
    for state, (_, heading) in STATES.items():
        names = [n for n, _, s in entries if s["state"] == state]
        if names:
            lines.append("- **%s:** %s" % (heading, ", ".join("`%s`" % n for n in names)))
    lines.append("")
    lines.append("Per-patch detail: [Patch reference](PATCHES.md#patch-sets-in-this-repository).")
    return "\n".join(lines)


def render(kind, entries):
    return {"table": table, "panel": panel}[kind](entries)


def replace_block(text, kind, body):
    start, end = "<!-- patch-status:%s -->" % kind, "<!-- /patch-status:%s -->" % kind
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit("no %s ... %s block to fill" % (start, end))
    return pattern.sub(lambda _: "%s\n%s\n%s" % (start, body, end), text, count=1)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="fail if a block is out of date")
    args = ap.parse_args(argv)

    entries = load()
    stale = []
    for kind, path in TARGETS.items():
        old = path.read_text()
        new = replace_block(old, kind, render(kind, entries))
        if new != old:
            stale.append(os.path.relpath(path, ROOT))
            if not args.check:
                path.write_text(new)
    if args.check and stale:
        print("stale: %s - run: python3 tools/patch_status.py" % ", ".join(stale))
        return 1
    print(
        "%s: %d patch set(s)"
        % ("up to date" if not stale else "rewrote " + ", ".join(stale), len(entries))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
