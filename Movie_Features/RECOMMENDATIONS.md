# 🎯 Recommendations

**Status**: ✅ Fully Implemented  
**Backend Module**: `movie_mcp_server.py`  
**Database**: Ratings, watchlist, and movie embeddings (VECTOR(1024))

---

## What Are Recommendations?

The system analyzes what your group has watched and how they rated it, then suggests new movies that match your group's taste. Every recommendation comes with an explanation of **why** it was picked.

There are two types of recommendations, each built differently:

---

## How the Algorithm Works

### Type 1: Group Recommendations

When you ask "Recommend movies for my group", the system goes through 5 steps:

**Step 1 - Find what the group likes**: Looks at all group ratings. Movies rated 3.5 stars or higher are "liked". Movies rated 2 stars or lower are "disliked".

**Step 2 - Extract the group's taste profile**: Fetches details for the top 10 liked movies and counts how often each genre and director appears. This reveals the group's favorite genres (e.g., Sci-Fi appeared 6 times, Action 4 times) and favorite directors (e.g., Nolan appeared 3 times).

**Step 3 - Search for candidates**: Takes the group's top 3 genres and uses **semantic search** to find movies matching those genres. The search uses 1024-dimensional vector embeddings to find movies with similar themes and tone, not just keyword matches.

**Step 4 - Filter out watched movies**: Removes any movie the group has already watched or rated, so you never get recommended something you've already seen.

**Step 5 - Score and explain**: Each candidate movie gets a match score based on how many of the group's favorite genres it matches. If the director is also a group favorite, the score gets boosted. The system generates a human-readable explanation for each pick.

### Type 2: Personalized Pick (After Comparison)

When you compare 2 or 3 movies and ask "Which one should I watch?", the system picks the best one for you personally:

**Step 1 - Build your taste profile**: Looks at movies you've rated 4 stars or higher ("loved"). Extracts your favorite genres, directors, and preferred runtime range (your average liked movie runtime ±20 minutes).

**Step 2 - Score each movie** using 4 factors:

* **TMDB rating (30%)**: The movie's overall quality score from TMDB. Higher rated movies get more points.
* **Genre match (25%)**: How many of your favorite genres the movie has. Each matching genre adds points based on how often you've watched that genre.
* **Runtime fit (15%)**: Whether the movie's length matches your preferred runtime range. If you tend to love 120-minute movies, a 120-minute candidate scores higher than a 90-minute one.
* **Director affinity (30%)**: If the director is someone you've loved before, big bonus. Also recognizes acclaimed directors (Nolan, Spielberg, Tarantino, Villeneuve, etc.) even if you haven't rated their work yet.

**Step 3 - Pick the winner**: The highest-scoring movie becomes the recommendation. The system also provides 2 alternatives and explains why each was scored the way it was.

---

## Two Examples

### Example 1: Group Recommendation

**User says**: "Recommend movies for Friday Movie Night"

**What happens behind the scenes**:
1. System finds Friday Movie Night has rated 15 movies. 10 were liked (3.5+ stars), 2 were disliked (≤2 stars).
2. Analyzes the 10 liked movies. Top genres: Sci-Fi (6 movies), Action (4 movies), Thriller (3 movies). Top director: Christopher Nolan (3 movies). Average runtime: 135 minutes.
3. Semantic search for "Sci-Fi Action Thriller movies" returns 20 candidates.
4. Filters out the 12 already-watched movies. 8 candidates remain.
5. Scores each candidate. **Interstellar** scores highest - it's Sci-Fi + Action + Thriller (3/3 genre match) and directed by Nolan (group favorite, +0.2 boost).

**Results**:
1. **Interstellar** (match score: 1.2) - "Perfect match for your love of Sci-Fi, Action, Thriller from favorite director Christopher Nolan."
2. **Gravity** (match score: 0.8) - "Perfect match for your love of Sci-Fi, Thriller."
3. **Dune** (match score: 0.7) - "Perfect match for your love of Sci-Fi, Action."

### Example 2: Personalized Pick

**User says**: "I'm comparing Inception, Interstellar, and Tenet. Which should I watch?"

**What happens behind the scenes**:
1. Builds your taste profile from your rating history. You've loved 8 movies. Your top genres: Sci-Fi (5), Action (4), Drama (3). Your top director: Christopher Nolan (4 movies loved). Your preferred runtime: 125-165 minutes.
2. Scores each movie:
   * **Inception**: TMDB rating 8.8 (×3 = 26.4). Genre match: Sci-Fi +5, Action +5 = 10. Runtime 148 min (within preferred range) +6. Director: Nolan, you've loved his work before +10. **Total: 52.4**
   * **Interstellar**: TMDB rating 8.4 (×3 = 25.2). Genre match: Sci-Fi +5, Drama +5 = 10. Runtime 169 min (outside preferred range, but epic scale) +3. Director: Nolan, you've loved his work before +10. **Total: 48.2**
   * **Tenet**: TMDB rating 7.3 (×3 = 21.9). Genre match: Sci-Fi +5, Action +5 = 10. Runtime 150 min (within preferred range) +6. Director: Nolan, you've loved his work before +10. **Total: 47.9**

**Result**: **Inception** wins with a score of 52.4. Reason: "Matches your love for Sci-Fi, Action, matches your preferred runtime, and you've loved Christopher Nolan's work before." Alternatives: Interstellar (48.2), Tenet (47.9).

---

## Rating Scale

All ratings in the system use a 1-5 scale:

* **Loved** (4.0+ stars): Used to build taste profiles for personalized picks
* **Liked** (3.5+ stars): Used to identify group preferences for group recommendations
* **Disliked** (≤2.0 stars): Used to filter out movies the group doesn't want to see again

---

## How Watched Movies Are Excluded

When searching for candidates, the system checks the watchlist for each movie. If a movie has been marked as "watched" for the group, it's excluded from results. This happens at the search level, before scoring, so watched movies never even enter the candidate pool.

---

## Backend Tools

All recommendation logic lives in the backend (`movie_mcp_server.py`), making it callable by any client:

* **`get_group_preferences`** - Analyzes a group's liked/disliked movies and returns statistics
* **`get_explained_group_recommendations`** - Full group recommendation workflow with explanations
* **`get_personalized_recommendation`** - Picks the best movie from a comparison set based on personal taste
* **`save_group_recommendation`** - Saves a recommendation for later reference

The frontend only formats these responses for display - no scoring or filtering happens in the UI.

---

## Limitations

* **Cold start**: Groups with fewer than 3 ratings won't get meaningful recommendations. The taste profile needs data to work with.
* **Top 10 limit**: Group recommendations analyze at most the top 10 liked movies to keep things fast (avoids too many API calls to fetch movie details).
* **Director recognition**: The notable directors list is hardcoded. New acclaimed directors need to be added manually.

---

## Related Documentation

* **[SEMANTIC_SEARCH.md](./SEMANTIC_SEARCH.md)** - How vector embeddings power the candidate search step
* **[HYBRID_SEARCH.md](./HYBRID_SEARCH.md)** - The advanced query engine that powers semantic search with entity extraction, 4 TMDB candidate strategies, and dynamic scoring
* **[TMDB_INTEGRATION.md](./TMDB_INTEGRATION.md)** - How movies are fetched from TMDB, embedded, and cached in the database



