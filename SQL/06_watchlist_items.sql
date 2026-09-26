-- ====================================
-- TABLE: watchlist_items
-- ====================================
-- Group watchlist - movies the group wants to watch together
-- Lakebase Postgres compatible version

CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    movie_id INT NOT NULL,
    added_by TEXT,
    added_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'pending'
);

-- Primary key constraint
ALTER TABLE watchlist_items ADD CONSTRAINT watchlist_items_pk PRIMARY KEY (watchlist_id);

-- Unique constraint: Each movie can only appear once in a group's watchlist
ALTER TABLE watchlist_items ADD CONSTRAINT unique_watchlist UNIQUE (group_id, movie_id);

-- Comments
COMMENT ON TABLE watchlist_items IS 'Group watchlist - movies the group wants to watch together';
COMMENT ON COLUMN watchlist_items.watchlist_id IS 'Unique watchlist item identifier';
COMMENT ON COLUMN watchlist_items.group_id IS 'Which group this watchlist item belongs to (FK: groups.group_id)';
COMMENT ON COLUMN watchlist_items.movie_id IS 'Movie on the watchlist (FK: movies.movie_id)';
COMMENT ON COLUMN watchlist_items.added_by IS 'User who added this movie to the watchlist (FK: users.user_id)';
COMMENT ON COLUMN watchlist_items.added_at IS 'When movie was added to watchlist';
COMMENT ON COLUMN watchlist_items.status IS 'pending = not watched yet, watched = already watched';

-- Performance optimization indexes
CREATE INDEX idx_watchlist_group_status ON watchlist_items(group_id, status);
CREATE INDEX idx_watchlist_movie ON watchlist_items(movie_id);