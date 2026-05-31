# Changelog

All notable changes to Citadel PBO Tools are recorded here.

## 1.0.0 Beta

First Citadel-branded release. Built from a clean codebase with the
following capabilities out of the gate:

### Citadel PBO Builder

- Project Source and Build Output paths with independent named presets.
- Mono-addon and multi-addon project layouts; map/terrain work folders
  (`source`, `exports`, `terrainbuilder`, `tb`) are excluded from build
  targets automatically.
- Build pipeline:
  - Per-addon isolated staging folders.
  - Configurable exclude patterns.
  - Optional PAA update from `.png` / `.tga` sources via `ImageToPAA.exe`.
  - Binarize of `.p3d` and `.wrp` files in parallel; ODOL `.p3d` files in
    source are skipped to avoid DayZ Tools access violations.
  - Root and nested `config.cpp` -> `config.bin` conversion via
    `CfgConvert.exe`.
  - Stored-mode PBO packing with `prefix` / `product` / `version` properties.
  - Signing with `DSSignFile.exe` and `.bikey` copy into `Keys/`.
  - Safe publishing: backup existing artifacts, replace, restore on failure.
- Content-fingerprint build cache (size + SHA1 over file content) so a file
  edit that keeps mtime and size unchanged still invalidates the cache.
- Force rebuild + per-addon `Skip unchanged` controls.
- DayZ Tools auto-detection across every Steam library (registry +
  `libraryfolders.vdf`), not only the default `C:\Program Files\Steam`
  install.
- Scrollable Options window with all DayZ Tool paths, pipeline toggles,
  safety toggles, exclude patterns, Binarize addon scan folders, and
  thirteen individually toggleable preflight checks.
- Severity-tagged log with a runtime filter (`All`, `Hide INFO`,
  `Warnings + Errors`, `Errors Only`) that does not affect on-disk logs.
- Build logs saved to `_citadel_logs/` under the build output.

### Preflight

- Prefix sanity (multiple files, drive paths, slashes).
- `config.cpp` presence; optional syntax check via `CfgConvert.exe`.
- `CfgPatches` / `requiredAddons[]` hints.
- DayZ script `modded class` declarations with illegal base classes.
- Reference scanning for missing or excluded `.paa`, `.rvmat`, `.p3d`,
  `.wss`, `.ogg`, `.cfg`, `.cpp`, `.hpp`, `.h`, `.emat`, `.edds`, `.ptc`,
  `.shp`, `.dbf`, `.shx`, `.prj`.
- Risky path-name characters.
- Case-only path conflicts.
- Texture freshness (.paa older than its .png/.tga source).
- ODOL `.p3d` files present in source trees (info notice).
- Terrain WRP: `worldName` validation, `.wrp` discoverability, multiple
  `worldName` warnings.
- Navmesh folder warnings.
- Terrain source/export file warnings (`.pew`, `.tv4p`, `.raw`, etc.).
- Terrain size breakdown by top-level folder.
- Reports exported as `.txt` and `.json` to
  `_citadel_preflight_reports/`.

### Citadel PBO Inspector

- PBO header parsing with prefix, product, file count, total size.
- Expandable folder tree with size / packing method / timestamp columns.
- Stored + BI LZSS (`Cprs`) entry preview and extraction.
- Text preview with C/config-style syntax highlighting for `.cpp`, `.hpp`,
  `.h`, `.c`, `.rvmat`, `.sqf`, `.cfg`.
- P3D metadata scan (ODOL / MLOD format, version, LOD resolution list,
  textures, materials, proxies, animations).
- Drag-and-drop `.pbo` files into the window when `tkinterdnd2` is
  available.
- `Reload PBO` for manually typed paths or files that changed on disk.
- Extract selected files, selected folders, or the entire archive.
- Safe extraction paths: absolute paths and parent-folder traversal are
  refused.
- Optional `.bin` to `.cpp` conversion and `.rvmat` / `.bisurf` / `.mat`
  derapification via `CfgConvert.exe` on extraction.
- `texHeaders.bin` is skipped during `.bin` conversion because it is not a
  config bin.

### Brand and polish

- Citadel purple/violet shield theme applied uniformly across both apps,
  sampled from the Citadel brand logo.
- Status badges with `Ready`, `Building`, `Preflight`, `Done`, and `Error`
  states.
- Window position + size persisted between sessions.
- JSON settings under `%APPDATA%\Citadel\PBO_Tools\` so EXE upgrades keep
  configuration intact.

### Tests

- pytest suite covering PBO read/write round trip, safe extraction, LZSS
  decoding, prefix file parsing, addon discovery, and preflight rules.
