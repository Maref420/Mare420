create table if not exists audit_events (
    event_id uuid primary key,
    contract_version text not null,
    event_type text not null,
    operation_id text not null,
    agent_id text not null,
    timestamp timestamptz not null,
    action text not null,
    resource text not null,
    result text not null,
    metadata jsonb not null
);

create index if not exists idx_audit_events_operation_id
    on audit_events (operation_id);

create index if not exists idx_audit_events_agent_id
    on audit_events (agent_id);

create index if not exists idx_audit_events_timestamp
    on audit_events (timestamp);

revoke update, delete on audit_events from anon, authenticated;
