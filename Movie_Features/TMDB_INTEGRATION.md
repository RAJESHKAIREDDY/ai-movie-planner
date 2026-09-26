# 🎬 TMDB Integration

**Status**: ✅ Fully Implemented  
**Backend Module**: `movie_mcp_server.py`  
**External API**: [The Movie Database (TMDB)](https://www.themoviedb.org/)

---

## What Is TMDB Integration?

TMDB (The Movie Database) is the project's external data source for all movie information — titles, plots, genres, cast, directors, ratings, posters, trailers, and streaming availability. The system fetches movies from TMDB, enriches them with 1024-dimensional vector embeddings, and caches them in the database so future searches don't need to call the API again.

The database grows smarter over time. Every search that finds new movies automatically fetches, embeds, and stores them.

---

## How It Works

### Step 1: API Key Management

The TMDB API key is stored securely in Databricks secrets (not hardcoded in the code). On first use, the system retrieves it from the secrets store and caches it at the module level for the rest of the session. This means the key is fetched once per app startup, not on every API call.

### Step 2: Rate Limiting

TMDB's free tier allows 50 API calls per second. The system enforces a self-imposed limit of 40 calls per second using a sliding window rate limiter. This leaves headroom to avoid hitting the external limit and getting blocked.

If the rate limit is reached, the system automatically pauses and waits before making the next call — no errors are thrown, just a brief delay.

### Step 3: HTTP Session with Retry

All TMDB API calls go through a shared HTTP session with built-in resilience:
* **Connection pooling** — reuses TCP connections across calls for faster performance
* **Automatic retries** — up to 3 retries with exponential backoff (0.5s, 1s, 1.5s) on rate limit (429) and server errors (500, 502, 503, 504)
* **Timeouts** — 10 seconds per API call, 20-60 seconds for embedding generation

This means transient TMDB outages or rate limit spikes are handled automatically without failing the user's search.

### Step 4: Fetching Movie Details

When the system needs full information about a movie, it calls TMDB's movie endpoint with `append_to_response=credits,keywords,reviews,videos,watch/providers`. This single call returns:

* **Core info** — title, overview, release date, runtime, TMDB rating, vote count, original language
* **Cast** — top 5 billed actors
* **Director** — extracted from crew list
* **Genres** — list of TMDB genre names (Action, Sci-Fi, Comedy, etc.)
* **Keywords** — top 5 thematic tags (e.g., "time travel", "heist", "artificial intelligence")
* **Reviews** — top 3 user reviews (truncated to 300 characters)
* **Trailer** — YouTube trailer URL
* **Streaming providers** — where to watch (US region)
* **Poster path** — stored as a path, converted to full URL on display

### Step 5: Parallel Fetching

When multiple movies need to be fetched (e.g., 20-35 candidates from a search), the system uses asynchronous HTTP (aiohttp) to fetch them all in parallel rather than one at a time. This turns what would be 30 sequential API calls (~300ms each = 9 seconds total) into parallel calls that complete in about 1-2 seconds.

Failed fetches are silently dropped — if one movie out of 30 fails, the other 29 still get processed.

### Step 6: Embedding Generation

Once movie details are fetched, each movie needs a 1024-dimensional vector embedding for semantic search. The system uses Databricks BGE Large (`databricks-bge-large-en`) — a foundation model hosted on Databricks serving endpoints.

The text fed to the embedding model is: the movie's overview, followed by its genres and keywords. For example: "A hacker discovers reality is a simulation. Genres: Action, Sci-Fi. Keywords: simulation, artificial intelligence, dystopian."

Embeddings can be generated one at a time or in batches. Batch mode sends all movie texts in a single API call to the serving endpoint, which is much faster for 10+ movies.

### Step 7: Database Storage

Movies are stored in the `movies` table with all their details plus the 1024-dim embedding vector. The system uses two storage modes:

* **Single upsert** — for when one movie is added (e.g., when rating a movie). Uses ON CONFLICT DO UPDATE, so if the movie already exists, all fields are refreshed with the latest TMDB data.
* **Batch insert** — for when many movies are added at once (e.g., after a search). Uses ON CONFLICT DO NOTHING, so duplicates are silently skipped.

The database stores: movie_id, title, overview, release_date, runtime, tmdb_rating, vote_count, genres (as JSONB), cast (as JSONB), director, keywords (as JSONB), poster_path, embedding (as VECTOR(1024)), and original_language.

### Step 8: Poster URL Handling

TMDB returns just the poster path (e.g., `/abc123.jpg`), not the full URL. The system stores the path in the database and constructs the full URL (`https://image.tmdb.org/t/p/w500{path}`) when displaying to the user. If a poster path is missing from the database, the system fetches it from TMDB on demand and caches it for future use.

---

## The Caching Pipeline

The full flow from user search to cached movie:

1. User searches for movies
2. System checks which candidate movies are already in the database with embeddings
3. Missing movies are fetched from TMDB in parallel
4. Each new movie gets a 1024-dim embedding from BGE Large
5. All new movies are batch-inserted into the database
6. Future searches for the same movies skip TMDB entirely — they're cached locally with embeddings ready

This means the more the system is used, the faster it gets. Popular movies that are searched frequently are served entirely from the database with zero TMDB API calls.

---

## Seeding the Database

The `populate_movies_by_genre` tool lets you pre-populate the database with popular movies from a specific genre. This is useful before the system has been used much — it ensures common movies are already cached with embeddings when users start searching.

It fetches up to 20 popular movies per genre from TMDB's discover API, generates embeddings in batch, and inserts them all at once. Genres are mapped to TMDB genre IDs (e.g., Sci-Fi = 878, Action = 28, Comedy = 35).

---

## Backend Tools

All TMDB integration lives in the backend (`movie_mcp_server.py`):

* **`get_tmdb_api_key`** - Fetches and caches the API key from Databricks secrets
* **`search_tmdb_movies`** - Title search via TMDB API with similarity + popularity ranking
* **`get_tmdb_movie_details`** - Full movie details (cast, director, keywords, reviews, trailer, streaming)
* **`fetch_all_movie_details_parallel`** - Async parallel fetching of multiple movies
* **`generate_movie_embedding`** - Single 1024-dim embedding via BGE Large
* **`generate_embeddings_batch`** - Batch embeddings for multiple movies at once
* **`insert_movies_batch`** - Batch database insert with deduplication
* **`populate_movies_by_genre`** - Seed database with popular movies from a genre
* **`_upsert_movie`** - Single movie insert/update with latest TMDB data

The frontend never calls TMDB directly — it only displays what the backend returns.

---

## Rate Limits and Timeouts

| Setting | Value | Purpose |
|---|---|---|
| TMDB API rate limit | 40 calls/sec | Self-imposed (TMDB allows 50/sec) |
| TMDB API timeout | 10 seconds | Per API call |
| Embedding timeout (single) | 20 seconds | One movie embedding |
| Embedding timeout (batch) | 60 seconds | Multiple movie embeddings |
| Query embedding timeout | 30 seconds | User's search query embedding |
| HTTP retry attempts | 3 | With exponential backoff |
| LLM entity extraction timeout | 20 seconds | For query understanding |

---

## Two Examples

### Example 1: First-Time Search (Cold Cache)

**User says**: "best sci-fi movies about space exploration"

**What happens**:
1. LLM extracts entities: genres = ["Science Fiction"], quality mode = on.
2. TMDB candidate fetch: Strategy C (genre discovery) returns 20 sci-fi movies. Strategy D (keyword discovery for "space exploration") returns 15 more. After deduplication: 28 unique movies.
3. Database check: 3 movies already cached with embeddings. 25 movies are missing.
4. Parallel TMDB fetch: 25 movies fetched simultaneously via async HTTP (~2 seconds).
5. Batch embedding: 25 movies sent to BGE Large in one API call. 25 × 1024-dim vectors returned (~3 seconds).
6. Batch insert: All 25 movies inserted into the database with embeddings.
7. Hybrid scoring: All 28 movies (3 cached + 25 new) scored against the query.
8. Total time: ~8 seconds (first search). Future searches for these movies: ~0.5 seconds.

### Example 2: Repeat Search (Warm Cache)

**User says**: "best sci-fi movies about space exploration" (same query, next day)

**What happens**:
1. Same entity extraction and candidate fetch: 28 movies.
2. Database check: All 28 movies already cached with embeddings. Zero TMDB API calls needed.
3. Hybrid scoring: All 28 movies scored directly from database.
4. Total time: ~0.5 seconds.

**Key difference**: The first search pays the cost of fetching and embedding from TMDB. Every subsequent search for those movies is served entirely from the local database — no TMDB calls, no embedding generation, just vector similarity scoring.

---

## Related Documentation

* **[SEMANTIC_SEARCH.md](./SEMANTIC_SEARCH.md)** - How the 1024-dim embeddings are used for vector similarity search
* **[HYBRID_SEARCH.md](./HYBRID_SEARCH.md)** - How TMDB candidates are fetched via 4 strategies and scored with dynamic weights
* **[RECOMMENDATIONS.md](./RECOMMENDATIONS.md)** - How cached movie data feeds into group recommendations

---

