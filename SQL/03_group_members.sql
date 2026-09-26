-- ====================================
-- TABLE: group_members
-- ====================================
-- Maps users to groups (many-to-many relationship)
-- Lakebase Postgres compatible version

CREATE TABLE IF NOT EXISTS group_members (
    membership_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT now()
);

-- Primary key constraint
ALTER TABLE group_members ADD CONSTRAINT group_members_pk PRIMARY KEY (membership_id);

-- Unique constraint: Each user can only be in a group once
ALTER TABLE group_members ADD CONSTRAINT unique_member UNIQUE (group_id, user_id);

-- Comments
COMMENT ON TABLE group_members IS 'Group membership - links users to groups (many-to-many relationship)';
COMMENT ON COLUMN group_members.membership_id IS 'Unique membership identifier';
COMMENT ON COLUMN group_members.group_id IS 'Reference to the group (FK: groups.group_id)';
COMMENT ON COLUMN group_members.user_id IS 'Reference to the user (FK: users.user_id)';
COMMENT ON COLUMN group_members.joined_at IS 'When user joined the group';

-- Performance optimization indexes
CREATE INDEX idx_group_members_group ON group_members(group_id);
CREATE INDEX idx_group_members_user ON group_members(user_id);