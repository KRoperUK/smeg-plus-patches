# The cartography subsystem

How the unit's map data is organised, and what it would take to supply your own.

This page exists because the answer changed. `CAPABILITIES.md` used to park maps as
"proprietary and uninspectable"; then the container turned out to be a gzipped tar of tiles;
then the **engine turned out to be shipped unstripped**. Every claim here comes from files in
the update packages, not from inference — the evidence is named as it goes.

## Where the truth comes from

Two PowerPC ELF files carry the whole subsystem, and neither is stripped:

| file | where | symbols |
|---|---|---|
| `db_dwnl_ppc.out` | the **map** package (`M49RG20-Q0123-2001/db_dwnl_ppc.out`) | 1,829 symbols, 1,205 functions |
| `db_dwnl_gl.out` | the **firmware** package (`NAV/DB_DWNL/`) | 1,900 symbols, 1,278 functions |

They are the cartography module — `db_dwnl` = "database download" — for the PC build and the
head-unit ("GL") build respectively. `tools/elfsyms.py` reads them.

!!! tip "Check these first, always"

    This is the same lesson as `tools/elfsyms.py`'s note in `AGENTS.md`: the package ships
    unstripped binaries, so **before reverse-engineering anything, check whether it already
    has a name**. The map subsystem cost nothing to identify because the vendor shipped the
    function and type names.

## The file tree

Both builds contain the filename templates verbatim. Reconstructed, the runtime layout under
`<root>/MAPPE/` is:

```
MAPPE/                        per-country root, %03d = country id (001 = Italy)
  %03d.DEG                    country-level geometry
  %03d/%03d.DEG               parcel geometry
  %03d/%03d%s.DEG .DPL .DRL   per-parcel geometry variants
  %03d/%03d%s.DST             street / road attribute data
  %03d/%03dPOI.DAT            the POI records
  %03d/%03dcat.poi  CAT.POI   POI categories
  %03d/%03dDSP.POI            POI spatial index
  %03d/%03dDPA.LZW            (LZW-compressed members)
  %03d/%03dSIG.LZW
  %03d/%03d_NOMSERV.LZW .DAT  service names
  %03d/%03d_MFT.DAT           MFT index - see the loader below
  %03d/%03d.TIT  %03d/%03d_NV.dat  %03d/%03d_EPC.LET
  %03d/%s/TOP/LZW%s.TOP       topology
  %03d/%s/TOP/NAMETOP.LZW     place names
  %03d/%s/LET/%sTOP.LET       lettering / labels
  %03d/%s/LET/%sKWD.LET  %sKWD_CH.LET  %sFLPY.LET
  %03d/%s/IND/%sCOM.IND       indices, one per family
  %03d/%s/CAT/%sDCP.CAT       categories
  %03d/%s/KWD/LZW%s.KWD       keywords
  %03d/%s/FLPY/LZW%s.FLP      phonetic / flypy
  %03d/%s/INSCIV/LZW%s.S_C    civil numbering
  %03d/BCR_TABLE.DAT  BCR_OFFSET.IND  SEG_TO_BCR.IND
  %03d/LANE.DAT  %03d/JUNCTION.DAT
  %03d/NAMECITY.DAT  %03d/SCITTANAME.DAT  %03d/EPC_COORD.DAT  %03d/fonemi.lzw
  %03d/gen_det.dat  %03d/divieti.dat  %03d/SCC.IMP
  %03d/JV_FILES/              (path built by Get_path_jv_files)
  %03d/RDSTMC/CCODE%X/…       TMC traffic tables, per code and location
MAPPE/%03d/FILES_VER.DAT      per-country file version
MAPPE/%03d/GRUPPO_4_CID.DAT   group/brand tables
MAPPE/%03d/%03d_GRUPPO_BCR.DAT
MAPPE/POI_USER/CURR_VERS_POI.DAT   the *user* POI store, separate from the map
GRUPPO_4_ROOT.DAT             root group table
```

**`%s` is a sub-family tag**, not a country: the same parcel is queried as `LZW%s.TOP`,
`%sCOM.IND`, `%sDCP.CAT`, `LZW%s.KWD`, `%sFLPY.LET` — one file per data family within a
parcel directory.

## The data model

The type names survive in the mangled function names, and they are the whole vocabulary:

| type | meaning |
|---|---|
| `TYPE_GEO_COORD` | a coordinate pair |
| `EXPORT_ID_PARC`, `EXPORT_ID_PARC_DB4`, `TYPE_ID_PARC_DB4` | a **parcel** — the tile id |
| `TYPE_DRAW_LEVEL` | level of detail |
| `TYPE_ID_SEG`, `TYPE_ID_SEG_DB4` | a road **segment** id |
| `TYPE_DRAW_SEG_PARC`, `TYPE_DRAW_LINK_PARC` | segments and topological links per parcel |
| `TYPE_DRAW_AREA`, `TYPE_DRAW_AREA_PTR` | polygons |
| `TYPE_DRAW_SERVICE` | services — POIs |
| `TYPE_DRAW_FACT` | facts — city centres |
| `TYPE_STREET_PTR`, `TYPE_ROAD_CODE` | street and road-code handles |
| `TYPE_SEG_BUFF`, `TYPE_SEG_LANE_TRAV` | segment buffers, lane traversal |
| `TYPE_ARCO_EXP`, `ARCO_EX_RID` | routing arcs (*arco* = edge) |
| `TYPE_EL_PARC_TABLE`, `TYPE_DATI_DEG_XY` | parcel tables and DEG geometry data |
| `TYPE_NET_MAP_USAGE`, `TYPE_DATI_DEG_XY` | routing network usage, geometry |
| `TYPE_ADM_CODE`, `TYPE_STR_TOP` | administrative codes, toponyms |
| `TYPE_CHAMPERARD`, `TYPE_INF_POI_USER` | guide data, user POI info |
| `CFilterFacility` | a **POI filter** class |

So the model is: **parcels (tiles) × draw levels**, each yielding segments, links, areas,
services and facts — plus a separate routing graph (`TYPE_ARCO_EXP`) with cost functions.

## The engine API

`CdCartogr` has 362 named methods in the PPC build. The ones that matter for writing data:

**Opening and locating**

```
CdCartogr::Open(..., mem_part, ...)         the main entry, takes a partition
CdCartogr::Initialize_db_seg / Close_db_seg
CdCartogr::Set_parcel_list(TYPE_DRAW_LEVEL, EXPORT_ID_PARC*, int*)
CdCartogr::Set_parcel_list_path(EXPORT_ID_PARC*)
CdCartogr::Open_db_rds / Open_db_lgr / Open_db_fac
```

**Loading, per parcel and draw level**

```
Load_segs_by_parc_cache(EXPORT_ID_PARC, …, TYPE_DRAW_LEVEL, …, TYPE_DRAW_SEG_PARC*, …)
Load_poly_by_parc_cache(…, TYPE_DRAW_AREA*, …)
Load_poi_by_parc_cache(…, CFilterFacility, …, TYPE_DRAW_SERVICE*, …)
Load_city_center_by_parc_cache(…, TYPE_DRAW_FACT*, …)
Get_segs_ptr_by_parc_cache / Get_links_ptr_by_parc_cache / Get_poly_ptr_by_parc_cache
```

**Queries — this is what a navigation unit actually calls**

```
Get_seg_id_of_map(TYPE_GEO_COORD, TYPE_GEO_COORD, …)   coords → segment
Get_seg_by_coord(TYPE_TRANSITABLE_FILTER, …, TYPE_GEO_COORD, TYPE_ID_SEG*)
Get_road_name_by_seg / Get_road_name_data_by_seg / Get_road_phoneme_by_seg
Get_adm_name_by_seg / Get_road_code_by_seg / Get_number_seg
Get_coord_by_house_number(TYPE_ROAD_CODE, long, TYPE_GEO_COORD*)    address → position
Get_coord_and_dir_by_house_number(…)
Get_fac_near(TYPE_GEO_COORD, CFilterFacility, …, TYPE_FAC_BUFF*, …)
Get_fac_by_point / Get_fac_on_path          find POIs by point or along a route
Is_speed_trap_DB(int*)                       speeds cameras are a first-class concept
Is_category_on_DB / Is_guide_DB
Get_segs_to_or_from_node(TYPE_ID_SEG, …, TYPE_TRANSITABLE_SIDES, TYPE_TRANSITABLE_FILTER, …)
Calcola_speed_sum_from_det(…) / Calcola_eco_sum_from_det(…)    routing cost
```

**Reading — the loaders whose decompilation gives the struct layouts**

```
Read_parc_deg(TYPE_EL_PARC_TABLE*, void*)
Load_parc_deg / Load_parc_deg_full
Read_parc_seg_lgr / Read_parc_deg_lgr
Load_seg_mft_data_tsk(…)     MFT index: header, offset list, index, chain
Get_aree_det_pointer_without_wait(EXPORT_ID_PARC_DB4, …)
Get_poly_det_by_parc / Get_poly_and_put_info_in_buf_by_parc
Create_buff_output_ptr_scc_by_parc
Load_data_file_cache / Load_compress_data_file_cache
Load_first_data_file_with_filter / …_compress
```

## I/O and compression

Everything goes through a small I/O shim, and the strings name it:

```
open_osx  open_lzw  Open_misc
OSX_open  OSX_read  OSX_seek  OSX_size  OSX_close
fopen  fread  opendir
LZW_start  LZW:Read  LZW:Seek
```

So: `fopen`/`fread` underneath, an `OSX_*` layer on top, and **LZW** as the only compression
for the members that carry it. Not encryption — LZW, a long-since-standard algorithm.

Versions are checked rather than assumed: `Check_map_ver`, `Load_info_file_version`,
`FILES_VER.DAT`, `CD_VER.LA`, and `WRONG map version:map_ver=%d,map_ver_read=%s`.

**Providers appear by name.** The phoneme tables carry `\SAMPA=NAVTEQ;%s` and
`\SAMPA=TELEATLAS;%s` — SAMPA being a phonetic alphabet, so the TTS street-name phonemes come
from **Navteq** (now HERE, matching `PROVIDER:HERE` in `DVD_VER.NAV`) or **Tele Atlas**
(TomTom) depending on the dataset.

## So: can you build your own?

**It is no longer an unknown — it is a bounded engineering problem.** What is now known:

- the **container** (gzipped tar per country, ~790 members, 512 MB unpacked);
- the **destination layout** (every filename template, quoted verbatim from the binary);
- the **compression** (LZW, not a bespoke scheme);
- the **data model** (parcels × draw levels → segments, links, areas, services, facts);
- the **engine's API**, including the loaders that read each file type.

What is still missing is the **binary layout of each file type** — the bytes inside
`001.DEG`, `001%s.DST`, `LZW%s.TOP` and the rest. But that is a *finite, enumerable* list of
structs, and the loaders that parse them are named and available to decompile.

A realistic order of attack:

1. **Decompile the loaders**, one family at a time, starting with the smallest complete unit:
   `Read_parc_deg` and `Load_parc_deg` for geometry, `Read_parc_seg_lgr` for segments,
   `Load_seg_mft_data_tsk` for the MFT index. Ghidra's PowerPC big-endian **default** language
   is right for this core — see [Toolchain](TOOLCHAIN.md).
2. **Recover each struct** into a documented layout. This is where the actual work is: 15-odd
   file families, each with its own record format.
3. **Write an emitter** from an OpenStreetMap extract into those layouts.
4. **Satisfy the checks** — `FILES_VER.DAT`, `Check_map_ver`, the `GRUPPO_4_*` group tables.

**The honest scale.** That is a project, not a patch: it is strictly larger than everything
this repository has done so far. But it is now *legible* — a list of formats with named
readers — rather than a 372 MB blob. And the cheap routes still stand: the
[user POI store](CAPABILITIES.md#speed-cameras-danger-zones-the-one-navigation-win) needs none
of this, and `Is_speed_trap_DB` shows the engine already treats speed traps as a category.

## Worked example: the POI record, partly cracked

`001POI.DAT` is the most tractable file in the set, so it is the place to start. Parsing it as
`[address][name][binary][ff ff ff]` works cleanly from byte zero:

```
"VIA LUIGI COLOMBO"              "CARABINIERI, LAVENA PONTE TRESA"
   7d ca 00 d0 01 4d 00 17 30 ba 00 00 00 00 01 12 3c f8 00 30 23 55 10 20   ff ff ff

"VIA ROMA"                       "INTESA SANPAOLO"
   c1 bb 00 d0 01 4e 00 1b d5 a7 00 00 00 00 01 34 ae c4 00 30 23 44 60 56   ff ff ff

"VIA GUGLIELMO MARCONI"          "BANCA POPOLARE DI SONDRIO"
   cb aa 00 d0 01 4e 00 12 b7 69 00 00 00 00 01 18 2e 9c 00 30 13 99 13 73   ff ff ff

"VIA GUGLIELMO MARCONI, 2"       "BANCA POPOLARE DI SONDRIO"
   cb aa 00 d0 01 4f 00 12 b7 69 00 00 00 00 01 18 5e 94 00                 ff ff ff
```

Confirmed by reading the bytes:

- the record is `[address][name][binary]` and ends with a literal **`ff ff ff`**;
- the binary block is **variable length** — 22 bytes in one of the records above, 27 in its
  neighbour — so the tail carries an optional field group;
- `00 d0` at `+2` and `00 00 00 00 01` at `+10` are **constant across every record sampled**;
- the block is **address-linked**: the two `VIA GUGLIELMO MARCONI` records share `cb aa` at
  `+0` and `b7 69` at `+8`, and differ only where the house number differs.

**The coordinates are not yet decoded**, and the reason is a hypothesis worth stating: the
first field is small and varies with position but matches **no absolute encoding**. Testing
`Lavena Ponte Tresa` (≈45.96 N, 8.86 E) against the block for its Carabinieri record found
nothing under lat/lon scaled by 1e-5, 1e-6 or 1e-7, nor the `+90`/`+180` variants, at any
offset or field width. That is what a **parcel-relative delta** looks like — and it fits the
rest of the design: the engine is organised *by parcel* (`Set_parcel_list`, `EXPORT_ID_PARC`),
and `TYPE_DATI_DEG_XY` names geometry data with X/Y.

So finishing this one file means: decompile `Load_poi_by_parc_cache` and the POI reader to
recover the record struct, and take the parcel origin from the parcel table. That is the same
shape of work as every other family — which is exactly why the page calls it a project and not
a puzzle.

## PoC: OpenStreetMap in, name-pool out

The string-pool layer is fully understood and has now been driven end to end.

**The format.** `NAMECITY.DAT` and `%03d_NV.dat` are **plain NUL-separated strings** — no
header, no footer, no compression. Verified by round-trip: reading `005_NV.DAT` and writing it
back reproduces the file **byte for byte** (29,912 fields, 29,834 of them non-empty).

That the *empty* fields matter is worth recording, because it cost a cycle: the first attempt
filtered them out and the round-trip failed. The 78 empty fields are part of the format.

**The convention.** `NAMECITY.DAT` holds `NAME\TOWN`, and some entries carry a postcode
district:

```
ABBEY HEY\MANCHESTER
MANCHESTER AIRPORT\MANCHESTER
BL2 6 RADCLIFFE\MANCHESTER
```

Of the 1,863,417 strings in the UK table, **398 end in `\MANCHESTER`**, and 341 of those carry
a postcode district.

**The PoC, measured.** Overpass returns **2,443 ways** in a central-Manchester bounding box,
yielding **644 distinct street names**. Emitted in the unit's own format
(`<STREET>\MANCHESTER`) they produce a 16,832-byte pool that re-reads identically through the
same reader. So **OpenStreetMap → the unit's on-disk name format works**, for this layer, and
the round-trip against the real vendor file is the evidence that the format was understood
rather than guessed.

!!! warning "ODbL — a licence question, not a technical one"

    OpenStreetMap data is **ODbL**. Cartography built from it would be a *derivative
    database*, which carries **attribution and share-alike** obligations. That is a different
    kind of constraint from everything else on this page, and it applies to anything
    distributed. Worth deciding deliberately rather than discovering later.

**What the PoC does not do.** The name pool is the easy layer and carries **no geometry** — it
puts nothing on a screen. The coordinates are the hard part and they are not cracked.

## The coordinate problem, stated precisely

`%03dSCC.DST` is a settlement table and is the best-behaved binary in the set:

- records are a **fixed 92 bytes** (19,875 of them, the dominant gap);
- a record is `[name][name][10 bytes]`, the name appearing twice inside an 82-byte area;
- **every** 10-byte tail begins with `0x15`, and byte 3 is always `0x01`.

```
ST AGNES (Cornwall)      15 f4 f7 01 04 03 1d 01 96 03
ST IVES                  15 59 1b 01 20 02 05 00 0d 04
DOVER                    15 e7 4e 01 21 02 62 00 55 05
LOWESTOFT                15 b7 bd 01 22 00 ed 01 e1 05
MANCHESTER               15 b4 b5 01 22 00 ea 01 f1 02
NORWICH                  15 fb cb 01 22 03 84 03 1e 06
CARLISLE                 15 ff fb 01 3d 01 82 02 0a 02
```

Byte 4 tracks latitude loosely — `0x04` at Land's End, `0x22` across the Manchester/Lowestoft
band, `0x3d` at Carlisle — but it is **not** monotonic in latitude (`ST IVES` at 50.21 gives
`0x20` while `ST AGNES` at 50.31 gives `0x04`), so it is not a scaled coordinate. Nor do any
offset, width or endianness of the remaining bytes reproduce 50–55 N / −6 to +2 E under
1e-3…1e-7 scaling.

Two candidate readings remain, and both need the loader:

1. a **grid or parcel cell id** in byte 4, with a sub-cell offset beside it — plausible because
   the table is spatially ordered, starting at the south-west extreme;
2. a **reference into another file** (an offset or record id) whose table holds the geometry.

Settling it means decompiling `Load_city_center_by_parc_cache` and its reader, which is the
same step every other family needs. **The PoC above deliberately did not depend on it.**

### What the next step actually is

The reader is no longer a guess — the runtime ELF names it, and the names say what `SCC` is:

```
Load_city_centers_where_file_parc(TYPE_GEO_COORD, …, TYPE_DRAW_LEVEL, …, TYPE_RESULT*)
Create_buff_output_ptr_scc(TYPE_GEO_COORD, TYPE_GEO_COORD, …)      a *coordinate range*
Get_city_centers_by_point(TYPE_GEO_COORD, …, TYPE_CITY_CENTER*, …)
Search_elem_in_buf_city_centers(char*, u32, u32, TYPE_CITY_CENTER*, …)
```

Two things follow. `SCC` is a **spatial block** — `TYPE_INF_MAP_SCC_BLOCK` and
`TYPE_INF_PARC_SCC_BLOCK` are its map-level and parcel-level forms — so the `.DST` is a store
of those blocks, not one flat table. And the reader is driven by a **`TYPE_GEO_COORD`
bounding pair**, which is why `%03dSCC.DST` is spatially ordered: the file is written in the
order a coordinate sweep visits it.

So the field that means position is inside **`TYPE_CITY_CENTER`**, and reading it means
disassembling `Search_elem_in_buf_city_centers`, which is small and takes the struct directly.
That is the concrete next move — not more scaling guesses.

## What a map update actually has to get past

Cracking the formats is only the first requirement. A map package also has to be *accepted*,
and the strings show what accepts it.

**`CCT.DAT` is a licence token, and it is VIN-locked.** The application image opens
`/bd0/CCT.DAT`, decrypts it, and reads an activation key, a code, and the vehicle's VIN:

```
/bd0/CCT.DAT
Opening %s file....
Decrypted CCT table present into file %s:
Activation Key=%s
n Code=%s
GetUncryptedVIN : GetKeyInt uncrypted VIN faile…
(C_BCM_UPGRADE)  TestGetMapCode : %s
```

with `/Licence`, `/CCT.DAT.inf` and `C_MEDIA_MANAGER` alongside. The file itself is 456 bytes
at ~6.0 bits/byte of entropy — encoded, not a plain certificate.

**There are region gates too.** The updater carries `CheckEuropeContinent`,
`ReadContinentFromGruppoRoot`, `CONTINENT_ID`, and a `Crimea_Manager` with
`CheckIf_RUSSIA__UKRAINE_Key` — so the package declares a continent (`MEDIA_MAP.INI` says
`CONTINENT_ID:1 … EUROPE`) and the updater validates it. The map updater also carries
`Untar__7C_UNTGZPCcT1ii`, which confirms independently that the `*.BIN` files really are
tarballs.

**And the delivery path is not the firmware one.** Cartography has its own updater
(`C_SDHC_UPGRADE`), a separate system from `C_UPGRADE`. The map package is laid out for it —
`DATA/MAPPE/NNN/`, `DESCRI.DAT`, `CD_VER.*.INF`, `GRUPPO_4_*` — but which mechanism presents it
to the unit has not been established here.

!!! success "Answered: it covers the map data — and the container is re-sealable"

    Decrypting `CCT.DAT` (next section) yields a **per-country checksum keyed to that country's
    `DESCRI.DAT`**, which is the manifest over the country's payloads. So it **does bind the
    map data**, rather than merely authorising a region.

    That is not the dead end it sounds like. The value is **32 bits, not a signature**, and the
    cipher enclosing it is a byte subtraction whose key vector **ships in the application
    image**. So the token is re-sealable in principle, and what remains is identifying one
    checksum — the same shape as `contract.dat`, not the shape of a signed token.

    There is still a licensing dimension, and it is not the same question. `CCT.DAT` is how
    HERE's cartography is licensed per vehicle, and OpenStreetMap brings its own ODbL
    obligations. Both are decisions for whoever ships a map.

### What `CCT.DAT` is made of

**It is a fixed-block file.** `Test_Read_CCT_table` (`0x0169f330`) reads it **76 bytes at a
time** — `li r5, 0x4c` on the read and `cmpwi r3, 0x4c` on the return — and 456 = **6 × 76**.
The six records are visible directly:

```
rec 0: 30 34 32 | 0b 0b 01 0d 05 0f 0b 0f 06 0c | 0a | 37 64 46 3f … | 04 | 26 24 26 21 …
rec 1: 34 31 41 | 05 0c 0e 04 06 04 07 0b 08 03 0d | 35 38 73 3f …
```

Each record opens with **three printable bytes** — `042`, `341`, `427`, `624` in four of the
six — then a run of values in `0x00`–`0x0F`, then bytes in `0x20`–`0x6B`. So the file
interleaves a small-valued key stream with a data stream, and `0x0A` occurs inside the
small-valued runs, which is why the file *looks* line-structured to `cat`.

**The key table is in the application image**, not the file: `Test_Read_CCT_table` loads
`0x035E4CD8` (`lis r11, 0x35e ; addi r17, r11, 0x4cd8`) and indexes it with `lbzx`. That
region is initialised data — readable with `tools/ppcdis.py` or by slicing the inflated image —
and it holds small values in the same `0x00`–`0x0F` range, starting `00 04 01 0b 0b 01 0d 05
0f 0b 0f 06 0c`, which is *the same sequence* as the first record's key run. That overlap is
not a coincidence and is probably the thread to pull.

**It decrypts, and the key ships in the firmware.** Ghidra on `Test_Read_CCT_table`
(`0x0169f330`) gives the loop directly:

```c
iVar4 = iVar6 - ((iVar6 / 0x380) * 0x400 + (iVar6 / 0x380 & 0x1ffffffU) * -0x80);  // = iVar6 % 896
iVar6 = iVar4 + 1;
cVar5 = acStack_b2[iVar3] - ChipherCCT_Vect[iVar4];
acStack_b2[iVar3] = cVar5;
```

so the transform is a **byte subtraction against a key vector applied cyclically with period
896**, over a counter that runs continuously across all six 76-byte blocks. The
`0x92492493` constant that looked like a divide-by-7 is a **divide by 896** (`7 × 128`) — a
reminder that reading this by eye got it wrong and Ghidra got it right in one pass.

`ChipherCCT_Vect` is a **896-byte data symbol at `0x035E4CD8`, inside the application image**.
Applying it reproduces the plaintext exactly.

**What `CCT.DAT` actually says.** Decrypted, it is a per-country table — six records here,
one per country in the package:

```
001 … 4c75a293 … /MAPPE/001/DESCRI.DAT
002 … 05e1dd3e … /MAPPE/002/DESCRI.DAT
003 … e3eb4cb5 … /MAPPE/003/DESCRI.DAT
004 … 30d2c5af … /MAPPE/004/DESCRI.DAT
005 … 1b526603 … /MAPPE/005/DESCRI.DAT
012 … 4deaa03f … /MAPPE/012/DESCRI.DAT
```

**So the decisive question is answered in the affirmative: it covers the cartography.** It is a
per-country integrity value keyed to that country's `DESCRI.DAT` — and `DESCRI.DAT` is itself
the manifest carrying each payload's size and CRC, so the chain commits to the map data.

**And it is a checksum, not a signature.** The value is **32 bits, stored as ASCII hex**, and
the key it is enclosed by is a plain subtraction table sitting in the firmware. That is the
same shape as `contract.dat`, not the shape of a signed token.

**The one gap: the algorithm.** The value is not `crc32`, `adler32`, or a truncated
`md5`/`sha1`/`sha256` of the shipped `DESCRI.DAT` (nor of its `.inf`), and it is not `crc32`
of the country's payload `.BIN` in either its gzipped or inflated form — every combination
tried, on two countries, missed. So *which* bytes are summarised, and by what, is not
established. Given the firmware uses `crc32` everywhere else, a CRC over bytes that differ
from the shipped file (the updater `Untar`s the payloads, so the on-unit layout is not the
package layout) is the most likely explanation.

That gap matters, and its size is worth stating plainly: **identifying the checksum is what
decides whether a self-built map can be delivered.** The container is re-sealable — the cipher
is a subtraction and its key is in the image — so the remaining work is reproducing one
32-bit value, not breaking a signature.

**It is also a licence.** `CCT.DAT` is how HERE's cartography is licensed per vehicle, and
OpenStreetMap carries ODbL attribution and share-alike. Both are decisions for whoever ships a
map. This page documents the mechanism because that is what the repository does; it does not
provide a tool for forging the token.

## Caveats

- **Nothing here has been executed or tested.** Everything above is read from symbol tables
  and string tables in the shipped binaries, plus unpacking the shipped tars. No map data has
  been written, and no unit has been touched.
- The map package is **vendor data** and must never be committed — the same rule as the
  firmware. Nothing in this repository reproduces it.
- `%s` in the templates is a family tag whose exact values were not enumerated here.
- Only country `001` (Italy) was unpacked; the member counts and extensions are from that one
  part.
