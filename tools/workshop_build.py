#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf"]
# ///

"""Build a local searchable index for your own workshop manual copy."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / ".workshop_cache" / "workshop_index.json"

# procedure codes that matter to SMEG+ work: screen, fascia, radio, harnesses.
# matched as substrings of the bookmark title; pages are looked up, not stored.
RELEVANT_CODES = [
    "C5FG01A6P0",  # multifunction screen (the SMEG+ display)
    "C5FG01A7P0",  # instrument panel
    "C5FG01A8P0",  # centre console
    "C5FG01AEP0",  # dashboard
    "C5FG01APP0",  # dashboard, right-hand drive
    "C5FS011AP0",  # stripping-assembling dashboard
    "C5FS011BP0",  # stripping-assembling dashboard, right-hand drive
    "C5FG01AAP0",  # fascia panel air vents
    "C5FG01ADP0",  # fascia panel switches
    "D5AG014WP0",  # radio unit
    "D5AG014RP0",  # speakers
    "D5AG014UP0",  # radio aerial
    "D6AG013HP0",  # passenger-compartment harness
    "D6AM03P0",  # electrical harness repair
    "D6AM01HFP0",  # configure SMEG data-communication ECU
    "D6AM01CNP0",  # configure instrument panel
    "D6AM01CPP0",  # configure matrix display
]

# Public grouping, mirrored in docs/workshop-guide/. Codes not listed here land
# under "Other procedures". Order matters: the first matching group wins.
PROCEDURE_GROUPS = {
    "Body & fascia": [
        "C5FG01A6P0",  # multifunction screen
        "C5FG01A7P0",  # instrument panel
        "C5FG01AEP0",  # dashboard
        "C5FG01APP0",  # dashboard, right-hand drive
        "C5FS011AP0",  # stripping-assembling dashboard
        "C5FS011BP0",  # stripping-assembling dashboard, right-hand drive
        "C5FG01A8P0",  # centre console
        "C5FG01AAP0",  # fascia panel air vents
        "C5FG01ADP0",  # fascia panel switches
    ],
    "Electrical & audio": [
        "D5AG014WP0",  # radio unit
        "D5AG014RP0",  # speakers
        "D5AG014UP0",  # radio aerial
        "D6AG013HP0",  # passenger-compartment harness
        "D6AM03P0",  # electrical harness repair
        "D6AM01HFP0",  # configure SMEG data-communication ECU
        "D6AM01CNP0",  # configure instrument panel
        "D6AM01CPP0",  # configure matrix display
    ],
    "Mechanical": [
        "B1BG01BJP0",  # engine-gearbox assembly
        "B2BB010NP0",  # clutch tightening torques
        "B2BG011FP0",  # clutch mechanism
        "B2BI010EP0",  # bleed hydraulic clutch control
    ],
}


def group_for(title):
    """Return the public group for a bookmark title."""
    for group, codes in PROCEDURE_GROUPS.items():
        if any(code in title for code in codes):
            return group
    return "Other procedures"


def need_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        raise SystemExit(
            "pypdf is missing. Run with `uv run tools/workshop_build.py ...` "
            "so the PEP 723 dependencies are installed."
        )


def flatten(outline, reader, level=0):
    """Yield (level, title, 1-based page) for every bookmark, in order."""
    i = 0
    while i < len(outline):
        item = outline[i]
        if isinstance(item, list):
            yield from flatten(item, reader, level + 1)
            i += 1
            continue
        title = str(item.title)
        try:
            page = reader.get_destination_page_number(item) + 1
        except Exception:
            page = None
        yield (level, title, page)
        if i + 1 < len(outline) and isinstance(outline[i + 1], list):
            yield from flatten(outline[i + 1], reader, level + 1)
            i += 2
        else:
            i += 1


def build(src, relevant_only=False, index_text=True):
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    procedures = [
        {"level": lv, "title": t, "page": p} for lv, t, p in flatten(reader.outline, reader)
    ]
    pages = len(reader.pages)
    if relevant_only:
        wanted = set()
        for proc in procedures:
            if any(code in proc["title"] for code in RELEVANT_CODES):
                wanted.add(proc["page"])
                # the procedure's opening spread: first 3 pages carry the
                # location diagram and the first steps
                wanted.update({proc["page"] + 1, proc["page"] + 2})
        wanted = {p for p in wanted if p is not None and 1 <= p <= pages}
    else:
        wanted = set(range(1, pages + 1))
    page_text = {}
    if index_text:
        for p in sorted(wanted):
            try:
                text = (reader.pages[p - 1].extract_text() or "").strip()
            except Exception:
                text = ""
            if text:
                page_text[str(p)] = text[:4000]
    relevant = [pr for pr in procedures if any(c in pr["title"] for c in RELEVANT_CODES)]
    return {
        "source": Path(src).name,
        "pages": pages,
        "procedures": procedures,
        "relevant": relevant,
        "page_text": page_text,
        "ocr_pages": len(page_text),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The manual stays yours: only .workshop_cache/workshop_index.json "
        "(gitignored) is written, never anything committed.",
    )
    ap.add_argument("--src", required=True, help="your manual PDF (OCR'd copy)")
    ap.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="where to write the index (default: .workshop_cache/workshop_index.json)",
    )
    ap.add_argument(
        "--relevant-only",
        action="store_true",
        help="index text for SMEG-relevant pages only (fast); default is all pages",
    )
    ap.add_argument(
        "--print-table",
        action="store_true",
        help="print the SMEG-relevant procedures and their pages, grouped",
    )
    ap.add_argument(
        "--grep",
        default="",
        metavar="TEXT",
        help="print every bookmark whose title contains TEXT (case-insensitive) "
        "and write nothing; use it to find codes for any job",
    )
    args = ap.parse_args(argv)
    need_pypdf()
    src = Path(args.src).expanduser()
    if not src.is_file():
        raise SystemExit("no such file: %s" % src)
    if args.grep:
        needle = args.grep.lower()
        index = build(src, relevant_only=True, index_text=False)
        for proc in index["procedures"]:
            if needle in proc["title"].lower():
                print("p%-5s %s" % (proc["page"], proc["title"]))
        return 0
    index = build(src, relevant_only=args.relevant_only)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        "indexed %d procedures across %d pages (%d pages carry text) -> %s"
        % (len(index["procedures"]), index["pages"], index["ocr_pages"], out)
    )
    if not index["ocr_pages"]:
        print(
            "warning: no extractable text — run the OCR step first (docs/workshop-guide/local.md)"
        )
    if args.print_table:
        for group in list(PROCEDURE_GROUPS) + ["Other procedures"]:
            rows = [p for p in index["relevant"] if group_for(p["title"]) == group]
            if not rows:
                continue
            print("\n%s" % group)
            for proc in rows:
                print("  p%-5s %s" % (proc["page"], proc["title"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
