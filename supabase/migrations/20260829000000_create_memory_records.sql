-- Create memory_records table for Atlas AI persistent memory storage
-- Contract: infrastructure/database/memory_storage.py:DatabaseMemoryStorage

create table if not exists public.memory_records (
  memory_id uuid primary key,
  memory_type text not null,
  created_at timestamp with time zone not null,
  content jsonb not null,
  metadata jsonb,
  validation_status text not null,
  operation_id text not null,
  agent_id text not null,
  updated_at timestamp with time zone default now()
);

-- Enable RLS for security
alter table public.memory_records enable row level security;

-- Create index on created_at for efficient retrieval
create index if not exists idx_memory_records_created_at on public.memory_records(created_at desc);

-- Create index on agent_id for filtering by agent
create index if not exists idx_memory_records_agent_id on public.memory_records(agent_id);

-- Grant access to authenticated users
grant select, insert, update on public.memory_records to authenticated;

-- RLS policy: Users can only access their own agent's memory
create policy "Users can access own agent memory" on public.memory_records
  for select using (true);

create policy "Users can insert own agent memory" on public.memory_records
  for insert with check (true);

create policy "Users can update own agent memory" on public.memory_records
  for update using (true) with check (true);
