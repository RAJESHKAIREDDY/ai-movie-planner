# How Movie Search Works in AI Movie Planner

This document explains the two types of search used in the AI Movie Planner app, in simple terms.

---

## 🔍 Two Types of Search

Our app uses **two different search methods** depending on what you're looking for:

### 1. **Semantic Search** (AI-Powered Understanding)
### 2. **Movie Title Search** (Direct Lookup)

---

## 🧠 Semantic Search (AI-Powered)

### What is it?
Semantic search understands the **meaning** of your words, not just the exact text. It's like asking a friend "I want something romantic and funny" and they understand what you're feeling, not just matching keywords.

### When do we use it?
- When you describe **what kind of movie** you want
- Examples:
  - "Show me a good romantic movie"
  - "I want something scary"
  - "Find me a thriller with action"
  - "Something like Inception but lighter"

### How does it work?

1. **You type a description**: "good romantic movie"

2. **AI converts your words to numbers** (called "embeddings"):
   - The app uses Databricks `AI_QUERY` function
   - This converts "good romantic movie" into a list of 1024 numbers
   - These numbers represent the **meaning** of your words
   - Example: `[0.234, -0.567, 0.891, ...]`

3. **Compare to all movies**:
   - Every movie in our database also has these number representations
   - The app calculates **similarity scores** using math (cosine similarity)
   - Movies with similar meanings get higher scores

4. **Return the best matches**:
   - Movies are ranked by similarity
   - Top 5 movies are returned

### Real Example

**Your query**: "romantic comedy with strong female lead"

**What happens behind the scenes**:
```
1. AI converts your query → [0.12, -0.45, 0.89, ...] (1024 numbers)
2. Compare to all movies in database:
   - "Legally Blonde" → Similarity: 0.87 (very similar!)
   - "The Matrix" → Similarity: 0.23 (not similar)
   - "10 Things I Hate About You" → Similarity: 0.85 (similar!)
3. Return top matches:
   ✅ Legally Blonde
   ✅ 10 Things I Hate About You
   ✅ Clueless
```

### Technical Details (For Developers)

- **Model**: `databricks-bge-large-en` (BGE = Beijing General Embedding)
- **Embedding Dimension**: 1024 (each text becomes 1024 numbers)
- **Similarity Metric**: Cosine similarity
- **Database**: PostgreSQL with embeddings stored in `movie_embeddings` table
- **SQL Function**: `AI_QUERY('databricks-bge-large-en', 'your text', returnType => 'ARRAY<DOUBLE>')`

---

## 🎬 Movie Title Search (Direct Lookup)

### What is it?
Direct search looks for **exact or partial movie titles** in the database or from TMDB (The Movie Database).

### When do we use it?
- When you mention a **specific movie title**
- Examples:
  - "Add Inception to my watchlist"
  - "Search for The Matrix"
  - "Rate Interstellar 5 stars"
  - "Show me details for Knives Out"

### How does it work?

1. **You mention a movie title**: "Inception"

2. **Search TMDB database**:
   - App sends request to TMDB API: `GET /search/movie?query=Inception`
   - TMDB returns matching movies with details

3. **Return exact matches**:
   - Movies with matching titles are returned
   - Includes year, director, rating, etc.

### Real Example

**Your query**: "Add Inception to Friday Night Flicks"

**What happens behind the scenes**:
```
1. App extracts movie title: "Inception"
2. Call TMDB API:
   GET https://api.themoviedb.org/3/search/movie?query=Inception
3. TMDB returns:
   {
     "id": 27205,
     "title": "Inception",
     "year": 2010,
     "director": "Christopher Nolan",
     ...
   }
4. App uses movie_id=27205 to add to watchlist
```

### Technical Details (For Developers)

- **API**: TMDB (The Movie Database) REST API
- **Endpoint**: `https://api.themoviedb.org/3/search/movie`
- **Authentication**: API key stored in Databricks secrets
- **Match Type**: Partial text matching
- **Limit**: Default 1 result for exact matches

---

## 🆚 Semantic vs. Title Search Comparison

| Feature | Semantic Search 🧠 | Title Search 🎬 |
|---------|-------------------|-----------------|
| **Input** | Description of what you want | Specific movie title |
| **Example** | "scary movie with ghosts" | "The Conjuring" |
| **Technology** | AI embeddings + similarity | TMDB API text search |
| **Returns** | Multiple similar movies | Exact movie match |
| **Speed** | Slower (AI processing) | Faster (direct lookup) |
| **Accuracy** | Understands meaning | Requires exact title |

---

## 🔄 How the App Decides Which Search to Use

The app uses an **LLM router** (AI decision maker) to choose:

### Decision Flow:

```
User Query: "recommend a thriller for Friday Night Flicks"
         ↓
    LLM Router Analyzes
         ↓
    Does query mention specific title?
         ↓
    NO → Use Semantic Search
         ↓
    Search for: "thriller"
         ↓
    Return top 5 thriller movies
```

```
User Query: "add Inception to my watchlist"
         ↓
    LLM Router Analyzes
         ↓
    Does query mention specific title?
         ↓
    YES → Use Title Search
         ↓
    Search TMDB for: "Inception"
         ↓
    Return movie_id: 27205
```

---

## 🎯 Examples by Query Type

### ✅ Queries that use **Semantic Search**:

* "recommend a romantic movie"
* "find me something scary"
* "I want a feel-good comedy"
* "show me movies like Inception"
* "thriller with plot twists"

### ✅ Queries that use **Title Search**:

* "add Inception to watchlist"
* "search for The Matrix"
* "rate Interstellar 5 stars"
* "show details for Knives Out"
* "is The Dark Knight in my watchlist?"

---

## ⚙️ Behind the Scenes: The Full Pipeline

### Example: "Recommend a romantic movie for Friday Night Flicks"

```
1. 🔍 Frontend receives query
   └─> frontend.py: agent_loop()

2. 🧠 LLM Router decides tool
   └─> Tool: semantic_search_movies
   └─> Arguments: {query: "romantic movie", limit: 5}

3. 🔢 Generate embedding
   └─> movie_mcp_server.py: generate_query_embedding()
   └─> Call AI_QUERY: "romantic movie" → [0.234, -0.567, ...]

4. 🗄️ Search database
   └─> SQL: SELECT * FROM movies
           JOIN movie_embeddings
           ORDER BY cosine_similarity(embedding, [0.234, -0.567, ...])
           LIMIT 5

5. 📋 Format results
   └─> Return:
       - The Notebook (2004) - Similarity: 0.92
       - La La Land (2016) - Similarity: 0.89
       - Pride & Prejudice (2005) - Similarity: 0.87
       - Notting Hill (1999) - Similarity: 0.85
       - 10 Things I Hate About You (1999) - Similarity: 0.84

6. 🖥️ Display to user
   └─> Streamlit UI shows results
```

---

## 🛠️ Key Technologies Used

### For Semantic Search:
* **Databricks AI Functions**: `AI_QUERY` for embeddings
* **BGE Model**: Beijing General Embedding (large-en)
* **PostgreSQL**: Stores movie embeddings
* **Cosine Similarity**: Math to compare similarity

### For Title Search:
* **TMDB API**: The Movie Database
* **REST API**: HTTP requests
* **JSON**: Data format

### For Routing:
* **LLM**: Meta Llama 3.3 70B
* **Databricks Model Serving**: Hosts the LLM
* **JSON**: Structured decision format

---

## 💡 Why Two Search Methods?

### Semantic Search is great for:
* ✅ Discovering new movies
* ✅ Finding movies by vibe/mood
* ✅ "I don't know what I want, but I'll know it when I see it"

### Title Search is great for:
* ✅ Adding a specific movie you already know
* ✅ Fast, exact lookups
* ✅ "I want to add Inception, and I know exactly what I want"

### Together:
* 🎯 Covers all user needs
* 🚀 Fast when you know what you want
* 🧠 Smart when you're exploring

---

## 📊 Performance Metrics

| Operation | Average Time | Notes |
|-----------|--------------|-------|
| Generate embedding | ~1-2 seconds | Depends on SQL Warehouse |
| Semantic search | ~2-3 seconds | Includes embedding + search |
| Title search (TMDB) | ~0.5-1 second | Direct API call |
| LLM routing | ~1-2 seconds | Decides which tool to use |

---

## 🐛 Common Issues

### "Could not generate query embedding"
* **Cause**: SQL Warehouse AI function not accessible
* **Fix**: Grant app service principal "Can use" permission on warehouse

### "Movie not found"
* **Cause**: Title doesn't exist in TMDB
* **Fix**: Check spelling or try semantic search instead

### "Empty result from AI_QUERY"
* **Cause**: AI function returned no data
* **Fix**: Check warehouse is running, retry query
---

## 📝 Summary

* 🧠 **Semantic Search**: Understands meaning, finds similar movies by description
* 🎬 **Title Search**: Looks up exact movie titles from TMDB
* 🤖 **LLM Router**: Decides which search to use based on your query
* ⚡ **Fast + Smart**: Combines speed of direct lookup with intelligence of AI

---

*Last updated: 2026-01-09*
