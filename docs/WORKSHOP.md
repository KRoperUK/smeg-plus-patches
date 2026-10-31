# Workshop guide (208, 2012–2019)

How the SMEG+ jobs on this site map onto the car itself: which workshop
procedure to open, on which page, and how to read the manual as a searchable,
diagram-preserving viewer on your own machine.

!!! warning "Bring your own manual — it is not in this repository"

    The 208 workshop manual (a ~3,100-page, ~600-procedure PSA document) is a
    copyrighted vendor publication. Like firmware (see [the no-firmware rule](index.md#smeg-patches)),
    it is **never committed here**: no PDF, no extracted pages, no OCR text.
    Everything on this page works against **your own legally obtained copy**,
    kept outside the repo. The generated search index also stays on your machine
    (`.workshop_cache/`, gitignored).

!!! danger "Airbags, high voltage, and the fascia"

    Several procedures near the ones below work around pyrotechnic components
    (airbags, seat-belt pre-tensioners). Follow the manual's own safety
    sequences — battery disconnect, waiting times, connector handling — and treat
    them as mandatory, not advisory. If in doubt, stop and ask a professional.

## The manual at a glance

The copy this page was mapped against has **3,100 pages** and **597 bookmarked
procedures** in four top-level groups: Body Work, Electric Unit, Equipment, and
Mechanical. Its pages are scanned images, so a stock copy has **no searchable
text** — search and copy-paste only work after an OCR pass (below). Chapters
(bookmarks) work as shipped.

## SMEG+ jobs → workshop procedures

Every row is a procedure **code and page number**, not a copy of the procedure.
Open your own copy at the page and follow it there.

| what you are doing | procedure code | PDF page(s) |
|---|---|---|
| Remove/refit the multifunction screen (the SMEG+ display) | `C5FG01A6P0` | 1046, 1220, 1793 |
| Remove/refit the instrument panel | `C5FG01A7P0` | 1227, 1800 |
| Remove/refit the centre console | `C5FG01A8P0` | 1804 |
| Remove/refit the dashboard (incl. right-hand drive) | `C5FG01AEP0` / `C5FG01APP0` | 1826, 1852 |
| Strip/assemble the dashboard (incl. right-hand drive) | `C5FS011AP0` / `C5FS011BP0` | 1860, 1865 |
| Fascia panel air vents | `C5FG01AAP0` | 1055, 1813 |
| Fascia panel switches | `C5FG01ADP0` | 1063, 1821 |
| Remove/refit the radio unit | `D5AG014WP0` | 1182 |
| Speakers (front/rear doors) | `D5AG014RP0` | 1174 |
| Radio aerial | `D5AG014UP0` | 1178 |
| Passenger-compartment harness | `D6AG013HP0` | 1347 |
| Electrical harness repair | `D6AM03P0` | 1206, 1351, 1426 |
| Configure the SMEG data-communication ECU | `D6AM01HFP0` | 1201 |
| Configure the instrument panel / matrix display | `D6AM01CNP0` / `D6AM01CPP0` | 1199, 1231, 1233, 1870 |

The same procedure recurs in several manual sections (e.g. the multifunction
screen appears under Electric Unit and again under Equipment → Fascia Panel);
any listed page reaches the same sequence. For the box underneath the software —
connectors, pins, the AUX lines — start at [Hardware](HARDWARE.md); for getting
a package onto the car once the trim is back together, see
[Flashing](FLASHING.md).

## Step 1 — make your copy searchable

OCR adds a text layer; it does not touch the chapters or the diagrams. With
[OCRmyPDF](https://ocrmypdf.readthedocs.io/) (English text in this manual):

```sh
# Windows, inside WSL2 Ubuntu (tesseract-ocr-eng installed):
ocrmypdf --force-ocr -l eng --output-type pdf --optimize 1 \
  "peugeot-208-2012-2019_CHAPTERS_FIXED.pdf" \
  "peugeot-208-2012-2019_OCR_searchable.pdf"
```

Expect roughly 1–3 hours for the full manual on a many-core machine. The
output keeps all 597 chapters and renders identically — diagrams and images are
preserved because they are the original page scans.

## Step 2 — build the local index

`tools/workshop_build.py` reads **your** PDF's bookmarks and OCR text and writes
a search index under `.workshop_cache/` (gitignored, never committed):

```sh
uv run tools/workshop_build.py --src /path/to/peugeot-208-2012-2019_OCR_searchable.pdf
uv run tools/workshop_build.py --src /path/to/manual.pdf --relevant-only --print-table
```

It reports how many of the 597 procedures it found, how many pages carry OCR
text, and the SMEG-relevant subset from the table above. Run with `--help` for
all options; every option is also listed in [Tool reference](TOOLS.md).

## Step 3 — browse it

Open `tools/workshop_viewer.html` in a browser (double-click, or serve the repo
root and visit `tools/workshop_viewer.html`):

1. Pick your PDF (it never leaves your machine — it is loaded as a local object
   URL) and the generated `workshop_index.json`.
2. Filter the 597 procedures by code or keyword, or full-text search the OCR
   snippets for the SMEG-relevant pages.
3. Jump to any procedure: the viewer opens your PDF at that page, diagrams and
   wiring figures intact.

The public docs site's own search covers this page's procedure codes; the
in-PDF text search lives in the local viewer, next to the diagrams it describes.

## What this page does not do

- It does not replace the manual's safety sequences — those live in your copy.
- It does not host, quote, or paraphrase procedure steps beyond codes, short
  part names, and page numbers.
- It does not know your car's exact trim: 3-door vs 5-door and left- vs
  right-hand drive each have their own procedure variants, listed separately in
  the manual's bookmarks.
