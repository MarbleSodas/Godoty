-- Schema for metrics tracking (Source of Truth: backend/database/models.py)

CREATE TABLE IF NOT EXISTS project_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL UNIQUE,
    total_prompt_tokens INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_estimated_cost REAL DEFAULT 0.0,
    total_actual_cost REAL,
    session_count INTEGER DEFAULT 0,
    call_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    name TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS session_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    project_id TEXT,
    total_prompt_tokens INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_estimated_cost REAL DEFAULT 0.0,
    total_actual_cost REAL,
    call_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    models_used TEXT,
    FOREIGN KEY(project_id) REFERENCES project_metrics(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS api_call_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL UNIQUE,
    session_id TEXT,
    project_id TEXT,
    message_id TEXT,
    agent_type TEXT,
    model_id TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0.0,
    actual_cost REAL,
    generation_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stop_reason TEXT,
    tool_calls_count INTEGER DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES session_metrics(session_id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES project_metrics(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_call_metrics_session_id ON api_call_metrics(session_id);
CREATE INDEX IF NOT EXISTS idx_api_call_metrics_project_id ON api_call_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_api_call_metrics_created_at ON api_call_metrics(created_at);