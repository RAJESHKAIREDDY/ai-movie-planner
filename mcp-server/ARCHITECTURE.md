# AI Movie Planner - Architecture

## System Overview

The AI Movie Planner is a Databricks App that combines multiple AI technologies to provide intelligent movie recommendations through natural language interaction.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Browser                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Streamlit Frontend                         │
│                    (frontend.py)                             │
│  • Chat UI                                                   │
│  • Session management                                        │
│  • Result formatting                                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM Agent Router                          │
│              (Meta Llama 3.3 70B)                            │
│  • Query understanding                                       │
│  • Tool selection                                            │
│  • Context extraction (groups, movies)                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                FastMCP Server Layer                          │
│               (movie_mcp_server.py)                          │
│  • 12 MCP tools                                              │
│  • Input validation                                          │
│  • Error handling                                            │
└─────┬──────────────────┬─────────────────┬─────────────────┘
      │                  │                 │
      ▼                  ▼                 ▼
┌──────────┐  ┌────────────────┐  ┌──────────────┐
│   TMDB   │  │   Lakebase     │  │ SQL Warehouse│
│   API    │  │   PostgreSQL   │  │  (AI_QUERY)  │
│          │  │                │  │              │
│ 700K+    │  │ • Movies       │  │ • Embeddings │
│ Movies   │  │ • Groups       │  │ • Semantic   │
│          │  │ • Watchlists   │  │   Search     │
│          │  │ • Ratings      │  │              │
└──────────┘  └────────────────┘  └──────────────┘
```

## Component Details

### 1. Frontend Layer (frontend.py)

**Purpose**: User interface and agent orchestration

**Key Functions**:
* `agent_loop(user_query)` - Main query processing pipeline
* `build_dynamic_tool_descriptions()` - Builds tool manifest from MCP server
* `call_tool(tool_name, args)` - Invokes MCP tools
* `format_response(result)` - Formats tool results for display

**Technologies**:
* Streamlit 1.36.0 for UI
* Databricks Model Serving for LLM routing
* Session state management

**Flow**:
1. User types query → Streamlit captures input
2. Query sent to LLM router with tool manifest
3. LLM decides which tool to call + extracts arguments
4. Tool validation (resolve group names, movie titles)
5. Tool execution via MCP
6. Result formatting + display

### 2. LLM Router

**Purpose**: Intelligent query routing and context extraction

**Model**: Meta Llama 3.3 70B Instruct
**Temperature**: 0.1 (low for deterministic routing)
**Max Tokens**: 300

**Responsibilities**:
1. **Tool Selection**: Choose 1 of 12 tools based on user intent
2. **Context Extraction**:
   * Multi-word group names ("Friday Night Flicks")
   * Movie titles with year
   * Ratings, preferences, filters
3. **Placeholder Prevention**: Never return MISSING_MOVIE, MISSING_GROUP
4. **Workflow Understanding**: "recommend" → search first, then save

**Router Prompt Structure**:
```
Available Tools: <12 tool descriptions>
User Query: "<user input>"

Rules:
- Extract multi-word group names
- Resolve movie titles
- Follow recommendation workflow
- Never use placeholders

Output: JSON
{
  "tool": "semantic_search_movies",
  "arguments": {"query": "thriller", "limit": 5}
}
```

### 3. FastMCP Server (movie_mcp_server.py)

**Purpose**: Expose 12 tools via Model Context Protocol

**MCP Tools**:

| Tool | Input | Output | Data Source |
|------|-------|--------|-------------|
| search_movies | query, limit | List[Movie] | TMDB API |
| semantic_search_movies | query, limit | List[Movie] | SQL Warehouse + Lakebase |
| get_movie_details | movie_id | Movie | TMDB API |
| get_trending_movies | limit | List[Movie] | Lakebase |
| create_group | group_name | Group | Lakebase |
| list_my_groups | - | List[Group] | Lakebase |
| get_group_by_name | group_name | Group | Lakebase |
| get_group_members | group_id | List[Member] | Lakebase |
| add_to_watchlist | group_id, movie_id | Status | Lakebase |
| get_watchlist | group_id | List[Movie] | Lakebase |
| rate_movie | group_id, movie_id, rating | Status | Lakebase |
| save_group_recommendation | group_id, movie_id, reason | Status | Lakebase |

**Key Features**:
* Retry logic for TMDB API (3 attempts, exponential backoff)
* Connection pooling for Lakebase
* Structured error responses
* Logging for debugging

### 4. Data Layer

#### TMDB API
* **Purpose**: External movie data source
* **Rate Limit**: 40 requests / 10 seconds
* **Authentication**: API key in Databricks secrets
* **Endpoints Used**:
  * `/3/search/movie` - Search by title
  * `/3/movie/{id}` - Movie details
  * `/3/movie/{id}/credits` - Cast & crew

#### Lakebase PostgreSQL
* **Purpose**: Persistent data storage
* **Connection**: psycopg2 with connection pooling
* **Tables**:

```sql
-- Users
users (
  user_id VARCHAR PRIMARY KEY,  -- Email address
  username VARCHAR,
  email VARCHAR UNIQUE,
  created_at TIMESTAMP
)

-- Movies from TMDB with embeddings
movies (
  movie_id INTEGER PRIMARY KEY,  -- TMDB ID
  title VARCHAR(255),
  overview TEXT,
  release_date DATE,
  runtime INTEGER,
  tmdb_rating DECIMAL(3,1),
  genres JSONB,  -- JSONB array (not ARRAY)
  cast JSONB,    -- JSONB array (not ARRAY)
  director VARCHAR,
  keywords JSONB,  -- JSONB array (not ARRAY)
  embedding VECTOR(1024),  -- Vector with HNSW index
  original_language VARCHAR
)
CREATE INDEX movies_embedding_idx ON movies USING hnsw (embedding vector_cosine_ops);

-- User groups
groups (
  group_id VARCHAR PRIMARY KEY,  -- Generated ID
  group_name VARCHAR(255),
  description TEXT,
  created_by VARCHAR REFERENCES users(user_id),
  created_at TIMESTAMP,
  is_active BOOLEAN
)

-- Group memberships
group_members (
  membership_id VARCHAR PRIMARY KEY,  -- Generated ID
  group_id VARCHAR REFERENCES groups,
  user_id VARCHAR REFERENCES users(user_id),
  joined_at TIMESTAMP
)

-- Watchlists
watchlist_items (
  watchlist_id VARCHAR PRIMARY KEY,  -- Generated ID
  group_id VARCHAR REFERENCES groups,
  movie_id INTEGER REFERENCES movies,
  added_by VARCHAR REFERENCES users(user_id),
  status VARCHAR,  -- 'pending' or 'watched'
  added_at TIMESTAMP,
  UNIQUE (group_id, movie_id)
)

-- Ratings
ratings (
  rating_id VARCHAR PRIMARY KEY,  -- Generated ID
  group_id VARCHAR REFERENCES groups,
  movie_id INTEGER REFERENCES movies,
  user_id VARCHAR REFERENCES users(user_id),
  rating INTEGER CHECK (rating BETWEEN 1 AND 10),
  review_text TEXT,
  created_at TIMESTAMP,
  UNIQUE (user_id, movie_id, group_id)
)

-- Recommendations
recommendations (
  recommendation_id VARCHAR PRIMARY KEY,  -- Generated ID
  group_id VARCHAR REFERENCES groups,
  movie_id INTEGER REFERENCES movies,
  requested_by VARCHAR REFERENCES users(user_id),
  explanation TEXT,
  request_context TEXT,
  request_embedding VECTOR(1024),
  recommendation_score DECIMAL(3,2),
  created_at TIMESTAMP
)
```

**Key Schema Notes:**
- `genres`, `cast`, `keywords` are **JSONB** (not ARRAY) for flexible JSON storage
- `embedding` fields use **VECTOR(1024)** type with HNSW index for fast semantic search
- All FKs have `ON UPDATE CASCADE ON DELETE CASCADE`
- See SCHEMA.md for complete ERD diagram

#### SQL Warehouse (AI_QUERY)
* **Purpose**: Generate embeddings for semantic search
* **Model**: databricks-bge-large-en (Beijing General Embedding)
* **Dimension**: 1024
* **Function**: `AI_QUERY('databricks-bge-large-en', 'text', returnType => 'ARRAY<DOUBLE>')`

**Semantic Search Process**:
1. User query: "romantic thriller"
2. Generate embedding via AI_QUERY → [0.234, -0.567, ...] (1024 floats)
3. Compare to all movie embeddings using cosine similarity
4. Return top N most similar movies

**Cosine Similarity Formula**:
```
similarity = (A · B) / (||A|| * ||B||)

Where:
A = query embedding
B = movie embedding
· = dot product
|| || = magnitude
```

## Data Flow Examples

### Example 1: Semantic Search

```
User: "recommend a romantic movie for Friday Night Flicks"
  ↓
LLM Router:
  tool: "semantic_search_movies"
  args: {query: "romantic movie", limit: 5}
  ↓
Frontend Validation:
  - Resolve "Friday Night Flicks" → UUID (group_id)
  ↓
MCP Tool: semantic_search_movies
  ↓
SQL Warehouse AI_QUERY:
  "romantic movie" → [0.12, -0.45, 0.89, ...] (1024 floats)
  ↓
Lakebase Query:
  SELECT m.*, 
         cosine_similarity(e.embedding, ARRAY[0.12, -0.45, ...]) AS score
  FROM movies m
  JOIN movie_embeddings e ON m.movie_id = e.movie_id
  ORDER BY score DESC
  LIMIT 5
  ↓
Results:
  1. The Notebook (2004) - Score: 0.92
  2. La La Land (2016) - Score: 0.89
  3. Pride & Prejudice (2005) - Score: 0.87
  ...
  ↓
Frontend: Format + Display
```

### Example 2: Add to Watchlist

```
User: "add Inception to Movie Club"
  ↓
LLM Router:
  tool: "add_to_watchlist"
  args: {group_id: "Movie Club", movie_id: "Inception"}
  ↓
Frontend Validation:
  - Resolve "Movie Club" → UUID
  - Resolve "Inception" → TMDB ID (27205)
  ↓
MCP Tool: add_to_watchlist
  ↓
Lakebase INSERT:
  INSERT INTO watchlist (group_id, movie_id, added_by, added_at)
  VALUES ('uuid...', 27205, 'user@example.com', NOW())
  ↓
Frontend: "✅ Added Inception to Movie Club"
```

## Security

### Authentication
* **App-level**: Databricks OAuth2 (user authentication)
* **Service Principal**: App runs as service principal for backend access
* **Secrets**: TMDB API key, Lakebase URL stored in Databricks secrets

### Authorization
* **SQL Warehouse**: Service principal needs "Can use" permission
* **Lakebase**: Connection string includes credentials
* **User Context**: `get_current_user()` from Databricks identity

### Data Isolation
* Groups are user-scoped (created_by = current user)
* Watchlists and ratings are group-scoped
* No cross-group data access

## Performance Optimizations

### 1. Connection Pooling
* psycopg2 connection pool (min=2, max=10 connections)
* Reuse connections across requests

### 2. Caching (Future)
* Cache frequent queries (trending movies)
* Cache embeddings (already generated)
* Cache TMDB responses (24h TTL)

### 3. Batch Operations
* Bulk insert for watchlist items
* Batch embedding generation for new movies

### 4. SQL Warehouse Warm-up
* Keep warehouse running during active hours
* Auto-stop after 10 min idle

## Error Handling

### Retry Logic
* TMDB API: 3 attempts with exponential backoff
* Lakebase: 2 attempts with 1s delay
* AI_QUERY: 3 attempts with 2s delay

### Graceful Degradation
* If semantic search fails → fallback to title search
* If TMDB API fails → use cached data
* If group not found → list available groups

### Logging
* INFO: Successful operations, performance metrics
* WARNING: Placeholders detected, missing data
* ERROR: API failures, database errors

**Log Format**:
```
[2026-01-09 10:30:45] INFO: 🔍 Routing user query: 'recommend...'
[2026-01-09 10:30:46] INFO: 🛠️  Selected tool: semantic_search_movies
[2026-01-09 10:30:48] INFO: ✅ Query embedding generated (1024 dims)
[2026-01-09 10:30:49] INFO: ✅ Found 5 matching movies
```

## Deployment

### Compute
* **Type**: Serverless (Medium)
* **Auto-scaling**: Yes
* **Cold start**: ~30 seconds

### Environment
* **Python**: 3.11
* **Dependencies**: See requirements.txt
* **Secrets**: 2 (tmdb-api-key, lakebase-url)

### Monitoring
* App logs in Databricks Apps console
* Filter by: [APP], [BUILD], or by severity
* Real-time log tailing available

## Testing Strategy

### Unit Tests (test_frontend.py)
* UUID validation
* Placeholder detection
* Group name extraction
* JSON serialization

### Integration Tests (test_smoke.py)
* End-to-end workflow
* TMDB API connection
* Semantic search
* Watchlist operations

### Manual Testing
* Real-time query testing with logs
* Edge case validation
* Performance benchmarking

## Future Architecture Enhancements

### 1. Caching Layer
```
Redis/Memcached
  ↓
Current Architecture
```

### 2. Analytics Pipeline
```
App Events → Delta Table → Dashboard
```

### 3. ML Personalization
```
User History → ML Model → Personalized Recommendations
```

### 4. Notification Service
```
Watchlist Changes → Event Queue → Notification Service
```

---

*For more details, see:*
* [README.md](./README.md) - Setup and usage
* [SEARCH_EXPLAINED.md](./SEARCH_EXPLAINED.md) - Semantic search details
* [TEST_README.md](./TEST_README.md) - Testing guide
