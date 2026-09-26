"""
AI Movie Night Planner MCP Server

Exposes movie recommendation tools over MCP (Model Context Protocol).
Follows Alpaca pattern for user identity (default email parameters).

User & Identity:
    - get_current_user() - Get authenticated user info
    - list_all_users() - List all users in the system (for dropdown)
    - switch_user(user_name) - Switch active user context (searches group members)
    - create_and_add_user_to_group(user_name, user_email, group_id) - Create new user and add to group

Movie Discovery:
    - search_movies(query, limit) - Search for movies
    - get_movie_details(movie_id) - Get detailed movie info
    - compare_movies(movie_id1, movie_id2, movie_id3) - Compare 2-3 movies

Group Management:
    - list_user_groups(email) - List groups created/joined by user [Alpaca pattern]
    - get_group_by_name(group_name) - Find group by name
    - list_all_groups(limit) - List all groups in system
    - create_group(group_name, description, email) - Create new group [Alpaca pattern]
    - add_group_member(group_id, user_id) - Add user to group
    - get_group_members(group_id) - Get all members of a group

Watchlist Management:
    - add_to_watchlist(group_id, movie_id) - Add movie to group watchlist
    - get_watchlist(group_id, status) - Get group's watchlist
    - remove_from_watchlist(group_id, movie_id) - Remove from watchlist

Ratings & Reviews:
    - rate_movie(group_id, movie_id, rating, review, email) - Rate a movie [Alpaca pattern]
    - get_movie_ratings(movie_id, group_id) - Get ratings for a movie
    - get_group_ratings(group_id) - Get all movies rated by a group
    - get_my_ratings(group_id, email) - Get user's ratings [Alpaca pattern]

Preferences & Analysis:
    - get_group_preferences(group_id) - Analyze group's movie preferences

Deploy as Databricks App. Run locally: python movie_mcp_server.py
"""

import os
import sys
import logging
import requests
import json
import random
import string
import base64
import re
import time
import asyncio
import aiohttp
from typing import Optional
from contextvars import ContextVar
from functools import wraps
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from databricks.sdk import WorkspaceClient

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Make fastmcp optional for environments where only tool functions are needed
try:
    from fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False
    # Define a dummy decorator for when fastmcp is not available
    class DummyMCP:
        def __init__(self, name):
            self.name = name
        def tool(self, func):
            return func
    FastMCP = DummyMCP

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("movie-mcp-server")

# Only create MCP server if fastmcp is available
if FASTMCP_AVAILABLE:
    mcp = FastMCP("ai-movie-night-planner")
else:
    mcp = DummyMCP("ai-movie-night-planner")
    logger.info("Running without FastMCP - tool functions available for direct import")

# Global context & connection pooling
_request_context: ContextVar[dict] = ContextVar('request_context', default={})
_TMDB_API_KEY_CACHE: Optional[str] = None

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# RATING SCALES EXPLANATION:
# - TMDB ratings (from TheMovieDB API): stored and processed internally as /10 scale
# - User ratings (from our ratings table): stored and processed as /5 scale
# - Display: ALL ratings shown to users are normalized to /5 scale for consistency
#   (TMDB ratings are divided by 2 before display in get_personalized_recommendation)

# Quality filter thresholds (used in semantic_search_movies for "top/best" queries)
QUALITY_MIN_RATING = 6.5  # TMDB ratings are /10 scale (internal processing)
QUALITY_MIN_VOTE_COUNT = 100

# Rating thresholds for preference analysis (get_group_preferences) - ALL ON /5 SCALE
LIKED_RATING_THRESHOLD = 3.5
LOVED_RATING_THRESHOLD = 4.0  # Higher bar for 'loved' movies (used by dashboard and taste profile)
DISLIKED_RATING_THRESHOLD = 2.0
DEFAULT_MIN_RATING_THRESHOLD = 2.5

# Sentiment thresholds (on /5 scale) for rating display
SENTIMENT_LOVED_THRESHOLD = 4.5    # 4.5/5 - Loved it!
SENTIMENT_LIKED_THRESHOLD = 3.5    # 3.5/5 - Liked it
SENTIMENT_OKAY_THRESHOLD = 2.5     # 2.5/5 - It's okay


def get_rating_sentiment(rating: float) -> str:
    """Classify a rating into a sentiment category.
    
    Business rule: thresholds on /5 scale (user-facing scale).
    Frontend maps the returned category to emoji/label for display.
    
    Returns: 'loved', 'liked', 'okay', or 'disliked'
    """
    if rating >= SENTIMENT_LOVED_THRESHOLD:
        return 'loved'
    elif rating >= SENTIMENT_LIKED_THRESHOLD:
        return 'liked'
    elif rating >= SENTIMENT_OKAY_THRESHOLD:
        return 'okay'
    else:
        return 'disliked'

# TMDB API settings
TMDB_API_TIMEOUT = 10          # seconds for TMDB API calls
TMDB_SEARCH_MULTIPLIER = 2     # search_movies fetches limit * this for filtering
TMDB_MAX_POPULATE_LIMIT = 20   # max movies per genre in populate_movies_by_genre

# LLM entity extraction settings
LLM_MAX_TOKENS = 200
LLM_TEMPERATURE = 0.1
LLM_TIMEOUT = 20               # seconds for LLM API calls

# Embedding API settings
EMBEDDING_TIMEOUT = 20          # single embedding
EMBEDDING_BATCH_TIMEOUT = 60   # batch embeddings
EMBEDDING_QUERY_TIMEOUT = 30  # query embedding in semantic search

# Candidate fetch limits (TMDB discovery/search in semantic_search_movies)
CANDIDATE_LIMIT_SEARCH = 10
CANDIDATE_LIMIT_KEYWORD = 15
CANDIDATE_LIMIT_PERSON = 10
CANDIDATE_LIMIT_GENRE = 20

# Configure HTTP session with retry strategy and connection pooling
_http_session = requests.Session()
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20
    )
    _http_session.mount("http://", adapter)
    _http_session.mount("https://", adapter)
    logger.info("✅ HTTP session configured with retry strategy and connection pooling")
except Exception as e:
    logger.warning(f"Failed to configure HTTP session retry strategy: {e}")

# Email validation pattern (RFC 5322 simplified)
_EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# UUID validation pattern (for group ID resolution)
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

from decimal import Decimal as _Decimal
from datetime import date as _date


def make_json_serializable(obj):
    """Recursively convert datetime and Decimal to JSON-serializable types.
    
    Database query results from lakebase may contain Decimal and datetime objects.
    This utility ensures all return values are clean JSON types.
    Called by frontend's call_tool() to sanitize backend results.
    """
    if isinstance(obj, (datetime, _date)):
        return obj.isoformat()
    elif isinstance(obj, _Decimal):
        return float(obj)
    elif hasattr(obj, 'items'):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    return obj


def validate_email(email: str) -> bool:
    """Validate email format using regex pattern.
    
    Public function - can be called by frontend and other clients.
    """
    if not email or not isinstance(email, str):
        return False
    return _EMAIL_PATTERN.match(email.strip()) is not None


def _sanitize_error(e: Exception, context: str = None) -> str:
    """Sanitize error messages for user-facing responses.
    Logs full error internally, returns a safe message to users.
    """
    raw_msg = str(e)
    # Truncate overly long messages (e.g., SQL errors, stack traces)
    if len(raw_msg) > 200:
        raw_msg = raw_msg[:200] + '...'
    # Remove potential internal hostnames/IPs
    raw_msg = re.sub(r'https?://[\w.-]+', '[URL]', raw_msg)
    raw_msg = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', raw_msg)
    prefix = f"{context}: " if context else ""
    return f"{prefix}{raw_msg}"


def _get_end_user_email() -> str:
    """
    Get the actual end user's email from X-Forwarded-User header.
    """
    headers = _request_context.get()
    
    forwarded_user = headers.get('x-forwarded-user')
    forwarded_email = headers.get('x-forwarded-email')
    
    if forwarded_user:
        return forwarded_user
    
    if forwarded_email:
        return forwarded_email
    
    # Fallback for local testing - use service principal
    try:
        w = WorkspaceClient()
        user_name = w.current_user.me().user_name or 'rajesh@gmail.com'
        
        # Detect service principal UUIDs (not real email addresses)
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', user_name.lower()):
            logger.info(f"Detected service principal UUID: {user_name}, using default email")
            return 'rajesh@gmail.com'
        
        return user_name
    except Exception as e:
        logger.warning(f"Failed to get user from WorkspaceClient: {e}")
        return 'rajesh@gmail.com'

def _generate_group_id(group_name: str) -> str:
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', group_name).lower()
    random_digits = ''.join(random.choices(string.digits, k=2))
    return f"{clean_name}{random_digits}"


def _validate_embedding_str(embedding_str: str) -> bool:
    """Validate that an embedding string is safe for SQL interpolation.
    Ensures it contains only numbers, commas, brackets, spaces, minus signs, and dots.
    """
    if not embedding_str or not isinstance(embedding_str, str):
        return False
    # Must start with [ and end with ]
    if not (embedding_str.strip().startswith('[') and embedding_str.strip().endswith(']')):
        return False
    # Must only contain numeric vector characters
    if not re.match(r'^\[[\d.,\s\-eE+]+\]$', embedding_str.strip()):
        return False
    return True


_ALLOWED_ID_TABLES = {
    'watchlist_items': 'watchlist_id',
    'group_members': 'membership_id',
    'ratings': 'rating_id',
    'recommendations': 'recommendation_id'
}

# Pre-defined SQL queries to prevent SQL injection via table/column names
_ID_COUNT_QUERIES = {
    'watchlist_items': "SELECT COUNT(*) as count FROM watchlist_items WHERE watchlist_id LIKE %s",
    'group_members': "SELECT COUNT(*) as count FROM group_members WHERE membership_id LIKE %s",
    'ratings': "SELECT COUNT(*) as count FROM ratings WHERE rating_id LIKE %s",
    'recommendations': "SELECT COUNT(*) as count FROM recommendations WHERE recommendation_id LIKE %s"
}


def _generate_id_with_prefix(text: str, table: str, id_column: str) -> str:
    """Generate a prefixed ID safely without SQL injection risk."""
    # Validate table and column combination
    if table not in _ALLOWED_ID_TABLES or _ALLOWED_ID_TABLES[table] != id_column:
        raise ValueError(f"Invalid table ({table}) or ID column ({id_column}) requested.")
    
    # Get pre-defined query (no string interpolation)
    sql = _ID_COUNT_QUERIES.get(table)
    if not sql:
        raise ValueError(f"No query defined for table: {table}")

    prefix = re.sub(r'[^a-zA-Z]', '', text)[:3].upper()
    if len(prefix) < 3:
        prefix = prefix.ljust(3, 'X')
    
    try:
        result = lakebase.run_query(sql, (f"{prefix}%",))
        count = result[0]['count'] if result else 0
    except Exception as e:
        logger.warning(f"Failed to count {table} for prefix {prefix}: {e}")
        count = 0
    
    return f"{prefix}{count+1:03d}"


def _ensure_user_exists(email: str) -> None:
    """
    Auto-register a user in the database if they don't exist.
    
    This eliminates the need for manual user creation - the first time
    someone uses the system, their user record is automatically created.
    
    Uses ON CONFLICT DO NOTHING so multiple concurrent calls are safe.
    
    IMPORTANT: Skips service principals (UUID format) to prevent auto-registration
    of non-human identities.
    """
    try:
        # Skip service principals (UUID format) — only register real users
        if '@' not in email:
            logger.info(f"Skipping auto-registration for service principal: {email}")
            return
        
        username = email.split('@')[0]  # Extract username from email
        sql = """
        INSERT INTO users (user_id, username, email)
        VALUES (%s, %s, %s)
        ON CONFLICT (email) DO NOTHING
        """
        lakebase.run_write(sql, (email, username, email))
        logger.info(f"Ensured user exists: {email}")
    except Exception as e:
        logger.warning(f"Failed to ensure user exists for {email}: {e}")


def _get_user_id_from_email(email: str) -> str:
    """
    Get user_id from email. In this system, user_id IS the email (not an integer).
    The DBML schema shows user_id as integer for documentation, but the actual
    implementation uses email as the primary key for users.
    
    Args:
        email: User's email address
        
    Returns:
        user_id (which is the email)
    """
    return email


def _upsert_movie(movie_id: str, movie_details: dict, embedding: list) -> None:
    """
    Insert or update a movie in the movies table.
    
    Args:
        movie_id: TMDB movie ID (string)
        movie_details: Movie details dict from get_tmdb_movie_details()
        embedding: Movie embedding vector (list of floats)
    """
    try:
        import json
        
        movie_id_int = int(movie_id)
        title = movie_details.get('title', '')
        overview = movie_details.get('overview', '')
        release_date = movie_details.get('release_date') or None
        runtime = movie_details.get('runtime') or None
        tmdb_rating = movie_details.get('vote_average') or 0
        vote_count = movie_details.get('vote_count') or 0
        genres = json.dumps(movie_details.get('genres', []))
        cast = json.dumps(movie_details.get('cast', []))
        director = movie_details.get('director') or None
        keywords = json.dumps(movie_details.get('keywords', []))
        poster_path = movie_details.get('poster_path') or None
        original_language = movie_details.get('original_language') or 'en'
        
        # Convert embedding list to vector string format
        embedding_str = f"[{','.join(map(str, embedding))}]"
        
        sql = """
        INSERT INTO movies (
            movie_id, title, overview, release_date, runtime, 
            tmdb_rating, vote_count, genres, "cast", director, keywords, poster_path, embedding, original_language
        )
        VALUES (
            %s, %s, %s, %s, %s, 
            %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s::vector, %s
        )
        ON CONFLICT (movie_id) DO UPDATE
        SET 
            title = EXCLUDED.title,
            overview = EXCLUDED.overview,
            release_date = EXCLUDED.release_date,
            runtime = EXCLUDED.runtime,
            tmdb_rating = EXCLUDED.tmdb_rating,
            vote_count = EXCLUDED.vote_count,
            genres = EXCLUDED.genres,
            "cast" = EXCLUDED."cast",
            director = EXCLUDED.director,
            keywords = EXCLUDED.keywords,
            poster_path = EXCLUDED.poster_path,
            embedding = EXCLUDED.embedding,
            original_language = EXCLUDED.original_language
        """
        
        lakebase.run_write(sql, (
            movie_id_int, title, overview, release_date, runtime,
            tmdb_rating, vote_count, genres, cast, director, keywords, poster_path, embedding_str, original_language
        ))
        
        logger.info(f"✅ Upserted movie {movie_id}: {title}")
    except Exception as e:
        logger.exception(f"❌ Failed to upsert movie {movie_id}: {e}")
        # Don't raise - allow the calling function to continue


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        headers = {
            'x-forwarded-user': request.headers.get('x-forwarded-user'),
            'x-forwarded-email': request.headers.get('x-forwarded-email'),
        }
        _request_context.set(headers)
        response = await call_next(request)
        return response


# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """Simple rate limiter using a sliding window approach."""
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
    
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            self.calls = [t for t in self.calls if t > now - self.period]
            
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached for {func.__name__}, sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    self.calls = [t for t in self.calls if t > time.time() - self.period]
            
            self.calls.append(time.time())
            return func(*args, **kwargs)
        
        return wrapper


# ============================================================================
# TMDB API HELPERS
# ============================================================================

def get_tmdb_api_key() -> str:
    """Get TMDB API key from Databricks secrets with module-level caching."""
    global _TMDB_API_KEY_CACHE
    if _TMDB_API_KEY_CACHE is not None:
        return _TMDB_API_KEY_CACHE

    try:
        w = WorkspaceClient()
        scope = os.getenv('TMDB_SECRET_SCOPE', 'database')
        key = os.getenv('TMDB_SECRET_KEY', 'tmdb-api-key')
        
        secret_response = w.secrets.get_secret(scope=scope, key=key)
        encoded_key = secret_response.value
        api_key = base64.b64decode(encoded_key).decode('utf-8')
        
        _TMDB_API_KEY_CACHE = api_key
        return api_key
    except Exception as e:
        logger.exception("Failed to get TMDB API key")
        raise


@RateLimiter(max_calls=40, period=1.0)  # 40 calls per second (TMDB free tier is 50/sec)
def search_tmdb_movies(query: str, limit: int = 10) -> list:
    """Search movies using TMDB API with relevance filtering."""
    
    def calculate_similarity(query_text: str, title: str) -> float:
        """Calculate how similar the query is to the movie title (0.0 to 1.0)"""
        return SequenceMatcher(None, query_text.lower(), title.lower()).ratio()
    
    try:
        api_key = get_tmdb_api_key()
        url = "https://api.themoviedb.org/3/search/movie"
        params = {
            "api_key": api_key,
            "query": query,
            "page": 1
        }
        
        response = _http_session.get(url, params=params, timeout=TMDB_API_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        results = data.get('results', [])
        
        movies = []
        for movie in results:
            title = movie.get('title', '')
            similarity = calculate_similarity(query, title)
            
            # Include all results; rank by similarity but don't filter
            movies.append({
                'movie_id': str(movie.get('id')),
                'title': title,
                'overview': movie.get('overview'),
                'release_date': movie.get('release_date'),
                'vote_average': movie.get('vote_average'),
                'tmdb_rating': movie.get('vote_average'),
                'popularity': movie.get('popularity'),
                'similarity_score': round(similarity, 2),
                'poster_url': f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None,
                'release_year': movie.get('release_date')[:4] if movie.get('release_date') and len(movie.get('release_date')) >= 4 else None
            })
        
        # Composite ranking: similarity (70%) + popularity (30%)
        # This prevents obscure matches from outranking popular exact/close matches
        max_popularity = max([m['popularity'] for m in movies]) if movies else 1
        for movie in movies:
            # Normalize popularity to 0-1 scale
            norm_popularity = movie['popularity'] / max_popularity if max_popularity > 0 else 0
            # Composite score: heavily favor similarity, but use popularity as tiebreaker
            movie['composite_score'] = (movie['similarity_score'] * 0.7) + (norm_popularity * 0.3)
        
        # Sort by composite score (best match first)
        movies.sort(key=lambda x: x['composite_score'], reverse=True)
        
        return movies[:limit]
    except Exception as e:
        logger.exception(f"TMDB API search failed: {query}")
        raise  # Re-raise so callers can handle the error

def generate_movie_embedding(movie_details: dict) -> list:
    """
    Generate a 1024-dimensional embedding vector for a movie using Databricks BGE Large.
    Uses direct REST API to bypass SQL Warehouse latency and string escaping issues.
    """
    try:
        overview = movie_details.get('overview', '')
        genres = ', '.join(movie_details.get('genres', []))
        keywords = ', '.join(movie_details.get('keywords', []))
        
        text_to_embed = f"{overview}. Genres: {genres}. Keywords: {keywords}"
        
        w = WorkspaceClient()
        host = w.config.host
        
        url = f"{host}/serving-endpoints/databricks-bge-large-en/invocations"
        headers = w.config.authenticate()
        headers["Content-Type"] = "application/json"
        
        payload = {
            "input": [text_to_embed]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=EMBEDDING_TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        
        # OpenAI-compatible format returns embeddings in a "data" array
        if "data" in result and len(result["data"]) > 0:
            embedding = result["data"][0]["embedding"]
            logger.info(f"✅ Generated embedding for movie '{movie_details.get('title')}' (dim: {len(embedding)})")
            return embedding
        elif "predictions" in result and len(result["predictions"]) > 0:
            embedding = result["predictions"][0]
            logger.info(f"✅ Generated embedding for movie '{movie_details.get('title')}' (dim: {len(embedding)})")
            return embedding
        else:
            logger.warning(f"❌ Unexpected embedding response format for '{movie_details.get('title')}': {result}")
            return None
            
    except Exception as e:
        logger.exception(f"Failed to generate embedding for movie '{movie_details.get('title')}': {e}")
        return None


# Reusable SQL for upserting a single movie with embedding
_MOVIE_UPSERT_SQL = """
INSERT INTO movies (
    movie_id, title, overview, release_date, runtime, 
    tmdb_rating, vote_count, genres, "cast", director, keywords, embedding, original_language
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::vector, %s)
ON CONFLICT (movie_id) DO UPDATE SET 
    title = EXCLUDED.title,
    overview = EXCLUDED.overview,
    release_date = EXCLUDED.release_date,
    runtime = EXCLUDED.runtime,
    tmdb_rating = EXCLUDED.tmdb_rating,
    vote_count = EXCLUDED.vote_count,
    genres = EXCLUDED.genres,
    "cast" = EXCLUDED."cast",
    director = EXCLUDED.director,
    keywords = EXCLUDED.keywords,
    embedding = EXCLUDED.embedding,
    original_language = EXCLUDED.original_language
"""

def _upsert_movie(movie_id: str, movie_details: dict, embedding: list = None) -> None:
    """Insert or update a movie record with optional embedding. Shared by add_to_watchlist and rate_movie."""
    embedding_str = f"[{','.join(map(str, embedding))}]" if embedding else None
    lakebase.run_write(_MOVIE_UPSERT_SQL, (
        int(movie_id),
        movie_details.get('title'),
        movie_details.get('overview'),
        movie_details.get('release_date') or None,
        movie_details.get('runtime'),
        movie_details.get('vote_average'),
        movie_details.get('vote_count', 0),
        json.dumps(movie_details.get('genres', [])),
        json.dumps(movie_details.get('cast', [])),
        movie_details.get('director'),
        json.dumps(movie_details.get('keywords', [])),
        embedding_str,
        movie_details.get('original_language')
    ))


def _generate_query_embedding(query: str) -> tuple:
    """Generate a query embedding string via REST API.
    Shared by semantic_search_movies and save_group_recommendation.
    
    Returns:
        (embedding_str, None) on success, or (None, error_msg) on failure.
    """
    try:
        # Validate query is not empty
        if not query or not query.strip():
            error_msg = "Query text is empty or whitespace-only"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        
        w = WorkspaceClient()
        host = w.config.host
        url = f"{host}/serving-endpoints/databricks-bge-large-en/invocations"
        headers = w.config.authenticate()
        headers["Content-Type"] = "application/json"
        payload = {"input": [query.strip()]}
        
        logger.info(f"🔄 Generating query embedding for: '{query[:50]}...' (length: {len(query)} chars)")
        
        # Retry logic with exponential backoff (3 attempts)
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=EMBEDDING_QUERY_TIMEOUT)
                response.raise_for_status()
                result = response.json()
                break  # Success, exit retry loop
            except requests.exceptions.HTTPError as http_err:
                if attempt < max_retries and response.status_code in [400, 429, 500, 502, 503]:
                    wait_time = 2 ** attempt  # 2, 4, 8 seconds
                    logger.warning(f"⚠️ Attempt {attempt}/{max_retries} failed with {response.status_code}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    # Final attempt failed or non-retryable error
                    raise
        
        if "data" in result:
            query_embedding = result["data"][0]["embedding"]
            logger.info("✅ Query embedding generated (OpenAI format)")
        elif "predictions" in result:
            query_embedding = result["predictions"][0]
            logger.info("✅ Query embedding generated (predictions format)")
        else:
            error_msg = f"Unexpected embedding response format: {list(result.keys())}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        
        if not _validate_embedding_str(embedding_str):
            error_msg = "Generated embedding string failed validation — possible data corruption"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        
        return embedding_str, None
    except Exception as e:
        error_msg = f"Failed to generate query embedding: {type(e).__name__}: {str(e)}"
        logger.exception(f"❌ {error_msg}")
        return None, error_msg


@RateLimiter(max_calls=40, period=1.0)  # 40 calls per second (TMDB free tier is 50/sec)
def get_tmdb_movie_details(movie_id: str) -> dict:
    """Get movie details from TMDB API."""
    try:
        api_key = get_tmdb_api_key()
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            "api_key": api_key,
            "append_to_response": "credits,keywords,reviews,videos,watch/providers"
        }
        
        response = _http_session.get(url, params=params, timeout=TMDB_API_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        cast = []
        if 'credits' in data and 'cast' in data['credits']:
            cast = [actor['name'] for actor in data['credits']['cast'][:5]]
        
        director = None
        if 'credits' in data and 'crew' in data['credits']:
            for person in data['credits']['crew']:
                if person.get('job') == 'Director':
                    director = person['name']
                    break
        
        genres = [g['name'] for g in data.get('genres', [])]
        
        release_date_str = data.get('release_date')
        release_date = release_date_str if release_date_str else None

        keywords = []
        if 'keywords' in data and 'keywords' in data['keywords']:
            keywords = [kw['name'] for kw in data['keywords']['keywords'][:10]]

        reviews = []
        if 'reviews' in data and 'results' in data['reviews']:
            for rev in data['reviews']['results'][:3]:
                content = rev.get('content', '')
                if len(content) > 300:
                    content = content[:300] + '...'
                reviews.append({'author': rev.get('author'), 'content': content})
                
        trailer_url = None
        if 'videos' in data and 'results' in data['videos']:
            for vid in data['videos']['results']:
                if vid.get('site') == 'YouTube' and vid.get('type') == 'Trailer':
                    trailer_url = f"https://www.youtube.com/watch?v={vid.get('key')}"
                    break
                    
        streaming_providers = []
        if 'watch/providers' in data and 'results' in data['watch/providers']:
            us_data = data['watch/providers']['results'].get('US', {})
            if 'flatrate' in us_data:
                streaming_providers = [p.get('provider_name') for p in us_data['flatrate']]   
        
        return {
            'movie_id': str(data.get('id')),
            'title': data.get('title'),
            'overview': data.get('overview'),
            'release_date': data.get('release_date'),
            'runtime': data.get('runtime'),
            'vote_average': data.get('vote_average'),
            'vote_count': data.get('vote_count', 0),
            'popularity': data.get('popularity'),
            'genres': genres,
            'cast': cast,
            'director': director,
            'keywords': keywords,
            'reviews': reviews,
            'trailer_url': trailer_url,
            'streaming_providers': streaming_providers,
            'poster_path': data.get('poster_path'),  # Store just the path (e.g., '/abc123.jpg'), not full URL
            'original_language': data.get('original_language')
        }
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            logger.info(f"Movie {movie_id} not found on TMDB (404)")
        else:
            logger.exception(f"TMDB API get_details failed: {movie_id}")
        return None
    except Exception as e:
        logger.exception(f"TMDB API get_details failed: {movie_id}")
        return None


def extract_search_entities(query: str) -> dict:
    """
    Extract structured search entities (genres, director, actor, max_runtime, language, year_min, year_max)
    from a user query using direct REST API call to serving endpoint.
    """
    entities = {
        "genres": [],
        "director": None,
        "actor": None,
        "max_runtime": None,
        "language": None,
        "year_min": None,
        "year_max": None
    }
    
    # 1. LLM-based extraction via REST API
    try:
        w = WorkspaceClient()
        host = w.config.host
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1)
        last_month_year = last_month_start.year
        last_month_num = last_month_start.month
        
        prompt = f"""Extract movie search filters from this user query: "{query}"

        Examples:
        Query: "best Christopher Nolan movies"
        Output: {{"genres": [], "director": "Christopher Nolan", "actor": null, "max_runtime": null, "language": null, "year_min": null, "year_max": null}}

        Query: "top sci-fi films under 2 hours"
        Output: {{"genres": ["Science Fiction"], "director": null, "actor": null, "max_runtime": 120, "language": null, "year_min": null, "year_max": null}}

        Query: "best movies released last month"
        Output: {{"genres": [], "director": null, "actor": null, "max_runtime": null, "language": null, "year_min": {last_month_year}, "year_max": {last_month_year}}}
        REASON: Today is {current_year}-{current_month:02d}. Last month was {last_month_year}-{last_month_num:02d}.

        Query: "Top romantic movies in Hindi Language"
        Output: {{"genres": ["Romance"], "director": null, "actor": null, "max_runtime": null, "language": "hi", "year_min": null, "year_max": null}}

        Query: "best Telugu action movies from 2023"
        Output: {{"genres": ["Action"], "director": null, "actor": null, "max_runtime": null, "language": "te", "year_min": 2023, "year_max": 2023}}

        Query: "recent thrillers"
        Output: {{"genres": ["Thriller"], "director": null, "actor": null, "max_runtime": null, "language": null, "year_min": {current_year - 2}, "year_max": {current_year}}}
        REASON: "recent" means last 2-3 years.

        Query: "boxing movie"
        Output: {{"genres": [], "director": null, "actor": null, "max_runtime": null, "language": null, "year_min": null, "year_max": null}}
        REASON: Sports-themed queries (boxing, football, racing, etc.) should NOT be extracted as genres.

        Now extract from: "{query}"

        CRITICAL RULES:
        - VALID GENRES ONLY: Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, War, Western
        - NEVER use "Sports" as a genre - it does not exist in TMDB!
        - For runtime: "under X minutes" = X, "under X hours" = X * 60
        - Extract directors and actors when mentioned
        - For language, use ISO 639-1 codes (e.g., 'hi' for Hindi, 'te' for Telugu, 'en' for English).
        - For year/date constraints:
          * "last month" → year_min={last_month_year}, year_max={last_month_year}
          * "released in 2023" or "from 2023" → year_min=2023, year_max=2023
          * "recent" or "new" → year_min={current_year - 2}, year_max={current_year}
          * "this year" → year_min={current_year}, year_max={current_year}
          * "since 2020" → year_min=2020, year_max={current_year}
          * If no date mentioned → year_min=null, year_max=null

        Respond ONLY with a valid JSON object matching this exact schema:
        {{
            "genres": ["list of valid TMDB genres from above"],
            "director": "full director name or null",
            "actor": "actor name or null",
            "max_runtime": integer minutes or null,
            "language": "ISO 639-1 language code or null",
            "year_min": integer year or null,
            "year_max": integer year or null
        }}
        """

        url = f"{host}/serving-endpoints/databricks-meta-llama-3-3-70b-instruct/invocations"
        headers = w.config.authenticate()
        headers["Content-Type"] = "application/json"

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE
        }
        
        logger.info(f"🔄 Calling serving endpoint via REST API for query: {query}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            raw_text = result["choices"][0]["message"]["content"]
        elif "predictions" in result:
            raw_text = result["predictions"][0]
        else:
            raise ValueError("Unexpected response format")
        
        # Strip markdown code fences
        raw_text = raw_text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        parsed = json.loads(raw_text)
        logger.info(f"✅ LLM extraction successful: {parsed}")
        
        # Whitelist genres against valid TMDB set
        valid_tmdb_genres = {
            'Action', 'Adventure', 'Animation', 'Comedy', 'Crime', 'Documentary', 
            'Drama', 'Family', 'Fantasy', 'History', 'Horror', 'Music', 
            'Mystery', 'Romance', 'Science Fiction', 'Thriller', 'War', 'Western'
        }
        extracted_genres = parsed.get("genres") or []
        safe_genres = [g for g in extracted_genres if g in valid_tmdb_genres]
        
        return {
            "genres": safe_genres,
            "director": parsed.get("director"),
            "actor": parsed.get("actor"),
            "max_runtime": parsed.get("max_runtime"),
            "language": parsed.get("language"),
            "year_min": parsed.get("year_min"),
            "year_max": parsed.get("year_max")
        }
            
    except Exception as e:
        logger.error(f"❌ LLM entity extraction failed: {type(e).__name__}: {str(e)}")
        logger.warning(f"Falling back to regex extraction")

    # 2. Rule-based Fallback
    query_lower = query.lower()
    
    # Check runtime
    runtime_match = re.search(r'(?:under|less\s+than|within|below|shorter\s+than)\s+(\d+)\s*(hour|hr|hrs|minute|min|mins)?', query_lower)
    if runtime_match:
        val = int(runtime_match.group(1))
        unit = runtime_match.group(2) or ''
        if 'h' in unit or 'hr' in unit:
            entities["max_runtime"] = val * 60
        elif 'min' in unit or (not unit and val > 10):
            entities["max_runtime"] = val
        else:
            entities["max_runtime"] = val * 60

    # Check genres
    genre_map = {
        'sci-fi': 'Science Fiction', 'scifi': 'Science Fiction', 'science fiction': 'Science Fiction',
        'action': 'Action', 'comedy': 'Comedy', 'thriller': 'Thriller', 'horror': 'Horror',
        'romance': 'Romance', 'drama': 'Drama', 'adventure': 'Adventure', 'fantasy': 'Fantasy',
        'animation': 'Animation', 'crime': 'Crime', 'mystery': 'Mystery'
    }
    for kw, g_name in genre_map.items():
        if re.search(rf'\b{kw}\b', query_lower):
            entities["genres"].append(g_name)
            
    # Basic Language Fallback
    if re.search(r'\bhindi\b', query_lower):
        entities["language"] = "hi"
    elif re.search(r'\btelugu\b', query_lower):
        entities["language"] = "te"
    elif re.search(r'\benglish\b', query_lower):
        entities["language"] = "en"
    elif re.search(r'\btamil\b', query_lower):
        entities["language"] = "ta"
    elif re.search(r'\bspanish\b', query_lower):
        entities["language"] = "es"
    
    # Year/Date Fallback
    current_year = datetime.now().year
    
    # Check for explicit year mentions (e.g., "2023", "from 2020")
    year_match = re.search(r'\b(19|20)\d{2}\b', query)
    if year_match:
        year = int(year_match.group(0))
        entities["year_min"] = year
        entities["year_max"] = year
    
    # Check for "last month"
    elif re.search(r'\blast\s+month\b', query_lower):
        last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1)
        entities["year_min"] = last_month_start.year
        entities["year_max"] = last_month_start.year
    
    # Check for "recent" or "new"
    elif re.search(r'\b(recent|new|latest)\b', query_lower):
        entities["year_min"] = current_year - 2
        entities["year_max"] = current_year
    
    # Check for "this year"
    elif re.search(r'\bthis\s+year\b', query_lower):
        entities["year_min"] = current_year
        entities["year_max"] = current_year

    logger.warning(f"Using fallback extraction result: {entities}")
    return entities
    
async def fetch_movie_details_async(session: aiohttp.ClientSession, movie_id: int, api_key: str) -> dict | None:
    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {
            "api_key": api_key,
            "append_to_response": "credits,keywords"
        }
        
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=TMDB_API_TIMEOUT)) as response:
            if response.status == 200:
                data = await response.json()
                
                genres = [g['name'] for g in data.get('genres', [])]
                
                keywords = []
                if 'keywords' in data and 'keywords' in data['keywords']:
                    keywords = [kw['name'] for kw in data['keywords']['keywords'][:5]]
                
                cast = []
                if 'credits' in data and 'cast' in data['credits']:
                    cast = [actor['name'] for actor in data['credits']['cast'][:5]]

                director = None
                if 'credits' in data and 'crew' in data['credits']:
                    for person in data['credits']['crew']:
                        if person.get('job') == 'Director':
                            director = person['name']
                            break
                
                return {
                    'movie_id': data.get('id'),
                    'title': data.get('title'),
                    'overview': data.get('overview', ''),
                    'release_date': data.get('release_date'),
                    'runtime': data.get('runtime'),
                    'tmdb_rating': data.get('vote_average'),
                    'vote_count': data.get('vote_count', 0),
                    'genres': genres,
                    'cast': cast,
                    'keywords': keywords,
                    'director': director,
                    'original_language': data.get('original_language')
                }
            else:
                logger.warning(f"Failed to fetch movie {movie_id}: HTTP {response.status}")
                return None
    except Exception as e:
        logger.warning(f"Error fetching movie {movie_id}: {e}")
        return None


async def fetch_all_movie_details_parallel(movie_ids: list[int], api_key: str) -> list[dict]:
    """
    Fetch multiple movie details from TMDB in parallel using aiohttp.
    
    Args:
        movie_ids: List of TMDB movie IDs
        api_key: TMDB API key
    
    Returns:
        List of movie detail dicts (only successful fetches)
    """
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_movie_details_async(session, movie_id, api_key) for movie_id in movie_ids]
        results = await asyncio.gather(*tasks)
        
        return [movie for movie in results if movie is not None]


def generate_embeddings_batch(movie_details_list: list[dict]) -> list[list[float]]:
    """
    Generate embeddings for multiple movies in a single batch API call.
    Uses direct REST API to bypass SQL Warehouse latency and string escaping issues.
    """
    if not movie_details_list:
        return []
        
    try:
        texts_to_embed = []
        for movie in movie_details_list:
            overview = movie.get('overview', '')
            genres = ', '.join(movie.get('genres', []))
            keywords = ', '.join(movie.get('keywords', []))
            text = f"{overview}. Genres: {genres}. Keywords: {keywords}"
            texts_to_embed.append(text)
        
        w = WorkspaceClient()
        host = w.config.host
        
        url = f"{host}/serving-endpoints/databricks-bge-large-en/invocations"
        
        headers = w.config.authenticate()
        headers["Content-Type"] = "application/json"
        
        payload = {
            "input": texts_to_embed
        }
        
        logger.info(f"🔄 Sending batch of {len(texts_to_embed)} movies to embedding endpoint...")
        logger.debug(f"Sample text (first 100 chars): {texts_to_embed[0][:100]}...")
        
        response = requests.post(url, headers=headers, json=payload, timeout=EMBEDDING_BATCH_TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        
        if "data" in result:
            # OpenAI-compatible: sort by index to preserve input order
            sorted_data = sorted(result["data"], key=lambda x: x.get("index", 0))
            embeddings = [item["embedding"] for item in sorted_data]
            logger.info(f"✅ Successfully generated {len(embeddings)} embeddings in batch")
            return embeddings
            
        elif "predictions" in result:
            embeddings = result["predictions"]
            logger.info(f"✅ Successfully generated {len(embeddings)} embeddings in batch")
            return embeddings
            
        else:
            logger.error(f"❌ Unexpected embedding response format. Keys: {list(result.keys())}")
            logger.error(f"Sample response: {str(result)[:500]}...")
            return []
            
    except Exception as e:
        logger.exception(f"Failed to generate batch embeddings: {e}")
        return []

def insert_movies_batch(movies_with_embeddings: list[tuple]) -> int:
    """
    Insert multiple movies into the database in a single batch operation.
    
    Uses ON CONFLICT DO NOTHING for automatic deduplication.
    Uses lakebase.run_write_many() with cursor.executemany() for efficiency.
    
    Args:
        movies_with_embeddings: List of tuples (movie_id, title, overview, release_date, runtime, 
        tmdb_rating, vote_count, genres, cast, director, keywords, poster_path, embedding_str, original_language)
    
    Returns:
        Number of rows inserted (excludes duplicates)
    """
    sql = """
        INSERT INTO movies (
            movie_id, title, overview, release_date, runtime, 
            tmdb_rating, vote_count, genres, "cast", director, keywords, poster_path, embedding, original_language
        )
        VALUES (
            %s, %s, %s, %s, %s, 
            %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s::vector, %s
        )
        ON CONFLICT (movie_id) DO NOTHING
        """
    
    try:
        count = lakebase.run_write_many(sql, movies_with_embeddings)
        logger.info(f"Batch inserted {count} new movies")
        return count
    except Exception as e:
        logger.exception(f"Failed to batch insert movies: {e}")
        return 0


@mcp.tool
def populate_movies_by_genre(genre: str, limit: int = 15) -> dict:
    try:
        """
        Populate the database with popular movies from a specific genre.
        
        Fetches movies from TMDB, generates embeddings, and inserts them into the database.
        Use this to seed the database before running semantic searches.
        
        Args:
            genre: Genre to populate (e.g., 'action', 'sci-fi', 'comedy', 'thriller')
            limit: Number of movies to fetch (max 20, default 15)
        
        Returns:
            Dict with status, genre, added_count, skipped_count, and processing_time_seconds
        """
        start_time = time.time()
        if limit > TMDB_MAX_POPULATE_LIMIT:
            limit = TMDB_MAX_POPULATE_LIMIT
        
        genre_map = {
            "sci-fi": "science fiction", "scifi": "science fiction", "sf": "science fiction",
            "action": "action", "comedy": "comedy", "drama": "drama", "horror": "horror",
            "thriller": "thriller", "romance": "romance", "adventure": "adventure",
            "animation": "animation", "crime": "crime", "documentary": "documentary",
            "family": "family", "fantasy": "fantasy", "history": "history",
            "music": "music", "mystery": "mystery", "war": "war", "western": "western"
        }
        tmdb_genre = genre_map.get(genre.lower().strip(), genre.lower().strip())
        
        tmdb_url = "https://api.themoviedb.org/3/discover/movie"
        api_key = get_tmdb_api_key()
        
        genre_ids = {
            "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
            "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
            "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
            "mystery": 9648, "romance": 10749, "science fiction": 878,
            "thriller": 53, "war": 10752, "western": 37
        }
        
        genre_id = genre_ids.get(tmdb_genre)
        if not genre_id:
            return {"status": "error", "message": f"Unknown genre: {genre}"}
        
        all_movies = []
        pages_to_fetch = min((limit // 20) + 1, 5)
        
        for page in range(1, pages_to_fetch + 1):
            params = {
                "api_key": api_key, "with_genres": genre_id,
                "sort_by": "popularity.desc", "page": page, "language": "en-US"
            }
            response = _http_session.get(tmdb_url, params=params, timeout=TMDB_API_TIMEOUT)
            response.raise_for_status()
            all_movies.extend(response.json().get("results", []))
            if len(all_movies) >= limit:
                break
        
        all_movies = all_movies[:limit]
        if not all_movies:
            return {"status": "no_results", "genre": genre, "added_count": 0}
        
        movie_ids = [m['id'] for m in all_movies]
        placeholders = ','.join(['%s'] * len(movie_ids))
        cache_sql = f"SELECT movie_id FROM movies WHERE movie_id IN ({placeholders}) AND embedding IS NOT NULL"
        cached_rows = lakebase.run_query(cache_sql, tuple(movie_ids))
        cached_ids = {row['movie_id'] for row in cached_rows}
        
        movies_to_add = [m for m in all_movies if m['id'] not in cached_ids]
        skipped_count = len(all_movies) - len(movies_to_add)
        
        if not movies_to_add:
            elapsed = time.time() - start_time
            return {
                "status": "success", "genre": genre, "added_count": 0,
                "skipped_count": skipped_count, "processing_time_seconds": round(elapsed, 1)
            }
        
        missing_ids = [m['id'] for m in movies_to_add]
        movie_details_list = asyncio.run(fetch_all_movie_details_parallel(missing_ids, api_key))
        
        added_count = 0
        if movie_details_list:
            embeddings = generate_embeddings_batch(movie_details_list)
            if len(embeddings) == len(movie_details_list):
                movies_with_embeddings = []
                for movie, embedding in zip(movie_details_list, embeddings):
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                    genres_str = json.dumps(movie.get('genres', []))
                    cast_str = json.dumps(movie.get("cast", []))
                    keywords_str = json.dumps(movie.get("keywords", []))
                    release_date = movie.get('release_date')
                    original_language = movie.get('original_language')
                    poster_path = movie.get('poster_path')  # Store just the path (e.g., '/abc123.jpg')
                    if not release_date:
                        release_date = None

                    movies_with_embeddings.append((
                        movie['movie_id'], movie['title'], movie['overview'], release_date,
                        movie['runtime'], movie['tmdb_rating'], movie.get('vote_count', 0), genres_str, cast_str,
                        movie['director'], keywords_str, poster_path, embedding_str, original_language
                    ))
                added_count = insert_movies_batch(movies_with_embeddings)
        
        elapsed = time.time() - start_time
        return {
            "status": "success", "genre": genre, "added_count": added_count,
            "skipped_count": skipped_count, "processing_time_seconds": round(elapsed, 1)
        }
    except Exception as e:
        logger.error(f"Error in populate_movies_by_genre: {e}")
        return {"status": "error", "message": _sanitize_error(e, "Failed to populate genre")}

# ============================================================================
# MCP TOOLS
# ============================================================================
@mcp.tool
def get_current_user() -> dict:
    try:
        email = _get_end_user_email()
        _ensure_user_exists(email)
        
        headers = _request_context.get()
        forwarded_user = headers.get('x-forwarded-user')
        
        return {
            "status": "success",
            "user_name": email,
            "email": email,
            "source": "request_header" if forwarded_user else "service_principal",
        }
    except Exception as e:
        logger.exception("Failed to get current user")
        return {
            "status": "error",
            "message": f"Failed to get current user: {str(e)}"
        }


@mcp.tool
def list_all_users() -> dict:
    """
    List all users across all groups (for user switching dropdown).
    
    Returns all unique users who are members of any group, sorted by username.
    Useful for populating a user selection dropdown in the UI.
    
    Returns:
        Dict with status and list of users with their email, username, and group memberships
    """
    try:
        sql = """
        SELECT DISTINCT 
            u.email as user_id,
            u.email,
            u.username,
            STRING_AGG(DISTINCT g.group_name, ', ') as groups,
            COUNT(DISTINCT g.group_id) as group_count
        FROM users u
        LEFT JOIN group_members gm ON u.email = gm.user_id
        LEFT JOIN groups g ON gm.group_id = g.group_id
        GROUP BY u.email, u.username
        ORDER BY u.username ASC
        """
        
        results = lakebase.run_query(sql)
        
        users = []
        for row in results:
            users.append({
                "email": row['email'],
                "username": row['username'],
                "groups": row['groups'],
                "group_count": row['group_count']
            })
        
        return {
            "status": "success",
            "count": len(users),
            "users": users
        }
    
    except Exception as e:
        logger.exception("Failed to list all users")
        return {
            "status": "error",
            "message": f"Failed to list users: {str(e)}"
        }


@mcp.tool
def switch_user(user_name: str) -> dict:
    """
    Search for a user by name or email across all group members.
    Returns user information if found, allowing the frontend to switch context.
    
    Use when:
    - User says "switch to [name]"
    - User says "update user to [name]"
    - User says "change user to [name]"
    
    Args:
        user_name: Name or email to search for (case-insensitive partial match)
    
    Returns:
        Dict with status, matched user details, and all groups they belong to
    """
    try:
        user_name_lower = user_name.lower().strip()
        logger.info(f"🔄 Searching for user matching: {user_name}")
        
        # Search all group members for matching users
        sql = """
        SELECT DISTINCT 
            gm.user_id,
            u.email,
            u.username,
            STRING_AGG(DISTINCT g.group_name, ', ') as groups
        FROM group_members gm
        LEFT JOIN users u ON gm.user_id = u.email
        LEFT JOIN groups g ON gm.group_id = g.group_id
        WHERE LOWER(gm.user_id) LIKE %s 
           OR LOWER(u.email) LIKE %s 
           OR LOWER(u.username) LIKE %s
        GROUP BY gm.user_id, u.email, u.username
        LIMIT 5
        """
        
        search_pattern = f"%{user_name_lower}%"
        results = lakebase.run_query(sql, (search_pattern, search_pattern, search_pattern))
        
        if results:
            matched_user = results[0]
            user_email = matched_user.get('email') or matched_user.get('user_id')
            username = matched_user.get('username') or user_email.split('@')[0] if '@' in user_email else user_email
            
            logger.info(f"✅ Found user: {username} ({user_email})")
            
            return {
                "status": "success",
                "user_email": user_email,
                "username": username,
                "groups": matched_user.get('groups', ''),
                "message": f"✅ Found user: {username}",
                "all_matches": [{"email": r.get('email'), "username": r.get('username')} for r in results]
            }
        else:
            logger.warning(f"⚠️ No user found matching: {user_name}")
            
            current_user = _get_end_user_email()
            groups_sql = """
            SELECT group_id, group_name, description
            FROM groups
            WHERE created_by = %s AND is_active = true
            ORDER BY created_at DESC
            """
            available_groups = lakebase.run_query(groups_sql, (current_user,))
            
            return {
                "status": "not_found",
                "searched_for": user_name,
                "message": f"❌ No user found matching '{user_name}' in any group members.",
                "action_needed": "create_new_user",
                "available_groups": available_groups,
                "instructions": {
                    "step_1": "Ask the user if they want to create a new user with this name",
                    "step_2": "If yes, ask for the user's email address",
                    "step_3": "Ask which group to add the new user to (show available_groups)",
                    "step_4": "Call create_and_add_user_to_group with the details"
                }
            }
    
    except Exception as e:
        logger.exception(f"Failed to search for user: {user_name}")
        return {
            "status": "error",
            "message": f"Failed to search for user: {str(e)}"
        }


@mcp.tool
def create_user(user_name: str, user_email: str) -> dict:
    """
    Create a new user account.
    
    Creates a user without adding them to any group. User can be added to groups later
    using add_group_member().
    
    Args:
        user_name: Username/display name for the new user
        user_email: Email address for the new user (must be unique)
    
    Returns:
        Dict with status, user_id, username, and email
    """
    try:
        logger.info(f"🆕 Creating new user: {user_name} ({user_email})")
        
        if not validate_email(user_email):
            return {
                "status": "error",
                "message": f"Invalid email format: {user_email}. Please provide a valid email address (e.g., user@example.com)."
            }
        
        check_sql = "SELECT email, username FROM users WHERE email = %s"
        existing = lakebase.run_query(check_sql, (user_email,))
        
        if existing:
            return {
                "status": "error",
                "message": f"User with email {user_email} already exists.",
                "existing_user": existing[0]
            }
        
        create_user_sql = """
        INSERT INTO users (user_id, username, email)
        VALUES (%s, %s, %s)
        """
        lakebase.run_write(create_user_sql, (user_email, user_name, user_email))
        logger.info(f"✅ Created user: {user_name} ({user_email})")
        
        return {
            "status": "success",
            "message": f"✅ Created user '{user_name}' successfully",
            "user_id": user_email,
            "username": user_name,
            "email": user_email
        }
    
    except Exception as e:
        logger.exception(f"Failed to create user: {user_name}")
        return {
            "status": "error",
            "message": f"Failed to create user: {str(e)}"
        }


@mcp.tool
def create_and_add_user_to_group(user_name: str, user_email: str, group_id: str) -> dict:
    """
    Convenience function: Create a new user and add them to a group in one step.
    
    This is a wrapper that calls create_user() followed by add_group_member().
    Use this when you want to create and add a user in a single operation.
    
    Args:
        user_name: Username/display name for the new user
        user_email: Email address for the new user (must be unique)
        group_id: Group ID to add the user to
    
    Returns:
        Dict with status, created user details, and membership info
    """
    try:
        logger.info(f"🆕 Creating new user and adding to group: {user_name} ({user_email})")
        
        # Step 1: Create the user
        create_result = create_user(user_name, user_email)
        
        if create_result.get("status") != "success":
            return create_result
        
        user_id = create_result.get("user_id")
        
        # Step 2: Add user to group
        add_result = add_group_member(group_id, user_id)
        
        if add_result.get("status") != "success":
            return {
                "status": "partial_success",
                "message": f"User '{user_name}' created but failed to add to group: {add_result.get('message')}",
                "user_created": True,
                "user_id": user_id,
                "user_email": user_email,
                "username": user_name,
                "group_added": False
            }
        
        return {
            "status": "success",
            "message": f"✅ Created user '{user_name}' and added to group '{add_result.get('group_name')}'",
            "user_id": user_id,
            "user_email": user_email,
            "username": user_name,
            "group_id": group_id,
            "group_name": add_result.get("group_name"),
            "membership_id": add_result.get("membership_id")
        }
    
    except Exception as e:
        logger.exception(f"Failed to create and add user: {user_name}")
        return {
            "status": "error",
            "message": f"Failed to create and add user: {str(e)}"
        }
        
@mcp.tool
def search_movies(
    query: str, 
    limit: int = 10,
    group_id: Optional[str] = None,
    exclude_watched: bool = True,
    exclude_disliked: bool = False,
    min_rating_threshold: float = 5.0
) -> dict:
    """
    Search for movies by SPECIFIC title only (e.g., 'Inception', 'The Dark Knight', 'Interstellar').
    
    Do NOT use for broad queries, genres, or thematic recommendations (e.g., 'top sci-fi movies', 'best action films').
    
    Use semantic_search_movies instead for:
    - Genre-based queries ('best sci-fi movies')
    - Thematic searches ('mind-bending thrillers')
    - Concept-based queries ('movies about time travel')
    - Quality descriptors ('top rated action films')
    
    By default, excludes already-watched movies when group_id is provided.
    Set exclude_watched=False to include watched movies in results.
    
    Args:
        query: Specific movie title to search for
        limit: Maximum number of results to return (default: 10)
        group_id: Optional group ID to filter by watchlist/ratings
        exclude_watched: If True, exclude movies marked as watched
        exclude_disliked: If True, exclude movies with low ratings
        min_rating_threshold: Minimum rating threshold for exclusion (default: 5.0)
    
    Returns:
        Dict with status, query, count, movies list, and filtering info
    """
    try:
        # ⚠️ VALIDATION: Detect misrouted group management commands
        # If the query contains group management keywords, reject it immediately
        group_mgmt_pattern = r'\b(create|make|new|add|start|setup|set\s+up)\s+(a\s+)?group\b'
        if re.search(group_mgmt_pattern, query, re.IGNORECASE):
            return {
                "status": "error",
                "error_type": "wrong_tool",
                "message": f"❌ This looks like a group management command, not a movie search.\n\nTo create a group, use: create_group(group_name='...')\nTo list groups, use: list_my_groups()",
                "query": query,
                "suggested_tool": "create_group"
            }
        
        # Strip non-title keywords before querying TMDB search
        clean_query = re.sub(r'\b(top|best|good|great|movies?|films?|recommend(ations?)?)\b', '', 
            query, 
            flags=re.IGNORECASE
        ).strip()

        if not clean_query:
            clean_query = query
        
        movies = search_tmdb_movies(clean_query, limit * TMDB_SEARCH_MULTIPLIER)
        
        if group_id and (exclude_watched or exclude_disliked):
            filtered_movies = []
            
            for movie in movies:
                movie_id = movie['movie_id']
                
                should_exclude = False
                
                if exclude_watched:
                    watched_sql = """
                    SELECT COUNT(*) as count
                    FROM watchlist_items
                    WHERE group_id = %s AND movie_id = %s AND status = 'watched'
                    """
                    watched_result = lakebase.run_query(watched_sql, (group_id, int(movie_id)))
                    if watched_result and watched_result[0]['count'] > 0:
                        should_exclude = True
                        logger.info(f"Excluding watched movie: {movie['title']}")
                
                if exclude_disliked and not should_exclude:
                    disliked_sql = """
                    SELECT MIN(rating) as min_rating
                    FROM ratings
                    WHERE group_id = %s AND movie_id = %s
                    """
                    disliked_result = lakebase.run_query(disliked_sql, (group_id, int(movie_id)))
                    if disliked_result and disliked_result[0]['min_rating'] is not None:
                        if disliked_result[0]['min_rating'] < min_rating_threshold:
                            should_exclude = True
                            logger.info(f"Excluding disliked movie: {movie['title']} (min rating: {disliked_result[0]['min_rating']})")
                
                if not should_exclude:
                    filtered_movies.append(movie)
                
                if len(filtered_movies) >= limit:
                    break
            
            movies = filtered_movies
        else:
            movies = movies[:limit]
        
        return {
            "status": "success",
            "query": query,
            "count": len(movies),
            "movies": movies,
            "filtered": (exclude_watched or exclude_disliked) and group_id is not None
        }
    except Exception as e:
        logger.exception(f"Failed to search movies: {query}")
        return {
            "status": "error",
            "message": f"Failed to search movies: {str(e)}"
        }


# TMDB genre ID mapping (shared by semantic_search_movies and populate_movies_by_genre)
_TMDB_GENRE_ID_MAP = {
    'Action': 28, 'Adventure': 12, 'Animation': 16, 'Comedy': 35,
    'Crime': 80, 'Documentary': 99, 'Drama': 18, 'Family': 10751,
    'Fantasy': 14, 'History': 36, 'Horror': 27, 'Music': 10402,
    'Mystery': 9648, 'Romance': 10749, 'Science Fiction': 878,
    'Thriller': 53, 'War': 10752, 'Western': 37
}

def _fetch_tmdb_candidates(clean_query: str, entities: dict, api_key: str) -> list:
    """Fetch candidate movie IDs from TMDB using multiple strategies.
    
    Strategies:
        A: Direct title search
        D: Keyword discovery (themes like 'heist', 'boxing')
        B: Person search (director/actor filmography)
        C: Genre discovery (genre-filtered popular movies)
    
    Returns:
        List of deduplicated TMDB movie IDs.
    """
    candidate_movies = []
    
    # Strategy A: Direct Search (catches specific movie titles hidden in the prompt)
    if clean_query:
        search_res = _http_session.get(
            "https://api.themoviedb.org/3/search/movie",
            params={"api_key": api_key, "query": clean_query, "page": 1},
            timeout=TMDB_API_TIMEOUT
        )
        if search_res.ok:
            candidate_movies.extend(search_res.json().get('results', [])[:CANDIDATE_LIMIT_SEARCH])
    
    # Strategy D: Keyword Discovery (catches themes like 'heist', 'boxing')
    if clean_query:
        kw_res = _http_session.get(
            "https://api.themoviedb.org/3/search/keyword",
            params={"api_key": api_key, "query": clean_query},
            timeout=TMDB_API_TIMEOUT
        )
        if kw_res.ok and kw_res.json().get('results'):
            top_kw_id = kw_res.json()['results'][0]['id']
            disc_res = _http_session.get(
                "https://api.themoviedb.org/3/discover/movie",
                params={"api_key": api_key, "with_keywords": top_kw_id, "sort_by": "popularity.desc"},
                timeout=TMDB_API_TIMEOUT
            )
            if disc_res.ok:
                candidate_movies.extend(disc_res.json().get('results', [])[:CANDIDATE_LIMIT_KEYWORD])
    
    # Strategy B: Person Search (if a director or actor was detected)
    person_name = entities.get("director") or entities.get("actor")
    if person_name:
        person_res = _http_session.get(
            "https://api.themoviedb.org/3/search/person",
            params={"api_key": api_key, "query": person_name},
            timeout=TMDB_API_TIMEOUT
        )
        if person_res.ok and person_res.json().get('results'):
            person_id = person_res.json()['results'][0]['id']
            credits_res = _http_session.get(
                f"https://api.themoviedb.org/3/person/{person_id}/movie_credits",
                params={"api_key": api_key},
                timeout=TMDB_API_TIMEOUT
            )
            if credits_res.ok:
                crew = credits_res.json().get('crew', [])
                cast = credits_res.json().get('cast', [])
                person_movies = [m for m in crew if m.get('job') == 'Director'] or cast
                candidate_movies.extend(person_movies[:CANDIDATE_LIMIT_PERSON])
    
    # Strategy C: Genre Discovery (if specific genres were requested)
    genre_ids = [_TMDB_GENRE_ID_MAP[g] for g in entities.get("genres", []) if g in _TMDB_GENRE_ID_MAP]
    if genre_ids:
        tmdb_params = {
            "api_key": api_key,
            "sort_by": "popularity.desc",
            "language": "en-US",
            "page": 1,
            "with_genres": ','.join(map(str, genre_ids))
        }
        if entities.get("language"):
            tmdb_params["with_original_language"] = entities["language"]
        discover_res = _http_session.get(
            "https://api.themoviedb.org/3/discover/movie",
            params=tmdb_params,
            timeout=TMDB_API_TIMEOUT
        )
        if discover_res.ok:
            candidate_movies.extend(discover_res.json().get('results', [])[:CANDIDATE_LIMIT_GENRE])
    
    # Deduplicate by movie ID
    unique_candidates = {m['id']: m for m in candidate_movies if 'id' in m}.values()
    return [m['id'] for m in unique_candidates]

@mcp.tool
def semantic_search_movies(
    query: str, 
    limit: int = 5,
    group_id: Optional[str] = None,
    exclude_watched: bool = True,
    exclude_disliked: bool = False,
    min_rating_threshold: float = 5.0
) -> dict:
    """
    Find movie recommendations based on concepts, descriptions, themes, directors, 
    actors, or genres (e.g., 'best sci-fi movies under 2 hours', 'Christopher Nolan thrillers').
    
    By default, excludes already-watched movies when group_id is provided.
    Set exclude_watched=False to include watched movies in results.
    """
    try:
        # ⚠️ VALIDATION: Detect misrouted group management commands
        # If the query contains group management keywords, reject it immediately
        group_mgmt_pattern = r'\b(create|make|new|add|start|setup|set\s+up)\s+(a\s+)?group\b'
        if re.search(group_mgmt_pattern, query, re.IGNORECASE):
            return {
                "status": "error",
                "error_type": "wrong_tool",
                "message": f"❌ This looks like a group management command, not a movie search.\n\nTo create a group, use: create_group(group_name='...')\nTo list groups, use: list_my_groups()",
                "query": query,
                "suggested_tool": "create_group"
            }
        
        start_time = time.time()
        api_key = get_tmdb_api_key()

        # ==========================================
        # STEP 1: DETECT QUALITY QUERY & EXTRACT ENTITIES
        # ==========================================
        quality_keywords = r'\b(top|best|popular|greatest|highly.rated|recommend|must.watch|classic)\b'
        is_quality_query = bool(re.search(quality_keywords, query, re.IGNORECASE))
        
        if is_quality_query:
            logger.info(f"🎯 Detected quality query: '{query}' - will prioritize highly-rated movies")
        
        entities = extract_search_entities(query)
        logger.info(f"Extracted search entities: {entities}")

        # Strip non-title keywords for TMDB search
        clean_query = re.sub(
            r'\b(top|best|good|great|movies?|films?|recommend(ations?)?|suggest|show|me)\b', 
            '', 
            query, 
            flags=re.IGNORECASE
        ).strip()

        # ==========================================
        # STEP 1b: FETCH TMDB CANDIDATES (Strategies A/B/C/D)
        # Uses multiple TMDB search strategies to gather candidate movies.
        # ==========================================
        movie_ids = _fetch_tmdb_candidates(clean_query, entities, api_key)

        # ==========================================
        # STEP 2: ENRICH DB — fetch details + embeddings for missing movies
        # ==========================================
        if movie_ids:
            placeholders = ','.join(['%s'] * len(movie_ids))
            cache_sql = f"SELECT movie_id FROM movies WHERE movie_id IN ({placeholders}) AND embedding IS NOT NULL"
            cached_rows = lakebase.run_query(cache_sql, tuple(movie_ids))
            cached_ids = {row['movie_id'] for row in cached_rows}
            missing_ids = [mid for mid in movie_ids if mid not in cached_ids]

            if missing_ids:
                movie_details_list = asyncio.run(fetch_all_movie_details_parallel(missing_ids, api_key))
                if movie_details_list:
                    embeddings = generate_embeddings_batch(movie_details_list)
                    if len(embeddings) == len(movie_details_list):
                        movies_with_embeddings = []
                        for movie, embedding in zip(movie_details_list, embeddings):
                            embedding_str = f"[{','.join(map(str, embedding))}]"
                            genres_str = json.dumps(movie.get('genres', []))
                            cast_str = json.dumps(movie.get('cast', []))
                            keywords_str = json.dumps(movie.get('keywords', []))
                            
                            release_date = movie.get('release_date')
                            poster_path = movie.get('poster_path')  # Store just the path (e.g., '/abc123.jpg')
                            if not release_date:
                                release_date = None
                            movies_with_embeddings.append((
                                movie['movie_id'], movie['title'], movie['overview'], release_date,
                                movie['runtime'], movie['tmdb_rating'], movie.get('vote_count', 0), genres_str, cast_str,
                                movie['director'], keywords_str, poster_path, embedding_str, movie.get('original_language')
                            ))
                        insert_movies_batch(movies_with_embeddings)

        # ==========================================
        # STEP 3: GENERATE QUERY EMBEDDING
        # Convert the user's raw query into a 1024-dim vector via _generate_query_embedding helper.
        # ==========================================
        logger.info(f"🔄 Generating query embedding for: '{query}' (length: {len(query)} chars)")
        
        embedding_str, error_msg = _generate_query_embedding(query)
        if error_msg:
            return {"status": "error", "message": error_msg}

        # ==========================================
        # STEP 4: DYNAMIC HYBRID SQL QUERY
        # Combine metadata filters, preference filters, and vector similarity.
        # ==========================================
        metadata_clauses = []
        user_filter_clauses = ["embedding IS NOT NULL"]
        query_params = []
        user_filter_params = []
        
        # -- Quality filter for "top/best" queries --
        if is_quality_query:
            user_filter_clauses.append(f"tmdb_rating >= {QUALITY_MIN_RATING}")
            user_filter_clauses.append(f"vote_count >= {QUALITY_MIN_VOTE_COUNT}")
            logger.info(f"🌟 Quality filter enabled: tmdb_rating >= {QUALITY_MIN_RATING} AND vote_count >= {QUALITY_MIN_VOTE_COUNT}")

        # -- Strict metadata filters --
        
        # 1. Director
        if entities.get("director"):
            metadata_clauses.append("director ILIKE %s")
            query_params.append(f"%{entities['director']}%")

        # 2. Actor / Cast (Checks both the cast JSON array and the overview text)
        if entities.get("actor"):
            metadata_clauses.append("(\"cast\"::text ILIKE %s OR overview ILIKE %s)")
            query_params.extend([f"%{entities['actor']}%", f"%{entities['actor']}%"])

        # 3. Genres
        if entities.get("genres"):
            genre_conditions = []
            for g in entities["genres"]:
                genre_conditions.append("genres::text ILIKE %s")
                query_params.append(f"%{g}%")
            metadata_clauses.append(f"({' OR '.join(genre_conditions)})")

        # 4. Runtime
        if entities.get("max_runtime"):
            metadata_clauses.append("runtime > 0 AND runtime <= %s")
            query_params.append(entities["max_runtime"])
        
        # 5. Language
        if entities.get("language"):
            metadata_clauses.append("original_language = %s")
            query_params.append(entities["language"])
        
        # 6. Year Range (Release Date)
        if entities.get("year_min") or entities.get("year_max"):
            year_min = entities.get("year_min")
            year_max = entities.get("year_max")
            
            if year_min and year_max:
                metadata_clauses.append("EXTRACT(YEAR FROM release_date) BETWEEN %s AND %s")
                query_params.extend([year_min, year_max])
                logger.info(f"📅 Year filter: {year_min} to {year_max}")
            elif year_min:
                metadata_clauses.append("EXTRACT(YEAR FROM release_date) >= %s")
                query_params.append(year_min)
                logger.info(f"📅 Year filter: >= {year_min}")
            elif year_max:
                metadata_clauses.append("EXTRACT(YEAR FROM release_date) <= %s")
                query_params.append(year_max)
                logger.info(f"📅 Year filter: <= {year_max}")

        # -- User preference filters (exclusions) --
        
        # 7. Exclude Watched Movies
        if exclude_watched and group_id:
            user_filter_clauses.append("""
                movie_id NOT IN (
                    SELECT movie_id FROM watchlist_items 
                    WHERE group_id = %s AND status = 'watched'
                )
            """)
            user_filter_params.append(group_id)
            
        # 8. Exclude Disliked Movies
        if exclude_disliked and group_id:
            user_filter_clauses.append("""
                movie_id NOT IN (
                    SELECT movie_id FROM ratings 
                    WHERE group_id = %s AND rating < %s
                )
            """)
            user_filter_params.extend([group_id, min_rating_threshold])

        all_clauses = user_filter_clauses + metadata_clauses
        where_clause = " AND ".join(all_clauses)
        all_params = user_filter_params + query_params
        
        # ==========================================
        # GENRE PRIMARY MATCH SCORING
        # Prioritize movies where the detected genre is the PRIMARY (first) genre,
        # preventing e.g. action films with romance subplots from dominating
        # pure "romantic movies" queries.
        # ==========================================
        has_genre_filter = bool(entities.get("genres")) and len(entities.get("genres", [])) > 0
        primary_genre = None
        
        if has_genre_filter:
            primary_genre = entities["genres"][0]
            # Sanitize for SQL interpolation (defense-in-depth)
            primary_genre = re.sub(r"[^a-zA-Z\s]", "", primary_genre)
            # genres::json->>0 extracts first array element; %% escapes % for psycopg2
            genre_match_clause = f"""
                CASE 
                    WHEN genres::json->>0 ILIKE '%%{primary_genre}%%' THEN 0.0
                    WHEN genres::text ILIKE '%%{primary_genre}%%' THEN 0.5
                    ELSE 1.0
                END
            """
            logger.info(f"🎬 Genre primary match enabled: prioritizing movies where '{primary_genre}' is the PRIMARY genre")
        else:
            genre_match_clause = "0.0"  # No genre filter = no penalty
        
        # Dynamic hybrid formula weights:
        #   With genre:    quality → 30/35/35, regular → 30/45/25 (genre/semantic/rating)
        #   Without genre: quality → 50/50,    regular → 70/30   (semantic/rating)
        if has_genre_filter:
            genre_weight = 0.30
            semantic_weight = 0.35 if is_quality_query else 0.45
            rating_weight = 0.35 if is_quality_query else 0.25
        else:
            genre_weight = 0.0
            semantic_weight = 0.5 if is_quality_query else 0.7
            rating_weight = 0.5 if is_quality_query else 0.3
        
        sql = f"""
        SELECT 
            movie_id, title, overview, runtime, tmdb_rating, genres::text as genres, director,
            release_date, original_language, poster_path,
            (embedding <=> '{embedding_str}'::vector) as distance,
            ({genre_weight} * ({genre_match_clause})) +
            ({semantic_weight} * (embedding <=> '{embedding_str}'::vector)) + 
            ({rating_weight} * (10 - COALESCE(tmdb_rating, 5.0)) / 10.0) as hybrid_score
        FROM movies 
        WHERE {where_clause} 
        ORDER BY hybrid_score ASC
        LIMIT {limit}
        """
        
        results = lakebase.run_query(sql, tuple(all_params))
        used_fallback = False

        # ==========================================
        # STEP 5: FALLBACK — drop strict filters, keep exclusions, retry with pure semantic
        # ==========================================
        if not results and metadata_clauses:
            used_fallback = True
            fallback_where = " AND ".join(user_filter_clauses)
            
            # Use same dynamic weights for fallback (including genre_match if applicable)
            fallback_sql = f"""
            SELECT 
                movie_id, title, overview, runtime, tmdb_rating, genres::text as genres, director,
                release_date, original_language, poster_path,
                (embedding <=> '{embedding_str}'::vector) as distance,
                ({genre_weight} * ({genre_match_clause})) +
                ({semantic_weight} * (embedding <=> '{embedding_str}'::vector)) + 
                ({rating_weight} * (10 - COALESCE(tmdb_rating, 5.0)) / 10.0) as hybrid_score
            FROM movies 
            WHERE {fallback_where}
            ORDER BY hybrid_score ASC
            LIMIT {limit}
            """
            results = lakebase.run_query(fallback_sql, tuple(user_filter_params))
            logger.warning(f"⚠️ No exact matches found for query '{query}' with filters {entities}. Using fallback semantic search.")

        movies = []
        for row in results:
            # Format poster URL (poster_path from DB is just the path, not full URL)
            poster_path = row.get('poster_path')
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            # FALLBACK: If poster_path is missing in DB, fetch from TMDB API
            if not poster_path:
                movie_id = str(row['movie_id'])
                try:
                    tmdb_details = tmdb_get_movie_details(movie_id)
                    if tmdb_details and tmdb_details.get('poster_path'):
                        poster_path = tmdb_details['poster_path']
                        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                        logger.info(f"✅ Fetched missing poster for movie_id {movie_id} from TMDB API")
                        
                        # Update database to cache the poster_path for future queries
                        try:
                            update_sql = "UPDATE movies SET poster_path = %s WHERE movie_id = %s"
                            lakebase.run_write(update_sql, (poster_path, int(movie_id)))
                            logger.info(f"✅ Updated poster_path in database for movie_id {movie_id}")
                        except Exception as update_err:
                            logger.warning(f"⚠️ Failed to update poster_path in DB for movie_id {movie_id}: {update_err}")
                except Exception as fetch_err:
                    logger.warning(f"⚠️ Failed to fetch poster from TMDB for movie_id {movie_id}: {fetch_err}")
            
            # Extract year from release_date
            release_date = row.get('release_date')
            release_year = None
            if release_date:
                release_year_str = str(release_date)[:4] if len(str(release_date)) >= 4 else None
                if release_year_str:
                    release_year = int(release_year_str)
            
            movies.append({
                'movie_id': str(row['movie_id']),
                'title': row['title'],
                'overview': row['overview'],
                'runtime': row['runtime'],
                'tmdb_rating': row['tmdb_rating'],
                'genres': row['genres'],
                'director': row['director'],
                'poster_url': poster_url,
                'release_year': release_year,
                'release_date': release_date,
                'original_language': row.get('original_language'),
                'similarity_score': round(1.0 - row['distance'], 3),
                'hybrid_score': round(float(row['hybrid_score']), 3)
            })

        elapsed = time.time() - start_time
        return {
            "status": "success",
            "query": query,
            "detected_entities": entities,
            "count": len(movies),
            "movies": movies,
            "used_fallback": used_fallback,
            "fallback_message": f"No exact matches found for your specific criteria. Showing similar movies instead." if used_fallback else None,
            "quality_mode_enabled": is_quality_query,
            "quality_mode_info": f"Prioritizing highly-rated movies (tmdb_rating >= {QUALITY_MIN_RATING}, vote_count >= {QUALITY_MIN_VOTE_COUNT}) with {int(semantic_weight*100)}% semantic + {int(rating_weight*100)}% rating weighting" if is_quality_query else None,
            "genre_primary_match_enabled": has_genre_filter,
            "genre_primary_match_info": f"Prioritizing movies where '{primary_genre}' is the PRIMARY genre (30% genre + {int(semantic_weight*100)}% semantic + {int(rating_weight*100)}% rating)" if has_genre_filter and primary_genre else None,
            "processing_time_seconds": round(elapsed, 2)
        }

    except Exception as e:
        logger.exception(f"Failed to semantic search movies: {query}")
        return {"status": "error", "message": _sanitize_error(e, "Search failed")}

@mcp.tool
def get_movie_details(movie_id: str) -> dict:
    """
    Get detailed information about a specific movie from TMDB using its TMDB movie ID.
    
    IMPORTANT: This tool requires a NUMERIC TMDB movie ID (e.g., '437617'), NOT a movie title.
    
    **Correct workflow when user asks about a movie by title:**
    1. First call search_movies(query='<movie title>') to find the movie
    2. Extract the movie_id from the search results
    3. Then call get_movie_details(movie_id='<numeric_id>')
    
    Use when:
    - You already have the TMDB movie ID from a search
    - User asks for details about a movie you previously searched for
    - You need full cast, director, reviews, trailers, etc.
    
    Args:
        movie_id: TMDB movie ID (numeric string like '437617', NOT 'Arjun Reddy')
    
    Returns:
        A dict with full movie details including cast, director, keywords, reviews, trailer, streaming providers
    """
    try:
        movie = get_tmdb_movie_details(movie_id)
        
        if movie:
            # Format poster URL (poster_path from TMDB is just the path, not full URL)
            poster_path = movie.get('poster_path')
            if poster_path:
                movie['poster_url'] = f"https://image.tmdb.org/t/p/w500{poster_path}"
            else:
                movie['poster_url'] = None
            
            return {
                "status": "success",
                "movie": movie
            }
        else:
            return {
                "status": "not_found",
                "message": f"Movie {movie_id} not found on TMDB"
            }
    except Exception as e:
        logger.exception(f"Failed to get movie details: {movie_id}")
        return {
            "status": "error",
            "message": f"Failed to get movie details: {str(e)}"
        }


@mcp.tool
def add_to_watchlist(movie_id: str, group_id: str = None, email: str = 'rajesh@gmail.com') -> dict:
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        if not group_id:
            sql = """
            SELECT g.group_id, g.group_name, g.description, g.created_at, COUNT(DISTINCT gm.user_id) as member_count
            FROM groups g LEFT JOIN group_members gm ON g.group_id = gm.group_id
            WHERE g.created_by = %s AND g.is_active = true GROUP BY g.group_id, g.group_name, g.description, g.created_at
            ORDER BY g.created_at DESC
            """
            groups = lakebase.run_query(sql, (user_email,))
            
            if len(groups) == 0:
                return {"status": "no_groups", "message": "You don't have any groups yet. Create a group first."}
            elif len(groups) == 1:
                group_id = groups[0]['group_id']
            else:
                formatted_groups = [
                    {
                        "number": idx,
                        "group_id": g['group_id'],
                        "group_name": g['group_name'],
                        "description": g.get('description') or "No description",
                        "created_at": g['created_at'].strftime("%Y-%m-%d %H:%M") if g.get('created_at') else "Unknown",
                        "member_count": g.get('member_count', 0)
                    }
                    for idx, g in enumerate(groups, 1)
                ]
                return {"status": "needs_group_selection", "available_groups": formatted_groups, "movie_id": movie_id}
        
        # 🔒 AUTHORIZATION CHECK: Verify user is a member of this group
        membership_check_sql = """
        SELECT COUNT(*) as is_member
        FROM group_members
        WHERE group_id = %s AND user_id = %s
        """
        membership_result = lakebase.run_query(membership_check_sql, (group_id, user_email))
        is_member = membership_result[0]['is_member'] > 0 if membership_result else False
        
        if not is_member:
            # Get group name for better error message
            group_name_sql = "SELECT group_name FROM groups WHERE group_id = %s"
            group_name_result = lakebase.run_query(group_name_sql, (group_id,))
            group_name = group_name_result[0]['group_name'] if group_name_result else group_id
            
            logger.warning(f"🚫 Authorization failed: {user_email} is not a member of group {group_id}")
            return {
                "status": "error",
                "error_type": "authorization_failed",
                "message": f"❌ You cannot add movies to '{group_name}' because you are not a member of this group.\n\nPlease ask the group owner to add you as a member first."
            }
        
        # 🔍 DUPLICATE CHECK: Check if movie already exists in watchlist FIRST
        check_existing_sql = "SELECT status FROM watchlist_items WHERE group_id = %s AND movie_id = %s"
        existing_result = lakebase.run_query(check_existing_sql, (group_id, int(movie_id)))
        
        if existing_result:
            # Movie already exists - return error based on status
            current_status = existing_result[0]['status']
            
            if current_status == 'watched':
                logger.warning(f"⚠️ Movie {movie_id} already watched in group {group_id}")
                return {
                    "status": "error",
                    "message": f"This movie has already been watched by your group. Check your watch history!",
                    "already_exists": True,
                    "current_status": "watched"
                }
            else:  # status == 'pending'
                logger.warning(f"⚠️ Movie {movie_id} already in pending watchlist for group {group_id}")
                return {
                    "status": "error",
                    "message": f"This movie is already in your pending watchlist",
                    "already_exists": True,
                    "current_status": "pending"
                }
        
        # Movie not in watchlist - proceed with adding it
        movie_details = get_tmdb_movie_details(movie_id)
        if not movie_details:
            return {"status": "error", "message": f"Movie {movie_id} not found on TMDB"}
        
        embedding = generate_movie_embedding(movie_details)
        _upsert_movie(movie_id, movie_details, embedding)
        
        # Get user_id (which is the email in this system)
        user_id = _get_user_id_from_email(user_email)
        
        watchlist_id = _generate_id_with_prefix(movie_details.get('title'), 'watchlist_items', 'watchlist_id')
        watchlist_sql = """
        INSERT INTO watchlist_items (watchlist_id, group_id, movie_id, added_by, status)
        VALUES (%s, %s, %s, %s, 'pending') 
        ON CONFLICT (group_id, movie_id) DO NOTHING
        """
        
        logger.info(f"📝 Adding to watchlist: movie_id={movie_id}, group_id={group_id}, user_id={user_id}")
        rows_affected = lakebase.run_write(watchlist_sql, (watchlist_id, group_id, int(movie_id), user_id))
        logger.info(f"✅ Watchlist write completed: {rows_affected} rows affected")
        
        if rows_affected == 0:
            # Race condition: another request inserted the same movie between our check and insert
            logger.warning(f"⚠️ Race condition detected: movie {movie_id} was added by another request")
            return {
                "status": "error",
                "message": f"Unable to add movie - please try again"
            }

        return {
            "status": "success",
            "message": f"Movie '{movie_details.get('title')}' added to watchlist",
            "watchlist_id": watchlist_id,
            "movie_id": movie_id,
            "movie_title": movie_details.get('title'),
            "already_exists": False
        }
    except Exception as e:
        logger.exception("Failed to add to watchlist")
        return {"status": "error", "message": _sanitize_error(e, "Failed to add to watchlist")}


@mcp.tool
def get_watchlist(group_id: str, status: Optional[str] = None, filter_by_user: Optional[str] = None, exclude_rated_by: Optional[str] = None) -> dict:
    """
    Get the watchlist for a group.
    
    Args:
        group_id: Group UUID
        status: Optional filter by status ('pending' or 'watched')
        filter_by_user: Optional email to filter watchlist items added by a specific user
        exclude_rated_by: Optional email to exclude movies this user has already rated in this group
    
    Returns:
        List of movies in the watchlist with their details
    """
    try:
        sql = """
        SELECT 
            w.watchlist_id,
            w.group_id,
            w.movie_id,
            w.added_by,
            w.added_at,
            w.status,
            u.email as user_email,
            m.title,
            m.overview,
            m.runtime,
            m.tmdb_rating,
            m.genres::text as genres,
            m.release_date,
            EXTRACT(YEAR FROM m.release_date) as release_year,
            m.director,
            m.poster_path,
            m.original_language
        FROM watchlist_items w
        JOIN movies m ON w.movie_id = m.movie_id
        LEFT JOIN users u ON w.added_by = u.user_id
        WHERE w.group_id = %s
        """
        
        params = [group_id]
        if status:
            sql += " AND w.status = %s"
            params.append(status)
        if filter_by_user:
            sql += " AND w.added_by = %s"
            params.append(filter_by_user)
        if exclude_rated_by:
            sql += " AND w.movie_id NOT IN (SELECT r.movie_id FROM ratings r WHERE r.user_id = %s AND r.group_id = %s)"
            params.append(exclude_rated_by)
            params.append(group_id)
        
        sql += " ORDER BY w.added_at DESC"
        results = lakebase.run_query(sql, tuple(params))
        
        # Format poster URLs (poster_path from DB is just the path, not full URL)
        for movie in results:
            poster_path = movie.get('poster_path')
            if poster_path:
                movie['poster_url'] = f"https://image.tmdb.org/t/p/w500{poster_path}"
            else:
                movie['poster_url'] = None
        
        return {
            "status": "success",
            "group_id": group_id,
            "count": len(results),
            "watchlist": results
        }
    except Exception as e:
        logger.exception(f"Failed to get watchlist")
        return {
            "status": "error",
            "message": f"Failed to get watchlist: {str(e)}"
        }


@mcp.tool
def mark_as_watched(group_id: str, movie_id: str, email: str = 'rajesh@gmail.com') -> dict:
    """
    Mark a movie in the watchlist as 'watched' without rating it.
    
    Use when:
    - User says "mark that as watched"
    - User says "we watched that one already"
    - User wants to track that they've seen a movie but doesn't want to rate it
    
    Args:
        group_id: Group UUID
        movie_id: TMDB movie ID
        email: User email
    
    Returns:
        Confirmation that the movie was marked as watched
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        # 🔒 AUTHORIZATION CHECK: Verify user is a member of this group
        membership_check_sql = """
        SELECT COUNT(*) as is_member
        FROM group_members
        WHERE group_id = %s AND user_id = %s
        """
        membership_result = lakebase.run_query(membership_check_sql, (group_id, user_email))
        is_member = membership_result[0]['is_member'] > 0 if membership_result else False
        
        if not is_member:
            # Get group name for better error message
            group_name_sql = "SELECT group_name FROM groups WHERE group_id = %s"
            group_name_result = lakebase.run_query(group_name_sql, (group_id,))
            group_name = group_name_result[0]['group_name'] if group_name_result else group_id
            
            logger.warning(f"🚫 Authorization failed: {user_email} is not a member of group {group_id}")
            return {
                "status": "error",
                "error_type": "authorization_failed",
                "message": f"❌ You cannot mark movies as watched in '{group_name}' because you are not a member of this group.\n\nPlease ask the group owner to add you as a member first."
            }
        
        # MODEL 2: Mark movie as watched for the ENTIRE GROUP (group-level action)
        # This is the "we watched this together" action that makes it disappear for everyone
        sql = """
        UPDATE watchlist_items
        SET status = 'watched'
        WHERE group_id = %s AND movie_id = %s
        """
        
        rows_affected = lakebase.run_write(sql, (group_id, int(movie_id)))
        
        if rows_affected == 0:
            return {
                "status": "error",
                "message": "Movie not found in watchlist. Add it to the watchlist first."
            }
        
        movie_sql = "SELECT title FROM movies WHERE movie_id = %s"
        movie_result = lakebase.run_query(movie_sql, (int(movie_id),))
        movie_title = movie_result[0]['title'] if movie_result else f"Movie {movie_id}"
        
        return {
            "status": "success",
            "message": f"Marked '{movie_title}' as watched",
            "movie_id": movie_id,
            "movie_title": movie_title
        }
    except Exception as e:
        logger.exception("Failed to mark as watched")
        return {
            "status": "error",
            "message": f"Failed to mark as watched: {str(e)}"
        }


@mcp.tool
def get_group_by_name(group_name: str) -> dict:
    """
    Find a group by name (case-insensitive search).
    
    Use this when the user refers to a group by name like:
    "add to the Friday Night Movies group" or "my movie club"
    
    Args:
        group_name: The name or partial name of the group
    
    Returns:
        The matching group details, or error if not found
    """
    try:
        sql = """
        SELECT 
            group_id,
            group_name,
            description,
            created_by,
            created_at,
            is_active
        FROM groups
        WHERE LOWER(group_name) LIKE LOWER(%s)
        ORDER BY created_at DESC
        LIMIT 1
        """
        
        search_pattern = f"%{group_name}%"
        results = lakebase.run_query(sql, (search_pattern,))
        
        if results:
            return {
                "status": "success",
                "group": results[0]
            }
        else:
            return {
                "status": "not_found",
                "message": f"No group found matching '{group_name}'"
            }
    except Exception as e:
        logger.exception(f"Failed to search for group")
        return {
            "status": "error",
            "message": f"Failed to search for group: {str(e)}"
        }


@mcp.tool
def resolve_group_id(group_id_or_name: str, email: str = 'rajesh@gmail.com') -> dict:
    """
    Resolve a group identifier (UUID or name) to a valid group UUID.

    Handles three cases:
    1. Missing/placeholder values (MISSING_GROUP, current_group, etc.) -> returns error with available groups
    2. Valid UUID -> verifies the group exists
    3. Group name -> resolves to UUID via case-insensitive search

    Args:
        group_id_or_name: Group UUID, group name, or placeholder from LLM
        email: User email for listing available groups when input is missing

    Returns:
        {"status": "success", "resolved_id": "<uuid>"} on success
        {"status": "error", "message": "<user-friendly error>"} on failure
    """
    try:
        raw = group_id_or_name or ""

        # Case 1: Missing or placeholder values
        if not raw or raw.upper() == "MISSING_GROUP" or raw.lower() in ["current_group", "my_group", "default"]:
            logger.warning(f"⚠️  Missing or placeholder group_id: '{raw}'")
            groups_result = list_my_groups(email=email)
            if groups_result.get("groups"):
                group_list = "\n".join([f"- **{g['group_name']}** (ID: `{g['group_id']}`)" for g in groups_result["groups"][:5]])
                return {"status": "error", "message": f"Please specify a group. Available groups:\n\n{group_list}"}
            return {"status": "error", "message": "Please create a group first."}

        # Case 2: Already a valid UUID -> verify it exists
        if UUID_PATTERN.match(raw):
            verification = get_group_members(group_id=raw)
            if verification.get("status") == "error":
                return {"status": "error", "message": f"❌ The group ID '{raw}' doesn't exist.\n\nTip: Use 'list my groups' to see available groups."}
            return {"status": "success", "resolved_id": raw}

        # Case 3: Resolve group name to UUID
        logger.info(f"🔄 Resolving group name '{raw}' to UUID...")
        group_lookup = get_group_by_name(group_name=raw)
        if group_lookup.get("group"):
            resolved_id = group_lookup["group"]["group_id"]
            logger.info(f"✅ Resolved '{raw}' → UUID: {resolved_id}")
            return {"status": "success", "resolved_id": resolved_id}
        else:
            logger.error(f"❌ Group not found: '{raw}'")
            return {"status": "error", "message": f"❌ I couldn't find a group named '{raw}'. Please check the name.\n\nTip: Use 'list my groups' to see available groups."}
    except Exception as e:
        logger.exception(f"Failed to resolve group_id: {group_id_or_name}")
        return {"status": "error", "message": f"Failed to resolve group: {str(e)}"}


@mcp.tool
def resolve_movie_id(movie_id_or_title: str) -> dict:
    """
    Resolve a movie identifier (numeric TMDB ID or title) to a valid numeric movie ID.

    Handles three cases:
    1. Already numeric -> return as-is
    2. Placeholder values (MISSING_MOVIE, UNKNOWN, etc.) -> returns error
    3. Movie title -> searches TMDB and returns matches (asks user to choose if multiple)

    Args:
        movie_id_or_title: TMDB movie ID (numeric string) or movie title

    Returns:
        {"status": "success", "resolved_id": "<numeric_id>"} when single confident match
        {"status": "multiple_matches", "matches": [...]} when multiple similar movies found
        {"status": "error", "message": "<user-friendly error>"} on failure
    """
    try:
        raw = movie_id_or_title or ""

        # Case 1: Already numeric
        if str(raw).isdigit():
            return {"status": "success", "resolved_id": str(raw)}

        # Case 2: Placeholder values from LLM
        if str(raw).upper() in ["MISSING_MOVIE", "UNKNOWN", "TBD", "NULL", "NONE"]:
            logger.warning(f"⚠️  Rejected placeholder movie_id: '{raw}'")
            return {"status": "error", "message": "⚠️ I need a specific movie title. Could you tell me which movie you'd like to work with?"}

        # Case 3: Search by title
        logger.info(f"🔄 Resolving movie title '{raw}' to ID...")
        
        # Parse input to extract title and disambiguation context (year, director)
        import re
        search_query = str(raw)
        filter_year = None
        filter_director = None
        
        # Extract year: "Titanic 1997", "Titanic (1997)", "Titanic 1997 James Cameron"
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', search_query)
        if year_match:
            filter_year = int(year_match.group(1))
            # Remove year from search query
            search_query = search_query[:year_match.start()] + search_query[year_match.end():]
            search_query = search_query.replace('()', '').strip()
            logger.info(f"🎬 Extracted year filter: {filter_year}")
        
        # Extract director: ONLY when explicitly mentioned with keywords
        # This prevents movie titles like "Accidental Partners" from being mistaken as director names
        director_pattern = r'\b(directed by|by|director)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        dir_match = re.search(director_pattern, search_query, re.IGNORECASE)
        if dir_match:
            filter_director = dir_match.group(2)
            # Remove from search query
            search_query = search_query[:dir_match.start()] + search_query[dir_match.end():]
            search_query = search_query.strip()
            logger.info(f"🎬 Extracted director filter: {filter_director}")
        
        # Handle sequel numbers: "Ironman 1" -> "Iron Man" (first movie)
        sequel_match = re.search(r'\s+(1|2|3|I|II|III)\s*$', search_query, re.IGNORECASE)
        if sequel_match:
            # User said "Movie 1" - they want the first/original
            search_query = search_query[:sequel_match.start()].strip()
            logger.info(f"🎬 Detected sequel reference, searching for: '{search_query}'")
        
        # Clean up search query
        search_query = search_query.strip()
        
        # Search TMDB with cleaned title
        logger.info(f"🔍 Searching TMDB for title: '{search_query}'")
        search_results = search_tmdb_movies(query=search_query, limit=10)  # Get up to 10 to show options
        if not search_results:
            logger.error(f"❌ Movie not found: '{raw}'")
            return {"status": "error", "message": f"Sorry, I couldn't find the movie '{raw}'."}
        
        # Apply filters if provided
        filtered_results = search_results
        
        # Filter by year if provided (allow ±1 year tolerance)
        if filter_year:
            year_filtered = [
                r for r in filtered_results 
                if r.get('release_year') and abs(int(r.get('release_year')) - filter_year) <= 1
            ]
            if year_filtered:
                filtered_results = year_filtered
                logger.info(f"✅ Filtered to {len(filtered_results)} movies from year {filter_year}")
            else:
                logger.warning(f"⚠️ No movies found for year {filter_year}, showing all results")
        
        # Filter by director if provided (fuzzy match on director name)
        if filter_director and filtered_results:
            # Fetch director info for top candidates
            director_filtered = []
            for movie in filtered_results[:5]:  # Check top 5 only for performance
                movie_id = movie.get('movie_id') or movie.get('id')
                try:
                    details = get_tmdb_movie_details(movie_id)
                    movie_director = details.get('director', '')
                    if movie_director and filter_director.lower() in movie_director.lower():
                        director_filtered.append(movie)
                        logger.info(f"✅ Director match: {movie.get('title')} directed by {movie_director}")
                except Exception as e:
                    logger.warning(f"Could not fetch director for movie {movie_id}: {e}")
            
            if director_filtered:
                filtered_results = director_filtered
                logger.info(f"✅ Filtered to {len(filtered_results)} movies by director '{filter_director}'")
            else:
                logger.warning(f"⚠️ No movies found for director '{filter_director}', showing all results")
        
        search_results = filtered_results
        
        # If sequel number was detected, prefer earlier releases
        if sequel_match:
            sequel_num = sequel_match.group(1).upper()
            # Filter for movies with actual release dates
            dated_results = [r for r in search_results if r.get('release_year')]
            if dated_results:
                # For "1" or "I", pick the earliest popular match
                if sequel_num in ['1', 'I']:
                    dated_results.sort(key=lambda x: (x.get('release_year', '9999')))
                search_results = dated_results
        
        # Check if we have a confident single match (very high similarity)
        top_match = search_results[0]
        top_similarity = top_match.get('similarity_score', 0)
        
        # Auto-resolve only if:
        # 1. Single result, OR
        # 2. Top match has very high similarity (>0.9) AND significantly better than second
        if len(search_results) == 1:
            resolved_id = str(top_match.get("movie_id") or top_match.get("id"))
            resolved_title = top_match.get("title", "Unknown")
            logger.info(f"✅ Single match found: '{raw}' → '{resolved_title}' (ID: {resolved_id})")
            return {"status": "success", "resolved_id": resolved_id}
        
        # Check if top match is significantly better than others (exact match)
        if len(search_results) > 1:
            second_similarity = search_results[1].get('similarity_score', 0)
            # Exact match with clear winner
            if top_similarity > 0.95 and (top_similarity - second_similarity) > 0.2:
                resolved_id = str(top_match.get("movie_id") or top_match.get("id"))
                resolved_title = top_match.get("title", "Unknown")
                logger.info(f"✅ Confident match: '{raw}' → '{resolved_title}' (ID: {resolved_id})")
                return {"status": "success", "resolved_id": resolved_id}
        
        # Multiple similar matches - return all options for user to choose
        logger.info(f"🎬 Multiple movies found for '{raw}', returning {len(search_results)} options")
        
        # Format matches with distinguishing info (including director for disambiguation)
        formatted_matches = []
        for idx, movie in enumerate(search_results[:10], 1):
            movie_id = str(movie.get("movie_id") or movie.get("id"))
            
            # Fetch director info for disambiguation
            director = None
            try:
                details = get_tmdb_movie_details(movie_id)
                director = details.get('director', 'N/A')
            except Exception as e:
                logger.warning(f"Could not fetch director for movie {movie_id}: {e}")
                director = 'N/A'
            
            match_info = {
                "number": idx,
                "movie_id": movie_id,
                "title": movie.get("title", "Unknown"),
                "release_year": movie.get("release_year"),
                "tmdb_rating": movie.get("tmdb_rating") or movie.get("vote_average"),
                "overview": movie.get("overview", "")[:150] + "..." if movie.get("overview") and len(movie.get("overview", "")) > 150 else movie.get("overview", ""),
                "poster_url": movie.get("poster_url"),
                "director": director,
                "similarity_score": movie.get("similarity_score")
            }
            formatted_matches.append(match_info)
        
        return {
            "status": "multiple_matches",
            "message": f"I found {len(formatted_matches)} movies matching '{raw}'. Which one did you mean?",
            "searched_title": raw,
            "match_count": len(formatted_matches),
            "matches": formatted_matches
        }
        
    except Exception as e:
        logger.exception(f"Failed to resolve movie_id: {movie_id_or_title}")
        return {"status": "error", "message": f"Failed to resolve movie: {str(e)}"}


@mcp.tool
def list_my_groups(email: str = 'rajesh@gmail.com') -> dict:
    """
    List all groups created by the current user.
    
    Args:
        email: User email (defaults to 'rajesh@gmail.com')
    
    Returns:
        List of groups created by the user
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        sql = """
        SELECT group_id, group_name, description, created_by, created_at, is_active
        FROM groups
        WHERE created_by = %s
        ORDER BY created_at DESC
        """
        results = lakebase.run_query(sql, (user_email,))
        return {"status": "success", "count": len(results), "groups": results}
    except Exception as e:
        logger.exception("Failed to list user groups")
        return {"status": "error", "message": _sanitize_error(e, "Failed to list user groups")}


@mcp.tool
def list_all_groups(limit: int = 10) -> dict:
    """
    List all groups in the system (most recently created first).
    
    Args:
        limit: Maximum number of groups to return (default 10)
    
    Returns:
        List of all groups
    """
    try:
        sql = """
        SELECT 
            group_id,
            group_name,
            description,
            created_by,
            created_at,
            is_active,
            (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.group_id) as member_count
        FROM groups g
        ORDER BY created_at DESC
        LIMIT %s
        """
        
        results = lakebase.run_query(sql, (limit,))
        
        return {
            "status": "success",
            "count": len(results),
            "groups": results
        }
    except Exception as e:
        logger.exception(f"Failed to list all groups")
        return {
            "status": "error",
            "message": f"Failed to list all groups: {str(e)}"
        }


@mcp.tool
def create_group(group_name: str, description: str, email: str = 'rajesh@gmail.com') -> dict:
    try:
        _ensure_user_exists(email)       
        
        # Check if a group with this name already exists for this user
        check_sql = """
        SELECT group_id, group_name 
        FROM groups 
        WHERE created_by = %s AND group_name = %s AND is_active = true
        """
        existing_groups = lakebase.run_query(check_sql, (email, group_name))
        
        if existing_groups and len(existing_groups) > 0:
            # Get ALL user's groups to show them what names are taken
            all_groups_sql = """
            SELECT 
                g.group_id,
                g.group_name,
                g.description,
                TO_CHAR(g.created_at, 'MM/DD/YYYY') as created_at,
                COUNT(DISTINCT gm.user_id) as member_count
            FROM groups g
            LEFT JOIN group_members gm ON g.group_id = gm.group_id
            WHERE g.created_by = %s AND g.is_active = true
            GROUP BY g.group_id, g.group_name, g.description, g.created_at
            ORDER BY g.created_at DESC
            """
            all_user_groups = lakebase.run_query(all_groups_sql, (email,))
            
            return {
                "status": "error",
                "error_type": "duplicate_group_name",
                "message": f"A group named '{group_name}' already exists.\n\nPlease choose a different name.",
                "existing_group_id": existing_groups[0]['group_id'],
                "all_existing_groups": all_user_groups,
                "instruction": "DO NOT modify the name automatically (e.g., adding numbers). Tell the user: 'A group named X already exists. Your existing groups are: [list group names].\n\nPlease choose a different name.' Wait for their response before retrying."
            }
        
        group_id = _generate_group_id(group_name)
        
        sql = """
        INSERT INTO groups (group_id, group_name, description, created_by)
        VALUES (%s, %s, %s, %s)
        """
        
        lakebase.run_write(sql, (group_id, group_name, description, email))
        add_group_member(group_id, email)
        return {
            "status": "success",
            "message": f"Group '{group_name}' created successfully",
            "group_id": group_id,
            "group_name": group_name
        }
    except Exception as e:
        logger.exception(f"Failed to create group")
        return {
            "status": "error",
            "message": f"Failed to create group: {str(e)}"
        }


@mcp.tool
def list_user_groups(email: str = 'rajesh@gmail.com') -> dict:
    """
    List all movie night groups created by or joined by the authenticated user.
    
    Args:
        email: User's email (defaults to 'rajesh@gmail.com').
               When user identity forwarding is enabled, agents will
               automatically pass the correct email.
    
    Returns:
        List of groups with name, description, creation date, and member count
    """
    try:
        sql = """
        SELECT 
            g.group_id,
            g.group_name,
            g.description,
            TO_CHAR(g.created_at, 'MM/DD/YYYY') as created_at,
            g.created_by,
            COUNT(DISTINCT gm.user_id) as member_count
        FROM groups g
        LEFT JOIN group_members gm ON g.group_id = gm.group_id
        WHERE g.is_active = true 
          AND (g.created_by = %s OR EXISTS (
              SELECT 1 FROM group_members gm2 
              WHERE gm2.group_id = g.group_id 
                AND gm2.user_id = %s
          ))
        GROUP BY g.group_id, g.group_name, g.description, g.created_at, g.created_by
        ORDER BY g.created_at DESC
        """
        
        groups = lakebase.run_query(sql, (email, email))
        
        return {
            "status": "success",
            "count": len(groups),
            "groups": groups
        }
    except Exception as e:
        logger.exception(f"Failed to list user groups")
        return {
            "status": "error",
            "message": f"Failed to list groups: {str(e)}"
        }


@mcp.tool
def get_group_members(group_id: str) -> dict:
    """
    Get all members of a movie night group.
    
    Use this when the user asks about group members:
    - "who is in the Friday Night Movies group?"
    - "show me members of my recent group"
    - "list members in group X"
    
    Args:
        group_id: Group UUID
    
    Returns:
        List of group members with their details
    """
    try:
        sql = """
        SELECT 
            gm.membership_id,
            gm.user_id,
            gm.joined_at,
            u.email,
            u.username,
            u.created_at as user_created_at
        FROM group_members gm
        LEFT JOIN users u ON gm.user_id = u.email
        WHERE gm.group_id = %s
        ORDER BY gm.joined_at ASC
        """
        
        results = lakebase.run_query(sql, (group_id,))
        
        return {
            "status": "success",
            "group_id": group_id,
            "member_count": len(results),
            "members": results
        }
    except Exception as e:
        logger.exception(f"Failed to get group members")
        return {
            "status": "error",
            "message": f"Failed to get group members: {str(e)}"
        }


@mcp.tool
def add_group_member(group_id: str, user_id: str) -> dict:
    """
    Add a user to a movie night group.
    
    Args:
        group_id: Group UUID
        user_id: User email address
    
    Returns:
        Confirmation of membership
    """
    try:
        _ensure_user_exists(user_id)
        
        # Get group name to generate ID prefix
        group_sql = "SELECT group_name FROM groups WHERE group_id = %s"
        group_result = lakebase.run_query(group_sql, (group_id,))
        group_name = group_result[0]['group_name'] if group_result else 'UNK'
        
        # Generate membership_id: {first_3_letters}{sequence}
        membership_id = _generate_id_with_prefix(
            group_name,
            'group_members',
            'membership_id'
        )
        
        sql = """
        INSERT INTO group_members (membership_id, group_id, user_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (group_id, user_id) DO NOTHING
        """
        
        lakebase.run_write(sql, (membership_id, group_id, user_id))
        
        return {
            "status": "success",
            "message": f"User {user_id} added to group {group_id}",
            "membership_id": membership_id
        }
    except Exception as e:
        logger.exception(f"Failed to add group member")
        return {
            "status": "error",
            "message": f"Failed to add group member: {str(e)}"
        }


@mcp.tool
def remove_from_watchlist(group_id: str, movie_id: str, email: str = 'rajesh@gmail.com') -> dict:
    """
    Remove a movie from a group's watchlist.
    
    Use when user says:
    - "remove Inception from our watchlist"
    - "delete that movie from the watchlist"
    
    Args:
        group_id: Group UUID
        movie_id: TMDB movie ID
        email: User email (defaults to 'rajesh@gmail.com')
    
    Returns:
        Confirmation of removal
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        # 🔒 AUTHORIZATION CHECK: Verify user is a member of this group
        membership_check_sql = """
        SELECT COUNT(*) as is_member
        FROM group_members
        WHERE group_id = %s AND user_id = %s
        """
        membership_result = lakebase.run_query(membership_check_sql, (group_id, user_email))
        is_member = membership_result[0]['is_member'] > 0 if membership_result else False
        
        if not is_member:
            # Get group name for better error message
            group_name_sql = "SELECT group_name FROM groups WHERE group_id = %s"
            group_name_result = lakebase.run_query(group_name_sql, (group_id,))
            group_name = group_name_result[0]['group_name'] if group_name_result else group_id
            
            logger.warning(f"🚫 Authorization failed: {user_email} is not a member of group {group_id}")
            return {
                "status": "error",
                "error_type": "authorization_failed",
                "message": f"❌ You cannot remove movies from '{group_name}' because you are not a member of this group.\n\nPlease ask the group owner to add you as a member first."
            }
        
        sql = """
        DELETE FROM watchlist_items
        WHERE group_id = %s AND movie_id = %s
        """
        
        lakebase.run_write(sql, (group_id, movie_id))
        
        return {
            "status": "success",
            "message": f"Movie {movie_id} removed from group {group_id}'s watchlist"
        }
    except Exception as e:
        logger.exception(f"Failed to remove from watchlist")
        return {
            "status": "error",
            "message": f"Failed to remove from watchlist: {str(e)}"
        }


@mcp.tool
def rate_movie(
    movie_id: str,
    rating: float,  # Accept float to handle "X/5" notation parsed as decimals
    group_id: str = None,
    review: str = None,
    email: str = 'rajesh@gmail.com'
) -> dict:
    """
    Rate a movie that is already in the group's watchlist.
    
    BUSINESS RULE: Users can only rate movies that are in their group's watchlist.
    If the movie is not in the watchlist, the rating will be rejected.
    
    Use when:
    - User says "I rate [movie] X/5"
    - User says "[movie] was X stars"
    
    Workflow:
    1. Verify user is a group member
    2. Verify movie is in the watchlist (pending or watched)
    3. If not in watchlist, return error asking user to add it first
    4. Accept rating (1-5 scale)
    5. Auto-mark movie as 'watched' for the group
    
    Args:
        movie_id: TMDB movie ID (numeric string)
        rating: Rating on 1-5 scale (whole number)
        group_id: Group UUID (optional, will prompt if multiple groups)
        review: Optional review text
        email: User email (Alpaca pattern)
    
    Returns:
        Success with rating details, or error if not in watchlist
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        if not group_id:
            sql = """
            SELECT g.group_id, g.group_name, g.description, g.created_at, COUNT(DISTINCT gm.user_id) as member_count
            FROM groups g
            LEFT JOIN group_members gm ON g.group_id = gm.group_id
            WHERE g.created_by = %s AND g.is_active = true
            GROUP BY g.group_id, g.group_name, g.description, g.created_at
            ORDER BY g.created_at DESC
            """
            groups = lakebase.run_query(sql, (user_email,))
            
            if len(groups) == 0:
                return {"status": "no_groups", "message": "You don't have any groups yet. Create a group first."}
            elif len(groups) == 1:
                group_id = groups[0]['group_id']
            else:
                formatted_groups = [
                    {
                        "number": idx,
                        "group_id": g['group_id'],
                        "group_name": g['group_name'],
                        "description": g.get('description') or "No description",
                        "created_at": g['created_at'].strftime("%Y-%m-%d %H:%M") if g.get('created_at') else "Unknown",
                        "member_count": g.get('member_count', 0)
                    }
                    for idx, g in enumerate(groups, 1)
                ]
                return {
                    "status": "needs_group_selection",
                    "message": "Multiple groups found. Which group is this rating for?",
                    "available_groups": formatted_groups,
                    "movie_id": movie_id,
                    "rating": rating,
                    "review": review
                }
        
        # Validate rating FIRST before any conversion
        # Reject any rating outside 0.1-5.0 range (catches both too-low and too-high values)
        if rating < 0.1 or rating > 5.0:
            return {
                "status": "error",
                "message": f"❌ Invalid rating: {rating}. Ratings must be between 1 and 5 stars. Please try again with a valid rating (e.g., '4 stars' or '3.5/5')."
            }
        
        # Handle edge case: if rating is a float between 0-1, it might be parsed as X/5 fraction
        # Example: "4/5" parsed as 4÷5=0.8 → should be interpreted as 4
        if 0 < rating < 1:
            # Assume it's a fraction out of 5, convert back to integer scale
            rating = round(rating * 5)
            logger.info(f"📊 Converted fractional rating to integer: {rating}/5")
        
        # Final validation after conversion
        if not (1 <= rating <= 5):
            return {"status": "error", "message": "Rating must be between 1 and 5. Please provide a whole number (e.g., 4, not 4/5 or 0.8)."}
        
        # 🔒 AUTHORIZATION CHECK: Verify user is a member of this group
        membership_check_sql = """
        SELECT COUNT(*) as is_member
        FROM group_members
        WHERE group_id = %s AND user_id = %s
        """
        membership_result = lakebase.run_query(membership_check_sql, (group_id, user_email))
        is_member = membership_result[0]['is_member'] > 0 if membership_result else False
        
        if not is_member:
            # Get group name for better error message
            group_name_sql = "SELECT group_name FROM groups WHERE group_id = %s"
            group_name_result = lakebase.run_query(group_name_sql, (group_id,))
            group_name = group_name_result[0]['group_name'] if group_name_result else group_id
            
            logger.warning(f"🚫 Authorization failed: {user_email} is not a member of group {group_id}")
            return {
                "status": "error",
                "error_type": "authorization_failed",
                "message": f"❌ You cannot rate movies in '{group_name}' because you are not a member of this group.\n\nPlease ask the group owner to add you as a member first."
            }
        
        # 🔒 BUSINESS RULE: You can only rate movies that are in the watchlist or already watched
        # Check if movie exists in this group's watchlist
        watchlist_check_sql = """
        SELECT status, added_at
        FROM watchlist_items
        WHERE group_id = %s AND movie_id = %s
        """
        watchlist_result = lakebase.run_query(watchlist_check_sql, (group_id, int(movie_id)))
        
        if not watchlist_result:
            logger.warning(f"🚫 Rating blocked: movie {movie_id} not in watchlist for group {group_id}")
            return {
                "status": "error",
                "error_type": "not_in_watchlist",
                "message": f"❌ You can only rate movies that are in your group's watchlist.\n\nPlease add this movie to your watchlist first before rating it.",
                "movie_id": movie_id
            }
        
        movie_details = get_tmdb_movie_details(movie_id)
        if not movie_details:
            return {"status": "error", "message": f"Movie {movie_id} not found on TMDB"}
        
        embedding = generate_movie_embedding(movie_details)
        _upsert_movie(movie_id, movie_details, embedding)
        
        rating_id = _generate_id_with_prefix(movie_details.get('title'), 'ratings', 'rating_id')
        sql = """
        INSERT INTO ratings (rating_id, group_id, movie_id, user_id, rating, review_text, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, movie_id, group_id) DO UPDATE
        SET rating = EXCLUDED.rating,
            review_text = EXCLUDED.review_text,
            created_at = NOW()
        """
        lakebase.run_write(sql, (rating_id, group_id, int(movie_id), user_email, rating, review))
        
        # ✅ AUTO-MARK AS WATCHED: If someone rated it, they watched it!
        # UPSERT into watchlist_items: ensures ANY rated movie becomes "watched" for the group.
        # This is a group-level action - once rated by anyone, it's marked watched for the entire group.
        try:
            # Generate watchlist_id for potential new insert
            watchlist_id_for_rating = _generate_id_with_prefix(
                movie_details.get('title'), 
                'watchlist_items', 
                'watchlist_id'
            )
            
            mark_watched_sql = """
            INSERT INTO watchlist_items (watchlist_id, group_id, movie_id, added_by, status)
            VALUES (%s, %s, %s, %s, 'watched')
            ON CONFLICT (group_id, movie_id) 
            DO UPDATE SET status = 'watched'
            """
            rows_updated = lakebase.run_write(
                mark_watched_sql, 
                (watchlist_id_for_rating, group_id, int(movie_id), user_email)
            )
            logger.info(f"✅ Auto-marked movie {movie_id} as watched in group {group_id} after rating (upsert)")
        except Exception as mark_error:
            # Don't fail the rating if marking watched fails
            logger.warning(f"⚠️ Failed to auto-mark as watched after rating: {mark_error}")
        
        # Display on /5 scale (backend now stores /5, same as user input)
        stars = "⭐" * round(rating)
        
        return {
            "status": "success",
            "message": f"Rated '{movie_details.get('title')}' with {stars} {rating:.1f}/5",
            "rating_id": rating_id,
            "movie_id": movie_id,
            "user": user_email,
            "rating": rating,
            "review": review,
            "movie_title": movie_details.get('title')
        }
    except Exception as e:
        logger.exception("Failed to rate movie")
        return {"status": "error", "message": _sanitize_error(e, "Failed to rate movie")}


@mcp.tool
def get_movie_ratings(movie_id: str, group_id: str = None) -> dict:
    """
    Get all ratings for a specific movie, optionally scoped to a group.
    
    Use when user asks:
    - "what did people think of Inception?"
    - "show me ratings for that movie"
    - "did our group like this movie?"
    
    Args:
        movie_id: TMDB movie ID
        group_id: Optional group filter
    
    Returns:
        List of ratings with user info
    """
    try:
        # Convert movie_id to int for database query
        movie_id_int = int(movie_id)
        
        if group_id:
            sql = """
            SELECT 
                r.rating_id,
                r.rating,
                r.review_text as review,
                r.created_at,
                r.user_id,
                COALESCE(u.username, u.email, 'Anonymous') as username,
                u.email,
                m.title as movie_title,
                EXTRACT(YEAR FROM m.release_date) as release_year
            FROM ratings r
            LEFT JOIN users u ON r.user_id = u.email
            LEFT JOIN movies m ON r.movie_id = m.movie_id
            WHERE r.movie_id = %s AND r.group_id = %s
            ORDER BY r.created_at DESC
            """
            results = lakebase.run_query(sql, (movie_id_int, group_id))
        else:
            sql = """
            SELECT 
                r.rating_id,
                r.rating,
                r.review_text as review,
                r.created_at,
                r.user_id,
                COALESCE(u.username, u.email, 'Anonymous') as username,
                u.email,
                m.title as movie_title,
                EXTRACT(YEAR FROM m.release_date) as release_year
            FROM ratings r
            LEFT JOIN users u ON r.user_id = u.email
            LEFT JOIN movies m ON r.movie_id = m.movie_id
            WHERE r.movie_id = %s
            ORDER BY r.created_at DESC
            """
            results = lakebase.run_query(sql, (movie_id_int,))
        
        # Calculate average and add sentiment to each rating
        avg_rating = sum(r['rating'] for r in results) / len(results) if results else 0
        
        # Add sentiment classification to each rating
        for rating_obj in results:
            rating_obj['sentiment'] = get_rating_sentiment(rating_obj['rating'])
        
        return {
            "status": "success",
            "movie_id": movie_id,
            "group_id": group_id,
            "rating_count": len(results),
            "average_rating": round(avg_rating, 1),
            "ratings": results
        }
    except Exception as e:
        logger.exception(f"Failed to get movie ratings")
        return {
            "status": "error",
            "message": f"Failed to get movie ratings: {str(e)}"
        }


@mcp.tool
def get_group_ratings(group_id: str) -> dict:
    """
    Get all movies rated by a group (watch history).
    
    Use when user asks:
    - "what movies has our group watched?"
    - "show me our watch history"
    - "what did we rate highly?"
    
    Args:
        group_id: Group UUID
    
    Returns:
        List of rated movies with average ratings
    """
    try:
        sql = """
        SELECT 
            r.movie_id,
            m.title as movie_title,
            AVG(r.rating) as avg_rating,
            COUNT(r.rating_id) as rating_count,
            MAX(r.created_at) as last_rated,
            STRING_AGG(DISTINCT u.username, ', ') as raters
        FROM ratings r
        LEFT JOIN movies m ON r.movie_id = m.movie_id
        LEFT JOIN users u ON r.user_id = u.email
        WHERE r.group_id = %s
        GROUP BY r.movie_id, m.title
        ORDER BY last_rated DESC
        """
        
        results = lakebase.run_query(sql, (group_id,))
        
        return {
            "status": "success",
            "group_id": group_id,
            "movie_count": len(results),
            "rated_movies": results
        }
    except Exception as e:
        logger.exception(f"Failed to get group ratings")
        return {
            "status": "error",
            "message": f"Failed to get group ratings: {str(e)}"
        }


@mcp.tool
def get_my_ratings(group_id: str = None, email: str = 'rajesh@gmail.com') -> dict:
    """
    Get all ratings by the authenticated user.
    
    Uses the authenticated user's email.
    
    Use when user asks:
    - "what movies have I rated?"
    - "show me my ratings"
    - "what did I rate highly?"
    
    Args:
        group_id: Optional group filter
        email: User email (defaults to 'rajesh@gmail.com').
               Agents will pass correct email when user auth is enabled.
    
    Returns:
        List of user's ratings
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        if group_id:
            sql = """
            SELECT 
                r.rating_id,
                r.movie_id,
                m.title as movie_title,
                r.rating,
                r.review_text as review,
                r.created_at as rated_at,
                r.group_id
            FROM ratings r
            LEFT JOIN movies m ON r.movie_id = m.movie_id
            WHERE r.user_id = %s AND r.group_id = %s
            ORDER BY r.created_at DESC
            """
            results = lakebase.run_query(sql, (user_email, group_id))
        else:
            sql = """
            SELECT 
                r.rating_id,
                r.movie_id,
                m.title as movie_title,
                r.rating,
                r.review_text as review,
                r.created_at as rated_at,
                r.group_id
            FROM ratings r
            LEFT JOIN movies m ON r.movie_id = m.movie_id
            WHERE r.user_id = %s
            ORDER BY r.created_at DESC
            """
            results = lakebase.run_query(sql, (user_email,))
        
        # Add sentiment category to each rating (business rule lives in backend)
        for r in results:
            r['sentiment'] = get_rating_sentiment(float(r.get('rating', 0)))
        
        return {
            "status": "success",
            "user": user_email,
            "group_id": group_id,
            "rating_count": len(results),
            "ratings": results
        }
    except Exception as e:
        logger.exception(f"Failed to get user ratings for {email}")
        return {
            "status": "error",
            "message": f"Failed to get user ratings: {str(e)}"
        }


@mcp.tool
def get_user_dashboard_stats(group_id: str, email: str = 'rajesh@gmail.com') -> dict:
    """
    Get pre-computed dashboard statistics for a user in a group.
    
    Returns aggregated stats so the frontend doesn't need to compute them:
    - movies_watched, movies_pending, total_watchlist
    - avg_rating_given (on /5 scale)
    - total_ratings
    
    Use when rendering a user's personal dashboard:
    - "show my dashboard"
    - Before rendering personal stats panel
    
    Args:
        group_id: Group UUID
        email: User email (defaults to 'rajesh@gmail.com'). Agents will pass correct email.
    
    Returns:
        Summary stats dict with pre-computed counts and averages.
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        # Watchlist stats for this USER in this group
        # Filter by added_by to show only movies this specific user added
        # Status field: 'pending' = not watched yet, 'watched' = group watched it
        watchlist_sql = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'watched' THEN 1 END) as watched,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
        FROM watchlist_items
        WHERE group_id = %s AND added_by = %s
        """
        watchlist_stats = lakebase.run_query(watchlist_sql, (group_id, user_email))
        wl = watchlist_stats[0] if watchlist_stats else {}
        
        # Rating stats for this user in this group
        ratings_sql = """
        SELECT 
            COUNT(*) as total_ratings,
            COALESCE(AVG(rating), 0) as avg_rating_given
        FROM ratings
        WHERE user_id = %s AND group_id = %s
        """
        ratings_stats = lakebase.run_query(ratings_sql, (user_email, group_id))
        rt = ratings_stats[0] if ratings_stats else {}
        
        # Movies watched by ANY group member but NOT rated by this user yet
        # (Group-level watched status: if anyone in the group watched it, others should rate it)
        watched_not_rated_sql = """
        SELECT 
            wi.movie_id,
            m.title,
            EXTRACT(YEAR FROM m.release_date) as release_year
        FROM watchlist_items wi
        JOIN movies m ON wi.movie_id = m.movie_id
        LEFT JOIN ratings r ON r.movie_id = wi.movie_id 
                            AND r.user_id = %s 
                            AND r.group_id = wi.group_id
        WHERE wi.group_id = %s 
          AND wi.status = 'watched'
          AND r.rating_id IS NULL
        ORDER BY wi.added_at DESC
        """
        watched_not_rated_movies = lakebase.run_query(watched_not_rated_sql, (user_email, group_id))
        
        return {
            "status": "success",
            "movies_watched": int(wl.get('watched', 0) or 0),
            "movies_pending": int(wl.get('pending', 0) or 0),
            "total_watchlist": int(wl.get('total', 0) or 0),
            "avg_rating_given": round(float(rt.get('avg_rating_given', 0) or 0), 1),  # On /5 scale
            "total_ratings": int(rt.get('total_ratings', 0) or 0),
            "watched_not_rated": [{
                "movie_id": row['movie_id'],
                "title": row['title'],
                "release_year": row.get('release_year')
            } for row in watched_not_rated_movies]
        }
    except Exception as e:
        logger.exception(f"Failed to get dashboard stats for {email}")
        return {
            "status": "error",
            "message": f"Failed to get dashboard stats: {str(e)}"
        }


@mcp.tool
def get_group_preferences(group_id: str) -> dict:
    """
    Analyze a group's movie preferences based on their ratings.
    
    Use when recommending movies:
    - "what kind of movies does our group like?"
    - Before calling generate_recommendations
    
    Returns group's preferred genres, themes, and rating patterns.
    
    Args:
        group_id: Group UUID
    
    Returns:
        Preference analysis with liked genres, disliked movies, etc.
    """
    try:
        sql_liked = f"""
        SELECT 
            r.movie_id,
            AVG(r.rating) as avg_rating
        FROM ratings r
        WHERE r.group_id = %s AND r.rating >= {LIKED_RATING_THRESHOLD}
        GROUP BY r.movie_id
        ORDER BY avg_rating DESC
        """
        liked_movies = lakebase.run_query(sql_liked, (group_id,))
        
        sql_disliked = f"""
        SELECT 
            r.movie_id,
            AVG(r.rating) as avg_rating
        FROM ratings r
        WHERE r.group_id = %s AND r.rating <= {DISLIKED_RATING_THRESHOLD}
        GROUP BY r.movie_id
        ORDER BY avg_rating ASC
        """
        disliked_movies = lakebase.run_query(sql_disliked, (group_id,))
        
        sql_stats = """
        SELECT 
            AVG(rating) as avg_rating,
            COUNT(DISTINCT movie_id) as movies_rated,
            COUNT(DISTINCT user_id) as active_members
        FROM ratings
        WHERE group_id = %s
        """
        stats = lakebase.run_query(sql_stats, (group_id,))
        
        return {
            "status": "success",
            "group_id": group_id,
            "liked_movies": [m['movie_id'] for m in liked_movies],
            "disliked_movies": [m['movie_id'] for m in disliked_movies],
            "statistics": stats[0] if stats else {},
            "recommendation": "Use liked_movies to find similar movies. Avoid disliked_movies."
        }
    except Exception as e:
        logger.exception(f"Failed to analyze group preferences")
        return {
            "status": "error",
            "message": f"Failed to analyze group preferences: {str(e)}"
        }

@mcp.tool
def get_explained_group_recommendations(group_id: str, limit: int = 5) -> dict:
    """
    Get personalized movie recommendations for a group with detailed explanations.
    
    Analyzes the group's rating history to identify favorite genres, directors,
    and viewing patterns, then searches for matching movies and explains why
    each recommendation fits the group's taste.
    
    This is the COMPLETE workflow tool - combines preference extraction, movie search,
    and explanation generation in one backend call.
    
    Use when user asks:
    - "Recommend movies for [group] and explain why"
    - "Suggest movies for [group] with reasons"
    - "What should [group] watch next and why?"
    
    Args:
        group_id: Group UUID
        limit: Maximum number of recommendations to return (default: 5)
    
    Returns:
        {
            "status": "success",
            "group_id": "...",
            "group_name": "...",
            "group_profile": {
                "favorite_genres": ["Action", "Sci-Fi", "Thriller"],
                "favorite_directors": ["Christopher Nolan", "Denis Villeneuve"],
                "avg_rating": 4.5,
                "preferred_runtime": 140,
                "movies_rated": 25
            },
            "recommendations": [
                {
                    "movie": {...},  # Full movie object with all details
                    "explanation": "Perfect match for your love of Action, Sci-Fi...",
                    "matching_genres": ["Action", "Sci-Fi"],
                    "match_score": 0.95
                }
            ]
        }
    """
    try:
        # Step 1: Get group name for display
        group_name_sql = "SELECT group_name FROM groups WHERE group_id = %s"
        group_name_result = lakebase.run_query(group_name_sql, (group_id,))
        group_name_display = group_name_result[0]['group_name'] if group_name_result else group_id
        
        # Step 2: Get group preferences
        prefs_result = get_group_preferences(group_id=group_id)
        
        if prefs_result.get('status') != 'success':
            return {
                "status": "error",
                "message": f"Could not analyze {group_name_display}'s preferences. Try adding more ratings first."
            }
        
        stats = prefs_result.get('statistics', {})
        movies_rated = stats.get('movies_rated', 0)
        
        if movies_rated == 0:
            return {
                "status": "error",
                "message": f"{group_name_display} hasn't rated any movies yet! Start rating movies to get personalized recommendations."
            }
        
        # Step 3: Analyze liked movies to extract preferences
        liked_movie_ids = prefs_result.get('liked_movies', [])
        genre_counts = {}
        director_counts = {}
        runtimes = []
        
        logger.info(f"🎬 Analyzing {len(liked_movie_ids)} liked movies for group {group_id}...")
        
        for movie_id in liked_movie_ids[:10]:  # Top 10 liked movies
            try:
                details_result = get_movie_details(movie_id=str(movie_id))
                if details_result.get('status') == 'success' and details_result.get('movie'):
                    movie = details_result['movie']
                    
                    # Count genres
                    genres = movie.get('genres', [])
                    if isinstance(genres, str):
                        try:
                            genres = json.loads(genres)
                        except:
                            genres = []
                    for genre in genres:
                        genre_name = genre.get('name', genre) if isinstance(genre, dict) else genre
                        if genre_name:
                            genre_counts[genre_name] = genre_counts.get(genre_name, 0) + 1
                    
                    # Count directors
                    director = movie.get('director')
                    if director and director != 'N/A':
                        director_counts[director] = director_counts.get(director, 0) + 1
                    
                    # Track runtime
                    runtime = movie.get('runtime')
                    if runtime and runtime > 0:
                        runtimes.append(runtime)
            except Exception as e:
                logger.warning(f"Failed to fetch movie {movie_id} for analysis: {e}")
        
        if not genre_counts:
            return {
                "status": "error",
                "message": f"Could not determine {group_name_display}'s favorite genres. Try rating more movies with clear genre tags."
            }
        
        # Get top genres and directors
        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
        top_genres = [g for g, _ in sorted_genres[:3]]
        
        sorted_directors = sorted(director_counts.items(), key=lambda x: x[1], reverse=True)
        top_directors = [d for d, c in sorted_directors[:2]]
        
        avg_runtime = sum(runtimes) // len(runtimes) if runtimes else None
        
        logger.info(f"✅ Group profile: genres={top_genres}, directors={top_directors}, avg_runtime={avg_runtime}")
        
        # Step 4: Search for movies matching top genres
        search_query = " ".join(top_genres) + " movies"
        logger.info(f"🔍 Searching for: '{search_query}'")
        
        search_result = semantic_search_movies(query=search_query, limit=limit * 2)  # Get extra for filtering
        
        if search_result.get('status') != 'success' or not search_result.get('movies'):
            return {
                "status": "error",
                "message": f"No recommendations found matching {group_name_display}'s preferences."
            }
        
        # Step 5: Build recommendations with explanations
        recommendations = []
        candidate_movies = search_result['movies'][:limit]
        
        for movie in candidate_movies:
            title = movie.get('title', 'Unknown')
            rating = movie.get('tmdb_rating', 0)
            director = movie.get('director')
            
            # Extract movie genres
            movie_genres = movie.get('genres', [])
            if isinstance(movie_genres, str):
                try:
                    movie_genres = json.loads(movie_genres)
                except:
                    movie_genres = []
            movie_genre_names = [g.get('name', g) if isinstance(g, dict) else g for g in movie_genres]
            
            # Calculate match score and build explanation
            matching_genres = [g for g in movie_genre_names if g in top_genres]
            match_score = len(matching_genres) / len(top_genres) if top_genres else 0
            
            # Build explanation parts
            explanation_parts = []
            if matching_genres:
                explanation_parts.append(f"Perfect match for your love of {', '.join(matching_genres)}")
            if director and director in director_counts:
                explanation_parts.append(f"from favorite director {director}")
                match_score += 0.2  # Boost score for favorite director
            if rating >= 7.5:
                explanation_parts.append(f"highly acclaimed ({rating}/10 rating)")
            elif rating >= 6.5:
                explanation_parts.append(f"well-received ({rating}/10 rating)")
            
            explanation = ". ".join(p.capitalize() if i == 0 else p for i, p in enumerate(explanation_parts)) + "."
            
            recommendations.append({
                "movie": movie,
                "explanation": explanation,
                "matching_genres": matching_genres,
                "match_score": round(match_score, 2)
            })
        
        # Sort by match score (highest first)
        recommendations.sort(key=lambda x: x['match_score'], reverse=True)
        
        # Step 6: Return structured result
        return {
            "status": "success",
            "group_id": group_id,
            "group_name": group_name_display,
            "group_profile": {
                "favorite_genres": top_genres,
                "favorite_directors": top_directors,
                "avg_rating": round(stats.get('avg_rating', 0), 1),
                "preferred_runtime": avg_runtime,
                "movies_rated": movies_rated
            },
            "recommendations": recommendations[:limit]  # Return only requested count
        }
    except Exception as e:
        logger.exception(f"Failed to generate explained recommendations for group {group_id}")
        return {
            "status": "error",
            "message": f"Failed to generate recommendations: {str(e)}"
        }


@mcp.tool
def compare_movies(movie_title1: str, movie_title2: str, movie_title3: str = None) -> dict:
    """Compare 2 or 3 movies by title.
    
    Args:
        movie_title1: First movie title to compare
        movie_title2: Second movie title to compare
        movie_title3: Optional third movie title to compare
        
    Returns:
        Dict with status, movie_count, and comparisons list
    """
    try:
        titles = [t for t in [movie_title1, movie_title2, movie_title3] if t]
        
        if len(titles) < 2:
            return {
                "status": "error",
                "message": "At least 2 movie titles are required for comparison"
            }
        
        comparisons = []
        not_found = []

        for title in titles:
            try:
                search_results = search_tmdb_movies(query=title, limit=1)
                
                if not search_results:
                    logger.warning(f"Movie not found: {title}")
                    not_found.append(title)
                    continue

                movie_id = search_results[0]["movie_id"]

                details = get_movie_details(movie_id)
                if details.get("status") == "success":
                    movie = details.get("movie", {})
                    release_date = movie.get("release_date") or ""
                    
                    comparisons.append({
                        "movie_id": movie_id,
                        "title": movie.get("title"),
                        "runtime": movie.get("runtime"),
                        "genres": movie.get("genres"),
                        "tmdb_rating": movie.get("vote_average"),
                        "release_year": release_date[:4] if release_date else None,
                        "release_date": release_date,
                        "overview": movie.get("overview"),
                        "poster_url": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None,
                        "original_language": movie.get("original_language"),
                        "director": movie.get("director")
                    })
                else:
                    logger.warning(f"Failed to get details for movie: {title}")
                    not_found.append(title)
                    
            except Exception as e:
                logger.exception(f"Error processing movie '{title}': {e}")
                not_found.append(title)
                continue
        
        if not comparisons:
            return {
                "status": "error",
                "message": f"Could not find any of the requested movies: {', '.join(titles)}"
            }

        return {
            "status": "success",
            "movie_count": len(comparisons),
            "comparisons": comparisons,
            "not_found": not_found if not_found else None
        }
        
    except Exception as e:
        logger.exception(f"Failed to compare movies")
        return {
            "status": "error",
            "message": f"Failed to compare movies: {str(e)}"
        }


def _build_taste_profile(ratings: list) -> dict:
    """Build a user taste profile from their rating history.

    Fetches movie details for highly-rated movies to analyze genre, director,
    and runtime preferences. Limits to most recent 10 loved movies to avoid
    excessive API calls.

    Args:
        ratings: List of rating dicts from get_my_ratings

    Returns:
        Taste profile dict with genre_weights, director_affinity, runtime prefs
    """
    profile = {
        'genre_weights': {},       # {'Drama': 3, 'Sci-Fi': 2, ...}
        'director_affinity': {},   # {'Christopher Nolan': 2, ...}
        'preferred_runtime_min': 0,
        'preferred_runtime_max': 0,
        'avg_rating_given': 0.0,
        'total_ratings': len(ratings)
    }

    if not ratings:
        return profile

    # Calculate average rating given (on /5 scale)
    total = sum(float(r.get('rating', 0)) for r in ratings)
    profile['avg_rating_given'] = total / len(ratings) if ratings else 2.5

    # Analyze highly-rated movies (rating >= LOVED_RATING_THRESHOLD)
    loved = [r for r in ratings if float(r.get('rating', 0)) >= LOVED_RATING_THRESHOLD]
    # Limit to most recent 10 to avoid too many TMDB API calls
    loved = loved[:10]

    runtimes = []

    for rating_entry in loved:
        movie_id = rating_entry.get('movie_id')
        if not movie_id:
            continue

        try:
            details = get_tmdb_movie_details(str(movie_id))
            if not details:
                continue

            # Genre analysis
            for genre in details.get('genres', []):
                genre_name = genre if isinstance(genre, str) else genre.get('name', '')
                if genre_name:
                    profile['genre_weights'][genre_name] = profile['genre_weights'].get(genre_name, 0) + 1

            # Director analysis
            director = details.get('director')
            if director:
                profile['director_affinity'][director] = profile['director_affinity'].get(director, 0) + 1

            # Runtime analysis
            runtime = details.get('runtime')
            if runtime and runtime > 0:
                runtimes.append(runtime)

        except Exception as e:
            logger.warning(f"Could not fetch details for movie_id {movie_id}: {e}")
            continue

    # Calculate preferred runtime range (avg +/- 20 minutes)
    if runtimes:
        avg_runtime = sum(runtimes) / len(runtimes)
        profile['preferred_runtime_min'] = int(avg_runtime - 20)
        profile['preferred_runtime_max'] = int(avg_runtime + 20)

    return profile


def _score_movie_for_user(movie: dict, taste_profile: dict) -> tuple:
    """Score a movie based on how well it matches the user's taste profile.

    Scoring weights:
        - TMDB rating:       30% (base quality)
        - Genre match:       25% (personal preference from history)
        - Runtime fit:       15% (personal preference from history)
        - Director affinity: 30% (personal history + general auteur recognition)

    Args:
        movie: Movie comparison dict (from compare_movies)
        taste_profile: User's taste profile from _build_taste_profile

    Returns:
        Tuple of (score: float, reasons: list[str])
    """
    score = 0.0
    reasons = []

    rating = float(movie.get('tmdb_rating') or movie.get('vote_average', 0) or 0)
    runtime = movie.get('runtime', 0) or 0
    director = movie.get('director', '') or ''

    # Extract genre names (handle both list-of-strings and list-of-dicts)
    genres_raw = movie.get('genres', [])
    if isinstance(genres_raw, list):
        genre_names = [g.get('name', g) if isinstance(g, dict) else str(g) for g in genres_raw]
    elif isinstance(genres_raw, str):
        genre_names = [genres_raw]
    else:
        genre_names = []

    has_history = taste_profile.get('total_ratings', 0) > 0

    # Factor 1: TMDB rating (30% weight)
    score += rating * 3

    # Factor 2: Genre match (25% weight)
    if has_history and taste_profile.get('genre_weights'):
        user_genres = taste_profile['genre_weights']
        matched_genres = []
        for genre in genre_names:
            if genre in user_genres:
                score += user_genres[genre] * 4
                matched_genres.append(genre)
        if matched_genres:
            reasons.append(f"matches your love for {', '.join(matched_genres[:2])}")
    else:
        # No history: general genre quality assessment
        primary_genre = genre_names[0].lower() if genre_names else ""
        all_genres_lower = [g.lower() for g in genre_names]
        if 'drama' in primary_genre or 'thriller' in primary_genre:
            score += 5
            reasons.append("acclaimed storytelling")
        elif 'sci-fi' in primary_genre or 'science fiction' in all_genres_lower:
            score += 5
            reasons.append("thought-provoking concepts")

    # Factor 3: Runtime preference (15% weight)
    if has_history and taste_profile.get('preferred_runtime_min', 0) > 0:
        pref_min = taste_profile['preferred_runtime_min']
        pref_max = taste_profile['preferred_runtime_max']
        if pref_min <= runtime <= pref_max:
            score += 6
            reasons.append("matches your preferred runtime")
        elif 90 <= runtime <= 150:
            score += 4
            reasons.append("well-paced runtime")
    else:
        if 90 <= runtime <= 150:
            score += 5
            reasons.append("well-paced runtime")
        elif runtime > 150:
            score += 3
            reasons.append("epic scale and depth")

    # Factor 4: Director affinity (30% weight - personal history + auteur recognition)
    if director and director != 'N/A':
        # Personal director affinity from user's rating history
        if has_history and director in taste_profile.get('director_affinity', {}):
            score += 10
            reasons.append(f"you've loved {director}'s work before")
        else:
            # General auteur recognition for acclaimed directors
            notable_directors = ['nolan', 'kubrick', 'spielberg', 'tarantino', 'scorsese',
                                'fincher', 'anderson', 'rajamouli', 'shankar', 'villeneuve',
                                'mani ratnam']
            for notable in notable_directors:
                if notable in director.lower():
                    score += 12
                    reasons.append(f"{director}'s masterful direction")
                    break

    return score, reasons


@mcp.tool
def get_personalized_recommendation(comparisons: list, email: str = 'rajesh@gmail.com', group_id: str = None) -> dict:
    """
    Generate a personalized movie recommendation from compared movies based on user's taste profile.

    Builds a taste profile from the user's rating history (genres, directors, runtime patterns)
    and scores each movie to recommend the best match. YouTube Music-style: one confident pick
    based on your viewing history, not a list of options to choose from.

    Use after compare_movies to get a personalized recommendation:
    - "which of these should I watch?"
    - "pick the best one for me"

    Args:
        comparisons: List of movie comparison dicts (from compare_movies output)
        email: User email (defaults to 'rajesh@gmail.com'). Agents will pass correct email.
        group_id: Group UUID for filtering ratings to a specific group.

    Returns:
        Structured recommendation with winner, reasons, alternatives, and taste profile info.
    """
    try:
        # Step 1: Fetch user's rating history
        ratings_result = get_my_ratings(group_id=group_id, email=email)
        ratings = ratings_result.get('ratings', []) if ratings_result.get('status') == 'success' else []

        # Step 2: Build taste profile from rating history
        taste_profile = _build_taste_profile(ratings)

        # Step 3: Score each movie against the taste profile
        scored_movies = []
        for movie in comparisons:
            score, reasons = _score_movie_for_user(movie, taste_profile)
            # Normalize TMDB rating (/10) to user-facing /5 scale for consistency
            tmdb_rating = movie.get('tmdb_rating') or movie.get('vote_average', 0)
            normalized_rating = round(tmdb_rating / 2, 1) if tmdb_rating else 0
            
            scored_movies.append({
                'title': movie.get('title', 'Unknown'),
                'movie_id': movie.get('movie_id'),
                'score': round(score, 1),
                'rating': normalized_rating,  # Now on /5 scale
                'reasons': reasons
            })

        # Sort by score (highest first)
        scored_movies.sort(key=lambda x: x['score'], reverse=True)

        winner = scored_movies[0] if scored_movies else None
        alternatives = scored_movies[1:3] if len(scored_movies) > 1 else []

        return {
            'status': 'success',
            'has_history': taste_profile['total_ratings'] > 0,
            'total_ratings': taste_profile['total_ratings'],
            'winner': winner,
            'alternatives': alternatives,
            'taste_profile': {
                'total_ratings': taste_profile['total_ratings'],
                'avg_rating_given': round(taste_profile['avg_rating_given'], 1),
                'top_genres': dict(sorted(taste_profile['genre_weights'].items(), key=lambda x: x[1], reverse=True)[:5]),
                'top_directors': dict(sorted(taste_profile['director_affinity'].items(), key=lambda x: x[1], reverse=True)[:3])
            }
        }
    except Exception as e:
        logger.exception(f"Failed to generate personalized recommendation: {e}")
        return {
            'status': 'error',
            'message': f"Failed to generate recommendation: {str(e)}"
        }

@mcp.tool
def save_group_recommendation(group_id: str, movie_id: str, explanation: str, request_context: str, score: float, email: str = 'rajesh@gmail.com') -> dict:
    """
    Save an AI-generated movie recommendation for a group.
    
    Args:
        group_id: Group UUID
        movie_id: TMDB movie ID to recommend
        explanation: Brief explanation of why this movie is a good fit
        request_context: The original user request (e.g., "mind-bending thriller")
        score: Confidence score for this recommendation (between 0.0 and 1.0)
        email: Agent identity parameter
    """
    try:
        user_email = email
        _ensure_user_exists(user_email)
        
        movie_details = get_tmdb_movie_details(movie_id)
        if not movie_details:
            return {"status": "error", "message": f"Movie {movie_id} not found on TMDB"}
        
        group_sql = "SELECT group_name FROM groups WHERE group_id = %s"
        group_result = lakebase.run_query(group_sql, (group_id,))
        group_name = group_result[0]['group_name'] if group_result else 'UNK'
        
        rec_id = _generate_id_with_prefix(group_name, 'recommendations', 'recommendation_id')
        
        # Generate query embedding using shared helper (safe REST API, no SQL injection)
        embedding_str, error_msg = _generate_query_embedding(request_context)
        if error_msg:
            return {"status": "error", "message": error_msg}
        
        sql = """
        INSERT INTO recommendations (
            recommendation_id, group_id, movie_id, requested_by, 
            explanation, request_context, request_embedding, recommendation_score, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """
        
        lakebase.run_write(sql, (rec_id, group_id, int(movie_id), user_email, explanation, request_context, embedding_str, score))
        
        return {
            "status": "success",
            "message": f"Recommendation saved for {movie_details.get('title')}",
            "recommendation_id": rec_id
        }
    except Exception as e:
        logger.exception("Failed to save recommendation")
        return {"status": "error", "message": _sanitize_error(e, "Failed to save recommendation")}
@mcp.tool
def get_group_recommendations(group_id: str) -> dict:
    """
    Get past AI-generated movie recommendations for this group.
    
    Args:
        group_id: Group UUID
    
    Returns:
        List of past recommendations with movie titles, explanations, and timestamps
    """
    try:
        sql = """
        SELECT 
            r.recommendation_id,
            r.movie_id,
            r.explanation,
            r.request_context,
            r.recommendation_score,
            r.created_at,
            m.title,
            m.overview
        FROM recommendations r
        JOIN movies m ON r.movie_id = m.movie_id
        WHERE r.group_id = %s
        ORDER BY r.created_at DESC
        """
        
        results = lakebase.run_query(sql, (group_id,))
        
        return {
            "status": "success",
            "count": len(results),
            "recommendations": results
        }
    except Exception as e:
        logger.exception("Failed to get recommendations")
        return {"status": "error", "message": _sanitize_error(e, "Failed to get recommendations")}

@mcp.tool
def health_check_tmdb() -> dict:
    """
    Test TMDB API connectivity and secret access.
    
    Returns diagnostic information about:
    - Secret retrieval (can we get the TMDB API key?)
    - TMDB API connectivity (can we reach api.themoviedb.org?)
    - Sample search results (can we search for movies?)
    
    Use this to diagnose why search_movies returns empty results.
    """
    try:
        diagnostics = {}
        
        # Test 1: Can we retrieve the secret?
        try:
            api_key = get_tmdb_api_key()
            diagnostics["secret_retrieval"] = "success"
            diagnostics["api_key_length"] = len(api_key)
        except Exception as e:
            diagnostics["secret_retrieval"] = "failed"
            diagnostics["secret_error"] = str(e)
            return {
                "status": "error",
                "message": "Failed to retrieve TMDB API key from secrets",
                "diagnostics": diagnostics
            }
        
        # Test 2: Can we reach TMDB API?
        try:
            url = "https://api.themoviedb.org/3/configuration"
            params = {"api_key": api_key}
            response = _http_session.get(url, params=params, timeout=5)
            diagnostics["api_connectivity"] = "success"
            diagnostics["api_status_code"] = response.status_code
            diagnostics["api_response_ok"] = response.ok
        except Exception as e:
            diagnostics["api_connectivity"] = "failed"
            diagnostics["api_error"] = str(e)
            return {
                "status": "error",
                "message": "TMDB API is not reachable",
                "diagnostics": diagnostics
            }
        
        # Test 3: Can we search for movies?
        try:
            movies = search_tmdb_movies("inception", limit=3)
            diagnostics["search_test"] = "success"
            diagnostics["search_result_count"] = len(movies)
            diagnostics["sample_movies"] = [m.get('title') for m in movies]
        except Exception as e:
            diagnostics["search_test"] = "failed"
            diagnostics["search_error"] = str(e)
            return {
                "status": "error",
                "message": "Movie search failed",
                "diagnostics": diagnostics
            }
        
        return {
            "status": "healthy",
            "message": "All TMDB API tests passed",
            "diagnostics": diagnostics
        }
    except Exception as e:
        logger.exception("Health check failed")
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}"
        }

# Add a root route so the base URL doesn't return 404
if FASTMCP_AVAILABLE and hasattr(mcp, 'app') and mcp.app is not None:
    @mcp.app.get("/")
    async def root():
        return {"status": "online", "message": "AI Movie Planner API is running successfully!"}
    
if __name__ == "__main__":
    if not FASTMCP_AVAILABLE:
        logger.error("FastMCP not available. Cannot run as MCP server.")
        logger.error("Install fastmcp-slim to run as an MCP server: pip install fastmcp-slim")
        sys.exit(1)
    
    #===================================================================
    # DATABRICKS APP DEPLOYMENT CONFIGURATION
    #===================================================================
    # Register middleware BEFORE mcp.run() to capture request headers
    if hasattr(mcp, 'app') and mcp.app is not None:
        mcp.app.add_middleware(RequestContextMiddleware)
        logger.info("Registered RequestContextMiddleware")
    
    # Read port from environment (required for Databricks Apps)
    # DATABRICKS_APP_PORT is set by the platform when deployed as an app
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    
    logger.info(f"Starting MCP server on port {port}")
    
    # Run with explicit configuration:
    # - transport="http": Use HTTP (not stdio)
    # - host="0.0.0.0": Bind to all interfaces (required for containerized apps)
    # - port: From DATABRICKS_APP_PORT environment variable
    mcp.run(transport="http", host="0.0.0.0", port=port)