-- Database schema for metrics tracking
-- Supports tracking token usage and costs at message, session, and project levels

-- Message-level metrics table
-- Stores individual API call metrics
CREATE TABLE IF NOT EXISTS message_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    session_id TEXT,
    project_id TEXT,
    
    -- Model information
    model_id TEXT NOT NULL,
    
    -- Token counts
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    
    -- Cost information (in USD)
    estimated_cost REAL NOT NULL DEFAULT 0.0,
    actual_cost REAL,  -- From /api/v1/generation endpoint
    
    -- OpenRouter generation ID for precise cost lookup
    generation_id TEXT,
    
    -- Timing information
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    response_time_ms INTEGER,
    
    -- Additional metadata
    stop_reason TEXT,
    tool_calls_count INTEGER DEFAULT 0,
    
    FOREIGN KEY (session_id) REFERENCES session_metrics(session_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES project_metrics(project_id) ON DELETE CASCADE
);

-- Session-level metrics table
-- Aggregates metrics for a conversation session
CREATE TABLE IF NOT EXISTS session_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    project_id TEXT,
    
    -- Aggregated token counts
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    
    -- Aggregated costs
    total_estimated_cost REAL NOT NULL DEFAULT 0.0,
    total_actual_cost REAL,
    
    -- Session information
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Session metadata
    models_used TEXT,  -- JSON array of model IDs used
    
    FOREIGN KEY (project_id) REFERENCES project_metrics(project_id) ON DELETE CASCADE
);

-- Project-level metrics table
-- Aggregates metrics for an entire project
CREATE TABLE IF NOT EXISTS project_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT UNIQUE NOT NULL,
    
    -- Aggregated token counts
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    
    -- Aggregated costs
    total_estimated_cost REAL NOT NULL DEFAULT 0.0,
    total_actual_cost REAL,
    
    -- Project information
    session_count INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Project metadata
    name TEXT,
    description TEXT
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_message_session ON message_metrics(session_id);
CREATE INDEX IF NOT EXISTS idx_message_project ON message_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_message_created ON message_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_message_model ON message_metrics(model_id);
CREATE INDEX IF NOT EXISTS idx_message_generation ON message_metrics(generation_id);

CREATE INDEX IF NOT EXISTS idx_session_project ON session_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_session_created ON session_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_session_updated ON session_metrics(updated_at);

CREATE INDEX IF NOT EXISTS idx_project_created ON project_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_project_updated ON project_metrics(updated_at);
