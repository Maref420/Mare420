alter table public.audit_events
    alter column event_id type text
    using event_id::text;

alter table public.audit_events
    enable row level security;

revoke all on public.audit_events from anon, authenticated;

grant insert on public.audit_events to service_role;
