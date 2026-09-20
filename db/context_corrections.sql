-- Extend the existing audited context store. Server-side access remains unchanged.
alter table public.business_context add column if not exists origin_id text;
alter table public.business_context add column if not exists change_reason text;
create unique index if not exists business_context_origin_unique
  on public.business_context(origin_id) where origin_id is not null;
notify pgrst, 'reload schema';
