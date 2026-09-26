"""


If the Python backfill script fails due to dependency issues, you can run this SQL
directly in your database to fix the 'Anonymous' user issue:

-- Step 1: Check how many users are missing
SELECT 
    COUNT(DISTINCT r.user_id) as total_raters,
    COUNT(DISTINCT CASE WHEN u.email IS NOT NULL THEN r.user_id END) as users_with_records,
    COUNT(DISTINCT CASE WHEN u.email IS NULL THEN r.user_id END) as missing_users
FROM ratings r
LEFT JOIN users u ON r.user_id = u.email;

-- Step 2: Backfill missing users from ratings table
INSERT INTO users (user_id, username, email)
SELECT DISTINCT 
    r.user_id,
    SPLIT_PART(r.user_id, '@', 1) as username,
    r.user_id as email
FROM ratings r
LEFT JOIN users u ON r.user_id = u.email
WHERE u.email IS NULL
ON CONFLICT (email) DO NOTHING;

-- Step 3: Verify the fix (should show 0 missing_users)
SELECT 
    COUNT(DISTINCT r.user_id) as total_raters,
    COUNT(DISTINCT CASE WHEN u.email IS NOT NULL THEN r.user_id END) as users_with_records,
    COUNT(DISTINCT CASE WHEN u.email IS NULL THEN r.user_id END) as missing_users
FROM ratings r
LEFT JOIN users u ON r.user_id = u.email;

===================================================================================
"""

import sys
import subprocess

# Install dependencies from requirements.txt before any imports
print("📦 Installing dependencies...")
# Upgrade typing_extensions first (needed by pydantic/fastmcp)
subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "typing_extensions>=4.6.0", "--quiet"])
requirements_path = '/Workspace/Users/rajesh.kyreddy@gmail.com/ai-movie-night-planner/mcp-server/requirements.txt'
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path, "--quiet"])
print("✅ Dependencies installed!\n")

import os

# Add the mcp-server directory to Python path so we can import lakebase and movie_mcp_server
# Use absolute path since __file__ may not work in notebook execution context
mcp_server_dir = '/Workspace/Users/rajesh.kyreddy@gmail.com/ai-movie-night-planner/mcp-server'
if mcp_server_dir not in sys.path:
    sys.path.insert(0, mcp_server_dir)

import json
import time
from databricks.sdk import WorkspaceClient

import lakebase
from movie_mcp_server import get_tmdb_api_key, _http_session

# Language code to full name mapping (ISO 639-1)
LANGUAGE_NAMES = {
    'en': 'English',
    'hi': 'Hindi',
    'te': 'Telugu',
    'ta': 'Tamil',
    'ml': 'Malayalam',
    'kn': 'Kannada',
    'bn': 'Bengali',
    'mr': 'Marathi',
    'gu': 'Gujarati',
    'pa': 'Punjabi',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese',
    'ru': 'Russian',
    'pt': 'Portuguese',
    'ar': 'Arabic',
    'tr': 'Turkish',
    'th': 'Thai',
    'vi': 'Vietnamese',
    'id': 'Indonesian',
    'nl': 'Dutch',
    'pl': 'Polish',
    'sv': 'Swedish',
    'da': 'Danish',
    'no': 'Norwegian',
    'fi': 'Finnish',
    'cs': 'Czech',
    'hu': 'Hungarian',
    'ro': 'Romanian',
    'el': 'Greek',
    'he': 'Hebrew',
    'uk': 'Ukrainian',
}

def get_language_name(code: str) -> str:
    """Convert language code to full name."""
    if not code:
        return 'Unknown'
    return LANGUAGE_NAMES.get(code, code.upper())

def backfill_movie_embeddings():
    """Finds movies missing embeddings and updates them using Databricks AI_QUERY."""
    
    # 1. Find movies that have no embedding
    sql_fetch = "SELECT movie_id, title, overview FROM movies WHERE embedding IS NULL"
    movies = lakebase.run_query(sql_fetch)
    
    if not movies:
        print("All movies already have embeddings!")
        return

    w = WorkspaceClient()
    warehouse_id = "57cfe19182c41cf4"
    
    for movie in movies:
        movie_id = movie['movie_id']
        title = movie['title']
        
        # Combine title and overview for a better semantic search match
        text_to_embed = f"{title}: {movie.get('overview', '')}"
        escaped_text = text_to_embed.replace("'", "''")
        
        # 2. Generate the 1024-dimension vector
        sql_query = f"SELECT AI_QUERY('databricks-bge-large-en', '{escaped_text}', returnType => 'ARRAY<DOUBLE>')"
        
        try:
            ai_response = w.statement_execution.execute_statement(
                warehouse_id=warehouse_id, statement=sql_query, wait_timeout="30s"
            )
            
            if ai_response.result and ai_response.result.data_array:
                embedding_json_str = ai_response.result.data_array[0][0]
                embedding_str_list = json.loads(embedding_json_str)
                query_embedding = [float(v) for v in embedding_str_list]
                embedding_str = f"[{','.join(map(str, query_embedding))}]"
                
                # 3. Save the generated vector back to the movie record
                sql_update = "UPDATE movies SET embedding = %s WHERE movie_id = %s"
                lakebase.run_write(sql_update, (embedding_str, movie_id))
                print(f"Updated embedding for: {title}")
                
        except Exception as e:
            print(f"Failed on {title}: {e}")


def backfill_movie_languages():
    """Finds movies missing original_language and updates them from TMDB."""
    
    # 1. Find movies that have no language
    sql_fetch = "SELECT movie_id FROM movies WHERE original_language IS NULL"
    movies = lakebase.run_query(sql_fetch)
    
    if not movies:
        print("All movies already have a language set!")
        return

    print(f"Found {len(movies)} movies to backfill. Fetching from TMDB...")
    api_key = get_tmdb_api_key()
    updates = []
    
    # 2. Fetch the original_language from TMDB
    for movie in movies:
        movie_id = movie['movie_id']
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        
        try:
            res = _http_session.get(url, params={"api_key": api_key}, timeout=5)
            if res.ok:
                lang = res.json().get('original_language')
                if lang:
                    updates.append((lang, movie_id))
            # Sleep briefly to respect TMDB API rate limits
            time.sleep(0.05) 
        except Exception as e:
            print(f"Failed to fetch movie {movie_id}: {e}")

    # 3. Update the database in a single batch
    if updates:
        sql_update = "UPDATE movies SET original_language = %s WHERE movie_id = %s"
        lakebase.run_write_many(sql_update, updates)
        print(f"Successfully backfilled {len(updates)} movies!")
    else:
        print("No language data was found to update.")


def backfill_vote_counts():
    """Finds movies with missing or zero vote_count and updates them from TMDB."""
    
    # 1. Find movies that have no vote_count or vote_count = 0
    sql_fetch = "SELECT movie_id, title FROM movies WHERE vote_count IS NULL OR vote_count = 0"
    movies = lakebase.run_query(sql_fetch)
    
    if not movies:
        print("All movies already have vote_count data!")
        return

    print(f"Found {len(movies)} movies to backfill. Fetching from TMDB...")
    api_key = get_tmdb_api_key()
    updates = []
    
    # 2. Fetch the vote_count from TMDB
    for movie in movies:
        movie_id = movie['movie_id']
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        
        try:
            res = _http_session.get(url, params={"api_key": api_key}, timeout=5)
            if res.ok:
                vote_count = res.json().get('vote_count', 0)
                updates.append((vote_count, movie_id))
            # Sleep briefly to respect TMDB API rate limits
            time.sleep(0.05) 
        except Exception as e:
            print(f"Failed to fetch movie {movie_id}: {e}")

    # 3. Update the database in a single batch
    if updates:
        sql_update = "UPDATE movies SET vote_count = %s WHERE movie_id = %s"
        lakebase.run_write_many(sql_update, updates)
        print(f"✅ Successfully backfilled vote_count for {len(updates)} movies!")
    else:
        print("No vote_count data was found to update.")


def convert_language_codes_to_names():
    """Convert two-letter language codes to full language names in the database."""
    
    # 1. Fetch all movies with language codes
    sql_fetch = "SELECT movie_id, original_language FROM movies WHERE original_language IS NOT NULL"
    movies = lakebase.run_query(sql_fetch)
    
    if not movies:
        print("No movies found with language codes!")
        return
    
    print(f"Found {len(movies)} movies to convert. Converting codes to full names...")
    updates = []
    
    # 2. Convert each code to full name
    for movie in movies:
        movie_id = movie['movie_id']
        lang_code = movie['original_language']
        
        # Only convert if it's still a 2-letter code
        if lang_code and len(lang_code) <= 3:
            full_name = get_language_name(lang_code)
            updates.append((full_name, movie_id))
    
    # 3. Update the database in a single batch
    if updates:
        sql_update = "UPDATE movies SET original_language = %s WHERE movie_id = %s"
        lakebase.run_write_many(sql_update, updates)
        print(f"✅ Successfully converted {len(updates)} language codes to full names!")
    else:
        print("No language codes needed conversion.")


def verify_languages():
    """Check the status of original_language data."""
    sql = """
    SELECT 
        COUNT(*) as total_movies,
        COUNT(original_language) as movies_with_language,
        COUNT(*) - COUNT(original_language) as movies_missing_language
    FROM movies
    """
    result = lakebase.run_query(sql)
    
    if result:
        row = result[0]
        print("\n📊 Language Data Status:")
        print("=" * 60)
        print(f"Total Movies:            {row['total_movies']}")
        print(f"Movies WITH Language:    {row['movies_with_language']}")
        print(f"Movies MISSING Language: {row['movies_missing_language']}")
        print()
        
        if row['movies_missing_language'] == 0:
            print("✅ All movies have language data!")
        else:
            print(f"⚠️  {row['movies_missing_language']} movies need backfilling.")
    
    # Show sample
    sample = lakebase.run_query(
        "SELECT movie_id, title, original_language FROM movies LIMIT 10"
    )
    if sample:
        print("\n📋 Sample Movies:")
        print("-" * 60)
        for m in sample:
            lang = m.get('original_language') or 'NULL'
            print(f"  {m['movie_id']:6} | {m['title'][:40]:40} | {lang}")


def backfill_poster_paths():
    """Finds movies missing poster_path and updates them from TMDB."""
    
    # 1. Find movies that have no poster_path
    sql_fetch = "SELECT movie_id, title FROM movies WHERE poster_path IS NULL"
    movies = lakebase.run_query(sql_fetch)
    
    if not movies:
        print("All movies already have poster_path data!")
        return

    print(f"Found {len(movies)} movies to backfill. Fetching from TMDB...")
    api_key = get_tmdb_api_key()
    updates = []
    
    # 2. Fetch the poster_path from TMDB
    for movie in movies:
        movie_id = movie['movie_id']
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        
        try:
            res = _http_session.get(url, params={"api_key": api_key}, timeout=5)
            if res.ok:
                poster_path = res.json().get('poster_path')  # Store just the path (e.g., '/abc123.jpg')
                if poster_path:  # Only update if TMDB has a poster
                    updates.append((poster_path, movie_id))
            # Sleep briefly to respect TMDB API rate limits
            time.sleep(0.05) 
        except Exception as e:
            print(f"Failed to fetch movie {movie_id}: {e}")

    # 3. Update the database in a single batch
    if updates:
        sql_update = "UPDATE movies SET poster_path = %s WHERE movie_id = %s"
        lakebase.run_write_many(sql_update, updates)
        print(f"✅ Successfully backfilled poster_path for {len(updates)} movies!")
    else:
        print("No poster_path data was found to update.")


def verify_poster_paths():
    """Check the status of poster_path data."""
    sql = """
    SELECT 
        COUNT(*) as total_movies,
        COUNT(poster_path) as movies_with_poster,
        COUNT(*) - COUNT(poster_path) as movies_missing_poster
    FROM movies
    """
    result = lakebase.run_query(sql)
    
    if result:
        row = result[0]
        print("\n📊 Poster Path Data Status:")
        print("=" * 60)
        print(f"Total Movies:               {row['total_movies']}")
        print(f"Movies WITH Poster Path:    {row['movies_with_poster']}")
        print(f"Movies MISSING Poster Path: {row['movies_missing_poster']}")
        print()
        
        if row['movies_missing_poster'] == 0:
            print("✅ All movies have poster_path data!")
        else:
            print(f"⚠️  {row['movies_missing_poster']} movies need backfilling.")
    
    # Show sample
    sample = lakebase.run_query(
        "SELECT movie_id, title, poster_path FROM movies LIMIT 10"
    )
    if sample:
        print("\n📋 Sample Movies:")
        print("-" * 60)
        for m in sample:
            poster = m.get('poster_path') or 'NULL'
            print(f"  {m['movie_id']:6} | {m['title'][:40]:40} | {poster}")


def backfill_missing_users():
    """Backfill the users table with all user_ids from the ratings table.
    
    Fixes the 'Anonymous' user issue where ratings were created before
    _ensure_user_exists was consistently called.
    """
    
    # 1. Find all user_ids in ratings that don't exist in users table
    check_sql = """
    SELECT 
        COUNT(DISTINCT r.user_id) as total_raters,
        COUNT(DISTINCT CASE WHEN u.email IS NOT NULL THEN r.user_id END) as users_with_records,
        COUNT(DISTINCT CASE WHEN u.email IS NULL THEN r.user_id END) as missing_users
    FROM ratings r
    LEFT JOIN users u ON r.user_id = u.email
    """
    before = lakebase.run_query(check_sql)
    
    if before:
        row = before[0]
        print("\n📊 Users Status (BEFORE):")
        print("=" * 60)
        print(f"Total raters:             {row['total_raters']}")
        print(f"Users with records:       {row['users_with_records']}")
        print(f"Missing users:            {row['missing_users']}")
        print()
        
        if row['missing_users'] == 0:
            print("✅ All ratings already have corresponding users!")
            return
    
    # 2. Backfill missing users
    backfill_sql = """
    INSERT INTO users (user_id, username, email)
    SELECT DISTINCT 
        r.user_id,
        SPLIT_PART(r.user_id, '@', 1) as username,
        r.user_id as email
    FROM ratings r
    LEFT JOIN users u ON r.user_id = u.email
    WHERE u.email IS NULL
    ON CONFLICT (email) DO NOTHING
    """
    
    rows_inserted = lakebase.run_write(backfill_sql, ())
    print(f"✅ Backfilled {rows_inserted} missing users from ratings table")
    
    # 3. Verify the fix
    after = lakebase.run_query(check_sql)
    if after:
        row = after[0]
        print("\n📊 Users Status (AFTER):")
        print("=" * 60)
        print(f"Total raters:             {row['total_raters']}")
        print(f"Users with records:       {row['users_with_records']}")
        print(f"Missing users:            {row['missing_users']}")
        print()


def verify_vote_counts():
    """Check the status of vote_count data."""
    sql = """
    SELECT 
        COUNT(*) as total_movies,
        COUNT(CASE WHEN vote_count > 0 THEN 1 END) as movies_with_votes,
        COUNT(CASE WHEN vote_count IS NULL OR vote_count = 0 THEN 1 END) as movies_missing_votes,
        AVG(vote_count) as avg_vote_count,
        MAX(vote_count) as max_vote_count,
        COUNT(CASE WHEN vote_count >= 100 THEN 1 END) as quality_threshold_count
    FROM movies
    """
    result = lakebase.run_query(sql)
    
    if result:
        row = result[0]
        print("\n📊 Vote Count Data Status:")
        print("=" * 60)
        print(f"Total Movies:                {row['total_movies']}")
        print(f"Movies WITH Vote Count:      {row['movies_with_votes']}")
        print(f"Movies MISSING Vote Count:   {row['movies_missing_votes']}")
        print(f"Average Vote Count:          {row['avg_vote_count']:.1f}" if row['avg_vote_count'] else "Average Vote Count:          0.0")
        print(f"Max Vote Count:              {row['max_vote_count']}")
        print(f"Quality Threshold (>= 100):  {row['quality_threshold_count']}")
        print()
        
        if row['movies_missing_votes'] == 0:
            print("✅ All movies have vote_count data!")
        else:
            print(f"⚠️  {row['movies_missing_votes']} movies need backfilling.")
    
    # Show sample
    sample = lakebase.run_query(
        "SELECT movie_id, title, vote_count FROM movies ORDER BY vote_count DESC LIMIT 10"
    )
    if sample:
        print("\n📋 Top 10 Movies by Vote Count:")
        print("-" * 60)
        for m in sample:
            votes = m.get('vote_count') or 0
            print(f"  {m['movie_id']:6} | {m['title'][:40]:40} | {votes:>6} votes")


def quick_backfill_posters_only():
    """Quick backfill for poster_path only (no other backfills)."""
    print("🖼️  QUICK POSTER BACKFILL")
    print("=" * 60)
    verify_poster_paths()
    print("\n🚀 Starting poster backfill...\n")
    backfill_poster_paths()
    print("\n✅ Done! Verifying results...")
    verify_poster_paths()


if __name__ == "__main__":
    # Run verification first
    print("🔍 Checking current state...")
    verify_languages()
    verify_vote_counts()
    verify_poster_paths()
    
    # Run backfill processes
    print("\n🚀 Starting backfill processes...\n")
    # backfill_movie_embeddings()  # Commented out - only run if needed
    
    # Backfill missing users from ratings table (fixes Anonymous user issue)
    print("\n👥 Backfilling missing users from ratings table...\n")
    backfill_missing_users()
    
    backfill_movie_languages()
    
    # Backfill vote counts
    print("\n📊 Backfilling vote counts from TMDB...\n")
    backfill_vote_counts()
    
    # Backfill poster paths
    print("\n🖼️  Backfilling poster paths from TMDB...\n")
    backfill_poster_paths()
    
    # Convert language codes to full names
    print("\n🔄 Converting language codes to full names...\n")
    convert_language_codes_to_names()
    
    # Verify again
    print("\n✅ Backfill complete! Verifying results...")
    verify_languages()
    verify_vote_counts()
    verify_poster_paths()