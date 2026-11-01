# Spec: native workshop guide (`/workshop-guide/`)

## Problem

SMEG+ work ends at the car: removing trim, reaching the head unit, unplugging
the right harness. The 208 workshop manual (3,100 pages, 597 procedures) holds
every sequence, but as a flat scanned PDF it is unusable from the docs site.
The previous iteration (a local PDF viewer page) kept the manual outside the
docs instead of bringing its structure into them.

## Goal

A native Zensical section that feels like part of smeg.kroper.uk:

- a **car map**: a schematic 208 with selectable parts (screen, panel, console,
  dashboard, vents, switches, radio, speakers, aerial, harness, SMEG ECU,
  engine/gearbox/clutch); selecting a part jumps to its procedure entry;
- **one entry per relevant procedure**: code, short name, PDF page(s), body
  variant notes (3-door / 5-door / RHD), and links into the SMEG+ docs that
  explain *why* the part matters (AUX lines, connectors, flashing);
- **full search** via the site's built-in search (procedure codes, part names).

## Hard boundary (legal)

The manual is a copyrighted PSA vendor publication. The public site carries
**metadata only**: procedure codes, short part names, page numbers, variant
notes, and our own cross-links. No copied steps, no torque values, no rendered
manual pages or diagrams. Same class of rule as the no-firmware rule
(`AGENTS.md` hard rule 1): if it needs the vendor document, it stays out of
the repo.

The *full* conversion — OCR text plus rendered page images per procedure —
exists as a **local-only converter** (`tools/workshop_convert.py`) whose output
is gitignored and previewed with `zensical serve`. It is never committed,
never attached to issues, never published.

## Information architecture

Committed (public, in nav under The unit → Workshop guide):

- `docs/workshop-guide/index.md` — landing page:
  1. what the section is and the legal boundary;
  2. a **start-here** table (electrical, body, mechanical, local workflow);
  3. the car map (inline SVG, hotspot per part, links to subpage anchors);
  4. how to read an entry (code, pages, variant, why it matters).
- `docs/workshop-guide/body.md` — body and fascia procedures, one
  `## <CODE> - <Part>` section each, plus a summary table.
- `docs/workshop-guide/electrical.md` — radio, speakers, aerial, harness, SMEG
  ECU and configuration entries.
- `docs/workshop-guide/mechanical.md` — the clutch cluster and engine-gearbox
  assembly, with a `## Clutch replacement` work order.
- `docs/workshop-guide/local.md` — OCR, index, converter, preview and
  troubleshooting, for the user's own copy.

Every procedure section gives code, manual page(s), variants, what it gives
access to, and `Related:` links into HARDWARE / AUX_SIGNAL / FLASHING etc.

Local-only (gitignored, built by the converter):

- `docs/workshop_generated/index.md` + `<code>.md` pages + `img/` renders —
  full procedure text and diagrams for personal use. Not in `zensical.toml`
  nav (the nav test walks `docs/**/*.md` but excludes this directory, because
  generated files must not leak into the committed nav). Preview with
  `zensical serve`; navigate to `/workshop_generated/`.

## Car map spec

- Original schematic line art (side view, committed as `tools/workshop_car.svg`
  template, inlined by hand into `docs/workshop-guide/index.md`): body,
  glasshouse, two wheels, roof aerial. No traced vendor figures.
- One hotspot per part: a numbered marker in the category colour (indigo body,
  teal electrical, orange mechanical), wrapped in
  `<a href="<subpage>/#<section-slug>">`. Slugs follow the site's existing
  header-slug rule (lowercase, spaces to hyphens, punctuation stripped), e.g.
  header `## C5FG01A6P0 - Multifunction screen` is linked as
  `#c5fg01a6p0-multifunction-screen`.
- Markers for co-located parts (screen / panel / ECU all behind the fascia)
  are offset so each stays tappable.

## Converter spec (`tools/workshop_convert.py`)

Input: the user's own OCR'd manual PDF (never in the repo).
Output: `docs/workshop_generated/` (gitignored).

- Reads the 597 bookmarks (code + title + 1-based page), same flattening as
  `workshop_build.py`.
- Per relevant procedure: writes `<code>.md` with the procedure's page range
  (up to the next bookmark, capped by `--max-pages`, default 15), OCR text per
  page as fenced content, and page renders (`img/<code>-p<page>.png`,
  Ghostscript/`pdftoppm` at 150 dpi, `--no-images` to skip). A truncated range
  says so in the page.
- Writes a generated landing page reusing the car-map SVG with links rewritten
  to the generated pages; markers for procedures not converted in this run fall
  back to the public entry. Tables are grouped by the same categories as the
  committed section (`PROCEDURE_GROUPS` in `workshop_build.py`).
- Runs are additive: existing generated pages stay and are re-listed, so a
  `--codes` run can extend a default build. `--clean` rebuilds from scratch.
- Warns when pages carry no text (manual not OCR'd yet).

## Acceptance

- `zensical build --strict` passes with the section (no hard links from
  committed pages to generated paths).
- `tool_reference --check`, docs-nav orphan test (now recursive, excluding
  `workshop_generated/` and `agents/`), header and no-PII checks pass.
- Every hotspot resolves to its section (slug rule verified against existing
  pages, e.g. `#how-the-boot-source-is-actually-chosen`), across all four
  subpages.
- Converter proven on 2+ procedures locally (text + images), output confirmed
  gitignored and uncommitted; incremental and `--clean` runs both produce a
  complete grouped landing page.
