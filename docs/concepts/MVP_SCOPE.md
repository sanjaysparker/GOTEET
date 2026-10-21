# GOTEET 1.0 — redesign + MVP scope (proposal, 2026-10-21)

Status: **proposal, awaiting concept selection.** Per AGENTS.md, final UI is not implemented until a concept is chosen.
Concept prototype: `docs/concepts/redesign-2026-10.html` (sample data, three shells, ⌘K palette, J/K navigation, drag on board).

## Design system

Adopt AIGIS "Noir Atelier" (`~/aigis-droneo/DESIGN.md`, `frontend/src/theme/tokens.css`) as the binding system:
OKLCH warm-noir neutrals, one pale-gold accent (≤10% of a view), status colours only on status and always paired with an icon,
Inter UI / JetBrains Mono data / Bodoni Moda moments, radius 2/4/10, hairlines, no shadows except overlays, 150–200 ms ease-out-quint.
This replaces the current GOTEET DESIGN.md palette (apricot `#ffab65`). Fonts get self-hosted (air-gap rule).

## Shell concepts (pick one)

| | A · Ledger | B · Hub | C · Atelier dock |
|---|---|---|---|
| Model | Linear | Microsoft Teams | AIGIS GCS cockpit |
| Layout | Sidebar + list + peek drawer | Icon rail + context list + main | Workspace tabs + 3 docked panels + status bar |
| Best at | Fast issue triage, keyboard flow | Chat-first team work, meetings | Seeing work, detail and chat at once |
| Weak at | Chat is secondary | Issue density | Small windows (<1280 px) |

Recommendation: **A · Ledger** as the default shell, with C's status bar and corner-tick focus from AIGIS.

## MVP features (what each reference app contributes)

| Area | Feature | Reference |
|---|---|---|
| Issues | Team keys (`AIG-142`), status workflow, priority, estimate, labels, assignee, sub-issues, relations (blocks/duplicates), list + board, bulk edit | Linear, Jira, Plane |
| Planning | Cycles/sprints with burn-up and scope change, backlog, roadmap/Gantt with milestones, project health updates | Linear, Jira, Plane |
| Inbox | Mentions, assignments, CI failures, agent requests; snooze, mark read | Linear |
| Views | Filters, saved views, group/sort, "My open work" | Linear, Jira |
| Chat | Channels, DMs, threads, reactions, message → issue, issue embeds, meeting link | Teams, Mattermost |
| Docs | Block docs linked to issues/projects, agent summary block | AFFiNE, Notion, Plane pages |
| Automations | Local rules: PR merged → Done, CI failed → Urgent issue, reaction → draft issue, weekly IST report | Jira Automation, Linear |
| Dev | GitHub PR/CI linked to issues (existing GitHub capture) | Linear, Plane |
| Agent | ⌘K ask/command, triage, focus ranking with stated reason, plans require Apply (review-first, audited) | AIGIS agent + Guardian pattern |
| Keep | Google sign-in/readers, Files, Media/CAD, Models, Agents/MCP, System, Profile/Preferences | existing GOTEET |

Out of MVP (later): real-time multi-user sync, video calls engine, whiteboard, time tracking, OKRs, Jira/Linear importers.

## Engineering plan after selection

1. Split `src/main.tsx` (59 KB in 140 lines) into `app/`, `features/<area>/`, `ui/` modules with a typed API client; no behaviour change, verified by existing tests + screenshots.
2. Token layer from AIGIS `tokens.css`; Radix primitives for menus, dialogs, tabs, switch (already dependencies).
3. Backend: `issues`, `cycles`, `issue_relations`, `views`, `automations`, `notifications` SQLite tables + migrations preserving existing `tasks`/`projects` (tasks migrate to issues, ids kept).
4. Fix audited defects (see bug audit) before new features land.
5. Each feature: pytest for API, tsc, live check in the app, screenshot evidence in `evidence/`.
