# Changelog

## [1.0.0](https://github.com/KRoperUK/smeg-plus-patches/compare/v0.3.0...v1.0.0) (2026-09-30)


### ⚠ BREAKING CHANGES

* the repository and Python distribution are renamed.

### Features

* add a schema-dumping tool and the databases layer docs ([#225](https://github.com/KRoperUK/smeg-plus-patches/issues/225)) ([f82de86](https://github.com/KRoperUK/smeg-plus-patches/commit/f82de8697a0d905ffa7d222cb337aafbc433840a))
* add CRC parameter recovery, and rule the checksum out of the CRC class ([#127](https://github.com/KRoperUK/smeg-plus-patches/issues/127)) ([434b1ab](https://github.com/KRoperUK/smeg-plus-patches/commit/434b1ab7247fe0a2719a75bbda3d955ecbdb4719))
* add the cartography metadata tool, and close the formatting gap ([#126](https://github.com/KRoperUK/smeg-plus-patches/issues/126)) ([d9c450e](https://github.com/KRoperUK/smeg-plus-patches/commit/d9c450e66783beace22e7fd1a8a24798b46efff0))
* an asset catalogue, so customising is a choice rather than a hunt ([#84](https://github.com/KRoperUK/smeg-plus-patches/issues/84)) ([5dff268](https://github.com/KRoperUK/smeg-plus-patches/commit/5dff268382f982392243ce9b840a423c3cf8bb88))
* audit a package's checksum cascade before it is flashed ([#131](https://github.com/KRoperUK/smeg-plus-patches/issues/131)) ([2d3ffe4](https://github.com/KRoperUK/smeg-plus-patches/commit/2d3ffe475e4be9631e7f304f28b74a060b13379f))
* aux-boot-restore lets AUX take part in the boot restore ([#148](https://github.com/KRoperUK/smeg-plus-patches/issues/148)) ([16ed264](https://github.com/KRoperUK/smeg-plus-patches/commit/16ed26489e6057a318273407e22a0dfe0282d5e3))
* aux-signal-switch candidate switches to AUX when its signal appears ([#156](https://github.com/KRoperUK/smeg-plus-patches/issues/156)) ([25a0348](https://github.com/KRoperUK/smeg-plus-patches/commit/25a034821cd60e79ad6d60a095d918192bf81163))
* boot-to-AUX variants for AUDIO_BT and AUDIO_BT_256 ([#222](https://github.com/KRoperUK/smeg-plus-patches/issues/222)) ([8a71c10](https://github.com/KRoperUK/smeg-plus-patches/commit/8a71c109f4277e3769f6b4f694284f8e91208329))
* builds/aux-boot.json is the minimal confirmed boot-to-AUX build ([#218](https://github.com/KRoperUK/smeg-plus-patches/issues/218)) ([c5cb4f5](https://github.com/KRoperUK/smeg-plus-patches/commit/c5cb4f5032cf935c87f0bd48c5f5e2a817cf523b))
* decode and rebuild the GUI string tables in the media partition ([#229](https://github.com/KRoperUK/smeg-plus-patches/issues/229)) ([48821d8](https://github.com/KRoperUK/smeg-plus-patches/commit/48821d83bd55ec7c2cbc3b5d690485e8c7c40183))
* diagnostic build that turns the application's own logging back on ([#70](https://github.com/KRoperUK/smeg-plus-patches/issues/70)) ([e5dfadb](https://github.com/KRoperUK/smeg-plus-patches/commit/e5dfadb1b5abd6fdfc19b0b07a7965ec3b0bad40))
* diff two releases by symbol, and locate a patch in another ([#133](https://github.com/KRoperUK/smeg-plus-patches/issues/133)) ([f0b6192](https://github.com/KRoperUK/smeg-plus-patches/commit/f0b61923a953cee8f3df01334d04a13f0a15ca13))
* drop the AUX idle signal mute ([#230](https://github.com/KRoperUK/smeg-plus-patches/issues/230)) ([b12862e](https://github.com/KRoperUK/smeg-plus-patches/commit/b12862e7470cb4cc831db2348227d150ef8b7035))
* dump the whole USER_DATA partition from SPYSTORE ([#118](https://github.com/KRoperUK/smeg-plus-patches/issues/118)) ([939d7d1](https://github.com/KRoperUK/smeg-plus-patches/commit/939d7d1a136a6cad8fceaab43020705189a7776c))
* force AUX as the default source, as a data edit ([#73](https://github.com/KRoperUK/smeg-plus-patches/issues/73)) ([c942278](https://github.com/KRoperUK/smeg-plus-patches/commit/c942278c8bfe283435c908cff971ee0a79cda0c8))
* force AUX on boot by patching C_MGR_SRC::StartUp restore ([#111](https://github.com/KRoperUK/smeg-plus-patches/issues/111)) ([8acb53a](https://github.com/KRoperUK/smeg-plus-patches/commit/8acb53a7a7eb60bc4e55e0b60379501999d8e2a5))
* generate the patch status tables from patches/*.json ([#207](https://github.com/KRoperUK/smeg-plus-patches/issues/207)) ([edf8a21](https://github.com/KRoperUK/smeg-plus-patches/commit/edf8a21266d8caea70ad5a09ca354cf10371a038))
* generate the tool reference page from each tool's --help ([#208](https://github.com/KRoperUK/smeg-plus-patches/issues/208)) ([166f855](https://github.com/KRoperUK/smeg-plus-patches/commit/166f855ef34a4668c217331a699859b2f180a003))
* hardware-verified flash, custom media tooling, and a manifest build ([#56](https://github.com/KRoperUK/smeg-plus-patches/issues/56)) ([91bb341](https://github.com/KRoperUK/smeg-plus-patches/commit/91bb3415ff22ac6cd73e631af59daf83debf74a0))
* identify the build from the image, and refuse rather than guess ([#128](https://github.com/KRoperUK/smeg-plus-patches/issues/128)) ([cb7010f](https://github.com/KRoperUK/smeg-plus-patches/commit/cb7010f34eb8b5ab2b05f03cf0847f533830d666))
* make the firmware's logging emit, and document the AUX chain gate by gate ([#87](https://github.com/KRoperUK/smeg-plus-patches/issues/87)) ([0acb6b6](https://github.com/KRoperUK/smeg-plus-patches/commit/0acb6b6d766aec7c46b0f04754fce2846f87f60d))
* one command to build a stock baseline package ([#135](https://github.com/KRoperUK/smeg-plus-patches/issues/135)) ([e71de61](https://github.com/KRoperUK/smeg-plus-patches/commit/e71de61122fec9eba4bfd4c52b236570770bdb70))
* opt-in firmware-in-the-loop tests against the user's own image ([#205](https://github.com/KRoperUK/smeg-plus-patches/issues/205)) ([1a2eb2b](https://github.com/KRoperUK/smeg-plus-patches/commit/1a2eb2bd863174919e066fffdf85c1b81bd608d7))
* point the logging sink at VxWorks logMsg, whose address is now known ([#95](https://github.com/KRoperUK/smeg-plus-patches/issues/95)) ([d1188b5](https://github.com/KRoperUK/smeg-plus-patches/commit/d1188b5802d2bc4ecf9837a67534e799f41eb343))
* pre-flight a package, and fail the build if it would not work ([#78](https://github.com/KRoperUK/smeg-plus-patches/issues/78)) ([2bfd1a5](https://github.com/KRoperUK/smeg-plus-patches/commit/2bfd1a57782304fddfbbe519ac2162e5a7834d6e))
* prepare the USB stick and prove the copy landed ([#130](https://github.com/KRoperUK/smeg-plus-patches/issues/130)) ([c1ac23b](https://github.com/KRoperUK/smeg-plus-patches/commit/c1ac23b19d1fb27cab8ccba485a80db17810a859))
* prepare_usb stops macOS indexing the stick and can eject it ([#196](https://github.com/KRoperUK/smeg-plus-patches/issues/196)) ([5c22f8f](https://github.com/KRoperUK/smeg-plus-patches/commit/5c22f8f932a4aeebc824a38d2b6ea9119d98bc61))
* re-seal contract.dat so patched packages are accepted ([#54](https://github.com/KRoperUK/smeg-plus-patches/issues/54)) ([660cb5b](https://github.com/KRoperUK/smeg-plus-patches/commit/660cb5bd475410125636c052e048fc3a60cf8dc8)), closes [#53](https://github.com/KRoperUK/smeg-plus-patches/issues/53)
* read and write the cartography name pools, with an OSM proof of concept ([#120](https://github.com/KRoperUK/smeg-plus-patches/issues/120)) ([9d0d62a](https://github.com/KRoperUK/smeg-plus-patches/commit/9d0d62a588748399cf37be9651f90b3df233133a))
* read the BigQuick container header and the VxWorks symbol table ([#226](https://github.com/KRoperUK/smeg-plus-patches/issues/226)) ([aee6544](https://github.com/KRoperUK/smeg-plus-patches/commit/aee65447743e92f9215d6c05d65ca8bca718d062))
* read the symbol tables the package has been shipping all along ([#90](https://github.com/KRoperUK/smeg-plus-patches/issues/90)) ([279a73c](https://github.com/KRoperUK/smeg-plus-patches/commit/279a73cc62900d65484b82630364010c62595b0a))
* retry the AUX default with a correct folder name and a did-it-apply beacon ([#99](https://github.com/KRoperUK/smeg-plus-patches/issues/99)) ([fd19db1](https://github.com/KRoperUK/smeg-plus-patches/commit/fd19db14051428eacef650ced129f351b46084fd))
* run firmware functions on an emulated CPU, and correct what that disproves ([#86](https://github.com/KRoperUK/smeg-plus-patches/issues/86)) ([5bf160c](https://github.com/KRoperUK/smeg-plus-patches/commit/5bf160cc6ec36d52a7e0bbf5be63cf5bf68097c7))
* ship a USER_DATA payload, where the unit actually reads its settings ([#74](https://github.com/KRoperUK/smeg-plus-patches/issues/74)) ([792c76d](https://github.com/KRoperUK/smeg-plus-patches/commit/792c76d3c87cfbd32698f8ced30a50ba5e55b738))
* spy collect also backs up /USER_DATA to the stick ([#108](https://github.com/KRoperUK/smeg-plus-patches/issues/108)) ([25271b6](https://github.com/KRoperUK/smeg-plus-patches/commit/25271b69da2cec7532463c3ab337ca65f68b89d0))
* **studio:** follow the desktop's light or dark scheme ([#76](https://github.com/KRoperUK/smeg-plus-patches/issues/76)) ([c990152](https://github.com/KRoperUK/smeg-plus-patches/commit/c990152e64606dc6f173956ca9c9a270ba7b1971))
* **studio:** icon buttons instead of text ([#71](https://github.com/KRoperUK/smeg-plus-patches/issues/71)) ([2878626](https://github.com/KRoperUK/smeg-plus-patches/commit/2878626ed78b003f6be0a47741c9c9012d1232ff))
* survey every function in the application image ([#152](https://github.com/KRoperUK/smeg-plus-patches/issues/152)) ([c336dd5](https://github.com/KRoperUK/smeg-plus-patches/commit/c336dd57b6bb157ec2f6290e1fadef435388f369))
* survey records vtables, virtual call sites and global reads/writes ([#210](https://github.com/KRoperUK/smeg-plus-patches/issues/210)) ([25f9a26](https://github.com/KRoperUK/smeg-plus-patches/commit/25f9a267be2eca5cca10c6d32b3c062418b27562))
* tools/spy_read.py reads a SPY capture in one command ([#204](https://github.com/KRoperUK/smeg-plus-patches/issues/204)) ([2c2f720](https://github.com/KRoperUK/smeg-plus-patches/commit/2c2f7209061f5316da18aa9476bf50a696da6de4))
* verify the USER_DATA FAT long filename before flashing ([#106](https://github.com/KRoperUK/smeg-plus-patches/issues/106)) ([3627aef](https://github.com/KRoperUK/smeg-plus-patches/commit/3627aef079d77540d69bebf0aa93eebdcf6865fc))
* verify the written package, and pin the patched instructions ([#129](https://github.com/KRoperUK/smeg-plus-patches/issues/129)) ([92f76ed](https://github.com/KRoperUK/smeg-plus-patches/commit/92f76eded707b142147440435a32ff5f5a818d0f))


### Bug Fixes

* a module with an empty AppBin is still a problem ([#139](https://github.com/KRoperUK/smeg-plus-patches/issues/139)) ([6c1a741](https://github.com/KRoperUK/smeg-plus-patches/commit/6c1a741f6cf023d194ac0d6febd3ca9c02858e29))
* apply each patch set to the package being built, not the stock source ([#113](https://github.com/KRoperUK/smeg-plus-patches/issues/113)) ([e1b5156](https://github.com/KRoperUK/smeg-plus-patches/commit/e1b5156890492801051da97e08aa25701610aecc))
* aux-boot-restore also clears PrOnly on AUX's boot activation ([#151](https://github.com/KRoperUK/smeg-plus-patches/issues/151)) ([a6259a0](https://github.com/KRoperUK/smeg-plus-patches/commit/a6259a0d703d4de3f9dfe0a457476874087e119e))
* aux-boot-restore clears PrOnly at AUX's own call site ([#149](https://github.com/KRoperUK/smeg-plus-patches/issues/149)) ([22d208a](https://github.com/KRoperUK/smeg-plus-patches/commit/22d208a515b0a6109eb8b69c34adfc5a27f2dcb3))
* aux-sticky dropped a branch condition and could never select AUX ([#89](https://github.com/KRoperUK/smeg-plus-patches/issues/89)) ([d49f274](https://github.com/KRoperUK/smeg-plus-patches/commit/d49f2741fb57d274f95b4e1ac691c50639961096))
* build complete USER_DATA database payloads ([#105](https://github.com/KRoperUK/smeg-plus-patches/issues/105)) ([ba45a30](https://github.com/KRoperUK/smeg-plus-patches/commit/ba45a3068b86b354067cb29a637d628255d4640b))
* close every file these tools and tests open ([#93](https://github.com/KRoperUK/smeg-plus-patches/issues/93)) ([69b9e5b](https://github.com/KRoperUK/smeg-plus-patches/commit/69b9e5b3b2c53517eeb7a4394b81065204e7639a))
* close the PEP 723 header in eight tools so uv run works ([#219](https://github.com/KRoperUK/smeg-plus-patches/issues/219)) ([3391120](https://github.com/KRoperUK/smeg-plus-patches/commit/3391120c515d643db3e824183c74b0dec83eb23f))
* fail pre-flight when a USER_DATA payload sits where the updater cannot read it ([#114](https://github.com/KRoperUK/smeg-plus-patches/issues/114)) ([83bf9dc](https://github.com/KRoperUK/smeg-plus-patches/commit/83bf9dc6c1ebe30d71e10d6fae450025fe05ea66))
* guard patches by firmware version, and report it in pre-flight ([#103](https://github.com/KRoperUK/smeg-plus-patches/issues/103)) ([96ff297](https://github.com/KRoperUK/smeg-plus-patches/commit/96ff2975d40bb3073e2d618884108d9e3eab9bc7))
* not every module ships an application image ([#138](https://github.com/KRoperUK/smeg-plus-patches/issues/138)) ([82f070c](https://github.com/KRoperUK/smeg-plus-patches/commit/82f070c27c12cd6daa06e24e10bb10fe1782fe23))
* patch_media writes the system.bin.inf CRC signed, as stock does ([#185](https://github.com/KRoperUK/smeg-plus-patches/issues/185)) ([00504f7](https://github.com/KRoperUK/smeg-plus-patches/commit/00504f78ea4aa580d06b2bacc835716e9193b8f8))
* patch_studio answers --help without PySide6 ([#203](https://github.com/KRoperUK/smeg-plus-patches/issues/203)) ([8d33057](https://github.com/KRoperUK/smeg-plus-patches/commit/8d330575be0f40680a3e9a03dc7b8e42b36816e7))
* preflight reports a stock site as stock when its patch is longer ([#213](https://github.com/KRoperUK/smeg-plus-patches/issues/213)) ([17571da](https://github.com/KRoperUK/smeg-plus-patches/commit/17571dae244134107077847002189f07a587af0d))
* preflight the module a build targets, not always NAV ([#223](https://github.com/KRoperUK/smeg-plus-patches/issues/223)) ([66fb8a7](https://github.com/KRoperUK/smeg-plus-patches/commit/66fb8a70efff6466d7b0d220e094e955e220060c))
* prepare_usb also removes the package folder's own shadow ([#150](https://github.com/KRoperUK/smeg-plus-patches/issues/150)) ([77609b8](https://github.com/KRoperUK/smeg-plus-patches/commit/77609b8d4886d0f848b4f137ab739c9b6de5b69a))
* prepare_usb removes the AppleDouble shadows macOS writes on FAT ([#146](https://github.com/KRoperUK/smeg-plus-patches/issues/146)) ([cb81d70](https://github.com/KRoperUK/smeg-plus-patches/commit/cb81d70cd61ae0287636f1a86bb2d5a44fc1abaf))
* recompute the trailing CRC32 of every patched ctrl file ([#159](https://github.com/KRoperUK/smeg-plus-patches/issues/159)) ([0aff2a4](https://github.com/KRoperUK/smeg-plus-patches/commit/0aff2a409b89c8b1dfae0dacec1f4a2efe950540))
* refuse to merge two packages together on a stick ([#132](https://github.com/KRoperUK/smeg-plus-patches/issues/132)) ([5494e4a](https://github.com/KRoperUK/smeg-plus-patches/commit/5494e4a00ba8b1f7b9dfe083de305ada0cb7bd25))
* resolve the CodeQL notes in survey.py and symbols.py ([#157](https://github.com/KRoperUK/smeg-plus-patches/issues/157)) ([8a32918](https://github.com/KRoperUK/smeg-plus-patches/commit/8a32918ca37d956375bfb1ae63746ea186dd54f7))
* resolve tone and splash sources like the other manifest paths ([#189](https://github.com/KRoperUK/smeg-plus-patches/issues/189)) ([b7fedf0](https://github.com/KRoperUK/smeg-plus-patches/commit/b7fedf05cf5e28744e247c4e5a42a80472e67b4c))
* ring tone names are patched in the application image, where the menu reads them ([#211](https://github.com/KRoperUK/smeg-plus-patches/issues/211)) ([6dac9b9](https://github.com/KRoperUK/smeg-plus-patches/commit/6dac9b9513bffa39a7067b872ded56f03577562b))
* settle the container header and VxWorks table against the real image ([#228](https://github.com/KRoperUK/smeg-plus-patches/issues/228)) ([f1aeb99](https://github.com/KRoperUK/smeg-plus-patches/commit/f1aeb9939141ee805f1e35d3d60113f78f0e6ba3))
* survey forgets a lis once its register is overwritten ([#153](https://github.com/KRoperUK/smeg-plus-patches/issues/153)) ([442b839](https://github.com/KRoperUK/smeg-plus-patches/commit/442b839839c633459c121783a6e4a85fad2c0c34))
* the logging sink is a stub, so neither diagnostic patch produces output ([#92](https://github.com/KRoperUK/smeg-plus-patches/issues/92)) ([b1ae396](https://github.com/KRoperUK/smeg-plus-patches/commit/b1ae396185b88760fc122d08ee67305930c78d8d))
* verify_package and preflight warn about a stale ctrl trailer ([#192](https://github.com/KRoperUK/smeg-plus-patches/issues/192)) ([7301e3a](https://github.com/KRoperUK/smeg-plus-patches/commit/7301e3a10f924bbad6e4fc1bc3b27ebda8c488c1))
* warn when a USER_DATA payload sits at a path the updater will not read ([#97](https://github.com/KRoperUK/smeg-plus-patches/issues/97)) ([b837f0f](https://github.com/KRoperUK/smeg-plus-patches/commit/b837f0fc3ac66f17f8b7f9363a408881ace42ccf))


### Refactors

* move the last duplicated checksum helpers into smeglib ([#231](https://github.com/KRoperUK/smeg-plus-patches/issues/231)) ([e6d372c](https://github.com/KRoperUK/smeg-plus-patches/commit/e6d372c71637e5c12d17e119bcd3ac2e72a24fe0))
* one checksum helper, not three ([#141](https://github.com/KRoperUK/smeg-plus-patches/issues/141)) ([60a8c27](https://github.com/KRoperUK/smeg-plus-patches/commit/60a8c275a7f0006b263c62b3a68f42597fafe22b))
* one home for the package checksum chain ([#227](https://github.com/KRoperUK/smeg-plus-patches/issues/227)) ([9b04544](https://github.com/KRoperUK/smeg-plus-patches/commit/9b04544cd6a4fba9e07faa5ebeaf9a9242b5a80f))
* one symbol-map reader, not four ([#136](https://github.com/KRoperUK/smeg-plus-patches/issues/136)) ([f65732b](https://github.com/KRoperUK/smeg-plus-patches/commit/f65732b752a7b41dc1299cafe20668633e1e85e2))


### Documentation

* add hardware, kernel/partition and prior-art pages ([#224](https://github.com/KRoperUK/smeg-plus-patches/issues/224)) ([44213f2](https://github.com/KRoperUK/smeg-plus-patches/commit/44213f2031d013921b78ba57843384c8509abac3))
* addresses are per firmware version, and the cheatcode screen is reachable ([#102](https://github.com/KRoperUK/smeg-plus-patches/issues/102)) ([7d043b8](https://github.com/KRoperUK/smeg-plus-patches/commit/7d043b888bef1c41284e6026f5e720c726bd6847))
* boot to AUX is confirmed on hardware ([#217](https://github.com/KRoperUK/smeg-plus-patches/issues/217)) ([e54907f](https://github.com/KRoperUK/smeg-plus-patches/commit/e54907f002a8770717ebbccde8007ee4cb2683b9))
* bound the checksum problem and record the third integrity layer ([#123](https://github.com/KRoperUK/smeg-plus-patches/issues/123)) ([104b343](https://github.com/KRoperUK/smeg-plus-patches/commit/104b343ec02a838391d5ab044df6d9c762ddcde3))
* bring the site's name, title and homepage up to what the project is ([#80](https://github.com/KRoperUK/smeg-plus-patches/issues/80)) ([49ac3db](https://github.com/KRoperUK/smeg-plus-patches/commit/49ac3db45d3345b11bebcb5631dc4595f1936593))
* CCT.DAT is an eight-byte string compare, not a signature ([#122](https://github.com/KRoperUK/smeg-plus-patches/issues/122)) ([53ff2a1](https://github.com/KRoperUK/smeg-plus-patches/commit/53ff2a143347ff4962ad4ceb2a134ec9ca8e91ce))
* close readings of the scheduler, audio module and HMI sources ([#154](https://github.com/KRoperUK/smeg-plus-patches/issues/154)) ([8ccc1f2](https://github.com/KRoperUK/smeg-plus-patches/commit/8ccc1f21eb28bdb4fddd1f892300ad905f1c0eaa))
* correct the ctrl manifest layout and what CheckType holds ([#160](https://github.com/KRoperUK/smeg-plus-patches/issues/160)) ([0aeb80e](https://github.com/KRoperUK/smeg-plus-patches/commit/0aeb80e21ca8c89b74940d4313f405d83d4eafa3))
* correct the studio's filename everywhere, and the venv that is not there ([#85](https://github.com/KRoperUK/smeg-plus-patches/issues/85)) ([48fe436](https://github.com/KRoperUK/smeg-plus-patches/commit/48fe4368e15553fbd6b0ba3df5929264d9d4defa))
* decrypt CCT.DAT - it binds the map data, and the container is re-sealable ([#121](https://github.com/KRoperUK/smeg-plus-patches/issues/121)) ([7ff2491](https://github.com/KRoperUK/smeg-plus-patches/commit/7ff24919a500a67e0c1b76948f73404acdaf14f1))
* diagram the media contract with mermaid ([#55](https://github.com/KRoperUK/smeg-plus-patches/issues/55)) ([07969b0](https://github.com/KRoperUK/smeg-plus-patches/commit/07969b03dcff633979de022411d65205175d554d))
* document the analysis toolchain and cross-platform setup ([#115](https://github.com/KRoperUK/smeg-plus-patches/issues/115)) ([7ef9cab](https://github.com/KRoperUK/smeg-plus-patches/commit/7ef9cabffb944d30ee8d8b9c2b81a069099dce2d))
* document the cartography subsystem and its file formats ([#119](https://github.com/KRoperUK/smeg-plus-patches/issues/119)) ([d0d24f0](https://github.com/KRoperUK/smeg-plus-patches/commit/d0d24f0d0dc4f6e238b293f5bf1edc3045039990))
* fix how Last_Source is matched, and pin the source id enum ([#100](https://github.com/KRoperUK/smeg-plus-patches/issues/100)) ([f1558fa](https://github.com/KRoperUK/smeg-plus-patches/commit/f1558fab36f8ec208a55f6c5c49a3e9da4ed2df1))
* how the boot source is chosen, and why aux-boot-default cannot work ([#145](https://github.com/KRoperUK/smeg-plus-patches/issues/145)) ([03996ca](https://github.com/KRoperUK/smeg-plus-patches/commit/03996ca899b7e55214bee00cb61522e5e8f2244b))
* how the next scheduler position is chosen, and what the version screen shows ([#214](https://github.com/KRoperUK/smeg-plus-patches/issues/214)) ([fc8a003](https://github.com/KRoperUK/smeg-plus-patches/commit/fc8a0030da0996efd904c929dcbd861e01192fc6))
* inventory every customisable asset in the unit ([#83](https://github.com/KRoperUK/smeg-plus-patches/issues/83)) ([1d27c17](https://github.com/KRoperUK/smeg-plus-patches/commit/1d27c17d0b27f398283cb2db066d1bd6e8696cb7))
* map the tools added this session into the agent guide ([#137](https://github.com/KRoperUK/smeg-plus-patches/issues/137)) ([6c700ae](https://github.com/KRoperUK/smeg-plus-patches/commit/6c700ae3f3e99c674ee24e3605d361a4bff00c38))
* read the coordinate loader - it is a planar integer grid, not a puzzle ([#124](https://github.com/KRoperUK/smeg-plus-patches/issues/124)) ([6483375](https://github.com/KRoperUK/smeg-plus-patches/commit/64833758c252ab4048995d1b5eb426794ea5d09f))
* record the first car test and correct the GUI_VER claim ([#144](https://github.com/KRoperUK/smeg-plus-patches/issues/144)) ([7dc6987](https://github.com/KRoperUK/smeg-plus-patches/commit/7dc69879cecbf1b03f46bd30bf08f7efea506535))
* record the session's working lessons in the agent brief ([#221](https://github.com/KRoperUK/smeg-plus-patches/issues/221)) ([f9e67e6](https://github.com/KRoperUK/smeg-plus-patches/commit/f9e67e608449d3a62f98089a8d779afaf7fc1f95))
* record what is reachable and what is not, and why ([#75](https://github.com/KRoperUK/smeg-plus-patches/issues/75)) ([2386c61](https://github.com/KRoperUK/smeg-plus-patches/commit/2386c61b056d49d537f79d2455079f261b60d508))
* record where the AUX level trim actually is ([#232](https://github.com/KRoperUK/smeg-plus-patches/issues/232)) ([c5eda38](https://github.com/KRoperUK/smeg-plus-patches/commit/c5eda38e6b5520015bbbd59bde8caf97c2e4fb7c))
* recovery, and the failure modes that are not documented ([#134](https://github.com/KRoperUK/smeg-plus-patches/issues/134)) ([68bd387](https://github.com/KRoperUK/smeg-plus-patches/commit/68bd387a6388b54c5de076ae2bd839f7c78b02e6))
* restructure site by firmware artefact and add zensical diagrams, tabs and cards ([#110](https://github.com/KRoperUK/smeg-plus-patches/issues/110)) ([6914422](https://github.com/KRoperUK/smeg-plus-patches/commit/6914422c6c5222254f72df6db6d553864dd2e06c))
* review every page and fill the gaps ([#158](https://github.com/KRoperUK/smeg-plus-patches/issues/158)) ([9bae215](https://github.com/KRoperUK/smeg-plus-patches/commit/9bae2151eaddb098fcaa0d68f737d0c8dc76a435))
* rewrite the documentation as a canonical source ([#220](https://github.com/KRoperUK/smeg-plus-patches/issues/220)) ([ce6d35d](https://github.com/KRoperUK/smeg-plus-patches/commit/ce6d35dbbbe3544a2fc1f57cf3fdf2a7d667a62f))
* spy-dump-userdata is confirmed on hardware ([#109](https://github.com/KRoperUK/smeg-plus-patches/issues/109)) ([412c340](https://github.com/KRoperUK/smeg-plus-patches/commit/412c340820ddf96ccb7f1f1553ee9411feb92a5d))
* the ctrl CheckType-3 value is a CRC-16 of the file ([#215](https://github.com/KRoperUK/smeg-plus-patches/issues/215)) ([0f9ce12](https://github.com/KRoperUK/smeg-plus-patches/commit/0f9ce12768338eb9eef8ba9770ee04653f968658))
* the media contract blocks modified firmware ([#52](https://github.com/KRoperUK/smeg-plus-patches/issues/52)) ([215eb8c](https://github.com/KRoperUK/smeg-plus-patches/commit/215eb8ce842ab8c64413b070593077d34b7cb36d)), closes [#51](https://github.com/KRoperUK/smeg-plus-patches/issues/51)
* the packing layer is bit-packed, which is why byte reads failed ([#125](https://github.com/KRoperUK/smeg-plus-patches/issues/125)) ([18cf2cf](https://github.com/KRoperUK/smeg-plus-patches/commit/18cf2cf497f130082413fde4d1f77563655bc2fe))
* the release PR's approval click is expected, and not for agents to automate ([#69](https://github.com/KRoperUK/smeg-plus-patches/issues/69)) ([f6d1b71](https://github.com/KRoperUK/smeg-plus-patches/commit/f6d1b71defb051c45ef1f3e20ada8c9390921d9c))
* the spy path bypasses the log sink, and the USER_DATA retry still did not apply ([#101](https://github.com/KRoperUK/smeg-plus-patches/issues/101)) ([d51c850](https://github.com/KRoperUK/smeg-plus-patches/commit/d51c850f1174edfd5fc705164d659aa94a2e1e97))
* the studio has been run, not just written ([#50](https://github.com/KRoperUK/smeg-plus-patches/issues/50)) ([3845ba3](https://github.com/KRoperUK/smeg-plus-patches/commit/3845ba3b4822d5f163a0b9caa90ee052e5a229cb))
* the user POI database, which is the better lead for speed cameras ([#82](https://github.com/KRoperUK/smeg-plus-patches/issues/82)) ([fcb0902](https://github.com/KRoperUK/smeg-plus-patches/commit/fcb0902331ba583c6165fe6c406b2a036fd3e0eb))
* three source numberings, and stop asserting which one Last_Source uses ([#98](https://github.com/KRoperUK/smeg-plus-patches/issues/98)) ([808499c](https://github.com/KRoperUK/smeg-plus-patches/commit/808499c4248dabddba05d46794a2105cd5bd93ec))
* update flow, cheat codes and the real AUX signal path ([#155](https://github.com/KRoperUK/smeg-plus-patches/issues/155)) ([7da7c01](https://github.com/KRoperUK/smeg-plus-patches/commit/7da7c01f27b81bfb6b08fda7441ebbc48e600722))
* weekly external link check and start-here paths for owners and researchers ([#209](https://github.com/KRoperUK/smeg-plus-patches/issues/209)) ([f724bf4](https://github.com/KRoperUK/smeg-plus-patches/commit/f724bf44f4323bcdd3bbdc51e2afb1de1c724407))
* write down the gotchas that have each cost time here ([#81](https://github.com/KRoperUK/smeg-plus-patches/issues/81)) ([81299e4](https://github.com/KRoperUK/smeg-plus-patches/commit/81299e4aacaecc79b134cd2992d5a0e084e8fa36))

## [0.3.0](https://github.com/KRoperUK/smeg-plus-patches/compare/v0.2.0...v0.3.0) (2026-09-12)


### Features

* preview ring tones from the studio ([#46](https://github.com/KRoperUK/smeg-plus-patches/issues/46)) ([f7c72c9](https://github.com/KRoperUK/smeg-plus-patches/commit/f7c72c986bb61a996052a8e1321e9f2fbc8fd341))


### Documentation

* add AGENTS.md and agent instructions ([#47](https://github.com/KRoperUK/smeg-plus-patches/issues/47)) ([395283f](https://github.com/KRoperUK/smeg-plus-patches/commit/395283ffa45be58399eb7c15a3abc21b6ff9ddae))

## [0.2.0](https://github.com/KRoperUK/smeg-plus-patches/compare/v0.1.0...v0.2.0) (2026-09-12)


### Features

* add always-available and sticky AUX patch definitions ([#30](https://github.com/KRoperUK/smeg-plus-patches/issues/30)) ([e3593cf](https://github.com/KRoperUK/smeg-plus-patches/commit/e3593cf801bdf77659fa8e9c223370e5574765b7))
* add ringtone converter and Qt studio ([#31](https://github.com/KRoperUK/smeg-plus-patches/issues/31)) ([9e71ffc](https://github.com/KRoperUK/smeg-plus-patches/commit/9e71ffc7bc5da4f4668eb7476051864d9aaa587e))
* media-partition patcher, ringtone UI, and uv support ([#42](https://github.com/KRoperUK/smeg-plus-patches/issues/42)) ([adeb3e5](https://github.com/KRoperUK/smeg-plus-patches/commit/adeb3e5e5b4c80495c1ff6b2ef2584ee404a15a0)), closes [#35](https://github.com/KRoperUK/smeg-plus-patches/issues/35) [#36](https://github.com/KRoperUK/smeg-plus-patches/issues/36) [#37](https://github.com/KRoperUK/smeg-plus-patches/issues/37)
* modernise the Ringtone Studio UI ([#33](https://github.com/KRoperUK/smeg-plus-patches/issues/33)) ([beb6e77](https://github.com/KRoperUK/smeg-plus-patches/commit/beb6e7719e63e69e53a44be2c15592a4e2979cbf))


### Bug Fixes

* validate the media tree in ringtones.py stage, and refresh the docs ([#41](https://github.com/KRoperUK/smeg-plus-patches/issues/41)) ([4a5712f](https://github.com/KRoperUK/smeg-plus-patches/commit/4a5712f23424ddc30dbced999c36872a404b12d7)), closes [#40](https://github.com/KRoperUK/smeg-plus-patches/issues/40)


### Documentation

* the media-partition SIZE fields are solved ([#34](https://github.com/KRoperUK/smeg-plus-patches/issues/34)) ([baa7e93](https://github.com/KRoperUK/smeg-plus-patches/commit/baa7e936737b2309acbffd8c78ed653a45200d8c))
