# Security Policy

## Reporting a vulnerability

If you believe you have found a security issue in Citadel PBO Tools — for
example a way for a malicious `.pbo` to escape the safe-extraction sandbox,
a code-execution path via crafted config files, or a way to leak signing
keys — please **do not open a public GitHub issue**.

Instead, contact the Citadel maintainer directly through one of:

- A private message on the Citadel Discord
- An email to the Citadel team lead

Include:

- Citadel PBO Tools version (Help -> About)
- A clear description of the issue
- Reproduction steps (a sample `.pbo` or addon folder is ideal)
- Your assessment of impact

We'll acknowledge the report quickly, investigate, and coordinate a fix.
Where possible we'll credit you in the release notes once a fix ships.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Things we already protect against

- Absolute paths and parent-folder traversal in PBO entry names (see
  `pbo._safe_target`).
- Encrypted PBO entries are refused rather than silently mis-extracted.
- Build cache is content-fingerprint based, not just mtime/size, so stale
  builds cannot slip past the cache.
- Safe publishing backs up existing artifacts before replacing them and
  restores on failure.

## Things that are NOT a security boundary

Citadel PBO Tools is an authoring tool for trusted Citadel team members.
The following are explicitly out of scope for the threat model:

- The user pointing the Builder at a project source on their own machine.
- Reading the user's own `.biprivatekey` to sign PBOs they built.
- Running DayZ Tools (`Binarize.exe`, `CfgConvert.exe`, `ImageToPAA.exe`,
  `DSSignFile.exe`) that the user has installed and configured.

If your concern is in this category it is a feature request, not a
vulnerability — use the regular issue tracker.
