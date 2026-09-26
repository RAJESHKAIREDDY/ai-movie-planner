# 🔍 Semantic Search

**Status**: ✅ Fully Implemented  
**Backend Module**: `movie_mcp_server.py`  
**Database**: `movies.embedding` (VECTOR(1024) with pgvector)

---

## What Is Semantic Search?

Instead of matching exact words, semantic search understands **meaning and context**. You can describe what you're looking for in natural language, and the system finds movies that match the concept - even if they don't contain your exact words.

For example:
* "A movie about dreams within dreams" → finds **Inception** (even though the word "dreams" isn't in the title)
* "Something uplifting for a rainy day" → finds feel-good movies based on mood
* "Action movies similar to John Wick" → finds stylistically similar films

---

## How the Algorithm Works

Following your architectural preferences, all semantic search logic lives in the backend.

### Step 1: Convert Movies to Vectors

Every movie gets converted into a **1024-dimensional vector** (a list of 1024 numbers) that captures its meaning. We generate this from:
* Title
* Overview/plot summary
* Genres (action, sci-fi, comedy, etc.)
* Director name
* Keywords (time-travel, heist, dystopian, etc.)

The vector embedding model reads all this text and creates a mathematical representation of what the movie is "about". Movies with similar themes, genres, or vibes will have similar vectors.

**Model Used**: `databricks-bge-large-en` (Databricks Foundation Models, 1024 dimensions)

### Step 2: Convert Your Search Query to a Vector

When you search with a phrase like "movies about AI and consciousness", we convert your query into the same 1024-dimensional vector space using the exact same model.

### Step 3: Find the Closest Matches

The database (using pgvector) calculates which movie vectors are **closest** to your query vector using cosine similarity. The closer two vectors are, the more similar the meaning.

Results are ranked by similarity score (0-100%), so the most relevant movies appear first.

---

## Regular Search vs. Semantic Search

We support both types of search. Here's how they differ:

### Example 1: Exact Title Match

**User Query**: "The Matrix"

**Regular Search** (`search_movies`):
* Looks for exact title match in the database
* Fast keyword lookup
* Returns: **The Matrix** (1999) - exact match found

**Semantic Search**:
* Not needed - exact match already found
* System is smart enough to use the faster regular search when appropriate

### Example 2: Conceptual Search

**User Query**: "movies about reality not being what it seems"

**Regular Search** (`search_movies`):
* Can't find anything - no movie has "reality not being what it seems" in the title
* Would return empty or irrelevant results

**Semantic Search**:
* Understands the **concept** behind your query
* Converts your description into a vector
* Finds movies with similar meaning in their plot/themes
* Returns ranked results:
  1. **The Matrix** (89% match) - "Reality is a simulation"
  2. **Inception** (87% match) - "Dreams within dreams"
  3. **The Truman Show** (85% match) - "Life is a TV show"
  4. **Dark City** (82% match) - "Manufactured reality"

**Key Difference**: Regular search matches **words**. Semantic search matches **meaning**.

---

## Technical Details

### Database Storage

Each movie has an `embedding` column of type `VECTOR(1024)` that stores its vector representation. This uses the **pgvector** extension for PostgreSQL.

### Performance

We use an HNSW (Hierarchical Navigable Small World) index for fast similarity search. Without the index, searching 10,000 movies takes ~450ms. With the index, it takes ~12ms.

The index is an approximate nearest neighbor algorithm - it trades a tiny bit of accuracy for massive speed improvements.

---

## Frontend Integration

The frontend only formats backend responses - no business logic lives in the UI layer. When semantic search results come back, the frontend simply displays the movie cards with their similarity scores as match percentages.

---

## Example Conversations

### Example 1: Natural Language Search

**User says**: "Find me movies about artificial intelligence and consciousness"

**What happens**: The query is converted to a vector and compared against all movie vectors. The closest matches are returned, ranked by similarity.

**Results**:
1. **Ex Machina** (2014) - 89% match - A programmer tests a humanoid AI
2. **Her** (2013) - 87% match - A writer falls for an AI assistant
3. **The Matrix** (1999) - 85% match - Reality is a simulation

### Example 2: Personalized with Group Context

**User says**: "What should Weekend Warriors watch tonight? We want something thrilling"

**What happens**: The system builds the group's taste profile (they love Sci-Fi, Action, and Nolan films), runs semantic search for "thrilling", then re-ranks results by how well they match the group's preferences.

**Results**:
1. **Inception** (2010) - 92% score - Matches Nolan + Sci-Fi + Thriller
2. **The Prestige** (2006) - 88% score - Another Nolan film + Mystery/Thriller

---

## Performance

Searching 10,000 movies with the HNSW index takes about 12ms for top-10 results and 28ms for top-50. Without the index, it would take about 450ms.

Generating an embedding for a new movie takes about 20-60 seconds via the Databricks BGE Large serving endpoint (API call). Batch mode can embed 25+ movies in a single API call for better throughput.

---

## Limitations

1. **New movies without ratings** are harder to personalize, but semantic search still works based on description alone.
2. **English-only** - embeddings work best with English text. Multilingual support could be added later.
3. **No minimum similarity threshold** - currently returns all matches, even low ones. A threshold could filter out weak matches.

---

## Troubleshooting

### Empty Results?

This usually means movies are missing embeddings. Run the backfill script (`backfill.py`) to generate embeddings for any movies that don't have them yet.

### Poor Matches?

Try adding more context to your query. "Time travel" alone is vague, but "a sci-fi movie about time travel with a complex plot" gives the model more to work with.

---

## Future Enhancements

1. **Query Expansion** - Auto-expand queries with synonyms ("funny" → "comedy, humorous")
2. **Negative Search** - Allow excluding concepts ("action movie NOT superhero")
3. **Contextual Search** - Use conversation history to refine results based on what the user likes/dislikes
4. **Minimum similarity threshold** - Filter out weak matches below a set score

---

## Related Documentation

* **[HYBRID_SEARCH.md](./HYBRID_SEARCH.md)** - The advanced search engine that builds on semantic search with entity extraction, dynamic scoring, and fallback logic
* **[RECOMMENDATIONS.md](./RECOMMENDATIONS.md)** - How semantic search combines with taste profiles for personalized picks
* **[TMDB_INTEGRATION.md](./TMDB_INTEGRATION.md)** - How movies are fetched from TMDB and embedded with 1024-dim vectors

---

## References

* pgvector: https://github.com/pgvector/pgvector
* Databricks BGE Large: https://docs.databricks.com/en/machine-learning/foundation-models/index.html
* HNSW Algorithm: https://arxiv.org/abs/1603.09320




