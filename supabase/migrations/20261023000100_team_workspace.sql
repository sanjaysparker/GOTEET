-- GOTEET: shared execution only. Personal snapshots and machine logs stay local.
create schema if not exists goteet_private;
revoke all on schema goteet_private from public;
grant usage on schema goteet_private to authenticated;
create table public.team_workspaces (
 id uuid primary key default gen_random_uuid(), name text not null check(length(trim(name)) between 1 and 120),
 owner_id uuid not null references auth.users(id), created_at timestamptz not null default now()
);
create table public.team_members (
 workspace_id uuid not null references public.team_workspaces on delete cascade,
 user_id uuid not null references auth.users on delete cascade,
 role text not null check(role in ('owner','admin','member','viewer')), display_name text not null default '',
 joined_at timestamptz not null default now(), primary key(workspace_id,user_id)
);
create function goteet_private.has_role(w uuid, roles text[]) returns boolean
 language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.team_members where workspace_id=w and user_id=(select auth.uid()) and role=any(roles)) $$;
revoke all on function goteet_private.has_role(uuid,text[]) from public;
grant execute on function goteet_private.has_role(uuid,text[]) to authenticated;
create table public.team_projects (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.team_workspaces on delete cascade,
 title text not null check(length(trim(title)) between 1 and 200), description text not null default '',
 status text not null default 'Planned' check(status in ('Planned','Active','Paused','Done')),
 start_date date, target_date date, created_by uuid not null default auth.uid() references auth.users,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(workspace_id,id), check(target_date is null or start_date is null or target_date>=start_date)
);
create table public.team_tasks (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.team_workspaces on delete cascade,
 project_id uuid, title text not null check(length(trim(title)) between 1 and 300), description text not null default '',
 status text not null default 'Todo' check(status in ('Backlog','Todo','In progress','In review','Blocked','Done')),
 priority text not null default 'Normal' check(priority in ('Urgent','High','Normal','Low')),
 assignee_id uuid, start_date date, due_date date,
 created_by uuid not null default auth.uid() references auth.users, created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 unique(workspace_id,id), foreign key(workspace_id,project_id) references public.team_projects(workspace_id,id),
 foreign key(workspace_id,assignee_id) references public.team_members(workspace_id,user_id),
 check(due_date is null or start_date is null or due_date>=start_date)
);
create table public.team_milestones (
 id uuid primary key default gen_random_uuid(),workspace_id uuid not null references public.team_workspaces on delete cascade,
 project_id uuid not null,title text not null check(length(trim(title)) between 1 and 200),due_date date not null,
 completed boolean not null default false,created_by uuid not null default auth.uid() references auth.users,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 foreign key(workspace_id,project_id) references public.team_projects(workspace_id,id)
);
-- Mattermost-inspired workspace/channel/post hierarchy. MVP channels are workspace-visible.
create table public.team_channels (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.team_workspaces on delete cascade,
 name text not null check(length(trim(name)) between 1 and 80),created_by uuid not null default auth.uid() references auth.users,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(workspace_id,id),unique(workspace_id,name)
);
create table public.team_updates (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.team_workspaces on delete cascade,
 channel_id uuid,project_id uuid,task_id uuid,author_id uuid not null default auth.uid() references auth.users,
 body text not null check(length(trim(body)) between 1 and 20000),
 source text not null default 'desktop' check(source in ('desktop','codex','claude','cli')),
 occurred_on date not null default current_date,created_at timestamptz not null default now(),
 unique(workspace_id,id),foreign key(workspace_id,channel_id) references public.team_channels(workspace_id,id),
 foreign key(workspace_id,project_id) references public.team_projects(workspace_id,id),
 foreign key(workspace_id,task_id) references public.team_tasks(workspace_id,id)
);
create table public.team_mentions (
 workspace_id uuid not null,update_id uuid not null,user_id uuid not null,
 primary key(update_id,user_id),foreign key(workspace_id,update_id) references public.team_updates(workspace_id,id) on delete cascade,
 foreign key(workspace_id,user_id) references public.team_members(workspace_id,user_id) on delete cascade
);
create function goteet_private.stamp_record() returns trigger language plpgsql set search_path='' as $$
begin
 if new.id<>old.id or new.workspace_id<>old.workspace_id or new.created_by<>old.created_by or new.created_at<>old.created_at then raise exception 'Record identity is immutable'; end if;
 new.updated_at=now();return new;
end $$;
create function public.create_team_workspace(workspace_name text) returns uuid language plpgsql security definer set search_path='' as $$
declare w uuid; u uuid:=auth.uid();
begin
 if u is null then raise exception 'Sign in first'; end if;
 insert into public.team_workspaces(name,owner_id) values(workspace_name,u) returning id into w;
 insert into public.team_members(workspace_id,user_id,role) values(w,u,'owner');
 insert into public.team_channels(workspace_id,name,created_by) values(w,'general',u),(w,'work-updates',u);
 return w;
end $$;
-- Add an already signed-up account explicitly; no invitation emails are sent.
create function public.add_team_member(w uuid, member_user_id uuid, member_role text default 'member') returns void
 language plpgsql security definer set search_path='' as $$
begin
 if not goteet_private.has_role(w,array['owner','admin']) then raise exception 'Workspace administrator required'; end if;
 if member_role not in ('member','viewer') then raise exception 'Choose member or viewer'; end if;
 insert into public.team_members(workspace_id,user_id,role) values(w,member_user_id,member_role);
end $$;
revoke all on function public.create_team_workspace(text) from public;
revoke all on function public.add_team_member(uuid,uuid,text) from public;
grant execute on function public.create_team_workspace(text),public.add_team_member(uuid,uuid,text) to authenticated;
alter table public.team_workspaces enable row level security;
alter table public.team_members enable row level security;
create policy workspace_read on public.team_workspaces for select to authenticated using(goteet_private.has_role(id,array['owner','admin','member','viewer']));
create policy members_read on public.team_members for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
grant select on public.team_workspaces,public.team_members to authenticated;

alter table public.team_projects enable row level security;
create index team_projects_workspace_idx on public.team_projects(workspace_id);
create policy read_members on public.team_projects for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_projects for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (created_by=auth.uid()));
grant select,insert on public.team_projects to authenticated;
create policy edit_members on public.team_projects for update to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member'])) with check(goteet_private.has_role(workspace_id,array['owner','admin','member']));
grant update on public.team_projects to authenticated;
create trigger stamp before update on public.team_projects for each row execute function goteet_private.stamp_record();
alter publication supabase_realtime add table public.team_projects;

alter table public.team_tasks enable row level security;
create index team_tasks_workspace_idx on public.team_tasks(workspace_id);
create policy read_members on public.team_tasks for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_tasks for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (created_by=auth.uid()));
grant select,insert on public.team_tasks to authenticated;
create policy edit_members on public.team_tasks for update to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member'])) with check(goteet_private.has_role(workspace_id,array['owner','admin','member']));
grant update on public.team_tasks to authenticated;
create trigger stamp before update on public.team_tasks for each row execute function goteet_private.stamp_record();
alter publication supabase_realtime add table public.team_tasks;

alter table public.team_milestones enable row level security;
create index team_milestones_workspace_idx on public.team_milestones(workspace_id);
create policy read_members on public.team_milestones for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_milestones for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (created_by=auth.uid()));
grant select,insert on public.team_milestones to authenticated;
create policy edit_members on public.team_milestones for update to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member'])) with check(goteet_private.has_role(workspace_id,array['owner','admin','member']));
grant update on public.team_milestones to authenticated;
create trigger stamp before update on public.team_milestones for each row execute function goteet_private.stamp_record();
alter publication supabase_realtime add table public.team_milestones;

alter table public.team_channels enable row level security;
create index team_channels_workspace_idx on public.team_channels(workspace_id);
create policy read_members on public.team_channels for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_channels for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (created_by=auth.uid()));
grant select,insert on public.team_channels to authenticated;
create policy edit_members on public.team_channels for update to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member'])) with check(goteet_private.has_role(workspace_id,array['owner','admin','member']));
grant update on public.team_channels to authenticated;
create trigger stamp before update on public.team_channels for each row execute function goteet_private.stamp_record();
alter publication supabase_realtime add table public.team_channels;

alter table public.team_updates enable row level security;
create index team_updates_workspace_idx on public.team_updates(workspace_id);
create policy read_members on public.team_updates for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_updates for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (author_id=auth.uid()));
grant select,insert on public.team_updates to authenticated;
alter publication supabase_realtime add table public.team_updates;

alter table public.team_mentions enable row level security;
create index team_mentions_workspace_idx on public.team_mentions(workspace_id);
create policy read_members on public.team_mentions for select to authenticated using(goteet_private.has_role(workspace_id,array['owner','admin','member','viewer']));
create policy insert_members on public.team_mentions for insert to authenticated with check(goteet_private.has_role(workspace_id,array['owner','admin','member']) and (exists(select 1 from public.team_updates u where u.id=update_id and u.workspace_id=team_mentions.workspace_id and u.author_id=auth.uid())));
grant select,insert on public.team_mentions to authenticated;
alter publication supabase_realtime add table public.team_mentions;

-- Immutable updates provide a durable team work log; no client DELETE permissions.
-- Override Supabase default table grants: expose only deliberately supported operations.
revoke all on public.team_workspaces,public.team_members,public.team_projects,public.team_tasks,public.team_milestones,public.team_channels,public.team_updates,public.team_mentions from anon,authenticated;
grant select on public.team_workspaces,public.team_members to authenticated;
grant select,insert,update on public.team_projects,public.team_tasks,public.team_milestones,public.team_channels to authenticated;
grant select,insert on public.team_updates,public.team_mentions to authenticated;
