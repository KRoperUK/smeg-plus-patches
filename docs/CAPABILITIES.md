# What is reachable, and what is not

This project has spent real time on things that turned out to be impossible, and the reasons
are worth writing down so nobody repeats them. Every claim here is grounded in the firmware
or in a hardware observation — the evidence is named so it can be checked.

!!! abstract "The short answer"

    Every "can it do X?" question resolves to one of three outcomes:

    1. **The code is already there** → it is a patch or a setting. (AUX, ZA files, BT PAN.)
    2. **It is a hardware capability** → it needs an external box. (CarPlay, WiFi.)
    3. **It is data we do not have and cannot generate** → out of reach. (Maps.)

## The two update systems

The unit has **two unrelated update paths**. Confusing them wastes effort, because they share
the USB port and nothing else.

| | firmware / head unit | cartography (maps) |
|---|---|---|
| content | `system.bin`, `AppBin/f_BigQuick.bin`, BSP, Renesas | map database |
| written by | `C_UPGRADE::UpgradeTask` — the flow in [Boot and update chain](FLASH_CHAIN.md) | `C_SDHC_UPGRADE` |
| protected by | `contract.dat` (see [Media protection](MEDIA_PROTECTION.md)) | its own, simpler scheme |
| updatable by us | **yes** | no — see below |

Maps being a separate system is not an inference: the updater has a whole subsystem for it,
with its own partition and format handling.

```
C_SDHC_UPGRADE::ReadCapacity / ReadCapacityInBlocks / CheckPartition
C_SDHC_UPGRADE::getSDBlkDeviceWrapper / sdhcMBRResetWrapper
[ERROR] - #8GB# Unable to format the cartography SD partition index='%d' cluster_size='%d'
ManageSD_8GB_DoublePartition()
```

**`/sdhc:0/` is not a card slot.** A Peugeot 208 (2015) has **no removable SD card** — the only
user interface is the USB socket in the centre console. That device name is an SDHC block
device the BSP exposes over **internal storage**, and the updater writes an MBR to it. So there
is no card to pull, image, or back up.

## Impossible, and why

### Native CarPlay

**No, and no amount of patching changes it.** Two independent blockers, one of them physical:

- The application image contains **zero** `CarPlay` strings. There is no stack to enable.
- CarPlay requires an **Apple MFi authentication coprocessor** in the accessory. The iPhone
  performs a cryptographic handshake with that chip and refuses to start a session without it.
  No firmware can emulate it, which is exactly why every retrofit on older head units is a
  piggyback box containing the SoC *and* that chip.
- CarPlay delivers **H.264** video. The unit's video handling is MPEG4 status events for USB
  file playback — there is no H.264 decoder, and no path to display an arbitrary stream.

What the unit *does* have is `iPod` support over USB (28 `MFi`-related strings, the `iPod`
source in the source menu). That is **iAP audio and metadata, not CarPlay.**

### New radios — WiFi, cellular

The USB stack is mass storage plus video; there is no network driver, so a USB WiFi dongle
will not enumerate. There is no WiFi or cellular hardware. Anything needing a new radio needs
an external box.

### Maps, beyond the last official release

!!! warning "An earlier version of this section was wrong"

    It said PSA had stopped shipping SMEG+ maps "years ago, so there is no feed to convert
    *from*", and that because the data sits on internal storage "we cannot even inspect it
    without opening the unit". **A 2023 package disproves both.** The correction matters,
    because it was the reason this was parked.

**The last release is Q1 2023, and it exists.** The package identifies itself in plain text:

```
MAP.inf          VER:Q1_23_120.0   SUBVER:1.1.31
DVD_VER.NAV      CONTINENT_ID:1  CONTINENT_NAME:EUROPE  PROVIDER:HERE
DVD_VER.NAV.INF  VERSION:120  RELEASE:0
MEDIA_MAP.INI    VOLUMELABEL:UHD6E2P01200REU  PRODUCT:Unique_DB6
```

Note the provider: **HERE**, not Magneti Marelli. So the cartography is a commercial dataset
delivered in a PSA wrapper, not a bespoke in-house format.

**And it is inspectable offline**, because the package carries the cartography itself rather
than only an installer:

```
MAPPE/001..005,012/   per-part descriptors
MAPPE/DESCRI.DAT      plain-text manifest:
                        CID,001,\DATA\MAPPE\001\001.BIN,size,372028557
                        CD_VER,001,\DATA\MAPPE\001\CD_VER.LA.INF,CRC,15a…
DATA/                 2.9 GB — the cartography
UPG/                   updater plugin: builtinsRNEG.out, db_dwnl_ppc.out
```

So the manifest layer is **text**, with per-part sizes and CRCs — and the payload is not one
opaque blob either. **Every `*.BIN` is a gzipped tar**, the same idiom as `system.bin`
itself. `001.BIN` is Italy, and it unpacks to **790 members / 512 MB**:

```
001.DEG                32 MB      geometry
001_DET.DRS           232 MB      the bulk of it
001POI.DAT             44 MB
001002.DEG / .DPL / .DRL          per-tile geometry sets
001DSP.POI  001_DA.POI  001_DE.POI …      POIs, including per-language sets
001*.DST               SAF SAU SCC SEM SHR SSH SSP STR STU   road/street attributes
001*.LET  (118)  .CAT (116)  .IND (116)  .S_C (115)  .TOP (115)
001DPA.LZW  001SIG.LZW            LZW-compressed members
```

Also per part: `001_PHONEMES.BIN` (a 122 MB tar of TTS phonemes) and `001_ZTL.BIN`
(restricted-traffic zones). `CD_VER.LA.INF` is plain text — `CID:001 / VERSION:120 /
CD_NAME:ITALY` — so the parts are per-country and self-describing.

**What that leaves.** The blockers are now two *research* problems, not availability
problems:

1. **The tile formats.** Roughly 15 distinct extensions with undocumented binary layouts, and
   the unit's own engine decides what it needs from each.
2. **The engine.** Rendering, label placement and routing live in the NAV image's map engine
   (`MMA_MapManager`, `V3D_Engine`) and are proprietary as well. Files have to satisfy it, not
   just parse.

So *writing your own cartography from OpenStreetMap* is a reverse-engineering project of a
size this repository has never taken on — the container is no longer the obstacle, but the
contents and the consumer both are. What remains cheap is the
[user POI route](#speed-cameras-danger-zones-the-one-navigation-win), which needs none of
this, and note that the retrofit piggyback these units are paired with already displays
OpenStreetMap-derived navigation today.

The on-unit copy is still behind the updater, so this does **not** make the *live* map data
readable — it makes the shipped cartography readable.

Third-party map updates for some other PSA units do circulate; that is a different platform
and is not evidence that this one is reachable.

## Present but gated — reachable with work

These already exist in the firmware. The work is finding the switch, not building the feature.

### Bluetooth tethering — the thing WiFi would be for

The unit supports **Bluetooth PAN** (network access point) over DUN/BNEP:

```
C_BCM_T2BF        connectivity.sqlite
```

So it can get internet through a paired phone, and it ships a **browser** to use it
(`browser.sqlite`, the `internet_default/` portal tree). No new hardware required. Tracked as
a spike.

### Speed cameras / danger zones — the one navigation win

Not on the cartography partition. They are **ZA files** the unit manages itself:

```
C_UPGRADE::ManageZAFiles
ManageZAFiles : Copy ZA files from /SYSTEM_DATA to /USER_DATA
AddListOfZARorPOIofProduct
(UpgradeTask): Transfert ZA in the Renesas OK
```

`ZAR` is *zones à risque*, the French legal formulation. The application image has
`Configure_Radar_Alert`, `Configure_Dangerous_Area_Alert` and `NOTIFY RADAR WARNING INFO` with
`coords %ld,%ld` — so it stores coordinates and alerts on them.

That means a **dedicated updater step, files in a partition we can already write, and no
dependency on map data.**

### And there is a user POI database, laid out in the clear

A second, independent route exists, and it looks more promising than the ZA files. The unit
has a **user POI store** with its paths visible in the application image:

```
/Mappe/POI_USER/%03d/%s
/Mappe/POI_USER/%03d/%s.LZW
/Mappe/POI_USER/CURR_VERS_POI.DAT
/Mappe/POI_USER/TEMP_%03d/%s
/sdhc:0/Data_Base/POILIST/
/TEMP_POI_VER.POI
```

and a user-facing import with its own success and failure dialogs:

```
UPG_POPUP_MAP_POI_IMPORT_PRO_Z3        UPG_POPUP_MAP_POI_IMPORT_FAIL_INF_Z1
```

`C_BCM_UPGRADE` manages it, and goes as far as flipping the filesystem access mode to do so:

```
(C_BCM_UPGRADE) DeletePOIForAllCID: SetWriteAccess to R/W returns ERROR!!!
(C_BCM_UPGRADE) DeleteAllPOI: SetWriteAccess to R/W returns ERROR
C_BCM_UPGRADE::DeletePOIForAllCID
```

Three things follow:

- POIs are stored **per index** (`%03d`), with a **version marker** (`CURR_VERS_POI.DAT`), so
  the unit tracks what it has and can replace it.
- Entries may be **LZW compressed** (`.LZW`) — a known, unencrypted, long-standing format
  rather than a bespoke one, which is a far better starting point than the map database.
- The upgrade code deliberately **sets the store read/write** to change it, so this is a
  supported modification, not a hack.

**What is still unknown:** the POI *record* layout — the bytes inside a POI file. The
surrounding structure is now mapped from the application image:

- **On the USB stick**, parts are numbered: `%s/DATA/MAPPE/%03d/%s`, with `CD_VER.NAV.inf`
  per part — the parts run `001`–`039` and they are the *cartography* numbering, so a POI
  import ships alongside them rather than replacing them.
- **On the unit**, the user store is `%s/Mappe/POI_USER/%03d/%s`, entries may be LZW
  compressed (`…/%s.LZW`), a staging area `…/POI_USER/TEMP_%03d/` is used during an import,
  and `CURR_VERS_POI.DAT` plus `/TEMP_POI_VER.POI` carry the version markers.
- **The import is a plugin**, not a hard-coded path: `t_upg_plugin_type` has
  `UPG_PLUGIN_TYPE_MODULE_POI_USER` and `UPG_PLUGIN_TYPE_LIST_POI_USER`, driven through
  `C_BCM_UPGRADE::AddListOfZARorPOIofCIDofProduct` / `AddListOfZARorPOIofProduct` and the
  `UpgPlugin.out` binary. That answers the second half: it *is* driven by the upgrade path,
  over a plugin interface, not by a bare file appearing on the stick.
- **`ZAR` categories are a database join, not a hard-coded list.** The image contains
  `… IN (SELECT "Group" FROM ZARAssociation WHERE IHMSubCategory = %d)`, and
  `nav_poi.sqlite` ships `ZARAssociation` with 15 rows — so which POI subcategories count as
  danger zones is editable data. See [Running the tools](RUNNING.md).

So the remaining offline question is the record layout alone.

**Why this is the better lead than the maps:** a current speed-camera dataset exists publicly
in a way map data does not, the container is a standard compression format, and the unit
already has a UI for importing POIs. None of that is true of the cartography.

### Other settings-driven behaviour

Seen in `up_common.sqlite` or the application image, all data rather than code:

- **Welcome image** — `SetWelcomeImageStatus` and a user-data popup family. Separate from the
  NAND boot logo, so this is where a custom image can actually go.
- **Jukebox** — `media_jkb_catalog.sqlite`.
- **Extra video inputs** — `video: Video_Input_2/3`, `Reverse1/2/3`.
- **Cheatcodes** — `cheatcodes.sqlite` is data.
- **Radio logos**, **GUI sounds**, **UI strings** — see the media partition notes.

Four settings databases have not been opened at all: `up_config.sqlite`, `up_user_hmi.sqlite`,
`desktopServices.sqlite`, `config_options.sqlite`. Feature flags hide in exactly such places.

## The hard boundary

**We can change behaviour, configuration and data. We cannot add hardware capability.** That
is the whole of it — the three-way test at the top of this page is just this boundary applied
case by case.

## The car's own look — the HARMONY module

The unit's on-screen styling is the **HARMONY** module, and it is **in the update package**.
`ManageHarmoniesVersions` and `ManageSkinCopyFromMedia` in the updater manage it.

!!! info "Where the rest of HARMONY lives"

    This section is the canonical "what it is and why it is gated". The on-disk
    container format is in [Media partition](MEDIA_PARTITION.md#the-harmony-module-ui-skins), and
    HARMONY's place among the other replaceable assets is in
    [Customising](CUSTOMISING.md).

### Five skins ship, and the unit names them

The `.bigharmony.ini` files document every variant in plain text:

```
BigHarm1 : GRAPHIC (LCB) / ELLIPTIC / CUBIC / GRAPHIC (LCD)
BigHarm2 : REDLINE / REFLEX / ESSENTIEL
BigHarm3 : SQUARE (NAV) / WARMLIGHT (NAV) / ESSENTIEL (DS)
BigHarm4 : SQUARE (AUDIO)
BigHarm5 : WARMLIGHT (AUDIO)
```

and which one a car gets is chosen by **vehicle trim**:

```
LIST_NAV:2,0,0,3,0,0          <- a NAV unit uses BigHarm2 and BigHarm3
LIST_AUDIO_BT:4,5
```

So a given car runs **one** of these while the others sit unused in the unit. Each is a
`BIG_HARMONY.bin` of 26–28 MB plus a per-display `BIG_SKIN_NAV.bin` / `BIG_SKIN_AUDIO.bin`.

This also explains the marque logo packages. `BigHarm3` is labelled *ESSENTIEL (DS)* — DS
branding is a **skin variant**, which is why `Data_base/graphics/logo/` holds `peugeot.pkg`,
`citroen.pkg` **and** `ds.pkg`. Those are the skin's brand artwork, not the boot splash. The
loop closes: we decoded them, they do nothing at boot, and now we know what does read them.

### Custom artwork: no

The payload is opaque, and not merely compressed:

```
00000000: 42 49 47 48 41 52 4d 4f 4e 59     "BIGHARMONY" + zero padding
HEADER_SIZE:900   HEADER_CRC32:817740569   VERSION_BIGHARMONY_STRUCT:01.00.00.b
zlib at 0x0 / 0x384 / 0x385 / 0x400 -> all fail
```

26 MB per skin that will not inflate. Almost certainly encrypted. Drawing your own theme means
breaking that format first — a project in its own right, not a patch.

### Switching skin: plausible, as a data change

The choice is a **mapping in a text `.ini`** inside the module, and the module is something the
package already ships. So switching a unit to a different one of the five looks like a file
edit rather than a code patch. That is the realistic route to changing how the car's screen
looks.

**Caveats.** Nobody has established which harmony a 208 NAV actually uses, so the alternatives
cannot be described yet. The updater **version-checks** harmonies and will erase and rewrite
them on a mismatch, so this is not free. And the vehicle type that drives the mapping may come
over CAN, which would make it less directly editable than it appears.
