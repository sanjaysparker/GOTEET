create function public.remove_team_member(w uuid, member_user_id uuid) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not goteet_private.has_role(w,array['owner','admin']) then raise exception 'Workspace administrator required'; end if;
 if not exists(select 1 from public.team_members where workspace_id=w and user_id=member_user_id and role in ('member','viewer')) then raise exception 'Only member or viewer accounts can be removed'; end if;
 update public.team_tasks set assignee_id=null where workspace_id=w and assignee_id=member_user_id;
 delete from public.team_members where workspace_id=w and user_id=member_user_id;
end $$;
revoke all on function public.remove_team_member(uuid,uuid) from public;
grant execute on function public.remove_team_member(uuid,uuid) to authenticated;
insert into storage.buckets(id,name,public,file_size_limit) values('goteet-team-files','goteet-team-files',false,52428800);
create policy goteet_files_read on storage.objects for select to authenticated
using(bucket_id='goteet-team-files' and goteet_private.has_role(((storage.foldername(name))[1])::uuid,array['owner','admin','member','viewer']));
create policy goteet_files_insert on storage.objects for insert to authenticated
with check(bucket_id='goteet-team-files' and (storage.foldername(name))[2]=auth.uid()::text and goteet_private.has_role(((storage.foldername(name))[1])::uuid,array['owner','admin','member']));
-- Immutable objects; upload a new object for a new version. Owners can clean up team files.
create policy goteet_files_delete on storage.objects for delete to authenticated
using(bucket_id='goteet-team-files' and goteet_private.has_role(((storage.foldername(name))[1])::uuid,array['owner','admin']));
