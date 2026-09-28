#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Generate docs/TOOLS.md: every tool, its purpose and its `--help`, from the tools themselves.

The tool tables in README.md, AGENTS.md, CLAUDE.md and docs/RUNNING.md drifted: one was
missing 14 of 31 tools. This page is written from each tool's docstring and `--help` instead.

`--check` compares what should not drift silently - the set of tools, their groups and their
one-line summaries - and not the `--help` text, whose formatting changes between Python
versions (3.13 locally, 3.14 in CI). Re-run without `--check` to refresh the whole page.

usage:
    python3 tools/tool_reference.py            # rewrite docs/TOOLS.md
    python3 tools/tool_reference.py --check    # exit 1 if a tool is missing or its summary changed
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PAGE = ROOT / "docs" / "TOOLS.md"

# every command-line tool belongs to exactly one group; a new tool must be added here
GROUPS = {
    "Build and flash": [
        "build_package",
        "patch_smeg",
        "patch_media",
        "patch_contract",
        "preflight",
        "verify_package",
        "prepare_usb",
        "fix_userdata_case",
        "patch_status",
    ],
    "Media: tones, logos, settings": ["ringtones", "assets", "splash", "patch_studio"],
    "Diagnostics": ["spy_read"],
    "Firmware analysis": [
        "unpack",
        "fingerprint",
        "survey",
        "ppcdis",
        "ppcemu",
        "xref",
        "callers",
        "mkelf",
        "elfsyms",
        "symdiff",
        "crc_recover",
        "cartography",
        "tool_reference",
    ],
    "Repository hooks": ["check_commit_msg", "check_no_pii"],
}


def docstring(path):
    return ast.get_docstring(ast.parse(path.read_text())) or ""


def summary(path):
    doc = docstring(path).strip()
    return doc.splitlines()[0].strip() if doc else "(no docstring)"


def discover():
    """(tools with a __main__ block, libraries without one), by module name."""
    tools, libs = [], []
    for path in sorted(TOOLS.glob("*.py")):
        if path.stem == "__init__":
            continue
        (tools if '__name__ == "__main__"' in path.read_text() else libs).append(path.stem)
    return tools, libs


def help_text(name):
    env = dict(os.environ, COLUMNS="100", PYTHON_COLORS="0", NO_COLOR="1")
    r = subprocess.run(
        [sys.executable, str(TOOLS / (name + ".py")), "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return r.returncode, (r.stdout or r.stderr).rstrip()


def ungrouped(tools):
    grouped = {n for names in GROUPS.values() for n in names}
    return [t for t in tools if t not in grouped]


def render():
    tools, libs = discover()
    lines = [
        "# Tools",
        "",
        "Every tool in `tools/`, generated from its own docstring and `--help` by",
        "`tools/tool_reference.py`. Run any of them with `uv run tools/<name>.py`; none needs",
        "setting up (see [Running the tools](RUNNING.md)).",
        "",
        '!!! note "Generated page"',
        "",
        "    Edit the tool's docstring or arguments, then run `python3 tools/tool_reference.py`.",
        "    A test fails when a tool is missing from this page or its summary has changed.",
        "",
    ]
    for group, names in GROUPS.items():
        present = [n for n in names if n in tools]
        if not present:
            continue
        lines += ["## %s" % group, "", "| tool | what it does |", "|---|---|"]
        lines += [
            "| [`%s.py`](#%s) | %s |" % (n, n.replace("_", "-"), summary(TOOLS / (n + ".py")))
            for n in present
        ]
        lines.append("")
        for n in present:
            code, text = help_text(n)
            lines += [
                "### %s" % n.replace("_", "-"),
                "",
                "`tools/%s.py`: %s" % (n, summary(TOOLS / (n + ".py"))),
                "",
            ]
            lines += [
                "```text",
                text if code == 0 else "(--help failed: %s)" % text.splitlines()[-1:],
                "```",
                "",
            ]
    lines += [
        "## Shared libraries",
        "",
        "Imported by the tools above; not run directly.",
        "",
        "| module | what it holds |",
        "|---|---|",
    ]
    lines += ["| `%s.py` | %s |" % (n, summary(TOOLS / (n + ".py"))) for n in libs]
    return "\n".join(lines) + "\n"


SUMMARY_ROW = re.compile(r"^\| \[`(\w+)\.py`\]\(#[\w-]+\) \| (.*) \|$", re.M)


def check():
    """Problems that should fail CI: missing or ungrouped tools, stale summaries."""
    tools, _ = discover()
    problems = ["%s.py is not in any group in tool_reference.GROUPS" % t for t in ungrouped(tools)]
    if not PAGE.exists():
        return problems + ["docs/TOOLS.md does not exist"]
    listed = dict(SUMMARY_ROW.findall(PAGE.read_text()))
    for t in tools:
        want = summary(TOOLS / (t + ".py"))
        if t not in listed:
            problems.append("%s.py is missing from docs/TOOLS.md" % t)
        elif listed[t] != want:
            problems.append("%s.py's summary changed" % t)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="fail if the page is missing a tool")
    args = ap.parse_args(argv)
    if args.check:
        problems = check()
        for p in problems:
            print(p)
        if problems:
            print("run: python3 tools/tool_reference.py")
        return 1 if problems else 0
    tools, _ = discover()
    missing = ungrouped(tools)
    if missing:
        raise SystemExit("add to GROUPS first: %s" % ", ".join(missing))
    PAGE.write_text(render())
    print("wrote %s (%d tools)" % (os.path.relpath(PAGE, ROOT), len(tools)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
