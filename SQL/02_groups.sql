-- ====================================
-- TABLE: groups
-- ====================================
-- Movie night groups where users watch movies together
-- Lakebase Postgres compatible version

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT NOT NULL,
    group_name TEXT NOT NULL,
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Primary key constraint
ALTER TABLE groups ADD CONSTRAINT groups_pk PRIMARY KEY (group_id);

-- Comments
COMMENT ON TABLE groups IS 'Movie night groups where users watch movies together';
COMMENT ON COLUMN groups.group_id IS 'Unique group identifier';
COMMENT ON COLUMN groups.group_name IS 'Name of the movie night group';
COMMENT ON COLUMN groups.description IS 'Optional description of the group purpose';
COMMENT ON COLUMN groups.created_by IS 'User who created the group (FK: users.user_id)';
COMMENT ON COLUMN groups.created_at IS 'Group creation timestamp';
COMMENT ON COLUMN groups.is_active IS 'Whether the group is currently active';

-- Create index for foreign key lookups
CREATE INDEX idx_groups_created_by ON groups(created_by);