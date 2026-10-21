# Changes

## 0.4.1 — 21 October 2026

- Made basic Google identity sign-in the primary flow, with account chooser and Log out. Data imports now start unselected under an optional panel; developer configuration is collapsed.
- Added branded callback success/cancel/error pages and an Open GOTEET desktop link.
- Refresh account status automatically; logout invalidates pending sign-in attempts.

## 0.4.0 — 21 October 2026

- Added selectable read-only Gmail, Drive, Calendar, Contacts and Google Tasks imports, with per-source results and capture times.
- Added imported-record previews and optional Google profile name/photo import.
- Preserved previous source snapshots when individual imports fail; separated accounts when changing Google identity.
- Verified installed Google login opens the system-browser account chooser. Google consent remains user-controlled.

## 0.3.1 — 21 October 2026

- Added local profile photo upload and optional personal/work details.
- Added accent, density, reduced-motion, start-view and timezone preferences.
- Replaced the app logo and kept the SPARKER credit in About only.
- Added graphical projects/tasks, linked project workspace, media thumbnails/viewers, native Files actions, measured System review and dedicated Models/Agents setup.
- Added reviewed agent actions and portable CLI/19-tool MCP/optional loopback CDP control.
- Fixed background desktop command processing and frozen voice-worker startup.
- Installed and verified the unsigned Mac arm64 build; see VERIFICATION.md for measured coverage and remaining setup requirements.

## 0.5.0 — Integrated readers and appearance
- Dedicated read-only Gmail reader with folders, search, pagination and on-demand body text.
- Drive contents preview inside GOTEET; native Google documents export as PDF after read-content consent.
- PDF page/zoom/text controls and semantic DOCX reading with outline, search and tables.
- Video transport and original-preserving image rotation.
- Graphite/Midnight/Paper appearance and custom accents; reduced-motion-aware reading transitions.
- Read aloud toggles Stop; Enter sends, Shift+Enter inserts a newline, IME composition stays intact.

## 0.5.1

- Calendar timeline and status board with existing project/task editors.
- Drive folders, breadcrumbs and thumbnail browsing.
- PDF first-page and supported document text previews on library cards.
- Report formatting, task completion controls and light-theme contrast fixes.
- Single-copy Mac cleanup command.
- Activity sampler foundation remains disabled and unfinished.
