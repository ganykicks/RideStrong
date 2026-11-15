-- RideStrong cloud workout progress. Run once in the Supabase SQL Editor.
-- User-specific RLS; publishable key can be safely used in browser only with RLS.
create table if not exists public.ride_progress (
  user_id uuid not null references auth.users(id) on delete cascade,
  workout_date date not null,
  status text not null check (status in ('done','skip','deleted')),
  reason text not null default '' check (char_length(reason) <= 120),
  client_updated_at timestamptz not null,
  primary key (user_id, workout_date)
);

alter table public.ride_progress enable row level security;
revoke all on public.ride_progress from anon, authenticated;
grant select, insert, update on public.ride_progress to authenticated;

drop policy if exists "RideStrong owner select" on public.ride_progress;
create policy "RideStrong owner select"
on public.ride_progress for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "RideStrong owner insert" on public.ride_progress;
create policy "RideStrong owner insert"
on public.ride_progress for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "RideStrong owner update" on public.ride_progress;
create policy "RideStrong owner update"
on public.ride_progress for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

-- Atomic last-update-wins merge prevents a stale device from overwriting
-- a newer record, including a cleared record (the 'deleted' tombstone).
create or replace function public.ride_progress_merge(
  p_date date,
  p_status text,
  p_reason text,
  p_updated_at timestamptz
) returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if (select auth.uid()) is null then
    raise exception 'Sign in to synchronize workout progress';
  end if;
  if p_date < date '2026-11-15' or p_date > date '2032-01-01'
     or p_status not in ('done','skip','deleted')
     or p_updated_at is null or char_length(coalesce(p_reason,'')) > 120 then
    raise exception 'Invalid RideStrong workout record';
  end if;
  insert into public.ride_progress
    (user_id, workout_date, status, reason, client_updated_at)
  values
    ((select auth.uid()),p_date,p_status,coalesce(p_reason,''),p_updated_at)
  on conflict (user_id, workout_date)
  do update set
    status = excluded.status,
    reason = excluded.reason,
    client_updated_at = excluded.client_updated_at
  where excluded.client_updated_at > public.ride_progress.client_updated_at;
end
$$;

revoke execute on function public.ride_progress_merge(date,text,text,timestamptz) from public, anon;
grant execute on function public.ride_progress_merge(date,text,text,timestamptz) to authenticated;
