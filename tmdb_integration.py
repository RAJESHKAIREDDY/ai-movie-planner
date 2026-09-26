"""
TMDB API Integration for AI Movie Night Planner

This script populates the movies table with data from The Movie Database (TMDB) API.
You need a free TMDB API key: https://www.themoviedb.org/settings/api

Usage in Databricks:
    1. Set TMDB_API_KEY environment variable or pass as parameter
    2. Set LAKEBASE_URL environment variable or configure Databricks secret
    3. Run: populate_movies(api_key=YOUR_KEY, num_pages=5)
"""

import os
import json
import requests
from datetime import datetime
from typing import Any
import time

# Import the Lakebase helper
import sys
sys.path.append('/Workspace/Users/rajesh.kyreddy@gmail.com/ai-movie-night-planner/mcp-server')
import lakebase

# Module-level constants
_TMDB_BASE_URL = os.environ.get("TMDB_API_BASE_URL", "https://api.themoviedb.org/3")
_DEFAULT_TIMEOUT = 30


class TMDBClient:
    """Client for interacting with TMDB API"""
    
    def __init__(self, api_key: str, base_url: str | None = None, timeout: int = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or _TMDB_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.params = {"api_key": api_key}  # Add API key to all requests
    
    def _make_request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make GET request to TMDB API"""
        url = f"{self.base_url}/{endpoint}"
        response = self._session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def get_popular_movies(self, page=1):
        """Get popular movies"""
        return self._make_request('movie/popular', {'page': page})
    
    def get_top_rated_movies(self, page=1):
        """Get top rated movies"""
        return self._make_request('movie/top_rated', {'page': page})
    
    def get_movie_details(self, movie_id):
        """Get detailed information about a specific movie"""
        return self._make_request(f'movie/{movie_id}', {
            'append_to_response': 'credits,keywords,videos'
        })
    
    def search_movies(self, query):
        """Search for movies by title"""
        return self._make_request('search/movie', {'query': query})


def extract_movie_data(tmdb_movie):
    """Extract and transform TMDB movie data for database insertion"""
    
    # Extract genres
    genres = [genre['name'] for genre in tmdb_movie.get('genres', [])]
    
    # Extract top 5 cast members
    credits = tmdb_movie.get('credits', {})
    cast_list = credits.get('cast', [])[:5]
    cast = [{'name': actor['name'], 'character': actor['character']} 
            for actor in cast_list]
    
    # Extract director
    crew = credits.get('crew', [])
    directors = [person['name'] for person in crew if person['job'] == 'Director']
    director = directors[0] if directors else None
    
    # Extract keywords
    keywords_data = tmdb_movie.get('keywords', {})
    keywords = [kw['name'] for kw in keywords_data.get('keywords', [])]
    
    # Parse release date
    release_date = tmdb_movie.get('release_date')
    if release_date:
        try:
            release_date = datetime.strptime(release_date, '%Y-%m-%d').date()
        except ValueError:
            release_date = None
    
    return {
        'movie_id': tmdb_movie['id'],
        'title': tmdb_movie['title'],
        'overview': tmdb_movie.get('overview'),
        'release_date': release_date,
        'runtime': tmdb_movie.get('runtime'),
        'tmdb_rating': tmdb_movie.get('vote_average'),
        'genres': genres,
        'cast': cast,
        'director': director,
        'keywords': keywords
    }


def _insert_movie(movie_data):
    """
    Insert or update a single movie in the movies table.
    Uses lakebase.run_write() for database access.
    """
    sql = """
    INSERT INTO movies (
        movie_id, title, overview, release_date, runtime, 
        tmdb_rating, genres, cast, director, keywords
    ) VALUES (
        %(movie_id)s, %(title)s, %(overview)s, %(release_date)s, %(runtime)s,
        %(tmdb_rating)s, %(genres)s, %(cast)s, %(director)s, %(keywords)s
    )
    ON CONFLICT (movie_id) 
    DO UPDATE SET
        title = EXCLUDED.title,
        overview = EXCLUDED.overview,
        release_date = EXCLUDED.release_date,
        runtime = EXCLUDED.runtime,
        tmdb_rating = EXCLUDED.tmdb_rating,
        genres = EXCLUDED.genres,
        cast = EXCLUDED.cast,
        director = EXCLUDED.director,
        keywords = EXCLUDED.keywords
    """
    
    # Convert lists/dicts to JSON strings for JSONB columns
    params = {
        'movie_id': movie_data['movie_id'],
        'title': movie_data['title'],
        'overview': movie_data.get('overview'),
        'release_date': movie_data.get('release_date'),
        'runtime': movie_data.get('runtime'),
        'tmdb_rating': movie_data.get('tmdb_rating'),
        'genres': json.dumps(movie_data.get('genres', [])),
        'cast': json.dumps(movie_data.get('cast', [])),
        'director': movie_data.get('director'),
        'keywords': json.dumps(movie_data.get('keywords', []))
    }
    
    return lakebase.run_write(sql, params)


def populate_movies(api_key=None, num_pages=5):
    """
    Main function to populate movies from TMDB into Lakebase.
    
    Args:
        api_key: TMDB API key (or set TMDB_API_KEY environment variable)
        num_pages: Number of pages to fetch from TMDB (20 movies per page)
    
    Returns:
        Number of movies processed
    """
    
    # Get API key from parameter or environment
    api_key = api_key or os.environ.get('TMDB_API_KEY')
    if not api_key:
        raise ValueError("TMDB API key required. Set TMDB_API_KEY environment variable or pass as parameter.")
    
    print("Initializing TMDB client...")
    tmdb = TMDBClient(api_key)
    
    print("Testing Lakebase connection...")
    try:
        # Test connection
        test_result = lakebase.run_query("SELECT 1 as test")
        print(f"✓ Connected to Lakebase: {test_result}")
    except Exception as e:
        print(f"✗ Failed to connect to Lakebase: {str(e)}")
        raise
    
    movies_processed = 0
    
    # Fetch popular movies
    print(f"\nFetching {num_pages} pages of popular movies...")
    for page in range(1, num_pages + 1):
        print(f"  Processing page {page}/{num_pages}...")
        
        popular = tmdb.get_popular_movies(page)
        
        for movie in popular['results']:
            try:
                # Get detailed information
                details = tmdb.get_movie_details(movie['id'])
                
                # Extract and insert data
                movie_data = extract_movie_data(details)
                _insert_movie(movie_data)
                
                movies_processed += 1
                print(f"    ✓ Inserted: {movie_data['title']} ({movie_data['movie_id']})")
                
                # Rate limiting - TMDB allows 40 requests per 10 seconds
                time.sleep(0.25)
                
            except Exception as e:
                print(f"    ✗ Error processing movie {movie['id']}: {str(e)}")
                continue
    
    print(f"\n✅ Successfully processed {movies_processed} movies!")
    return movies_processed


# ============================================
# EXAMPLE USAGE:
# ============================================

if __name__ == "__main__":
    # This allows you to run this file directly if needed
    import sys
    
    # Check for API key
    if not os.environ.get('TMDB_API_KEY'):
        print("Error: Set TMDB_API_KEY environment variable")
        sys.exit(1)
    
    # Run with default 5 pages (100 movies)
    populate_movies(num_pages=5)
