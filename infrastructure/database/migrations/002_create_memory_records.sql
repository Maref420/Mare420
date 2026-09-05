create table if not exists memory_records (
    memory_id text primary key,
    memory_type text not null,
    created_at timestamptz not null,
    content jsonb not null,
    metadata jsonb not null,
    validation_status text not null,
    operation_id text not null,
    agent_id text not null
);

create index if not exists idx_memory_records_operation_id
    on memory_records (operation_id);

create index if not exists idx_memory_records_agent_id
    on memory_records (agent_id);

create index if not exists idx_memory_records_created_at
    on memory_records (created_at);

create index if not exists idx_memory_records_memory_type
    on memory_records (memory_type);

create index if not exists idx_memory_records_validation_status
    on memory_records (validation_status);
