# Open-source fit review — 21 October 2026

For this brief, use a focused Electron/React/FastAPI work assistant with live API/MCP, and preserve Plane for a later shared project integration. This is a fit assessment, not a security audit or a claim of Jira/Linear feature parity.

| Source | Fit | Evidence and decision |
|---|---|---|
| [Plane](https://github.com/makeplane/plane) | Closest maintained Linear/Jira-style project reference | Issues, cycles, modules, views and project analytics. AGPL-3.0. Existing installation at `/Users/sanju/code/plane-local`, currently not running. Preserve it; do not fork its whole server into a personal assistant. |
| [Huly original](https://github.com/hcengineering/platform/blob/develop/README.md) | Closest combined project/chat product model | Source includes Chat, Project Management, CRM, HRM and ATS. Original README says repository is frozen and hosted Huly discontinued. Do not choose this origin as a maintained dependency. |
| [Platform Collective](https://github.com/Platform-Collective/platform) | Successor referenced by Huly | Active community continuation, EPL-2.0. Smaller independent adoption history than the original; evaluate maintenance and deployment before a production commitment. Clone kept for reference. |
| [Mattermost](https://github.com/mattermost/mattermost) | Strong team communication reference | Source and integration APIs inspected; deployment and edition-specific license/feature boundaries need checking. It does not replace the personal development/media/reporting layer. |
| [Focalboard](https://github.com/mattermost-community/focalboard) | Board/task reference | Narrower than the requested app; last observed push May 2026. Not selected as the foundation. Inspect its exact license before reuse. |
| [AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) | Documents and AI workspace reference | AGPL-3.0; different stack and primary focus. Useful product reference, not an Electron/React component drop-in. |
| [Vikunja](https://github.com/go-vikunja/vikunja) | Focused task manager | AGPL-3.0; useful for task organisation, not the entire requested assistant. |
| [Taiga backend](https://github.com/taigaio/taiga-back) | Agile execution reference | Backend metadata reports MPL-2.0 at inspection. Treat licenses per repository and version, not from outdated product summaries. |
| [OpenClaw](https://github.com/openclaw/openclaw) | Broad autonomous assistant reference | MIT, large observed adoption. Agent runtime and channels rather than a complete integrated project/media desktop. Not installed as a privileged system agent. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Memory and agent workflow reference | MIT. Useful agent runtime reference; not a project-management and people-chat replacement. |
| [Activepieces](https://github.com/activepieces/activepieces) | Connector/workflow option | Community/enterprise source boundaries need exact license inspection. A future automation adapter, not the main app UI. |

Stars, push dates, archive flags and license metadata were captured from GitHub into `data/opensource.json`. These indicate activity/adoption only. No vulnerability audit, security certification or trend ranking was performed.

## Source inspection and actual reuse

Huly original cloned at `references/huly`, commit `8ed328fef4d3f37824a01b32bab13257116c6c45`; successor cloned at `references/platform-collective`. Source inspection covered tracker project/status/date models, chunter channel/message author models, calendar and desktop structure. Reference patterns informed the schema; Huly implementation files are not copied into the app or shipped. Keep upstream licensing intact inside the reference clones.

Existing Plane source at `/Users/sanju/code/plane` was inspected read-only. No existing Plane data, containers, credentials or source were changed.

Runtime components actually integrated through package dependencies: Electron desktop shell, React, Vite, Lucide icons, Inter font, FastAPI, SQLite, official MCP Python SDK, keyring, Ollama HTTP API and faster-whisper. Exact versions are pinned in package-lock.json and requirements-lock.txt; upstream licenses remain with their distributions.

## Initial coverage

37 repositories accessible through two gh accounts; default-branch commit metadata for the last 30 days, at most 1000 per repo; first 100 open PRs/issues and latest 10 workflow runs. One empty repository returned HTTP 409. No complete source-code correctness audit.

79 local Git checkouts/submodules/worktrees and 4,383 media/document files in selected work folders. Depth limited to five, with deeper folders skipped; Photos Library access was denied by macOS. Hidden configuration/credential directories, app bundles, symlinks and backups excluded.

Google Workspace import: first 35 matching recent mail records before authentication-message filtering; 30 recent Drive metadata records; primary calendar inspected for 21–28 October 2026 with no events returned. Two relevant email threads were inspected for confirmed follow-ups, and only operational summaries were retained. Standalone Google OAuth remains a separate setup.

## Profile and settings component integration

[shadcn/ui](https://github.com/shadcn-ui/ui), approximately 126,000 stars at inspection and MIT licensed, was cloned into `references/shadcn-ui` for sidebar/account-menu patterns. Runtime dropdown menu, switch and tabs components are integrated from [Radix Primitives](https://github.com/radix-ui/primitives), MIT licensed. These are actual installed dependencies used by the profile menu, account settings, preferences and permission controls. GOTEET applies its own design tokens and real backend operations. Stars alone were not treated as a trust guarantee.

## ERPNext and motion references

[ERPNext](https://github.com/frappe/erpnext), reference checkout `references/erpnext` at commit `6de47690f780e41e463652d54bf5010100b59521`, was inspected for project/task links, explicit statuses, task-completion percentages, role permissions and linked records. GOTEET's Project workspace now links actual tasks, dates, attachments and a project channel, with completion calculated as Done tasks / linked tasks. ERPNext GPL-3.0 implementation code is not copied or bundled. This is concept reuse, not ERP/HR/accounting parity.

[Friction](https://github.com/friction2d/friction) is a Qt/Skia motion-graphics authoring application under GPL-3.0. It was evaluated as the user-supplied reference. For runtime UI animation, [Motion](https://github.com/motiondivision/motion) is integrated as a React dependency; [Recharts](https://github.com/recharts/recharts) provides real project/task/activity charts; [Three.js](https://github.com/mrdoob/three.js) provides STL, OBJ and embedded-resource GLB previews. Their exact installed versions and licenses remain in the lockfile/dependency distributions.
