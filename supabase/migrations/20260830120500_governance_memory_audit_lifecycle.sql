-- Governance Memory + Audit Lifecycle Enforcement
-- Governed by:
-- - contracts/schemas/memory/memory-contract-v1.json
-- - contracts/schemas/audit/audit-storage-v1.json
-- - governance/policies/memory/lifecycle-policy.yaml

create extension if not exists pgcrypto;

create table if not exists memory_records (
    memory_id text primary key,
    memory_type text not null check (
        memory_type in ('working', 'episodic', 'semantic', 'procedural')
    ),
    created_at timestamptz not null,
    content jsonb not null,
    metadata jsonb not null default '{}',
    validation_status text not null check (validation_status = 'validated'),
    operation_id text not null,
    agent_id text not null
);

create index if not exists idx_memory_records_type
    on memory_records(memory_type);

create index if not exists idx_memory_records_agent
    on memory_records(agent_id);

create index if not exists idx_memory_records_created_at
    on memory_records(created_at);

create index if not exists idx_memory_records_working_expires_at
    on memory_records((metadata->>'expires_at'))
    where memory_type = 'working';

create table if not exists audit_events (
    event_id uuid primary key default gen_random_uuid(),
    contract_version text not null,
    event_type text not null,
    operation_id text not null,
    agent_id text not null,
    timestamp timestamptz not null default now(),
    action text not null,
    resource text not null,
    result text not null,
    metadata jsonb not null default '{}'
);

create or replace function forbid_audit_events_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'audit_events is immutable: UPDATE/DELETE forbidden by governance';
end;
$$;

drop trigger if exists trg_forbid_audit_events_update on audit_events;
create trigger trg_forbid_audit_events_update
before update on audit_events
for each row execute function forbid_audit_events_mutation();

drop trigger if exists trg_forbid_audit_events_delete on audit_events;
create trigger trg_forbid_audit_events_delete
before delete on audit_events
for each row execute function forbid_audit_events_mutation();
