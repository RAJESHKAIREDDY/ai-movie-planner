-- ====================================
-- TABLE: users
-- ====================================
-- Simple user identification (no authentication)
-- Users can create groups and rate movies
-- Run this manually in your Lakebase Postgres database before running the notebook

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Note: No additional indexes needed - UNIQUE constraints on username and email
-- automatically create unique indexes for lookups

-- Sample comment
COMMENT ON TABLE users IS 'User accounts for the AI Movie Night Planner';
COMMENT ON COLUMN users.user_id IS 'Unique user identifier';
COMMENT ON COLUMN users.username IS 'Unique username for display';
COMMENT ON COLUMN users.email IS 'User email address';