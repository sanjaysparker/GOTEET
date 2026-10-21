# GOTEET bug audit (2026-10-21, v0.5.4, commit 41b60b5)

Method: read-only review plus requests against an isolated backend (`WORKMATE_HOME` in a temp dir). `tsc --noEmit` exit 0 and `pytest -q` 37 passed; neither catches the defects below.

29 defects: 0 critical, 5 high, 15 medium, 9 low.

## High
| file:line | Defect | Evidence |
|---|---|---|
| engine.py:80-82, mcp_server.py:17-19 | `save_task` upserts defaults for omitted fields | Partial update `{"id":"t1","title":"Ship","status":"Done"}` reset project/owner/priority/due |
| operations.py:16-17, mcp_server.py:27-29 | `save_project` same overwrite | Partial update cleared description, start/target dates; project left Timeline |
| src/main.tsx:59,61 | Stale closure in 5 s poller resets selected model | `if(!model&&…)setModel(models[0])` reads first-render `model` |
| settings.py:31 | Fixed `settings.tmp`, no lock | 40 concurrent saves: 23 × HTTP 500 + lost updates |
| google_auth.py:104-111,73-91,155-157 | Logout / account switch keeps old `workspace.json` | Account A mail/calendar visible and fed to assistant after switch |

## Medium
| file:line | Defect |
|---|---|
| api.py:61-75,279,322 | Member auth is per-route, not per-object (member overwrote owner task, read arbitrary channel) |
| settings.py:29 | Bad timezone → 500 |
| engine.py:74-79,88-89 | Non-string status/due → 500 |
| ui_control.py:28, agent.py:179-181 | Queued command expires at 60 s while native dialog open → false "partial" |
| agent.py:106-171 | `execute` has no lock; double apply duplicates actions |
| api.py:397 | `/api/agent/plan` ignores `agent_enabled` gate |
| src/main.tsx:107, api.py:251-256 | Project chat uploads rejected (`project-<id>` not allowed) |
| src/DrivePanel.tsx:6,9 | Folder trail not reset on account switch |
| src/main.tsx:29 | `new Date('YYYY-MM-DD')` shows dates one day early in negative-offset TZ |
| src/main.tsx:72 | Editor saves full stale snapshot, last-write-wins |
| engine.py:21-24 | Tasks link projects by name; rename orphans tasks |
| workmate_client.py:28 | `X-GOTEET-Actor` ignored; agent writes audited as Sanju |
| api.py:122-140, model_setup.py:120 | Missing CLI / timeout → raw 500 |
| api.py:228-238 | Blocking PIL + sync SQLite on event loop |
| workmate_client.py:15-30 | Stale `data/runtime.json` fallback; non-JSON errors crash |

## Low
main.cjs:59 422 `detail` shown as `[object Object]` · api.py:265 `..` attachment name accepted · main.tsx:61/63/68 pollers without in-flight guards, 1.5 MB snapshot every 5 s · engine.py:17-40 DDL per connect, no WAL · google_auth.py:69 `PENDING` unbounded · media_library.py:7 preview allowlist never revoked · agent_management.py:13 ignores `~/.claude/skills` · api.py:299-301 hardcoded 'Sanju' · PlanningWorkspace/MailPanel raw IPC error prefix.

## Architecture
1. `App` in main.tsx ≈ 52 KB, ~42 `useState`, 13 effects in one closure.
2. No typed API contract (`Record<string,any>` ×16, backend `value:dict`); no DELETE routes.
3. Whole-object last-write-wins writes with no versioning or actor attribution.
4. State split across SQLite, settings.json, workspace.json, inventory.json and process dicts with no locks.
5. Polling (1 s/2 s/5 s) instead of push; time-based command status.
