# Contributing to Citadel PBO Tools

Thanks for being interested in helping out. Citadel PBO Tools is an internal
Citadel project; contributions are welcomed from authorized Citadel
contributors and trusted DayZ modders that the team has invited.

## Quick start

```powershell
git clone https://github.com/Sk3tch-Dev-Ux/Citadel_PBO_Tools.git
cd Citadel_PBO_Tools
python -m pip install -r requirements-dev.txt
python -m pytest
```

Then either run the apps from source —

```powershell
python citadel_pbo_builder.py
python citadel_pbo_inspector.py
```

— or build the EXEs:

```powershell
.\scripts\build_citadel_pbo_builder.ps1
.\scripts\build_citadel_pbo_inspector.ps1
```

## Project layout

```
citadel/
  core/        # PBO format, theme, settings, DayZ Tools, cache, logging, signing
  builder/     # Addon discovery, build pipeline, preflight rules, path presets
  inspector/   # PBO viewer, P3D metadata scanner
  gui/         # Tkinter UIs for Builder and Inspector
assets/        # citadel.ico and citadel_logo.png (brand assets)
scripts/       # PyInstaller build scripts (PowerShell)
tests/         # pytest regression suite
```

Entry points sit at the repo root:

- `citadel_pbo_builder.py`
- `citadel_pbo_inspector.py`
- `citadel_version.py` — single source of truth for the version string

## Coding conventions

- Python 3.11+ syntax. We test against 3.11, 3.12, and 3.13.
- Type hints on public functions. Module-level docstrings explain the *why*.
- No emojis in code or comments.
- Prefer composition over inheritance. Pipeline steps are plain functions.
- Side effects only at the edges (entry points, GUI, file system, subprocess
  calls). The `core` package should stay deterministic and testable.

## Testing

Run the full suite:

```powershell
python -m pytest
```

Filter to one file:

```powershell
python -m pytest tests/test_pbo.py -v
```

If your change touches PBO format, LZSS, preflight rules, or discovery,
**add a test**. If it touches signing, Binarize, or CfgConvert — describe how
you verified it against real DayZ Tools in the PR.

## Reporting bugs

Use the bug report template under
[`.github/ISSUE_TEMPLATE/bug_report.md`](.github/ISSUE_TEMPLATE/bug_report.md).
Include the Citadel PBO Tools version, the OS, the affected app, the
reproduction steps, and the log output from the in-app log window.

## Pull requests

1. Branch from `main`. Name the branch after the change, e.g.
   `fix/extract-prefix-roundtrip` or `feat/inspector-search`.
2. Run `python -m pytest`.
3. Update `CHANGELOG.md` under an `## Unreleased` heading (we move it into
   a numbered version at release time).
4. Bump `citadel_version.py` only when the PR introduces a user-visible
   change worth shipping.
5. Open the PR using the template. Fill out the checklist honestly — `[ ]`
   over a check you didn't actually do helps nobody.

## Release flow

Releases are driven by tags:

```powershell
git tag v1.0.0-beta
git push origin v1.0.0-beta
```

The `release` workflow in `.github/workflows/release.yml` builds the EXEs,
runs the test suite, generates SHA-256 checksums, and creates a GitHub
Release with the artifacts attached.

Versions ending in `-alpha`, `-beta`, or `-rc` are flagged as pre-releases
automatically.

## Key safety

Never commit:

- `.biprivatekey` files
- DayZ Tools paths that contain personal usernames
- Absolute paths from your local workstation
- Settings JSON from `%APPDATA%\Citadel\PBO_Tools\`

`.gitignore` covers the common cases, but a careful PR review still beats
relying on a glob.

## Code of conduct

Be helpful, be specific, and be kind. We're all here because we want the
build pipeline to suck less.
