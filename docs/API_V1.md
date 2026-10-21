# GOTEET work-management API v1

Local FastAPI service. Every request needs `Authorization: Bearer <token>` (owner token from `data/runtime.json`, or a member pairing token).
Errors: `400` validation (`{"detail": "..."}`), `401` no/bad token, `403` owner-only or capability disabled, `404` unknown id.
Times are ISO-8601 in Asia/Kolkata (`+05:30`). Dates are `YYYY-MM-DD`.

Implementation: `work.py` (domain), routes in `api.py`, schema migrations in `engine.migrate`.

## Permissions

| Route group | Owner | Member |
|---|---|---|
| GET/POST tasks, projects, concepts, relations, cycles, docs, views, inbox | yes | yes |
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
