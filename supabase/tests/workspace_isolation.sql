begin;
insert into auth.users(id) values('10000000-0000-0000-0000-000000000001'),('10000000-0000-0000-0000-000000000002'),('10000000-0000-0000-0000-000000000003');
set local role authenticated;
select set_config('request.jwt.claim.sub','10000000-0000-0000-0000-000000000001',true);
select public.create_team_workspace('Rollback security test');
select public.add_team_member((select id from public.team_workspaces limit 1),'10000000-0000-0000-0000-000000000002','viewer');
insert into public.team_projects(workspace_id,title) select id,'Test plan' from public.team_workspaces;
insert into public.team_updates(workspace_id,body,source) select id,'Test agent update','codex' from public.team_workspaces;
do $$ begin
 if (select count(*) from public.team_projects)<>1 then raise exception 'Owner read failed'; end if;
 begin
  update public.team_projects set created_by='10000000-0000-0000-0000-000000000002';
  raise exception 'Identity spoof unexpectedly succeeded';
 exception when raise_exception then
  if sqlerrm <> 'Record identity is immutable' then raise; end if;
 end;
end $$;
select set_config('request.jwt.claim.sub','10000000-0000-0000-0000-000000000002',true);
do $$ begin
 if (select count(*) from public.team_projects)<>1 then raise exception 'Viewer read failed'; end if;
 begin
  insert into public.team_projects(workspace_id,title) select id,'Forbidden' from public.team_workspaces;
  raise exception 'Viewer insert unexpectedly succeeded';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
update public.team_members set role='member' where user_id='10000000-0000-0000-0000-000000000002';
set local role authenticated;
insert into public.team_updates(workspace_id,body,source) select id,'Member work update','claude' from public.team_workspaces;
do $$ begin
 begin
  insert into public.team_updates(workspace_id,body,author_id) select id,'Forged author','10000000-0000-0000-0000-000000000001' from public.team_workspaces;
  raise exception 'Author spoof unexpectedly succeeded';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','10000000-0000-0000-0000-000000000001',true);
select public.remove_team_member((select id from public.team_workspaces limit 1),'10000000-0000-0000-0000-000000000002');
select set_config('request.jwt.claim.sub','10000000-0000-0000-0000-000000000002',true);
do $$ begin
 if exists(select 1 from public.team_updates) then raise exception 'Revoked user still has access'; end if;
end $$;
select set_config('request.jwt.claim.sub','10000000-0000-0000-0000-000000000003',true);
do $$ begin
 if exists(select 1 from public.team_projects) or exists(select 1 from public.team_updates) or exists(select 1 from public.team_members) then raise exception 'Cross-workspace data exposed'; end if;
end $$;
set local role anon;
do $$ begin
 begin
  perform * from public.team_projects;
  raise exception 'Anonymous read unexpectedly succeeded';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'PASS: owner create/read, author immutability, viewer read/write denial, member posting, spoof rejection, revocation, outsider isolation, anonymous denial. All test data rolled back.' as result;
rollback;
