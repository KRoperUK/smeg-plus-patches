# Workshop guide (208, 2012-2019)

The 208 workshop manual covers the whole car; this section is the index into
it. Pick a system, take the procedure **code** and **page number**, and open
your own copy there. It carries metadata only — no steps, no diagrams.

!!! warning "Bring your own manual — it is not in this repository"

    The 208 workshop manual (a ~3,100-page, ~600-procedure PSA document) is a
    copyrighted vendor publication. Like firmware (see [the no-firmware rule](../index.md#smeg-patches)),
    it is **never committed here**: no PDF, no extracted pages, no OCR text, no
    rendered diagrams. This section carries codes, part names, page numbers and
    our own cross-links only. Anything built from the manual's content runs on
    your machine, against your own copy — see [Reading your copy](local.md).

!!! danger "Airbags, pyrotechnics, and the fascia"

    Several procedures near the ones below work around pyrotechnic components
    (airbags, seat-belt pre-tensioners). Follow the manual's own safety
    sequences — battery disconnect, waiting times, connector handling — and
    treat them as mandatory, not advisory. If in doubt, stop and ask a
    professional.

## Start here

| If you need to… | Go to | Covers |
|---|---|---|
| Reach the display, radio, speakers or wiring | [Electrical & audio](electrical.md) | 7 procedures |
| Remove trim, vents, switches or the dashboard | [Body & fascia](body.md) | 6 procedures |
| Take the gearbox out or change the clutch | [Mechanical](mechanical.md) | 4 procedures |
| OCR your copy and build local pages | [Reading your copy](local.md) | the local workflow |

## Car map

Click a number to jump to the procedure entry. **Indigo** is body and fascia,
**teal** is electrical and audio, **orange** is mechanical.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 340" width="100%" role="img" aria-label="Schematic Peugeot 208 side view with twelve numbered, selectable parts">
  <g fill="none" stroke="#666" stroke-width="2" stroke-linejoin="round">
    <line x1="20" y1="292" x2="640" y2="292" stroke-width="1.5"/>
    <path d="M60,252 L72,208 Q76,192 96,190 L152,184 L212,126 Q220,116 234,116
             L358,116 Q370,116 378,126 L428,180 L518,192 Q558,197 574,216
             L588,236 Q593,250 578,252 L540,252 A38,38 0 0 0 462,252
             L208,252 A38,38 0 0 0 132,252 Z"/>
    <path d="M228,128 L356,128 L400,172 L208,172 Z" stroke-width="1.5"/>
    <line x1="292" y1="128" x2="292" y2="172" stroke-width="1.5"/>
    <line x1="318" y1="196" x2="340" y2="196" stroke-width="2.5"/>
    <line x1="228" y1="196" x2="250" y2="196" stroke-width="2.5"/>
    <circle cx="500" cy="262" r="30"/>
    <circle cx="500" cy="262" r="12" stroke-width="1.5"/>
    <circle cx="170" cy="262" r="30"/>
    <circle cx="170" cy="262" r="12" stroke-width="1.5"/>
    <path d="M246,116 L252,98 L258,116 Z" stroke-width="1.5"/>
  </g>
  <g font-family="system-ui,sans-serif" font-size="11" font-weight="bold" text-anchor="middle">
    <a href="body/#c5fg01a6p0-multifunction-screen"><title>Multifunction screen</title><circle cx="270" cy="165" r="11" fill="#3f51b5"/><text x="270" y="169" fill="#fff">1</text></a>
    <a href="body/#c5fg01a7p0-instrument-panel"><title>Instrument panel</title><circle cx="230" cy="172" r="11" fill="#3f51b5"/><text x="230" y="176" fill="#fff">2</text></a>
    <a href="body/#c5fg01aep0-dashboard"><title>Dashboard</title><circle cx="310" cy="140" r="11" fill="#3f51b5"/><text x="310" y="144" fill="#fff">3</text></a>
    <a href="body/#c5fg01a8p0-centre-console"><title>Centre console</title><circle cx="288" cy="234" r="11" fill="#3f51b5"/><text x="288" y="238" fill="#fff">4</text></a>
    <a href="body/#c5fg01aap0-fascia-air-vents"><title>Fascia air vents</title><circle cx="345" cy="152" r="11" fill="#3f51b5"/><text x="345" y="156" fill="#fff">5</text></a>
    <a href="body/#c5fg01adp0-fascia-panel-switches"><title>Fascia panel switches</title><circle cx="355" cy="185" r="11" fill="#3f51b5"/><text x="355" y="189" fill="#fff">6</text></a>
    <a href="electrical/#d5ag014wp0-radio-unit"><title>Radio unit</title><circle cx="275" cy="202" r="11" fill="#00796b"/><text x="275" y="206" fill="#fff">7</text></a>
    <a href="electrical/#d5ag014rp0-speakers"><title>Speakers</title><circle cx="360" cy="238" r="11" fill="#00796b"/><text x="360" y="242" fill="#fff">8</text></a>
    <a href="electrical/#d5ag014up0-radio-aerial"><title>Radio aerial</title><circle cx="252" cy="82" r="11" fill="#00796b"/><text x="252" y="86" fill="#fff">9</text><line x1="252" y1="93" x2="252" y2="99" stroke="#00796b" stroke-width="1.5"/></a>
    <a href="electrical/#d6ag013hp0-cabin-harness"><title>Cabin harness</title><circle cx="315" cy="245" r="11" fill="#00796b"/><text x="315" y="249" fill="#fff">10</text></a>
    <a href="electrical/#d6am01hfp0-smeg-ecu"><title>SMEG ECU</title><circle cx="320" cy="200" r="11" fill="#00796b"/><text x="320" y="204" fill="#fff">11</text></a>
    <a href="mechanical/#clutch-replacement"><title>Engine, gearbox and clutch</title><circle cx="110" cy="205" r="11" fill="#f57c00"/><text x="110" y="209" fill="#fff">12</text></a>
  </g>
</svg>

**Body & fascia:** 1. [Multifunction screen](body.md#c5fg01a6p0-multifunction-screen) ·
2. [Instrument panel](body.md#c5fg01a7p0-instrument-panel) ·
3. [Dashboard](body.md#c5fg01aep0-dashboard) ·
4. [Centre console](body.md#c5fg01a8p0-centre-console) ·
5. [Fascia air vents](body.md#c5fg01aap0-fascia-air-vents) ·
6. [Fascia panel switches](body.md#c5fg01adp0-fascia-panel-switches)

**Electrical & audio:** 7. [Radio unit](electrical.md#d5ag014wp0-radio-unit) ·
8. [Speakers](electrical.md#d5ag014rp0-speakers) ·
9. [Radio aerial](electrical.md#d5ag014up0-radio-aerial) ·
10. [Cabin harness](electrical.md#d6ag013hp0-cabin-harness) ·
11. [SMEG ECU](electrical.md#d6am01hfp0-smeg-ecu)

**Mechanical:** 12. [Engine, gearbox and clutch](mechanical.md#clutch-replacement)

## How to use an entry

Every entry gives you the same four things:

1. **Code** — e.g. `C5FG01A6P0`. It is the manual's bookmark key, so a search
   in your PDF finds the sequence, and the local index uses the same key.
2. **Manual pages** — 1-based PDF pages. The manual repeats some procedures in
   several sections, so more than one page can reach the same sequence.
3. **Variant** — 3-door, 5-door and right-hand drive have separate entries.
   Check the bookmark title matches your car before starting.
4. **Why it matters** — links into the SMEG+ pages that explain the part
   (connectors, AUX lines, flashing), so you know what you are looking at.

Page numbers refer to a **complete copy**. If yours is split into volumes or
has different front matter, use the bookmark rather than the number.

## Related reading

- [Hardware](../HARDWARE.md) — connectors, speaker outputs, the unit itself.
- [The AUX chain](../AUX_CHAIN.md) — what the radio and harness feed.
- [Flashing](../FLASHING.md) — the software side, once the trim is back on.
- [Tool reference](../TOOLS.md#workshop-build) — the two local tools.
