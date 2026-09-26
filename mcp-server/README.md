# 🍿 AI Movie Night Planner

**An intelligent movie recommendation app powered by Databricks, featuring semantic search, group watchlists, and personalized recommendations.**

[![Databricks](https://img.shields.io/badge/Databricks-Apps-red)](https://www.databricks.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-4.0.3-green)](https://github.com/jlowin/fastmcp)

## 🌟 Features

* **🧠 AI-Powered Semantic Search**: Find movies by description ("romantic comedy with plot twists")
* **🎬 TMDB Integration**: Search 700K+ movies from The Movie Database
* **👥 Group Management**: Create groups, share watchlists, and get group recommendations
* **⭐ Rating System**: Rate movies, track preferences, and get personalized suggestions
* **🔍 Smart Routing**: LLM-based agent automatically selects the right tool for your query
* **📊 Real-time Embeddings**: Uses Databricks AI_QUERY for semantic understanding

## 🏗️ Architecture

```
Streamlit UI (frontend.py)
    ↓
LLM Router (Meta Llama 3.3 70B)
    ↓
FastMCP Server (movie_mcp_server.py) ← 12 MCP Tools
    ↓
Lakebase PostgreSQL + TMDB API
    ↓
AI_QUERY (Embeddings) + SQL Warehouse
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed system design.

## 📁 Project Structure

```
mcp-server/
├── app.yaml                    # Databricks App configuration
├── requirements.txt            # Python dependencies
├── frontend.py                 # Streamlit UI + LLM agent router
├── movie_mcp_server.py         # FastMCP server (12 tools)
├── lakebase.py                 # PostgreSQL connection helper
├── test_frontend.py            # Unit tests
├── pytest.ini                  # Test configuration
├── setup.sh                    # One-command setup script
├── README.md                   # This file
├── SEARCH_EXPLAINED.md         # How semantic search works
├── ARCHITECTURE.md             # System design deep-dive
└── TEST_README.md              # Testing guide
```

### Key Files

* **frontend.py**: Streamlit UI, LLM router, tool orchestration, validation
* **movie_mcp_server.py**: FastMCP server with 12 tools (search, groups, watchlist, ratings)
* **lakebase.py**: Database connection with retry logic and connection pooling
* **app.yaml**: App config (name, compute size, secrets, resources)

## 🛠️ Available Tools (12 Total)

The FastMCP server exposes these tools for the AI agent:

### 🎬 Movie Search & Discovery
1. **search_movies(query, limit)** - Search TMDB by title
2. **semantic_search_movies(query, limit)** - AI-powered search by description
3. **get_movie_details(movie_id)** - Full movie details (cast, crew, ratings)
4. **get_trending_movies(limit)** - Top-rated movies

### 👥 Group Management
5. **create_group(group_name)** - Create a new movie group
6. **list_my_groups()** - List all your groups
7. **get_group_by_name(group_name)** - Find group by name
8. **get_group_members(group_id)** - List group members

### 📋 Watchlist & Ratings
9. **add_to_watchlist(group_id, movie_id)** - Add movie to group watchlist
10. **get_watchlist(group_id)** - View group's watchlist
11. **rate_movie(group_id, movie_id, rating)** - Rate a movie (1-5 stars)
12. **save_group_recommendation(group_id, movie_id, reason)** - Save recommended movie

See [SEARCH_EXPLAINED.md](./SEARCH_EXPLAINED.md) for how semantic vs. title search works.

## 📝 Prerequisites

### 1. **Databricks Workspace**
* Databricks workspace with Apps enabled
* Serverless compute available

### 2. **Lakebase PostgreSQL Database**
* Active Lakebase Postgres instance
* Required tables:
  * `movies` (TMDB movie data)
  * `movie_embeddings` (AI embeddings for semantic search)
  * `groups` (user groups)
  * `group_members` (group memberships)
  * `watchlist` (group watchlists)
  * `ratings` (movie ratings)
  * `recommendations` (saved recommendations)

### 3. **Databricks Secrets**
Create these secrets in the `database` scope:

**Via UI**:
1. Go to **Workspace Settings** → **Secrets**
2. Create scope: `database`
3. Add secret: `tmdb-api-key` (get from https://www.themoviedb.org/settings/api)
4. Add secret: `lakebase-url` (format: `postgresql://user:pass@host:port/db`)

**Via CLI (Optional)**:
```bash
databricks secrets put --scope database --key tmdb-api-key
databricks secrets put --scope database --key lakebase-url
```

### 4. **SQL Warehouse with AI Functions**
* Serverless SQL Warehouse (or Pro/Classic with AI functions enabled)
* App service principal must have **"Can use"** permission on the warehouse
* Warehouse ID: Configure in `movie_mcp_server.py`

### 5. **Model Serving Endpoint**
* LLM endpoint for agent routing (Meta Llama 3.3 70B or similar)
* Endpoint name configured in `frontend.py`
* App must have access to call the endpoint

### 6. **TMDB API Account**
* Free account at https://www.themoviedb.org
* API key from Settings → API
* Rate limit: 40 requests/10 seconds

## 🚀 Quick Start (UI-Based Deployment)

### Step 1: Verify Prerequisites

**Before deploying**, ensure you have:

✅ **Secrets configured** in Databricks:
* Scope: `database`
* Keys: `tmdb-api-key`, `lakebase-url`
* How: Workspace Settings → Secrets → Create Scope → Add Secrets

✅ **Lakebase database running** with tables created

✅ **SQL Warehouse available** (Serverless Starter Warehouse)

✅ **Model Serving endpoint** configured for LLM routing

### Step 2: Deploy the App (UI)

1. **Open your app**: [mcp-server-ai-movie-planner](#app-mcp-server-ai-movie-planner)
2. **Click "Deploy"** button (top right)
3. **Wait ~30-60 seconds** for deployment to complete
4. **Check status**: Should show "App is running" with green indicator
5. **Click "Open App"** to test

**Note**: The app deploys from your workspace folder:
```
/Users/<your-email>/ai-movie-night-planner/mcp-server
```

Any changes you make to files in this folder will be deployed when you click "Deploy".

### Step 3: Grant SQL Warehouse Permissions ⚠️ CRITICAL

**CRITICAL**: The app service principal needs "Can use" permission:

#### Find Your App's Service Principal Name:

**Option 1: Via App Details (Easiest)**
1. Open your [app](#app-mcp-server-ai-movie-planner)
2. Click the **⋮** (three dots) menu → **Details**
3. Copy the **Service Principal Name** (format: `app-<random-id> <app-name>`)

**Option 2: Check Logs**
1. Open your [app logs](#app-mcp-server-ai-movie-planner)
2. Look for deployment messages
3. Find the service principal name in the logs

**Example**: `app-1ec41d mcp-server-ai-movie-planner` (your ID will be different!)

#### Grant Permission:

1. Go to **SQL Warehouses** → **Serverless Starter Warehouse**
2. Click **Permissions** tab
3. Click **Grant**
4. Search for: **your service principal name** from above
5. Select **"Can use"**
6. Click **Grant**

**Without this**, semantic search will fail with "Could not generate query embedding".

## 🧪 Testing

### Automated Tests (Recommended: Use Notebook)

**Option 1: Test Runner Notebook** (No CLI needed):
1. Open: [AI Movie Planner - Test Runner](#notebook-3012339792841487)
2. Click **"Run All"**
3. View results in ~5 seconds

**Option 2: Pytest** (Requires local environment):
```bash
# Only if you have pytest installed locally
pytest test_frontend.py -v
pytest test_frontend.py::TestMovieIdResolution -v
pytest test_frontend.py::TestGroupHandling -v
```

### Manual Testing Queries

Try these in the deployed app:

**👍 Should Work:**
* "recommend a romantic movie for Friday Night Flicks"
* "search for Inception"
* "create a group called Movie Club"
* "add The Matrix to my watchlist"
* "rate Interstellar 5 stars"

**⚠️ Should Handle Gracefully:**
* "recommend something" (should ask for group)
* "add MISSING_MOVIE to watchlist" (should reject placeholder)
* "show watchlist for NonExistentGroup" (should return not found)

### Smoke Test Script

**Purpose**: Quick end-to-end validation after deployment

**Run via Notebook** (Recommended):
1. Open a new notebook in your workspace
2. Run:
   ```python
   %run /Workspace/Users/<your-email>/ai-movie-night-planner/mcp-server/test_smoke.py
   ```
3. View color-coded test results

**Run via CLI** (Optional):
```bash
python test_smoke.py
```

**Tests included**:
* ✅ Import required modules (requests, psycopg2, databricks-sdk)
* ✅ Check Databricks secrets (tmdb-api-key, lakebase-url)
* ✅ TMDB API connection & movie search
* ✅ Lakebase database connection & tables
* ✅ SQL Warehouse AI_QUERY function
* ✅ Semantic search components
* ✅ Group operations (create, read, delete)

**Expected output**:
```
🍿 AI Movie Planner - Smoke Test Suite

✅ PASS: requests imported
✅ PASS: psycopg2 imported
✅ PASS: TMDB API reachable (HTTP 200)
✅ PASS: Movie search works: Found 'Inception'
✅ PASS: Lakebase connection established
✅ PASS: AI_QUERY works (embedding generated)
...

🎉 All tests passed! Your app is ready to use.
```

## 💻 Local Development (Optional)

**Note**: This is optional - the app is designed to run as a Databricks App. Use this only if you want to test the MCP server locally on your laptop.

```bash
# Install dependencies
pip install -r requirements.txt

# Configure Databricks CLI (for secrets access)
databricks auth login

# Run the MCP server locally
python movie_mcp_server.py
```

The server will start on `http://localhost:8000`.

**Limitation**: Frontend (frontend.py) requires Databricks App environment and won't work locally without modifications.

## 🐛 Troubleshooting

### "Could not generate query embedding"

**Cause**: App service principal doesn't have SQL Warehouse permission.

**Fix**:
1. Go to SQL Warehouses → Serverless Starter Warehouse → Permissions
2. Grant "Can use" to `app-1ec41d mcp-server-ai-movie-planner`
3. Redeploy the app

### "Empty result from AI_QUERY"

**Cause**: SQL Warehouse AI function returned no data.

**Fix**:
1. **Check warehouse is running**: Go to SQL Warehouses in Databricks UI
2. **Test AI_QUERY manually** in a SQL notebook cell:
   ```sql
   SELECT AI_QUERY('databricks-bge-large-en', 'test query', returnType => 'ARRAY<DOUBLE>') as embedding
   ```
3. Verify warehouse supports AI functions (Serverless or Pro/Classic with AI enabled)

### "MISSING_MOVIE" TMDB 404 Error

**Cause**: LLM failed to resolve movie title to ID.

**Fix**: Already fixed in latest `frontend.py` - update and redeploy.

### Deployment Fails with Dependency Conflicts

**Cause**: Incompatible package versions.

**Fix**: Use the provided `requirements.txt` with:
* `fastmcp==4.0.3`
* `streamlit==1.36.0`
* No explicit `starlette` or `fastapi` pins

### App is STOPPED or Not Running

**Fix (UI)**:
1. Open [mcp-server-ai-movie-planner](#app-mcp-server-ai-movie-planner)
2. Check status indicator (should be green "Running")
3. If stopped, click **"Start"** and wait for it to reach "Running"
4. Then click **"Deploy"** to deploy latest code

**Fix (CLI - Optional)**:
```bash
databricks apps get mcp-server-ai-movie-planner --output JSON
databricks apps start mcp-server-ai-movie-planner --timeout 20m
databricks apps deploy mcp-server-ai-movie-planner
```

### Real-Time Debugging

1. Open app in one window
2. Open Apps logs page in another
3. Submit queries and watch for:
   * 🔍 Routing decisions
   * 🛠️ Tool selections
   * ⚠️ Warnings (placeholders, missing groups)
   * ❌ Errors (not found, permission issues)

## 📊 Performance

| Operation | Average Time | Notes |
|-----------|--------------|-------|
| Generate embedding | 1-2s | Depends on SQL Warehouse |
| Semantic search | 2-3s | Includes embedding + search |
| Title search (TMDB) | 0.5-1s | Direct API call |
| LLM routing | 1-2s | Decides which tool to use |
| Group operations | 0.2-0.5s | Direct database queries |

**Optimization Tips:**
* Use caching for frequent queries
* Batch embedding generation
* Keep SQL Warehouse warm for faster responses

## 🚀 Next Steps

### For Assignment:
1. ✅ **Documentation** - Complete! (README, ARCHITECTURE, SEARCH_EXPLAINED, setup.sh)
2. ✅ **Smoke test script** - Complete! (`test_smoke.py`)
3. ✅ **UI polish** - Complete! (Movie cards, posters, tables, ratings, sidebar) - See [UI_IMPROVEMENTS.md](./UI_IMPROVEMENTS.md)
4. □ **Deploy & Test** - Click "Deploy" button, verify UI improvements work
5. □ **Data pipeline job** (Optional) - TMDB fetch + embeddings backfill
6. □ **Demo** - Record video or share public link

### Future Enhancements:
* 📈 Analytics dashboard (most-watched, ratings distribution)
* 🔔 Notifications (new recommendations, watchlist updates)
* 🤝 Social features (friend recommendations, shared ratings)
* 🎯 ML model for personalized recommendations
* 📱 Mobile-friendly UI

## 📚 Learn More

* [SEARCH_EXPLAINED.md](./SEARCH_EXPLAINED.md) - How semantic search works
* [ARCHITECTURE.md](./ARCHITECTURE.md) - System design details
* [TEST_README.md](./TEST_README.md) - Testing guide
* [Databricks Apps Docs](https://docs.databricks.com/en/dev-tools/databricks-apps/index.html)
* [FastMCP GitHub](https://github.com/jlowin/fastmcp)
* [TMDB API Docs](https://developers.themoviedb.org/3)

---

## 💻 Appendix: CLI Commands (Optional)

**Note**: This project primarily uses the **Databricks Apps UI** for deployment. CLI commands below are provided as optional alternatives for advanced users.

### Deployment via CLI
```bash
# Check app status
databricks apps get mcp-server-ai-movie-planner --output JSON

# Deploy (alternative to clicking "Deploy" in UI)
databricks apps deploy mcp-server-ai-movie-planner
```

### Prerequisites Check via CLI
```bash
# Optional: Run setup validation script
bash setup.sh
```

### Testing via CLI
```bash
# Run tests (requires pytest installed locally)
pytest test_frontend.py -v

# Run smoke test
python test_smoke.py
```

**Recommended approach**: Use the UI-based workflow described in "Quick Start" above.

---

## 👏 Credits

Built with:
* **Databricks**: Platform, Apps, SQL Warehouse, AI_QUERY
* **FastMCP**: MCP server framework
* **Lakebase**: PostgreSQL database
* **Streamlit**: Frontend UI
* **TMDB**: Movie data
* **Meta Llama 3.3 70B**: LLM routing

---

*Last updated: 2026-02-09 | Version: 1.0.0*
