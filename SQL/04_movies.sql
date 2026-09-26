-- ====================================
-- TABLE: movies
-- ====================================
-- Movie catalog from TMDB API
-- Core table for semantic search and recommendations
-- Databricks SQL compatible version

CREATE TABLE IF NOT EXISTS movies (
    movie_id INT NOT NULL,
    title TEXT NOT NULL,
    overview TEXT,
    release_date DATE,
    runtime INT,
    tmdb_rating DECIMAL(2,1),
    vote_count INTEGER DEFAULT 0,
    
    -- Metadata for context and filtering (stored as JSONB)
    genres JSONB,
    cast JSONB,
    director TEXT,
    keywords JSONB,
    
    -- AI Semantic Search - CORE FEATURE
    -- Using BGE Large model from Databricks Foundation Models (1024 dimensions)
    -- Endpoint: databricks-bge-large-en
    embedding VECTOR(1024),
    
    created_at TIMESTAMPTZ DEFAULT now(),
    original_language TEXT
);

-- Primary key constraint
ALTER TABLE movies ADD CONSTRAINT movies_pk PRIMARY KEY (movie_id);

-- Performance optimization notes:
-- 1. For JSONB queries (genres, keywords), use:
--    SELECT * FROM movies WHERE genres @> '["Comedy"]'::jsonb;
--    SELECT * FROM movies WHERE keywords ? 'space';
-- 
-- 2. For vector similarity search on embeddings, use pgvector operators:
--    SELECT * FROM movies ORDER BY embedding <-> '[...]'::vector LIMIT 10;
--    (Cosine distance: <=>  |  L2 distance: <->  |  Inner product: <#>)
--
-- 3. Create indexes for better performance:
--    CREATE INDEX idx_movies_genres ON movies USING GIN (genres);
--    CREATE INDEX idx_movies_embedding ON movies USING ivfflat (embedding vector_cosine_ops);