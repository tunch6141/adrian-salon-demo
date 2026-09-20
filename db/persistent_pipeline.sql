-- Additive pipeline upgrade. Original functions and tables remain available.
begin;
alter table public.analyst_approval_log drop constraint if exists analyst_approval_log_kind_check;
alter table public.analyst_approval_log add constraint analyst_approval_log_kind_check
 check (kind in ('seed','correction','manual_sale','context','checkpoint_restore','automatic_import'));
create index if not exists analyst_approval_business_time on public.analyst_approval_log(business_id,approved_at desc);
create index if not exists analyst_versions_business_raw on public.analyst_clean_versions(business_id,raw_id);

create or replace function public.analyst_pipeline_ingest(p_business_id text,p_raw_id text,p_raw jsonb)
returns text language plpgsql security invoker set search_path='' as $$
begin
 if p_business_id is distinct from 'B001' or nullif(p_raw_id,'') is null
    or p_raw->>'format' is distinct from 'salon_raw_csv_v1'
    or jsonb_typeof(p_raw->'tables') is distinct from 'object' then raise exception 'Invalid raw batch'; end if;
 insert into public.analyst_raw_batches(business_id,raw_id,payload) values(p_business_id,p_raw_id,p_raw) on conflict do nothing;
 if not exists(select 1 from public.analyst_raw_batches where business_id=p_business_id and raw_id=p_raw_id and payload=p_raw)
 then raise exception 'Raw fingerprint conflict'; end if;
 return p_raw_id;
end $$;

create or replace function public.analyst_pipeline_current(p_business_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select public.analyst_dataset_read(h.business_id,h.version_id)
 from public.analyst_dataset_heads h where h.business_id=p_business_id;
$$;

create or replace function public.analyst_pipeline_publish(p_business_id text,p_expected_version uuid,p_raw_id text,
 p_snapshot jsonb,p_checkpoint jsonb,p_event_id uuid,p_actor text,p_kind text)
returns uuid language plpgsql security invoker set search_path='' as $$
declare current_version uuid; new_version uuid; prior jsonb; retry_version uuid; k text; delta jsonb='{}'::jsonb;
begin
 if p_business_id is distinct from 'B001' or nullif(trim(p_actor),'') is null or p_event_id is null then raise exception 'Invalid business or actor'; end if;
 if p_kind is null or p_kind not in ('seed','correction','manual_sale','context','checkpoint_restore','automatic_import') then raise exception 'Invalid event kind'; end if;
 if p_snapshot->>'format' is distinct from 'salon_canonical_v1' or jsonb_typeof(p_snapshot->'tables') is distinct from 'object'
 or p_snapshot->'tables'->'businesses'->0->>'business_id' is distinct from p_business_id
 or jsonb_typeof(p_snapshot->'issues') is distinct from 'array'
 or jsonb_typeof(p_snapshot->'audit') is distinct from 'array' then raise exception 'Invalid clean snapshot'; end if;
 if p_checkpoint->>'format' is distinct from 'piece1_owner_review_v1' then raise exception 'Invalid checkpoint'; end if;
 foreach k in array array['decisions','context','sales'] loop
  if jsonb_typeof(p_checkpoint->k) is distinct from 'array' then raise exception 'Invalid checkpoint list'; end if;
 end loop;
 perform pg_advisory_xact_lock(hashtextextended('analyst_dataset:'||p_business_id,0));
 select version_id into retry_version from public.analyst_approval_log where event_id=p_event_id and business_id=p_business_id;
 if retry_version is not null then
  if not exists(select 1 from public.analyst_clean_versions v join public.analyst_approval_log a using(version_id)
   where a.event_id=p_event_id and v.raw_id=p_raw_id and v.snapshot=p_snapshot and v.checkpoint=p_checkpoint
    and a.actor=p_actor and a.kind=p_kind and a.previous_version_id is not distinct from p_expected_version)
  then raise exception 'Conflicting retry payload'; end if;
  return retry_version;
 end if;
 select version_id into current_version from public.analyst_dataset_heads where business_id=p_business_id for update;
 if current_version is distinct from p_expected_version then raise exception 'Dataset changed since review' using errcode='40001'; end if;
 if not exists(select 1 from public.analyst_raw_batches where business_id=p_business_id and raw_id=p_raw_id) then raise exception 'Raw batch must be stored first'; end if;
 if current_version is null and p_kind<>'seed' then raise exception 'Initial import required'; end if;
 if current_version is not null and p_kind='seed' then raise exception 'Dataset already initialised'; end if;
 select checkpoint into prior from public.analyst_clean_versions where version_id=current_version;
 if p_kind='seed' and (p_checkpoint->'decisions'<>'[]'::jsonb or p_checkpoint->'sales'<>'[]'::jsonb or p_checkpoint->'context'<>'[]'::jsonb)
 then raise exception 'Seed cannot approve owner decisions'; end if;
 if p_kind='automatic_import' and p_checkpoint<>prior then raise exception 'Automatic import cannot approve new decisions'; end if;
 if p_kind not in ('seed','automatic_import') and not exists(select 1 from public.analyst_clean_versions where version_id=current_version and raw_id=p_raw_id)
 then raise exception 'Review must use the current raw batch'; end if;
 foreach k in array array['decisions','context','sales'] loop
  -- Prior decisions and amendments remain in order, even when another rule supersedes one.
  if exists(select 1 from jsonb_array_elements(coalesce(prior->k,'[]'::jsonb)) with ordinality old(value,n)
            where p_checkpoint->k->(old.n::int-1) is distinct from old.value)
  then raise exception 'Cannot erase or rewrite previous approvals'; end if;
  delta=delta||jsonb_build_object(k,coalesce((select jsonb_agg(value order by n)
       from jsonb_array_elements(p_checkpoint->k) with ordinality e(value,n)
       where n>jsonb_array_length(coalesce(prior->k,'[]'::jsonb))),'[]'::jsonb));
 end loop;
 insert into public.analyst_clean_versions(business_id,raw_id,snapshot,checkpoint)
 values(p_business_id,p_raw_id,p_snapshot,p_checkpoint) returning version_id into new_version;
 insert into public.analyst_approval_log(event_id,business_id,version_id,previous_version_id,actor,kind,details)
 values(p_event_id,p_business_id,new_version,current_version,p_actor,p_kind,jsonb_build_object(
  'changes',delta,'raw_id',p_raw_id,'cleaning_batch_id',p_snapshot->>'batch_id',
  'unresolved_issue_count',jsonb_array_length(p_snapshot->'issues'),
  'reused_rule_ids',coalesce((select jsonb_agg(distinct a->'approval'->>'rule_id')
   from jsonb_array_elements(p_snapshot->'audit') a where a->'approval'->>'rule_id' is not null),'[]'::jsonb),
  'approval_identity',case when p_kind in ('seed','automatic_import') then 'system_applied_rules' else 'self_reported_under_shared_demo_password' end));
 insert into public.analyst_dataset_heads(business_id,version_id) values(p_business_id,new_version)
 on conflict(business_id) do update set version_id=excluded.version_id;
 return new_version;
end $$;

create or replace function public.analyst_pipeline_history(p_business_id text)
returns jsonb language sql stable security invoker set search_path='' as $$
 select coalesce(jsonb_agg(to_jsonb(a) order by a.approved_at desc),'[]'::jsonb)
 from (select * from public.analyst_approval_log where business_id=p_business_id order by approved_at desc limit 100) a;
$$;

create or replace function public.analyst_prevent_history_mutation()
returns trigger language plpgsql security invoker set search_path='' as $$
begin raise exception 'Raw data, clean versions and approval history are append-only'; end $$;
drop trigger if exists analyst_raw_immutable on public.analyst_raw_batches;
create trigger analyst_raw_immutable before update or delete on public.analyst_raw_batches for each row execute function public.analyst_prevent_history_mutation();
drop trigger if exists analyst_versions_immutable on public.analyst_clean_versions;
create trigger analyst_versions_immutable before update or delete on public.analyst_clean_versions for each row execute function public.analyst_prevent_history_mutation();
drop trigger if exists analyst_approvals_immutable on public.analyst_approval_log;
create trigger analyst_approvals_immutable before update or delete on public.analyst_approval_log for each row execute function public.analyst_prevent_history_mutation();

alter table public.analyst_raw_batches enable row level security;
alter table public.analyst_clean_versions enable row level security;
alter table public.analyst_approval_log enable row level security;
alter table public.analyst_dataset_heads enable row level security;
revoke all on public.analyst_raw_batches,public.analyst_clean_versions,public.analyst_approval_log,public.analyst_dataset_heads from anon,authenticated;
revoke update,delete,truncate on public.analyst_raw_batches,public.analyst_clean_versions,public.analyst_approval_log from service_role;
grant select,insert on public.analyst_raw_batches,public.analyst_clean_versions,public.analyst_approval_log to service_role;
grant select,insert,update on public.analyst_dataset_heads to service_role;
revoke execute on function public.analyst_pipeline_ingest(text,text,jsonb),public.analyst_pipeline_current(text),
 public.analyst_pipeline_publish(text,uuid,text,jsonb,jsonb,uuid,text,text),public.analyst_pipeline_history(text),
 public.analyst_prevent_history_mutation() from public,anon,authenticated;
grant execute on function public.analyst_pipeline_ingest(text,text,jsonb),public.analyst_pipeline_current(text),
 public.analyst_pipeline_publish(text,uuid,text,jsonb,jsonb,uuid,text,text),public.analyst_pipeline_history(text) to service_role;
notify pgrst,'reload schema';
commit;
