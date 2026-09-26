-- ====================================
-- TABLE: recommendations
-- ====================================
-- AI agent recommendation history
-- Stores natural language requests and semantic matches
-- Lakebase Postgres compatible version

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    movie_id INT NOT NULL,
    requested_by TEXT,
    
    -- Natural language request and embedding
    request_context TEXT NOT NULL,
    request_embedding VECTOR(1024),
    
    -- Agent output
    explanation TEXT,
    recommendation_score DECIMAL(5,4),
    
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Primary key constraint
ALTER TABLE recommendations ADD CONSTRAINT recommendations_pk PRIMARY KEY (recommendation_id);

-- Comments
COMMENT ON TABLE recommendations IS 'AI agent recommendation history with semantic search capabilities';
COMMENT ON COLUMN recommendations.recommendation_id IS 'Unique recommendation identifier';
COMMENT ON COLUMN recommendations.group_id IS 'Group context for recommendation (FK: groups.group_id)';
COMMENT ON COLUMN recommendations.movie_id IS 'Recommended movie (FK: movies.movie_id)';
COMMENT ON COLUMN recommendations.requested_by IS 'User who requested the recommendation (FK: users.user_id)';
COMMENT ON COLUMN recommendations.request_context IS 'Natural language request from user (e.g., "a funny sci-fi movie under 2 hours")';
COMMENT ON COLUMN recommendations.request_embedding IS 'Vector embedding (1024 dims) of the request for semantic matching';
COMMENT ON COLUMN recommendations.explanation IS 'Why the agent recommended this movie';
COMMENT ON COLUMN recommendations.recommendation_score IS 'Agent confidence score (0.0-1.0)';
COMMENT ON COLUMN recommendations.created_at IS 'Recommendation creation timestamp';

-- Performance optimization indexes
CREATE INDEX idx_recommendations_group_movie ON recommendations(group_id, movie_id);
CREATE INDEX idx_recommendations_embedding ON recommendations USING ivfflat (request_embedding vector_cosine_ops);