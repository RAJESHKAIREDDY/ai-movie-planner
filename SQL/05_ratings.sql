-- ====================================
-- TABLE: ratings
-- ====================================
-- User ratings within group context
-- CRITICAL: Same user can rate same movie differently in different groups
-- Lakebase Postgres compatible version

CREATE TABLE IF NOT EXISTS ratings (
    rating_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    movie_id INT NOT NULL,
    group_id TEXT NOT NULL,
    
    rating DECIMAL(3,1) NOT NULL,
    review_text TEXT,
    watched_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    
    -- Check constraint for rating range
    CONSTRAINT rating_range CHECK (rating >= 0 AND rating <= 10)
);

-- Primary key constraint
ALTER TABLE ratings ADD CONSTRAINT ratings_pk PRIMARY KEY (rating_id);

-- Unique constraint: One rating per user per movie per group
ALTER TABLE ratings ADD CONSTRAINT unique_rating UNIQUE (user_id, movie_id, group_id);

-- Comments
COMMENT ON TABLE ratings IS 'User movie ratings within group context - supports different ratings per group';
COMMENT ON COLUMN ratings.rating_id IS 'Unique rating identifier';
COMMENT ON COLUMN ratings.user_id IS 'User who gave the rating (FK: users.user_id)';
COMMENT ON COLUMN ratings.movie_id IS 'Movie being rated (FK: movies.movie_id)';
COMMENT ON COLUMN ratings.group_id IS 'Group context - same user can rate same movie differently in different groups (FK: groups.group_id)';
COMMENT ON COLUMN ratings.rating IS 'Rating value (0.0-10.0)';
COMMENT ON COLUMN ratings.review_text IS 'Optional text review';
COMMENT ON COLUMN ratings.watched_date IS 'When the group watched this movie';
COMMENT ON COLUMN ratings.created_at IS 'Rating creation timestamp';

-- Performance optimization indexes
CREATE INDEX idx_ratings_group_movie ON ratings(group_id, movie_id);
CREATE INDEX idx_ratings_user ON ratings(user_id);