CREATE TABLE IF NOT EXISTS atlas_memory (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    content JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    validation_status TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    source TEXT DEFAULT 'UNKNOWN_SOURCE',
    source_type TEXT DEFAULT 'UNKNOWN_TYPE',
    regime TEXT DEFAULT 'UNKNOWN_REGIME',
    evidence_refs JSONB DEFAULT '[]',
    epistemic_status TEXT DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_memory_type ON atlas_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_agent_id ON atlas_memory(agent_id);
CREATE INDEX IF NOT EXISTS idx_validation ON atlas_memory(validation_status);
