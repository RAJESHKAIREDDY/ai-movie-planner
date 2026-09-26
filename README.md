# 🍿 AI Movie Night Planner

A conversational AI assistant that helps groups of friends find movies everyone will enjoy. Built with Databricks, Lakebase Postgres, TMDB API, and MCP (Model Context Protocol).

## What It Does

* **Group Movie Planning** - Create groups, add members, build collaborative watchlists
* **Smart Recommendations** - AI-powered suggestions based on group taste profiles
* **Semantic Search** - Find movies by description, mood, or theme (not just exact titles)
* **Ratings & Reviews** - Rate movies, track what you've watched, see sentiment analysis
* **Natural Conversation** - Chat with the assistant in plain English

## Project Structure

### mcp-server/ (Core Application)

| File | What It Does |
|------|-------------|
| **movie_mcp_server.py** | The backend. All business logic, 40+ MCP tools, database operations, TMDB integration, recommendations, and semantic search. Anything callable by any client lives here. |
| **frontend.py** | The UI. Streamlit chat interface, display formatting, session state, and LLM routing. No business logic - just presents what the backend returns. |
| **lakebase.py** | Postgres connection helper. Manages connections to Lakebase Postgres with context managers and query helpers. |
| **backfill.py** | Database maintenance utilities. Fixes missing users, populates movie metadata, verifies data integrity. |
| **test_frontend.py** | Frontend tests. |
| **test_smoke.py** | Smoke tests for backend tools. |
| **conftest.py** | Pytest configuration and shared fixtures. |
| **app.yaml** | Databricks App deployment config. |
| **requirements.txt** | Python dependencies for the MCP server. |

### SQL/ (Database Setup)

| File | What It Does |
|------|-------------|
| **01_users.sql** | Creates the users table (email, username). |
| **02_groups.sql** | Creates the groups table (movie night groups). |
| **03_group_members.sql** | Creates the group_members table (links users to groups). |
| **04_movies.sql** | Creates the movies table with VECTOR(1024) embedding column for semantic search. |
| **05_ratings.sql** | Creates the ratings table (user ratings with group context and sentiment). |
| **06_watchlist_items.sql** | Creates the watchlist_items table (group watchlists with pending/watched status). |
| **07_recommendations.sql** | Creates the recommendations table (AI recommendation history). |
| **README.md** | SQL setup guide - how to run these scripts against Lakebase Postgres. |

### docs/ (Feature Documentation)

| File | What It Does |
|------|-------------|
| **SEMANTIC_SEARCH.md** | How semantic search works - vector embeddings, pgvector similarity, and regular vs. semantic search with examples. |
| **HYBRID_SEARCH.md** | The advanced search engine - LLM entity extraction, 4 TMDB candidate strategies, dynamic scoring, quality mode, and fallback logic. |
| **RECOMMENDATIONS.md** | How recommendations work - group taste profiles, personalized scoring, and two recommendation types with examples. |
| **TMDB_INTEGRATION.md** | How movies enter the system - API key management, rate limiting, parallel fetching, embedding generation, and the caching pipeline. |

### Root Files

| File | What It Does |
|------|-------------|
| **setup_secrets.py** | Stores TMDB API key in Databricks secrets. |
| **requirements.txt** | Top-level Python dependencies. |
| **README.md** | This file. |

## Architecture

The project follows a strict **backend/frontend split**:

* **Backend** (`movie_mcp_server.py`) - All data fetching, business logic, scoring algorithms, and database operations. If an LLM or another app could call it, it belongs here.
* **Frontend** (`frontend.py`) - UI presentation only. Formats backend responses as markdown/HTML. Needs Streamlit session state or display logic = frontend.

## Quick Start

1. **Set up the database** - Run the SQL files in order (01-07) against your Lakebase Postgres database. See `SQL/README.md` for instructions.
2. **Store your TMDB API key** - Run `setup_secrets.py` to save it in Databricks secrets.
3. **Run the app** - From the `mcp-server/` directory, run `streamlit run frontend.py`.

## Feature Documentation

* **[Semantic Search](./docs/SEMANTIC_SEARCH.md)** - How vector similarity search finds movies by meaning, not just keywords.
* **[Hybrid Search](./docs/HYBRID_SEARCH.md)** - The advanced search engine with entity extraction, dynamic scoring, and fallback logic.
* **[Recommendations](./docs/RECOMMENDATIONS.md)** - How group taste profiles and personalized scoring power recommendations.
* **[TMDB Integration](./docs/TMDB_INTEGRATION.md)** - How movies are fetched from TMDB, embedded, and cached for fast repeat searches.

More feature docs coming soon: Group Management, Ratings & Reviews.

