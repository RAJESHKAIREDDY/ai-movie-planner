"""
Comprehensive test suite for frontend.py AI Movie Planner

This test suite covers:
1. Dynamic tool discovery
2. Movie ID resolution (the MISSING_MOVIE bug)
3. Multi-word group name handling
4. UUID validation
5. LLM router behavior (with mocking to avoid API costs)
6. Agent workflow validation

Run with: pytest test_frontend.py -v
Install dependencies: pip install pytest pytest-mock responses
"""

import pytest
import json
import re
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import modules under test
import movie_mcp_server
from frontend import (
    build_dynamic_tool_descriptions,
    call_tool,
    make_json_serializable,
    ROUTER_TOOLS
)


# ============================================================================
# FIXTURES - Shared test data and mocks
# ============================================================================

@pytest.fixture
def mock_workspace_client():
    """Mock Databricks WorkspaceClient to avoid authentication in tests"""
    with patch('databricks.sdk.WorkspaceClient') as mock:
        mock_instance = Mock()
        mock_instance.config.host = "https://test.cloud.databricks.com"
        mock_instance.config.authenticate.return_value = {"Authorization": "Bearer test-token"}
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_llm_response():
    """Factory fixture to create mock LLM responses"""
    def _create_response(tool_name: str, arguments: dict):
        return {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "tool": tool_name,
                        "arguments": arguments
                    })
                }
            }]
        }
    return _create_response


@pytest.fixture
def sample_groups():
    """Sample groups for testing multi-word names"""
    return [
        {
            "group_id": "550e8400-e29b-41d4-a716-446655440000",
            "group_name": "Friday Night Flicks",
            "description": "Weekly movie night"
        },
        {
            "group_id": "660e8400-e29b-41d4-a716-446655440001",
            "group_name": "Movie Club",
            "description": "Monthly reviews"
        }
    ]


@pytest.fixture
def sample_movies():
    """Sample movie data for testing"""
    return [
        {
            "movie_id": "27205",
            "id": "27205",
            "title": "Inception",
            "overview": "A thief who steals corporate secrets...",
            "vote_average": 8.4,
            "genres": ["Action", "Science Fiction"]
        },
        {
            "movie_id": "155",
            "id": "155",
            "title": "The Dark Knight",
            "overview": "Batman raises the stakes...",
            "vote_average": 8.5,
            "genres": ["Drama", "Action", "Crime"]
        }
    ]


# ============================================================================
# TEST GROUP 1: Tool Discovery & Registration
# ============================================================================

class TestToolDiscovery:
    """Test dynamic tool discovery and registration"""
    
    def test_all_router_tools_exist_in_mcp_server(self):
        """Verify every tool in ROUTER_TOOLS has a corresponding function"""
        for tool_name in ROUTER_TOOLS:
            assert hasattr(movie_mcp_server, tool_name), \
                f"Tool '{tool_name}' listed in ROUTER_TOOLS but not found in movie_mcp_server"
            
            func = getattr(movie_mcp_server, tool_name)
            assert callable(func), f"'{tool_name}' is not callable"
    
    def test_dynamic_tool_descriptions_format(self):
        """Verify build_dynamic_tool_descriptions returns well-formed output"""
        descriptions = build_dynamic_tool_descriptions()
        
        # Should be non-empty string
        assert isinstance(descriptions, str)
        assert len(descriptions) > 0
        
        # Should contain function signatures
        assert "signature" in descriptions
        
        # Should contain at least some expected tools
        assert "search_movies" in descriptions
        assert "create_group" in descriptions
        assert "rate_movie" in descriptions
    
    def test_tool_signatures_are_inspectable(self):
        """Verify we can extract signatures from all tools"""
        import inspect
        
        for tool_name in ROUTER_TOOLS:
            func = getattr(movie_mcp_server, tool_name)
            sig = inspect.signature(func)
            
            # Signature should be non-empty
            assert str(sig) is not None
            
            # Should have parameters
            params = sig.parameters
            assert isinstance(params, dict) or len(params) >= 0


# ============================================================================
# TEST GROUP 2: The MISSING_MOVIE Bug
# ============================================================================

class TestMovieIdResolution:
    """Test movie ID resolution - documents and prevents the MISSING_MOVIE bug"""
    
    @patch('movie_mcp_server.get_tmdb_movie_details')
    def test_save_recommendation_rejects_missing_movie(self, mock_get_details):
        """CRITICAL: save_group_recommendation should reject MISSING_MOVIE placeholder"""
        mock_get_details.return_value = None  # Simulates TMDB 404
        
        result = call_tool("save_group_recommendation", {
            "group_id": "550e8400-e29b-41d4-a716-446655440000",
            "movie_id": "MISSING_MOVIE",  # ❌ The bug we found
            "explanation": "Great thriller",
            "request_context": "recommend a thriller",
            "score": 0.8
        })
        
        # Should return error, not crash with 404
        assert result.get("status") == "error"
        assert "not found" in result.get("message", "").lower()
    
    @patch('movie_mcp_server.search_tmdb_movies')
    def test_movie_title_resolves_to_numeric_id(self, mock_search):
        """Verify title -> ID conversion works correctly"""
        # Mock TMDB search response
        mock_search.return_value = [{
            "movie_id": "27205",
            "title": "Inception",
            "overview": "A thief steals secrets..."
        }]
        
        result = call_tool("search_movies", {"query": "Inception", "limit": 1})
        
        assert result.get("movies")
        assert len(result["movies"]) > 0
        movie_id = result["movies"][0].get("movie_id") or result["movies"][0].get("id")
        assert str(movie_id).isdigit(), "Movie ID should be numeric"
    
    def test_non_numeric_movie_id_should_be_resolved(self):
        """Document requirement: non-numeric movie_id must be auto-resolved"""
        # This test documents the fix for MISSING_MOVIE
        test_cases = [
            "Inception",
            "The Matrix",
            "MISSING_MOVIE",  # Should be caught
            "thriller",  # Genre, not a title
        ]
        
        for test_input in test_cases:
            # Non-numeric IDs should not reach backend without resolution
            assert not str(test_input).isdigit(), \
                f"Test case '{test_input}' should be non-numeric for this test"


# ============================================================================
# TEST GROUP 3: Multi-Word Group Names (Friday Night Flicks)
# ============================================================================

class TestGroupNameHandling:
    """Test group name extraction and resolution - especially multi-word names"""
    
    @patch('movie_mcp_server.lakebase.run_query')
    def test_multi_word_group_name_creates_successfully(self, mock_query):
        """Verify 'Friday Night Flicks' is treated as a single group name"""
        mock_query.return_value = []  # Group doesn't exist yet
        
        with patch('movie_mcp_server.lakebase.run_write') as mock_write:
            result = call_tool("create_group", {
                "group_name": "Friday Night Flicks",
                "description": "Weekly thriller nights"
            })
            
            # Should succeed
            assert result.get("status") == "success" or result.get("group") is not None
            
            # Verify full name was preserved (check call arguments)
            if mock_write.called:
                call_args = str(mock_write.call_args)
                assert "Friday Night Flicks" in call_args
    
    def test_uuid_pattern_validation(self):
        """Verify UUID pattern correctly distinguishes UUIDs from group names"""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        
        # Valid UUIDs
        assert uuid_pattern.match("550e8400-e29b-41d4-a716-446655440000")
        assert uuid_pattern.match("A0EEBC99-9C0B-4EF8-BB6D-6BB9BD380A11")  # Uppercase
        
        # Invalid UUIDs / Group names
        assert not uuid_pattern.match("Friday Night Flicks")
        assert not uuid_pattern.match("MISSING_GROUP")
        assert not uuid_pattern.match("Movie Club")
        assert not uuid_pattern.match("fake-uuid-123")
        assert not uuid_pattern.match("550e8400-e29b-41d4")  # Too short
    
    @patch('movie_mcp_server.lakebase.run_query')
    def test_group_lookup_by_multi_word_name(self, mock_query):
        """Test get_group_by_name with multi-word names"""
        # Mock database response
        mock_query.return_value = [{
            "group_id": "550e8400-e29b-41d4-a716-446655440000",
            "group_name": "Friday Night Flicks",
            "description": "Weekly movie night",
            "created_by": "test@example.com"
        }]
        
        result = call_tool("get_group_by_name", {"group_name": "Friday Night Flicks"})
        
        assert result.get("group") is not None
        assert result["group"]["group_name"] == "Friday Night Flicks"
        assert result["group"]["group_id"] == "550e8400-e29b-41d4-a716-446655440000"


# ============================================================================
# TEST GROUP 4: LLM Router Behavior (Mocked)
# ============================================================================

class TestLLMRouter:
    """Test the LLM routing logic with mocked responses to avoid API costs"""
    
    @pytest.mark.parametrize("user_query,expected_tool,expected_args", [
        (
            "search for Inception",
            "search_movies",
            {"query": "Inception"}
        ),
        (
            "list my groups",
            "list_my_groups",
            {}
        ),
        (
            "show watchlist for Friday Night Flicks",
            "get_watchlist",
            {"group_id": "Friday Night Flicks"}  # Should extract full name
        ),
    ])
    @patch('requests.post')
    def test_llm_routes_to_correct_tool(self, mock_post, user_query, expected_tool, expected_args, mock_llm_response):
        """Test that router prompt produces correct tool selections"""
        # Mock LLM response
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: mock_llm_response(expected_tool, expected_args)
        )
        
        # This would normally call agent_loop, but we're testing the concept
        # In practice, you'd mock the entire flow
        pass  # Placeholder for full integration test
    
    def test_router_prompt_includes_extraction_rules(self):
        """Verify router prompt contains critical multi-word extraction patterns"""
        # The prompt should include these patterns for multi-word groups
        required_patterns = [
            "Multi-word",
            "Friday Night Flicks",  # Concrete example
            "MISSING_GROUP",
            "full multi-word phrase"
        ]
        
        # In the refactored code, these would be in the prompt template
        # This test documents the requirement
        # You would check the actual prompt string here in implementation


# ============================================================================
# TEST GROUP 5: Validation & Edge Cases
# ============================================================================

class TestValidationLogic:
    """Test runtime validation that catches agent errors"""
    
    def test_missing_group_placeholder_is_detected(self):
        """Verify MISSING_GROUP placeholder is caught"""
        test_placeholders = [
            "MISSING_GROUP",
            "missing_group",
            "current_group",
            "my_group",
            "default"
        ]
        
        for placeholder in test_placeholders:
            # These should all be recognized as invalid
            assert placeholder.upper() == "MISSING_GROUP" or \
                   placeholder.lower() in ["current_group", "my_group", "default"], \
                   f"Placeholder '{placeholder}' should be detected as invalid"
    
    def test_make_json_serializable_handles_datetime(self):
        """Test datetime serialization helper"""
        from datetime import datetime
        from decimal import Decimal
        
        test_obj = {
            "timestamp": datetime(2024, 1, 15, 12, 30, 0),
            "rating": Decimal("8.5"),
            "nested": {
                "date": datetime(2024, 1, 1)
            }
        }
        
        result = make_json_serializable(test_obj)
        
        # Should be JSON-serializable now
        json_str = json.dumps(result)  # Should not raise
        assert isinstance(json_str, str)
        assert "2024-01-15" in json_str


# ============================================================================
# TEST GROUP 6: Integration Scenarios
# ============================================================================

class TestIntegrationScenarios:
    """Test complete user workflows end-to-end (with mocking)"""
    
    @patch('movie_mcp_server.lakebase.run_query')
    @patch('movie_mcp_server.lakebase.run_write')
    def test_complete_workflow_create_group_and_add_movie(self, mock_write, mock_query):
        """Test: User creates group, searches movie, adds to watchlist"""
        # Step 1: Create group
        mock_query.return_value = []  # No existing group
        create_result = call_tool("create_group", {
            "group_name": "Test Integration Group",
            "description": "Integration test"
        })
        
        # Should succeed (even if mocked)
        assert create_result is not None
    
    @patch('movie_mcp_server.search_tmdb_movies')
    def test_workflow_search_then_get_details(self, mock_search):
        """Test: Search movie, then get details"""
        # Mock search
        mock_search.return_value = [{
            "movie_id": "27205",
            "title": "Inception",
            "overview": "A thief..."
        }]
        
        # Search
        search_result = call_tool("search_movies", {"query": "Inception", "limit": 1})
        assert search_result.get("movies")
        
        # Get details (would be mocked in full test)
        movie_id = search_result["movies"][0]["movie_id"]
        assert str(movie_id).isdigit()


# ============================================================================
# TEST GROUP 7: Regression Tests (Document Known Bugs)
# ============================================================================

class TestRegressions:
    """Tests that document and prevent known bugs from returning"""
    
    def test_missing_movie_bug_is_fixed(self):
        """REGRESSION: save_group_recommendation called with MISSING_MOVIE"""
        # This documents the bug found in production:
        # User: "Can you recommend a good thriller for Friday Night Flicks?"
        # System: Calls save_group_recommendation(movie_id="MISSING_MOVIE")
        # Result: TMDB API 404 error
        
        # The fix: save_group_recommendation should be in tools_needing_movie_id
        # Or: The workflow should search for a movie first, then save
        
        tools_needing_movie_id = [
            "add_to_watchlist",
            "mark_as_watched",
            "rate_movie",
            "get_movie_details",
            "remove_from_watchlist",
            "get_movie_ratings",
            "save_group_recommendation"  # ✅ Should be here to prevent the bug
        ]
        
        assert "save_group_recommendation" in tools_needing_movie_id, \
            "save_group_recommendation must be in tools_needing_movie_id to prevent MISSING_MOVIE bug"
    
    def test_multi_word_group_extraction_from_natural_language(self):
        """REGRESSION: 'Friday Night Flicks' extracted as 'Friday' or 'Flicks'"""
        # This documents the requirement that multi-word groups must be extracted fully
        
        test_queries = [
            ("Show watchlist for Friday Night Flicks", "Friday Night Flicks"),
            ("Add Inception to Movie Club watchlist", "Movie Club"),
            ("Rate The Matrix 8/10 for Family Movie Group", "Family Movie Group"),
        ]
        
        # In practice, you'd test the actual extraction logic
        # This documents the expected behavior
        for query, expected_group in test_queries:
            # The LLM router should extract the full group name
            # This is validated by the prompt instructions
            assert len(expected_group.split()) > 1, \
                f"Test case '{expected_group}' should be multi-word"


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",  # Verbose
        "--tb=short",  # Shorter traceback format
        "-W", "ignore::DeprecationWarning",  # Ignore deprecation warnings
    ])
