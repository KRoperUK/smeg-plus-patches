#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf"]
# ///

"""Convert your own workshop manual copy into local Zensical pages.

Reads the manual's bookmarks and OCR text and writes one page per relevant
procedure — text plus rendered page images (diagrams preserved) — under
`docs/workshop_generated/`, with a car-map landing page. Preview with
`zensical serve`; the output is gitignored and must never be committed.

Rendering needs `pdftoppm` (poppler) or Ghostscript `gs` on PATH; without
either the pages are text-only (`--no-images` forces that).

usage:
    python3 tools/workshop_convert.py --src YOUR_manual_ocr.pdf
    python3 tools/workshop_convert.py --src YOUR_manual_ocr.pdf --no-images
    python3 tools/workshop_convert.py --src YOUR_manual_ocr.pdf --all --dpi 120
    python3 tools/workshop_convert.py --src YOUR_manual_ocr.pdf --codes B2BG011FP0
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from workshop_build import (  # noqa: E402
    PROCEDURE_GROUPS,
    RELEVANT_CODES,
    flatten,
    group_for,
)

DEFAULT_OUT = ROOT / "docs" / "workshop_generated"
MAX_PAGES_PER_PROCEDURE = 15


def need_pypdf():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        raise SystemExit(
            "pypdf is missing. Run with `uv run tools/workshop_convert.py ...` "
            "so the PEP 723 dependencies are installed."
        )


def renderer():
    if shutil.which("pdftoppm"):
        return "pdftoppm"
    if shutil.which("gs"):
        return "gs"
    return None


def render_pages(src, first, last, dpi, img_dir, stem, kind):
    """Render PDF pages first..last to img_dir/stem-p<page>.png. Returns count."""
    made = 0
    if kind == "pdftoppm":
        out_prefix = str(img_dir / stem)
        r = subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-r",
                str(dpi),
                "-f",
                str(first),
                "-l",
                str(last),
                str(src),
                out_prefix,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise SystemExit("pdftoppm failed: %s" % (r.stderr.strip() or r.stdout.strip()))
        # pdftoppm names: <prefix>-<page>.png with zero-padding to the last page
        width = len(str(last))
        for p in range(first, last + 1):
            got = img_dir / ("%s-%0*d.png" % (stem, width, p))
            want = img_dir / ("%s-p%d.png" % (stem, p))
            if got.is_file():
                got.rename(want)
                made += 1
    else:  # gs
        for p in range(first, last + 1):
            want = img_dir / ("%s-p%d.png" % (stem, p))
            r = subprocess.run(
                [
                    "gs",
                    "-dSAFER",
                    "-dBATCH",
                    "-dNOPAUSE",
                    "-sDEVICE=png16m",
                    "-r",
                    "%dx%d" % (dpi, dpi),
                    "-dFirstPage=%d" % p,
                    "-dLastPage=%d" % p,
                    "-sOutputFile=%s" % want,
                    str(src),
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and want.is_file():
                made += 1
    return made


def code_of(title):
    m = re.search(r"\b([A-Z][A-Z0-9]{5,})\b", title)
    return m.group(1) if m else None


def read_page_header(md):
    """(stem, title, first page) from a previously generated procedure page."""
    text = md.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("#").strip()
    m = re.search(r"pages \*\*(\d+)", text)
    return (md.stem, title, int(m.group(1)) if m else 0)


def rewrite_map(svg, pages):
    """Point car-map hotspots at generated pages, or the public entry."""
    by_code = {}
    for stem, title, _page in pages:
        code = code_of(title)
        if code:
            by_code.setdefault(code, stem)
    clutch = by_code.get("B2BG011FP0")

    def target(area, anchor):
        for code, stem in by_code.items():
            if code.lower() in anchor:
                return "./%s/" % stem
        if anchor == "clutch-replacement" and clutch:
            return "./%s/" % clutch
        # not converted in this run: fall back to the public metadata page
        return "../workshop-guide/%s/#%s" % (area, anchor)

    def repl(m):
        return 'href="%s"' % target(m.group(1) or "", m.group(2))

    return re.sub(r'href="(?:([a-z0-9-]+)/)?#([a-z0-9-]+)"', repl, svg)


def convert(
    src,
    out_dir,
    dpi=150,
    no_images=False,
    all_procs=False,
    codes="",
    max_pages=MAX_PAGES_PER_PROCEDURE,
):
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    flat = [(lv, t, p) for lv, t, p in flatten(reader.outline, reader)]
    flat = [x for x in flat if x[2] is not None]
    total_pages = len(reader.pages)

    if all_procs:
        wanted = flat
    elif codes:
        codes = [c.strip() for c in codes.split(",") if c.strip()]
        wanted = [x for x in flat if any(c in x[1] for c in codes)]
        if not wanted:
            raise SystemExit("no procedures match: %s" % ", ".join(codes))
    else:
        wanted = [x for x in flat if any(c in x[1] for c in RELEVANT_CODES)]

    kind = None if no_images else renderer()
    if not no_images and kind is None:
        print("warning: no pdftoppm or gs on PATH — text-only pages")

    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "img"
    if kind:
        img_dir.mkdir(parents=True, exist_ok=True)

    # page range per procedure: up to the next bookmark, capped by --max-pages
    pages_of = {}
    full_of = {}
    for i, (_, _, p) in enumerate(flat):
        nxt = flat[i + 1][2] if i + 1 < len(flat) else total_pages + 1
        natural = list(range(p, min(nxt, total_pages + 1)))
        full_of[p] = natural
        pages_of[p] = natural[:max_pages]

    used_stems = {}
    pages = []
    for _lv, title, p in wanted:
        code = code_of(title) or ("p%d" % p)
        n = used_stems.get(code, 0) + 1
        used_stems[code] = n
        stem = code if n == 1 else "%s-%d" % (code, n)
        prange = pages_of.get(p, [p])
        full = full_of.get(p, prange)
        truncated = full[-1] if full and full[-1] != prange[-1] else None

        texts = {}
        for pg in prange:
            try:
                texts[pg] = (reader.pages[pg - 1].extract_text() or "").strip()
            except Exception:
                texts[pg] = ""

        made = render_pages(src, prange[0], prange[-1], dpi, img_dir, stem, kind) if kind else 0

        lines = [
            "# %s" % title,
            "",
            "Procedure `%s`, manual pages **%d–%d**." % (code, prange[0], prange[-1]),
            "Converted locally from your own copy — do not republish.",
            "",
        ]
        if truncated:
            lines += [
                "*This is the first %d pages; the bookmark range runs to page %d. "
                "Raise `--max-pages` to convert the rest.*" % (len(prange), truncated),
                "",
            ]
        for pg in prange:
            if kind and (img_dir / ("%s-p%d.png" % (stem, pg))).is_file():
                lines += ["![manual page %d](img/%s-p%d.png)" % (pg, stem, pg), ""]
            if texts[pg]:
                lines += ["## Page %d" % pg, "", texts[pg], ""]
        if not any(texts.values()) and not made:
            lines += [
                "*No text or images for this range — OCR your copy first "
                "(see the Workshop guide).*",
                "",
            ]
        (out_dir / ("%s.md" % stem)).write_text("\n".join(lines), encoding="utf-8")
        pages.append((stem, title, p))

    # merge with pages already in the output dir, so --codes runs are additive
    known = {stem: (stem, title, p) for stem, title, p in pages}
    for md in sorted(out_dir.glob("*.md")):
        if md.name == "index.md" or md.stem in known:
            continue
        try:
            known[md.stem] = read_page_header(md)
        except (OSError, IndexError):
            continue
    pages = sorted(known.values(), key=lambda x: (x[2] or 0, x[0]))

    # landing page: reuse the car map, retarget hotspots to generated pages
    svg = rewrite_map((HERE / "workshop_car.svg").read_text(encoding="utf-8"), pages)
    landing = [
        "# Workshop procedures (local build)",
        "",
        "Generated from your own manual copy. Do not republish.",
        "",
        "Converted procedures open below. Markers not converted in this "
        "build fall back to the public guide.",
        "",
        svg,
        "",
    ]
    for group in list(PROCEDURE_GROUPS) + ["Other procedures"]:
        rows = [x for x in pages if group_for(x[1]) == group]
        if not rows:
            continue
        # the manual repeats some procedures; one row per code, all pages
        by_code = {}
        for stem, title, p in rows:
            by_code.setdefault(code_of(title) or stem, []).append((stem, title, p))
        landing += ["## %s" % group, "", "| procedure | manual pages |", "|---|---|"]
        for occurrences in by_code.values():
            title = occurrences[0][1]
            links = ", ".join("[%d](%s/)" % (p, stem) for stem, _t, p in occurrences)
            landing.append("| %s | %s |" % (title, links))
        landing.append("")
    (out_dir / "index.md").write_text("\n".join(landing), encoding="utf-8")
    return pages


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--src", required=True, help="your manual PDF (OCR'd copy)")
    ap.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT),
        help="generated site dir (default: docs/workshop_generated)",
    )
    ap.add_argument("--dpi", type=int, default=150, help="render resolution (default: 150)")
    ap.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES_PER_PROCEDURE,
        help="pages per procedure (default: %d); raise it for long jobs" % MAX_PAGES_PER_PROCEDURE,
    )
    ap.add_argument("--no-images", action="store_true", help="skip page rendering")
    ap.add_argument(
        "--all", action="store_true", help="convert all 597 procedures, not just SMEG-relevant ones"
    )
    ap.add_argument(
        "--codes",
        default="",
        help="comma-separated procedure codes to convert (e.g. B2BG011FP0,B2BB010NP0); overrides the relevant set",
    )
    ap.add_argument(
        "--clean", action="store_true", help="delete the output directory first (full rebuild)"
    )
    args = ap.parse_args(argv)
    need_pypdf()
    src = Path(args.src).expanduser()
    if not src.is_file():
        raise SystemExit("no such file: %s" % src)
    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    try:
        out_dir.relative_to(ROOT)
    except ValueError:
        raise SystemExit("--out-dir must be inside the repository")
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    pages = convert(
        src,
        out_dir,
        dpi=args.dpi,
        no_images=args.no_images,
        all_procs=args.all,
        codes=args.codes,
        max_pages=args.max_pages,
    )
    print("wrote %d procedure pages -> %s" % (len(pages), out_dir))
    print("preview: zensical serve  (then open /workshop_generated/)")
    print("reminder: %s is gitignored — never commit it" % out_dir.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
