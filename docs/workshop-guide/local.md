# Reading your copy locally

The public section tells you **where** to look. This page turns your own copy
into searchable, native pages — OCR text and rendered diagrams included. All
output stays on your machine and is gitignored; none of it is committed.

## What you need

- your own copy of the manual PDF;
- Python 3.10+ and `uv` — the tools declare their own dependencies;
- for OCR: WSL2/Ubuntu (or Linux/macOS) with `ocrmypdf` and `tesseract-ocr-eng`;
- for page renders: `pdftoppm` (poppler) or Ghostscript `gs`. Without either,
  the converter writes text-only pages.

## 1. OCR the scan

The stock manual is scanned images: no search, no selectable text.

```sh
# WSL2 Ubuntu, with tesseract-ocr-eng installed
ocrmypdf --force-ocr -l eng --output-type pdf --optimize 1 \
  "peugeot-208-2012-2019_CHAPTERS_FIXED.pdf" \
  "peugeot-208-2012-2019_OCR_searchable.pdf"
```

Two practical notes from a 3,100-page run:

- Put the temporary directory on a real disk, not the small `/tmp` tmpfs:
  `TMPDIR=/var/tmp/ocrtmp ocrmypdf ...`
- Expect a large output (the OCR'd copy is several times the scan) and a long
  run. Give OCRmyPDF several jobs if your machine can take it (`--jobs 16`).

## 2. Find the procedure codes

List the SMEG-relevant procedures and their pages:

```sh
uv run tools/workshop_build.py --src manual_ocr.pdf --relevant-only --print-table
```

Search the whole 597-bookmark tree for any other job:

```sh
uv run tools/workshop_build.py --src manual_ocr.pdf --grep clutch
```

`--print-table` also writes the index; `--grep` only prints matches and writes
nothing. Drop `--relevant-only` to index text for every page in gitignored
`.workshop_cache/`.

## 3. Build local pages

The default set is the procedures linked from this section:

```sh
uv run tools/workshop_convert.py --src manual_ocr.pdf
```

Or convert a specific job by code — the clutch cluster:

```sh
uv run tools/workshop_convert.py --src manual_ocr.pdf \
  --codes B1BG01BJP0,B2BB010NP0,B2BG011FP0,B2BI010EP0
```

Runs are additive: pages already in the output directory stay, and the landing
page lists everything. Use `--clean` for a full rebuild, `--all` for all 597
procedures, `--no-images` for text only, `--dpi` to change render resolution,
and `--max-pages` to extend a long procedure (the default is 15 pages; a
truncated page says so).

## 4. Preview

```sh
zensical serve
```

Open `/workshop_generated/`. The landing page reuses the car map: converted
procedures link to their generated page, and anything not converted falls back
to the public entry.

## What gets written

| Path | Contents |
|---|---|
| `docs/workshop_generated/index.md` | car map and grouped procedure table |
| `docs/workshop_generated/<code>.md` | one procedure, OCR text per page |
| `docs/workshop_generated/img/<code>-p<page>.png` | rendered pages and diagrams |
| `.workshop_cache/workshop_index.json` | searchable index |

All four are gitignored. Do not commit them, attach them to an issue, or
publish them.

## Troubleshooting

- **`No space left on device`** — OCRmyPDF's temporary files filled `/tmp` (a
  small tmpfs on WSL2). Set `TMPDIR` to a directory on the ext4 disk.
- **No text in the output** — the PDF was not OCR'd, or OCR failed. Check with
  a text search in your reader before converting.
- **No images** — neither `pdftoppm` nor `gs` is on `PATH`. Install poppler
  (`poppler-utils`) or Ghostscript.
- **A procedure is missing** — the code list is a filter, not a whitelist for
  the whole manual. Use `--grep` to find the code, then `--codes`.
