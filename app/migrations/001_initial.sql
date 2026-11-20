-- 001_initial: full schema for the first release.
-- Conventions: integer ids, ISO-8601 UTC text timestamps, JSON stored as TEXT,
-- every tenant-owned row carries workspace_id and every query filters by it.

CREATE TABLE workspaces (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    default_language  TEXT NOT NULL DEFAULT 'English',
    timezone          TEXT NOT NULL DEFAULT 'UTC',
    away_message      TEXT NOT NULL DEFAULT '',
    business_hours    TEXT NOT NULL DEFAULT '{}',   -- {"mon":["09:00","18:00"], "sat":null, ...}
    llm_settings      TEXT NOT NULL DEFAULT '{}',   -- see services/settings.py LLM_DEFAULTS
    whatsapp_settings TEXT NOT NULL DEFAULT '{}',   -- see services/settings.py WHATSAPP_DEFAULTS
    agent_defaults    TEXT NOT NULL DEFAULT '{}',   -- see services/settings.py AGENT_DEFAULTS
    security_settings TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL
);

CREATE TABLE users (
    id             INTEGER PRIMARY KEY,
    workspace_id   INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('owner','admin','supervisor','viewer')),
    created_at     TEXT NOT NULL,
    last_active_at TEXT
);
CREATE INDEX idx_users_workspace ON users(workspace_id);

CREATE TABLE invites (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('admin','supervisor','viewer')),
    token        TEXT NOT NULL UNIQUE,
    invited_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    accepted_at  TEXT,
    UNIQUE (workspace_id, email)
);

CREATE TABLE agents (
    id             INTEGER PRIMARY KEY,
    workspace_id   INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    color          TEXT NOT NULL DEFAULT '#1F6FEB',
    instructions   TEXT NOT NULL DEFAULT '',
    model_override TEXT,                       -- JSON {"provider": "...", "model": "..."} or NULL
    active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);

CREATE TABLE provider_keys (
    id            INTEGER PRIMARY KEY,
    workspace_id  INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL CHECK (provider IN ('openai','anthropic','gemini','deepseek','qwen','openai_compatible')),
    api_key_enc   TEXT NOT NULL,               -- Fernet ciphertext, never returned by the API
    last4         TEXT NOT NULL,
    base_url      TEXT NOT NULL DEFAULT '',
    verified_at   TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (workspace_id, provider)
);

CREATE TABLE knowledge_files (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    kind         TEXT NOT NULL,                -- pdf, docx, xlsx, csv, txt, md, url, qa
    source_url   TEXT,
    stored_path  TEXT,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','indexing','ready','failed')),
    error        TEXT,
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX idx_kfiles_workspace ON knowledge_files(workspace_id);

CREATE TABLE agent_files (
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    file_id  INTEGER NOT NULL REFERENCES knowledge_files(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, file_id)
);
CREATE INDEX idx_agent_files_file ON agent_files(file_id);

CREATE TABLE chunks (
    id           INTEGER PRIMARY KEY,
    file_id      INTEGER NOT NULL REFERENCES knowledge_files(id) ON DELETE CASCADE,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    locator      TEXT NOT NULL DEFAULT '',     -- e.g. "p.2", "Sheet1", "section 3"
    text         TEXT NOT NULL
);
CREATE INDEX idx_chunks_file ON chunks(file_id);

CREATE TABLE wa_connections (
    id                INTEGER PRIMARY KEY,
    workspace_id      INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    provider          TEXT NOT NULL CHECK (provider IN ('evolution','meta_cloud','generic','sandbox')),
    phone_number      TEXT NOT NULL DEFAULT '',
    config_enc        TEXT NOT NULL DEFAULT '', -- Fernet(JSON) with provider credentials
    webhook_token     TEXT NOT NULL,            -- secret path segment for inbound webhooks
    status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','connected','disconnected','expired','error')),
    status_detail     TEXT NOT NULL DEFAULT '',
    default_agent_id  INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    default_mode      TEXT CHECK (default_mode IN ('auto','draft','off')),
    last_event_at     TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_conn_workspace ON wa_connections(workspace_id);

CREATE TABLE contacts (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    wa_id        TEXT NOT NULL,                -- phone number in international format, digits only
    name         TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '[]',
    opted_out    INTEGER NOT NULL DEFAULT 0 CHECK (opted_out IN (0,1)),
    created_at   TEXT NOT NULL,
    UNIQUE (workspace_id, wa_id)
);

CREATE TABLE chats (
    id                   INTEGER PRIMARY KEY,
    workspace_id         INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connection_id        INTEGER NOT NULL REFERENCES wa_connections(id) ON DELETE CASCADE,
    contact_id           INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    agent_id             INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    mode                 TEXT NOT NULL DEFAULT 'draft' CHECK (mode IN ('auto','draft','off')),
    handoff_active       INTEGER NOT NULL DEFAULT 0 CHECK (handoff_active IN (0,1)),
    rules                TEXT NOT NULL DEFAULT '{}', -- {"handoff":true,"business_hours_only":false,"match_language":true}
    unread_count         INTEGER NOT NULL DEFAULT 0,
    last_message_at      TEXT,
    last_message_preview TEXT NOT NULL DEFAULT '',
    last_away_sent_at    TEXT,
    created_at           TEXT NOT NULL,
    UNIQUE (connection_id, contact_id)
);
CREATE INDEX idx_chats_workspace_last ON chats(workspace_id, last_message_at);

CREATE TABLE messages (
    id                  INTEGER PRIMARY KEY,
    chat_id             INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    direction           TEXT NOT NULL CHECK (direction IN ('in','out','system')),
    author              TEXT NOT NULL CHECK (author IN ('customer','agent','human','system')),
    text                TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('received','draft','queued','sent','failed','discarded','note')),
    provider_message_id TEXT,
    agent_id            INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    user_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sources             TEXT NOT NULL DEFAULT '[]',
    error               TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_messages_chat ON messages(chat_id, id);
-- Dedupe provider retries: the same inbound provider id is stored once per chat.
CREATE UNIQUE INDEX uq_messages_provider ON messages(chat_id, provider_message_id)
    WHERE provider_message_id IS NOT NULL;

CREATE TABLE playground_sessions (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id     INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    title        TEXT NOT NULL DEFAULT 'New chat',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX idx_pg_sessions_user ON playground_sessions(user_id, updated_at);

CREATE TABLE playground_messages (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES playground_sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
    text       TEXT NOT NULL,
    sources    TEXT NOT NULL DEFAULT '[]',
    meta       TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_pg_messages_session ON playground_messages(session_id, id);

CREATE TABLE usage_events (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,                -- agent_reply, platform_tokens, byok_tokens
    amount       INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_usage_workspace_time ON usage_events(workspace_id, created_at);

CREATE TABLE audit_log (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT NOT NULL,
    target       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_audit_workspace ON audit_log(workspace_id, id);
