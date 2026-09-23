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

## Caveats

- **Nothing here has been executed or tested.** Everything above is read from symbol tables
  and string tables in the shipped binaries, plus unpacking the shipped tars. No map data has
  been written, and no unit has been touched.
- The map package is **vendor data** and must never be committed — the same rule as the
  firmware. Nothing in this repository reproduces it.
- `%s` in the templates is a family tag whose exact values were not enumerated here.
- Only country `001` (Italy) was unpacked; the member counts and extensions are from that one
  part.
