# GOTEET shared workspace database

Project: **GOTEET**, organisation **Sparker2707**, region **Mumbai (ap-south-1)**.
Project ref: `ynjspephbavvnsslscsl`
API base: `https://ynjspephbavvnsslscsl.supabase.co`
Dashboard: https://supabase.com/dashboard/project/ynjspephbavvnsslscsl

## Deployed model

- `team_workspaces`: tenant and owner identity.
- `team_members`: owner/admin/member/viewer roles, scoped to a workspace.
- `team_projects`: shared plans with start/target dates.
- `team_tasks`: task status, priority, assignee, description and start/due dates.
- `team_milestones`: project milestones and completion.
- `team_channels`: workspace-visible channels (general and work-updates created with a workspace).
- `team_updates`: immutable work reports/messages with authenticated author and desktop/codex/claude/cli source label. Source label is client-declared, not proof of which agent ran.
- `team_mentions`: references to workspace members from an update.
- Private Storage bucket `goteet-team-files`: 50 MiB per object. Path: `<workspace UUID>/<uploader UUID>/<unique filename>`.

Project/channel/task references use composite workspace foreign keys. Every table has row-level security. Users cannot grant themselves membership or forge a message author. Realtime publication covers the six collaboration content tables. There are no client DELETE grants on work records. Updates remain immutable.

## Authenticated API contract

Clients use Supabase Auth access tokens and the project's publishable key, never the service-role key or database password.

1. Authenticate with Supabase Auth (desktop login wiring still pending).
2. Call `create_team_workspace(workspace_name)` to create an owned workspace and its default channels.
3. Owner/admin calls `add_team_member(w, member_user_id, member_role)` for an already registered account. Supported invitation roles are member/viewer; this RPC sends no email. A user-facing invitation flow is still pending.
4. Read/write team tables through the REST API using the user's JWT. Viewer writes are denied.
5. Subscribe to table changes for the selected workspace; re-fetch on reconnect. Concurrent editing/version conflict UX is not implemented yet.
6. Owner/admin calls `remove_team_member(w, member_user_id)` to revoke member/viewer access; assigned tasks become unassigned and historical updates remain.

CLI/MCP clients must authenticate as the teammate. They can submit an explicit work update or task change using the same API. The existing local MCP client has NOT yet been rewired to this cloud API.

## Local versus shared

No existing Mac tasks, mail, Drive snapshots, activity logs, reports, credentials or attachments were uploaded. The schema is ready but contains no production workspace/users yet. Keep private analysis local and publish only selected work summaries. The old SQLite workspace and installed 0.5.4 desktop remain unchanged.

## Operations

Supabase CLI 2.122.0 was used through npx. Database password is in this Mac's Keychain under service `in.droneos.goteet.cloud`, account `supabase-database-password`. Never put it in source or distribution packages.

Migrations are in `supabase/migrations`. Deploy with `supabase db push --linked`; do not reset the remote database. Verify with `supabase migration list --linked`. The local Supabase config is a development template, not proof of remote Auth/provider configuration.

Run the rollback-only database isolation test with:

```sh
npx supabase db query --linked --file supabase/tests/workspace_isolation.sql
```

Live tests: owner create/read, immutable author, viewer read/write denial, member posting, author-spoof rejection, membership revocation, outsider isolation and anonymous denial passed. All eight public team tables have RLS enabled. Tests use temporary auth IDs inside a transaction and roll back; no test accounts persist.

## Mattermost reference

Reviewed Mattermost's [team model](https://github.com/mattermost/mattermost/blob/master/server/public/model/team.go) and [channel model](https://github.com/mattermost/mattermost/blob/master/server/public/model/channel.go). Adapted the workspace → membership → channel → authored-post organisation; no Mattermost source was copied. Private channels, direct messages and threaded conversations are not implemented in this first schema.

## Remaining integration

Desktop Supabase login/session refresh, invitation UI, cloud workspace switcher, shared project/timeline views, signed-URL attachment UI and per-person agent pairing. Google provider configuration is separate from the existing local Drive OAuth connection. GitHub Releases distribute the app; Supabase stores team data. Download-page checking exists; automatic installer replacement is not yet implemented.

## Google cloud login implementation (23 October)

Source now includes `cloud_auth.py`, authenticated `/api/cloud/*` routes and the cloud-account panel in Connections. It uses browser OAuth with S256 PKCE, a single-use 10-minute local state, verified Supabase user identity, OS-keyring sessions, refresh, local sign-out and an RLS-filtered workspace list. No Google provider tokens are retained. `cloud_public.py` contains only the public project URL and legacy anon/publishable key; it grants no administrative access.

**Deployment blocker:** live `/auth/v1/settings` reports Google disabled. A Google **Web application** OAuth client must be configured in Supabase Authentication → Sign In / Providers → Google. The earlier Desktop client is for private source imports and is not this configuration.

- Google authorized redirect URI: `https://ynjspephbavvnsslscsl.supabase.co/auth/v1/callback`.
- Supabase Authentication → URL Configuration → Redirect URLs: add `http://127.0.0.1:*/api/cloud/callback**` for the desktop's dynamic loopback port and state query. Do not allow arbitrary external redirect hosts.
- Keep client secret in the Supabase provider configuration, never source, chat or desktop packages.
- Enable external Google audience for personal and company accounts, subject to company policy. Use the identity scopes openid/email/profile. Public brand verification is an independent Google process.
- Test actual login, automatic account refresh, restart restoration, logout and two-user isolation before releasing. Teammates need the packaged app, not Supabase CLI.

Verification: seven isolated authentication tests pass (disabled provider, callback host, PKCE and replay, expiry, refresh redaction, offline logout, provider-token exclusion); TypeScript/Vite build passes. Actual Google login is NOT verified and this change has not replaced the installed app. Shared project view synchronisation and invitation UI remain pending.
