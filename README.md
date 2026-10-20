# GOTEET MVP

An integrated desktop work assistant following the requested spark-aigis-maker architecture: Electron + React/Vite + FastAPI, with SQLite. First packaging target is macOS arm64. Windows and Linux targets are defined but must be built and tested on those systems.

## Included

- Personal daily brief, development activity and evidence-linked follow-ups.
- Tasks with owners, priorities, status and due dates; project plans and timelines.
- Workspace chat channels with authenticated authors and member pairing credentials.
- Concepts editable live through desktop, API, CLI or MCP.
- Media thumbnails, grid/list views, format/source/collection filters, sorting and in-app image/video/audio/PDF/text/Office-text/3D previews.
- On-demand file explorer with visible paths, native copy/share and confirmed recoverable Trash.
- Project/task charts, linked project workspaces and restrained navigation motion.
- Profile photos and optional role, organisation, location, website and bio; accent, density, start view, timezone and reduced-motion preferences.
- Dedicated Models and Agents panels for CLI login, OS-keyring API accounts, Ollama/Hugging Face GGUF downloads, skills and MCP registrations.
- Measured resource gauges, top memory users and bounded storage review with AI explanations.
- About-only SPARKER credit and public GitHub release checking.
- Daily/weekly report history and export.
- Google Desktop OAuth with PKCE/state and OS credential storage. Import your own Desktop OAuth client JSON in Connections. Basic Google sign-in and optional read-only Gmail, Drive and Calendar access are separate choices. Enable those APIs and configure your consent audience/test users in the Google project. Do not paste credentials in chat.
- Read-only Codex assistant using existing ChatGPT CLI login, plus local Ollama models.
- Microphone recording, local faster-whisper transcription and local system voice playback.

This is an MVP, not full Jira/Linear/Mattermost parity. Remote collaboration is not deployed. No paid hosting subscription or paid auth service is hardwired into the app. Third-party service limits, model availability and OAuth verification remain their providers' requirements.

## Run from source

Python 3.12 is required for the tested voice stack. Create `.venv312`, install `requirements-lock.txt`, then `npm ci && npm run build && npm run desktop`.

The desktop manages its backend lifetime. User state defaults to the OS app-data folder under `GOTEET/workspace`. For development with the current private inventory, set `WORKMATE_HOME=/Users/sanju/GOTEET` before launching. Secrets are not part of the source or distributable. Private inventory is provisioned to this user's app-data folder separately.

`WORKMATE_HOME` overrides the data root. OAuth tokens and client configuration use the OS credential store. The local API listens on a random loopback port with an owner-only runtime file. The app starts without Google login so local work remains usable while OAuth is being configured.

## Live Claude/Codex access

The bundled MCP server is registered with the local Codex CLI. Project-scoped `.mcp.json` provides the same server to Claude Code, which currently requires its normal approval. Existing unrelated servers were preserved. The 19 tools cover workspace data, media, files, system health, agent inventory and reviewed plans. Sending a message requires an explicit human instruction. See AGENT_ACCESS.md for the portable installed CLI, MCP and optional loopback CDP mode.

Run `.venv312/bin/python workmate_client.py status` while the app is open. List tasks with `tasks`. Create/update a task by piping JSON to `task`; project and concept commands work similarly. These clients call the live API rather than directly editing the database. Example payload:

```json
{"title":"Review the next release","project":"AIGIS","owner":"Sanju","status":"Todo","priority":"Normal","due":"","source_url":""}
```

## Team workspace deployment

Local chat persistence and separate member identities are implemented. For other devices, deploy the backend behind HTTPS and set `WORKMATE_SERVER_URL` and `WORKMATE_SERVER_TOKEN` before starting a desktop client. The owner can generate/revoke named member credentials. Members access shared tasks, project plans, concepts and channels; personal mail/files/reports/AI remain owner-only. Pairing does not send an invitation.

For server deployment, `WORKMATE_LISTEN_HOST` and `WORKMATE_PORT` choose the listener. Defaults remain loopback and a random port. Use an external HTTPS reverse proxy and restrict access; no remote listener has been enabled by this task. Google owner OAuth is designed for local desktop sign-in; production Google identity federation for team members is not implemented.

## Build

`scripts/package_backend.py` freezes the Python service for the current OS. Then `npm run build`, followed by `npm run package:mac`, `package:win` or `package:linux` on the appropriate OS. No CI release or remote publish is configured. Private snapshots and the task database must never be copied into distributable resources. The first local Mac build is unsigned.

## Reports

Daily and Friday weekly report automations are attached to the originating Codex chat. They depend on the local scheduler environment being available. They are not an always-on hosted reporting service. App reports show source capture times and stale/missing coverage. Historical comparison becomes more useful as successive snapshots accumulate.

See OPEN_SOURCE_REVIEW.md for the repository comparison and source/coverage limitations. See VERIFICATION.md for measured build and integration evidence.

Profile & settings is opened from the bottom-left account button. Permissions are enforced by the backend. File attachments can be added to saved tasks/projects/concepts and shared chat channels. System view shows measured hardware/resource state and available CLI tools.
