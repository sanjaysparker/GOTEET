# GOTEET work-management API v1

Local FastAPI service. Every request needs `Authorization: Bearer <token>` (owner token from `data/runtime.json`, or a member pairing token).
Errors: `400` validation (`{"detail": "..."}`), `401` no/bad token, `403` owner-only or capability disabled, `404` unknown id.
Times are ISO-8601 in Asia/Kolkata (`+05:30`). Dates are `YYYY-MM-DD`.

Implementation: `work.py` (domain), routes in `api.py`, schema migrations in `engine.migrate`.

## Permissions

| Route group | Owner | Member |
|---|---|---|
| GET/POST tasks, projects, concepts, relations, cycles, docs, views, inbox | yes | yes |
| `GET /api/goals`, `/api/deadlines` | yes | yes |
| `POST`/`DELETE` goals, key results, milestones | yes | 403 |
| `DELETE` on any resource | yes | 403 |
| `POST /api/automations`, `/toggle`, `DELETE` | yes | 403 |
| `GET /api/automations`, `POST /api/automations/{id}/run` (dry run) | yes | yes |
| `/api/insights*` | yes | 403 |

`X-GOTEET-Actor: <name>` (max 100 chars) sets the audit/inbox actor **only with the owner token**. Members are always audited as themselves.

## Tasks

Task object (`GET /api/tasks`, `/api/snapshot` → `tasks`, `POST /api/tasks` response):

```
{id, key, title, project, owner, status, priority, due, source_url, created_at, updated_at,
 estimate:int, labels:[str], cycle_id, parent_id, description, start_date, checklist:[{text,done}]}
```

- `status` ∈ `Backlog | Todo | In progress | In review | Blocked | Done`
- `priority` ∈ `Urgent | High | Normal | Low`
- `key`: assigned on create, never changes (even if the project changes). Prefix = first 3 alphanumerics of the task's project name uppercased **when that name matches a saved project**, otherwise `GOT` (e.g. `General`). Running number per prefix; numbers are never reused after deletes. Existing rows were backfilled in `created_at` order.
- `estimate`: integer 0–1000, default 0. `labels`: ≤20 unique trimmed strings ≤50 chars. `cycle_id`: `''` or an existing cycle. `parent_id`: `''` or an existing task; loops rejected.
- `POST /api/tasks` **merges**: with an existing `id`, only supplied keys change; omitted or `null` keys keep stored values. Without `id` (or an unknown `id`) a task is created; `title` required.
- Wrong types (e.g. numeric status/due) → 400.

`DELETE /api/tasks/{id}` → `{deleted, relations_removed}`. Removes the task, its details and its relations; children get `parent_id=''`. Docs keep the id but `linked_tasks` hides deleted ids on read.

## Projects and concepts

`POST /api/projects` merges like tasks (`name, description, status, start_date, target_date`).
`DELETE /api/projects/{id}` deletes only the project; tasks referencing its name stay.
`DELETE /api/concepts/{id}`.

## Relations

- `GET /api/relations?task_id=` → `[{id, from_id, to_id, type}]` where the task is either end (omit `task_id` for all).
- `POST /api/relations` `{from_id, to_id, type}`; `type` ∈ `blocks | relates | duplicates`. Self-relations and unknown ids → 400. Posting an identical relation returns the existing one.
- `DELETE /api/relations/{id}`.

## Cycles

`GET /api/cycles` →

```
[{id, name, start, end, status:'upcoming'|'active'|'completed', goal,
  stats:{issues, done, points, done_points, blocked, history:[{date, scope, done}]}}]
```

- `status` from today's date in Asia/Kolkata: before `start` upcoming, after `end` completed, else active.
- `points` = Σ`estimate`. `history`: one entry per day from `start` to `min(today, end)` (empty for upcoming cycles).
- `POST /api/cycles` `{id?, name, start, end, goal}` (merge). `end ≥ start`.
- `DELETE /api/cycles/{id}` → `{deleted, tasks_unset}`; sets `cycle_id=''` on its tasks.

**History limitation:** reconstructed from `task_events` (status/owner/cycle changes recorded by every task save since this version). For days before a task's first recorded event, its current value is used if it already existed (`created_at`). Changes made before v1 or directly in SQLite have no history, so past days can be approximate.

## Docs

- `GET /api/docs` → `[{id, title, body (markdown), project, linked_tasks:[ids], updated_at, author}]`, newest first.
- `POST /api/docs` merge semantics; `title` 1–500, `body` ≤200 000 chars, `linked_tasks` must be existing task ids. `author` = authenticated identity of the last writer.
- `DELETE /api/docs/{id}`.

## Saved views

- `GET /api/views` → `[{id, name, filters, updated_at}]`.
- `POST /api/views` `{id?, name, filters:{status?, priority?, owner?, project?, label?, cycle_id?, query?}}` (string values; unknown filter keys → 400). Filters are stored only; the client applies them.
- `DELETE /api/views/{id}`.

## Inbox

`GET /api/inbox` → up to 300 items newest first, snoozed items hidden until their time:

```
[{id, kind, title, detail, ref_type, ref_id, actor, created_at, read:boolean}]
```

| kind | generated when | ref |
|---|---|---|
| `assigned` | task created with an owner, or owner changes (not to `Unassigned`) | task |
| `status` | task status changes (except to Blocked) | task |
| `blocked` | task becomes Blocked (or is created Blocked) | task |
| `mention` | a chat message contains `@<display_name>` (case-insensitive, whole word) | channel |
| `automation` | an automation rule runs | task |
| `agent` | `/api/agent/plan` creates a plan ("Agent plan ready for review"), or `/api/insights/run` ("AI analysis ready") | plan |
| `chat` | reserved; not generated yet | |

- `POST /api/inbox/read` `{ids:[...]}` or `{ids:'all'}`.
- `POST /api/inbox/snooze` `{id, until}`; `until` ISO date-time (naive = Asia/Kolkata). 404 for unknown id.

Single-workspace inbox: items are not addressed to individual members (the Mac app is local single-user).

## Automations

`GET /api/automations` → `[{id, name, trigger, action, params, enabled, runs, last_run, last_result}]`.
Three disabled examples are seeded when the table is first created.

`POST /api/automations` `{id?, name, trigger, action, params, enabled?}` (merge on `id`; owner only). One `params` object holds trigger and action parameters:

| trigger | params | fires |
|---|---|---|
| `task_status` | `to_status` | after a save moves a task into that status |
| `task_created` | `project` (`''` = any) | after a task is created |
| `task_blocked_hours` | `hours` (0–8760) | on `GET /api/inbox` and `GET /api/snapshot`, for tasks Blocked at least that long; once per task per blocked episode |

| action | params |
|---|---|
| `set_field` | `field` ∈ `status|priority|owner|cycle_id`, `value` (validated) |
| `add_label` | `label` |
| `notify` | optional `message` |

- `POST /api/automations/{id}/toggle` → updated rule.
- `POST /api/automations/{id}/run` → `{automation, dry_run:true, matches:[{task_id, key, title, would, already_applied}], note}`. Changes nothing, not even `runs`.
- `DELETE /api/automations/{id}`.

Execution rules: runs happen synchronously inside the task save; each run increments `runs`, sets `last_run/last_result`, writes an `automation` inbox item and an audit row with actor `automation`. Saves made by an automation **do not trigger automations** (no recursion), but do still create `status`/`blocked`/`assigned` inbox items. Nothing is sent outside the app. A failed action records `last_result: "failed: …"` and does not fail the user's save.

## Insights (owner only)

- `GET /api/insights` → deterministic findings (`insights.analyse()`).
- `GET /api/insights/history` → past AI analyses.
- `POST /api/insights/run` `{provider, model, focus}` → requires `agent_enabled`; returns `{analysis, plan, insights}`; missing provider CLI or timeout → 400 with a clear message.

## Goals

Implementation: `goals.py`. Tables `goals`, `key_results`, `milestones` are created by additive migration. Reads (`GET`) are open to members; every `POST` and `DELETE` is owner only (403 for members). All writes merge on `id` and write an audit row (`goal:<id>`, `key-result:<id>`, `milestone:<id>`, `…:delete:<id>`).

`GET /api/goals` → Active goals first by `target_date` ascending (empty last), then Achieved, Paused, Dropped:

```
[{id, title, description, owner, status:'Active'|'Achieved'|'Paused'|'Dropped', start_date, target_date, project_id,
  progress:0..1, health:'On track'|'At risk'|'Off track'|'Achieved'|'No plan', elapsed:0..1|null, days_left:int|null,
  key_results:[{id, goal_id, title, kind:'tasks'|'manual', project_name, target, current, unit, due, progress:0..1, detail}],
  milestones:[{id, goal_id, project_id, title, due, done:boolean}], created_at, updated_at}]
```

- `POST /api/goals` `{id?, title (1-300), description?, owner?, status? (default Active), start_date?, target_date?, project_id?}`; dates `YYYY-MM-DD`, `target_date >= start_date`; unknown `project_id` 404. Setting status to `Achieved` raises an inbox item (`status`, "Goal achieved: <title>") once per transition.
- `DELETE /api/goals/{id}` → `{deleted, key_results_removed, milestones_removed}`; removes its key results and milestones.
- `POST /api/key-results` `{id?, goal_id, title, kind, project_name?, target?, current?, unit?, due?}`; unknown goal 404; `tasks` needs `project_name`; `manual` needs `target > 0`; numbers must be real JSON numbers. `DELETE /api/key-results/{id}`.
- `POST /api/milestones` `{id?, goal_id?, project_id?, title, due, done?}`; `due` required; `goal_id`/`project_id`, if non-empty, must exist (404). Changing `done` writes `milestone:done:<id>` or `milestone:reopen:<id>`. `DELETE /api/milestones/{id}`.

Progress (deterministic, recomputed on every read, today = Asia/Kolkata date):

| Item | Rule |
|---|---|
| KR `tasks` | done/total of tasks whose `project == project_name`; detail `3/8 tasks`; no tasks → progress 0, detail `No tasks yet` |
| KR `manual` | `clamp(current/target, 0, 1)`; detail `45 / 100 %` (unit appended when set) |
| Goal | mean of its KR progress; with no KRs, done/total milestones; with neither, 0 |
| `elapsed` | `clamp((today-start)/(target-start))` when both dates set (zero-length span: 1 on/after target, else 0); otherwise `null` |
| Health | `Achieved` if status Achieved or progress >= 1; else `No plan` if no KRs and no milestones; else `Off track` if target < today (progress < 1) or `elapsed - progress > 0.30`; else `At risk` if `elapsed - progress > 0.12`; else `On track` |

`GET /api/deadlines` → `{overdue:[…], this_week:[…], later:[…]}`, each item `{type:'task'|'milestone'|'goal'|'project'|'kr', id ('<type>:<ref_id>'), title, due, days (from today, negative = overdue), status, ref_id, goal_id, project}`. `this_week` = 0..7 days, `later` > 7. Nearest first, capped at 60 items in total. Sources: open tasks with a due date; undone milestones; Active goals' `target_date`; projects' `target_date` unless Done; key-result `due` while progress < 1.

Insights (`GET /api/insights`) adds `goal_health` (Off track critical, At risk warn; Active goals), `goal_deadline` (Active goal due within 7 days at progress < 0.7, warn), `milestone_overdue` (undone milestone past due, warn), and a top-level `goals:[{id, title, progress, health}]`. MCP: `goteet_goals` (read).

## Other changes in this version

- `POST /api/agent/plan` now requires `agent_enabled` (403 otherwise).
- Attachments: channel `project-<existing project id>` accepted; file names `''`, `.`, `..` rejected.
- `GET /api/team` uses the settings display name for the owner.
- Settings: serialized writes with a lock and unique temp file; invalid timezone → 400. Themes `noir glacier abyssal cirrus ember phosphor crimson orchid paper graphite midnight light` (default `noir`); `accent` `''` (theme accent) or `#rrggbb`; new `auto_analysis` (default true), `analysis_provider` (default `''`).
- Google logout or sign-in as a different account clears that account's snapshot keys from `workspace.json`, resets Drive setup state and removes cached Drive previews.
- SQLite: WAL, `busy_timeout=5000`, migrations once per database per process, connections closed after each `with engine.connect()` block.

## Limitations

- No optimistic concurrency/versioning: concurrent merges on the same field are last-write-wins.
- Tasks still link to projects by name; renaming a project does not move its tasks or keys.
- Member authorization is per route, not per object (members can edit any task).
- `task_blocked_hours` is evaluated only when the inbox or snapshot is read, not on a timer.
- Cycle history is best-effort (see above).

## Agent observer (passive local activity)

Opt-in, local-only, metadata-only. Implementation: `agent_observer.py`; settings `agent_observer_enabled` (default `false`) and `agent_observer_titles` (default `false`). All routes are owner only (members get 403). While disabled nothing under `~/.claude` or `~/.codex` is read and `GET /api/activity/overview` returns `{enabled:false, coverage:"Off. Enable in Settings → Permissions.", …empty lists}`; `POST /api/activity/scan` returns 403.

| Route | Purpose |
|---|---|
| `GET /api/activity/overview?days=14` | `{enabled, captured_at, coverage, errors, now, mcp_servers, sessions (latest 60), daily, projects, correlations, mistakes, suggestions, totals}`; stored data, no scan. `days` 1-60. |
| `POST /api/activity/scan` | Scan now (also runs on enable, then every 5 min in a background thread); returns the overview. 20 s budget; partial coverage is reported in `coverage`/`errors`. |
| `GET/POST /api/activity/map` | Ordered override rules `[{pattern, project}]` (POST replaces the list; pattern 1-300, project 1-100, max 200). A rule matches a cwd by path prefix or substring and wins over every other mapping. |
| `DELETE /api/activity/data` | Wipes sessions, daily rows, scan state and the parse cache; keeps your mapping rules. Audited. |

Sources: Claude Code `~/.claude/projects/*/*.jsonl`; Codex `~/.codex/sessions/**/rollout-*.jsonl` and uncompressed `archived_sessions`; psutil for running agents (`claude codex aider cursor-agent gemini`, plus node/python launched agents) and an MCP server process count; read-only `git log/status/rev-parse` (10 s timeout, optional locks off, never fetch) for inventory repos and repos seen in sessions. Lookback 14 days, rows retained 60 days; unchanged files are not reparsed (cache keyed by file mtime and size plus a mapping signature).

Never persisted or returned: message text (except a redacted 100-character `title` when `agent_observer_titles` is on), tool inputs/outputs, commands, file names or paths, tokens. `now[].cwd` is always `""` (paths are not returned). Persisted: counts, per-project time blocks, hashed ids, branch names, project names.

Project mapping order: override, saved GOTEET project (name equals repo-root folder or any path segment, case and `-_ ` ignored), git repo root folder (linked worktrees map to their main checkout), Claude scratch workspace `Scratch`, home directory `Home`, else the last folder.

Time: `active_minutes` sums gaps of at most 5 minutes between consecutive log events (agent working time, not human attention). `daily[].projects` and `projects[].minutes` are wall-clock per project (concurrent sessions in one project count once); different projects can overlap in time. `git_estimate_minutes`: commit clusters (gaps under 45 minutes) count span plus 15 minutes, an estimate. Table `activity_days(date, project, tool ∈ claude|codex|agent|git, minutes, sessions, commits)`.

Mistake signals (`mistakes[]`, `{id, severity, kind, project, title, detail, suggestion, evidence[]}`): `session_error_rate` (>= 10 tool calls and >= 30% errors; critical at >= 60% over >= 30 calls), `repeated_failures` (>= 3 identical failing calls in a row; critical at 6), `reverts` (critical at 3), `rework_after_feature` (>= 2 fix commits within 2 h of a feature commit in a day), `long_session_no_commit` (>= 90 active min, no commit in the session), `stale_dirty_tree` (> 3 d; warn at 7), `file_thrash` (>= 3 sessions in a day, each >= 10 files), `ci_failing_after_work` (critical), `unpushed_work` (>= 3 commits ahead for > 1 day). A new critical signal creates one inbox item (kind `agent`) per signal per ISO week.

Correlations (`correlations[]`, pairs, `Scratch`/`Home`/`Unknown` excluded): `score = 0.30*days_shared (Jaccard) + 0.20*min(1, hours_overlap/8) + 0.25*min(1, handoffs/6) + 0.15*min(1, same_session/2) + 0.10*min(1, shared_ci_failures/2)`; kept at score >= 0.15 and >= 2 evidence points. Handoff: one project's activity block ends and the other's starts within 30 minutes.

Suggestions are advice only and never change tasks: unlogged work (saved project, >= 60 agent min or >= 2 commits in 7 days, no task updated), projects that move together (score >= 0.5), no activity for >= 5 days with a deadline within 7 days (`goals.deadlines`), and sessions over 3 h.

Integration: `GET /api/insights` adds `activity_<kind>` findings (evidence `{type:'project', id:<name>}`) and `project_unlogged_work` when the last scan is under 30 minutes old; `insights.run` adds a compact `activity` block to the AI brief; daily/weekly reports gain an `## Activity` section when the observer is on and the window has data.

Codex schema assumptions: tool calls come from `event_msg/item_completed` items `CommandExecution` (error = `status:"failed"` and exit code not 130/143), `FileChange` (files = number of `changes` keys, error = failed status) and `McpToolCall` (failed status or `result.isError`); turns from `UserMessage` items (older `event_msg/user_message`); older rollouts without item events fall back to counting `response_item` `function_call`/`custom_tool_call` (errors 0). Sub-agent rollouts (`session_meta.source.subagent`) count time but 0 turns. Project cwd comes from `session_meta` and `turn_context` only. Compressed `.jsonl.zst` archives are not read (counted in `coverage`).
