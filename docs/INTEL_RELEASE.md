## Intel Mac installer

Download `GOTEET-0.5.7-mac-x64.dmg`, open it and drag GOTEET to Applications.

- For Intel Macs running macOS 14 Sonoma or newer. Apple Silicon users should retain their arm64 build.
- Bundles the Python backend, UI, media/CAD readers and compatible Intel speech dependencies. No Node, Python or Supabase CLI setup is required on a teammate's Mac.
- Includes Google/Supabase account setup, automatic account-status refresh, GOTEET-owned report scheduling and startup splash.
- GitHub cloud builds use the macos-15-intel runner; local cross-builds use Rosetta. Release verification requires a Mach-O architecture audit, packaged API smoke test, regression tests and DMG verification.
- Unsigned and not notarized: macOS may require approval in Privacy & Security.
- This repository is public. Downloads do not require repository access.
- Team collaboration remains an MVP; this release does not claim full Slack parity.

SHA-256 checksums are attached. Private workspace data and account credentials are not included.
