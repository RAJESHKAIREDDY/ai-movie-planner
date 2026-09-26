# 🔀 Hybrid Search

**Status**: ✅ Fully Implemented  
**Backend Module**: `movie_mcp_server.py` → `semantic_search_movies()`  
**Builds on**: [SEMANTIC_SEARCH.md](./SEMANTIC_SEARCH.md)

---

## What Is Hybrid Search?

Semantic search (covered in the previous doc) finds movies by matching meaning using vector embeddings. Hybrid search takes that foundation and adds **structured intelligence** on top — it understands directors, actors, genres, runtime, language, and year constraints from your natural language query, then combines all those signals with vector similarity and TMDB ratings into one scored result.

In short: semantic search matches *meaning*. Hybrid search matches meaning *plus* your specific constraints.

---

## How the Algorithm Works

The `semantic_search_movies` function runs through 5 steps:

### Step 1: Understand Your Query

When you type something like "best Christopher Nolan sci-fi movies under 2 hours", the system needs to understand what you're actually asking for. It does two things:

**Quality detection**: Checks if you used words like "top", "best", "greatest", "classic", or "must watch". If so, it turns on quality mode — which applies stricter rating thresholds and shifts the scoring weights.

**Entity extraction**: An LLM (Meta Llama 3.3 70B) reads your query and extracts structured filters:
* Genres (only valid TMDB genres — Action, Sci-Fi, Comedy, etc.)
* Director name
* Actor name
* Maximum runtime (converts "under 2 hours" to 120 minutes)
* Language (converts "Hindi" to "hi", "Telugu" to "te")
* Year range (understands "recent" as last 2-3 years, "from 2023" as 2023-2023)

If the LLM call fails, a rule-based fallback kicks in using regex patterns to extract the same information.

### Step 2: Fetch Candidate Movies from TMDB

The system uses **4 parallel strategies** to gather a wide pool of candidate movies:

* **Strategy A — Direct title search**: Searches TMDB by the cleaned-up query text. Catches specific movie titles hidden in your prompt.
* **Strategy B — Person filmography**: If a director or actor was detected, fetches their full filmography from TMDB.
* **Strategy C — Genre discovery**: If genres were detected, fetches popular movies in those genres from TMDB.
* **Strategy D — Keyword discovery**: Searches TMDB keywords to find thematic matches (e.g., "boxing", "heist", "time travel").

All results are deduplicated by movie ID. This multi-strategy approach ensures candidates aren't missed even if one strategy fails.

### Step 3: Enrich the Database

Any candidate movie not already in the database (or missing an embedding) is fetched from TMDB in parallel, given a 1024-dimensional vector embedding using `databricks-bge-large-en`, and stored. This means the database grows smarter over time — movies searched once are cached for future searches.

### Step 4: Dynamic Hybrid Scoring

This is the core of the algorithm. Each movie in the candidate pool gets scored using a **weighted formula** that combines three signals:

* **Genre match score** — Does the movie contain the genres you asked for? Movies where your searched genre is the *primary* (first-listed) genre get the best score. Movies where it appears later get a penalty. This prevents an action film with a romance subplot from dominating a "romantic movies" search.
* **Semantic similarity** — How close the movie's vector embedding is to your query's vector embedding (1024 dimensions, cosine distance).
* **TMDB rating** — The movie's overall quality score from TMDB (out of 10).

The weights **shift dynamically** based on what you asked:

| Query Type | Genre | Semantic | Rating |
|---|---|---|---|
| Has genres + quality words ("best sci-fi") | 30% | 35% | 35% |
| Has genres, no quality words ("sci-fi movies") | 30% | 45% | 25% |
| No genres + quality words ("best movies") | 0% | 50% | 50% |
| No genres, no quality words ("time travel") | 0% | 70% | 30% |

This means: if you search for "best sci-fi movies", the system weights quality and genre heavily. If you search for "mind-bending thrillers", it leans more on semantic meaning since there's no explicit quality or genre filter.

On top of the scoring, structured filters are applied as hard constraints:
* Director filter — movie's director must match
* Actor filter — actor must appear in cast or overview
* Runtime filter — movie must be under your max runtime
* Language filter — movie must be in your requested language
* Year filter — movie must be released within your year range
* Watched movies excluded (if group context provided)
* Disliked movies excluded (if enabled)

### Step 5: Fallback Logic

If the strict metadata filters return zero results, the system **drops the strict filters** (director, actor, runtime, etc.) but keeps the preference filters (watched/disliked exclusions) and retries with pure semantic search. This ensures you always get results — even if your exact criteria can't be fully matched.

---

## Two Examples

### Example 1: Simple Semantic Search

**User says**: "movies about dreams and reality"

**What happens**: No genres detected, no director, no runtime, no quality keywords. The system converts the query to a 1024-dim vector and finds the closest movie vectors. Weights: 70% semantic, 30% rating.

**Results**:
1. **Inception** (similarity: 89%) - Dreams within dreams
2. **The Matrix** (similarity: 85%) - Reality is a simulation
3. **Waking Life** (similarity: 81%) - A man walks through a dream

This is pure semantic search — no structured filters, just meaning matching.

### Example 2: Hybrid Search with Constraints

**User says**: "best Christopher Nolan sci-fi movies under 2 hours"

**What happens**:
1. **Quality detected**: "best" triggers quality mode (TMDB rating ≥ 6.5, vote count ≥ 100).
2. **Entities extracted**: director = "Christopher Nolan", genres = ["Science Fiction"], max_runtime = 120 minutes.
3. **TMDB candidates fetched**: Strategy B (Nolan's filmography) + Strategy C (sci-fi genre discovery) = 35 candidates after deduplication.
4. **Database enriched**: Any new movies fetched, embedded, and cached.
5. **Filters applied**: Director must be Nolan, genre must include Sci-Fi, runtime must be ≤ 120 minutes, TMDB rating ≥ 6.5.
6. **Hybrid scoring**: Weights are 30% genre + 35% semantic + 35% rating. Genre primary match gives priority to movies where Sci-Fi is the first genre.
7. **Results ranked** by hybrid score.

**Results**:
1. **Inception** (score: 0.22) - Sci-Fi is primary genre, Nolan directed, 8.8 TMDB rating, 148 min runtime — *wait, 148 > 120, so this gets filtered out by the runtime constraint!*
2. **Tenet** (score: 0.28) - Sci-Fi primary, Nolan directed, 7.3 rating, 150 min — *also filtered out (150 > 120)*
3. **Interstellar** (score: 0.31) - Sci-Fi primary, Nolan directed, 8.4 rating, 169 min — *also filtered out*

Since all Nolan sci-fi films exceed 2 hours, the **fallback kicks in**: drops the runtime and director filters, keeps quality mode + sci-fi genre filter, and retries with pure semantic search.

**Fallback results**:
1. **Inception** (score: 0.22) - "No exact matches found for your specific criteria. Showing similar movies instead."
2. **Minority Report** (score: 0.35) - Sci-Fi primary, 7.6 rating, 145 min
3. **Looper** (score: 0.38) - Sci-Fi primary, 7.4 rating, 119 min — *this one actually fits under 2 hours!*

**Key difference**: Simple semantic search just matches meaning. Hybrid search understands your constraints, tries to match all of them, and gracefully falls back when it can't.

---

## Quality Mode

When you use words like "top", "best", "greatest", "classic", or "must watch", the system:
* Applies a minimum TMDB rating threshold (≥ 6.5/10)
* Applies a minimum vote count threshold (≥ 100 votes)
* Shifts scoring weights to give TMDB rating more influence (35-50% instead of 25-30%)

This ensures "best sci-fi movies" returns critically acclaimed films, not just any sci-fi movie.

---

## Genre Primary Match

When you search for a specific genre like "romantic movies", many action and thriller films have romance subplots. Without genre primary match, these would pollute your results.

The system checks if your searched genre is the **first-listed genre** for each movie:
* Primary genre match (e.g., Romance is listed first) → no penalty
* Secondary genre match (e.g., Romance appears but isn't first) → 0.5 penalty
* No genre match at all → 1.0 penalty

This penalty is weighted at 30% of the total score, so it significantly affects ranking.

---

## Backend Tool

All hybrid search logic lives in the backend (`movie_mcp_server.py`):

* **`semantic_search_movies`** - The full hybrid search engine (entity extraction, TMDB candidate fetching, database enrichment, dynamic scoring, fallback)
* **`extract_search_entities`** - LLM-powered query understanding with regex fallback
* **`_fetch_tmdb_candidates`** - The 4-strategy TMDB candidate fetcher
* **`search_movies`** - Simpler title-only search (no hybrid scoring, just TMDB keyword match)

The frontend only formats the structured response for display.

---

## How This Differs from Semantic Search

| Feature | Semantic Search | Hybrid Search |
|---|---|---|
| Matches meaning | ✅ | ✅ |
| Understands directors | ❌ | ✅ |
| Understands actors | ❌ | ✅ |
| Understands genres | ❌ | ✅ |
| Understands runtime | ❌ | ✅ |
| Understands language | ❌ | ✅ |
| Understands year ranges | ❌ | ✅ |
| Quality mode (top/best) | ❌ | ✅ |
| Genre primary match | ❌ | ✅ |
| TMDB rating scoring | ❌ | ✅ |
| Fallback logic | ❌ | ✅ |
| Database auto-enrichment | ❌ | ✅ |

Semantic search is the foundation. Hybrid search is the full engine built on top of it.

---

## Related Documentation

* **[SEMANTIC_SEARCH.md](./SEMANTIC_SEARCH.md)** - The foundation: vector embeddings, cosine similarity, pgvector
* **[RECOMMENDATIONS.md](./RECOMMENDATIONS.md)** - How hybrid search feeds into group recommendations
* **[TMDB_INTEGRATION.md](./TMDB_INTEGRATION.md)** - How movies are fetched from TMDB and cached with embeddings

