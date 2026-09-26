import streamlit as st
import json
import sys
import os
import time
import inspect
import re
import logging
import requests
from typing import Dict, List, Any, Optional
from databricks.sdk import WorkspaceClient

logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors (hide INFO logs)
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("frontend")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import movie_mcp_server

w = WorkspaceClient()
host = w.config.host
MODEL_ENDPOINT = f"{host}/serving-endpoints/databricks-meta-llama-3-3-70b-instruct/invocations"

LANGUAGE_MAP = {
    'en': 'English', 'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil',
    'es': 'Spanish', 'fr': 'French', 'ja': 'Japanese', 'ko': 'Korean',
    'zh': 'Chinese', 'de': 'German', 'it': 'Italian', 'pt': 'Portuguese',
    'ru': 'Russian', 'ar': 'Arabic', 'ml': 'Malayalam', 'kn': 'Kannada',
    'mr': 'Marathi', 'bn': 'Bengali', 'pa': 'Punjabi', 'gu': 'Gujarati',
    'English': 'English', 'Hindi': 'Hindi', 'Telugu': 'Telugu',
    'Tamil': 'Tamil', 'Spanish': 'Spanish', 'French': 'French',
    'Japanese': 'Japanese', 'Korean': 'Korean', 'Chinese': 'Chinese',
    'German': 'German', 'Italian': 'Italian', 'Portuguese': 'Portuguese',
    'Russian': 'Russian', 'Arabic': 'Arabic', 'Malayalam': 'Malayalam',
    'Kannada': 'Kannada', 'Marathi': 'Marathi', 'Bengali': 'Bengali',
    'Punjabi': 'Punjabi', 'Gujarati': 'Gujarati',
}

GENRE_COLORS = {
    'Action': '#dc2626',      # Red - Bold and energetic
    'Comedy': '#f59e0b',      # Amber - Fun and bright
    'Drama': '#7c3aed',       # Purple - Elegant and deep
    'Horror': '#1f2937',      # Dark Gray - Mysterious
    'Romance': '#ec4899',     # Pink - Romantic and warm
    'Sci-Fi': '#0ea5e9',      # Sky Blue - Futuristic
    'Science Fiction': '#0ea5e9',  # Sky Blue - Futuristic
    'Thriller': '#8b5cf6',    # Violet - Suspenseful
    'Animation': '#10b981',   # Emerald - Playful
    'Crime': '#ef4444',       # Red - Intense
    'Mystery': '#6366f1',     # Indigo - Enigmatic
}

# Configuration Constants - centralized for easy tuning
class Config:
    """Application configuration constants."""
    # Display Limits
    MAX_TITLE_LENGTH_TABLE = 40
    MAX_TITLE_LENGTH_RATING = 35
    MAX_OVERVIEW_LENGTH = 300
    MAX_DISPLAY_MOVIES = 10
    MAX_GENRES_DISPLAY = 5
    
    # Cache Settings
    CACHE_TTL_SECONDS = 15
    
    # UI Settings
    CHAT_INPUT_MARGIN = "2rem"  # Positive margin for proper spacing

# Backward compatibility aliases
MAX_TITLE_LENGTH_TABLE = Config.MAX_TITLE_LENGTH_TABLE
MAX_TITLE_LENGTH_RATING = Config.MAX_TITLE_LENGTH_RATING
MAX_OVERVIEW_LENGTH = Config.MAX_OVERVIEW_LENGTH
MAX_DISPLAY_MOVIES = Config.MAX_DISPLAY_MOVIES
MAX_GENRES_DISPLAY = Config.MAX_GENRES_DISPLAY

EMPTY_WATCHLIST_HTML = """
<div class="empty-state">
    <div class="empty-state-icon">🎬</div>
    <h3 style="color: #2d3748; margin: 0 0 12px 0; font-weight: 600;">Your Watchlist is Empty</h3>
    <p style="color: #4a5568; font-size: 1.05em; margin: 0;">Start adding movies to plan your next movie night!</p>
    <p style="color: #718096; font-size: 0.9em; margin: 16px 0 0 0;">💡 Try: "Add Inception to watchlist for [group]"</p>
</div>\n\n"""

EMPTY_RATINGS_HTML = """
<div class="empty-state">
    <div class="empty-state-icon">⭐</div>
    <h3 style="color: #2d3748; margin: 0 0 12px 0; font-weight: 600;">No Ratings Yet</h3>
    <p style="color: #4a5568; font-size: 1.05em; margin: 0;">Share your thoughts and rate the movies you've watched!</p>
    <p style="color: #718096; font-size: 0.9em; margin: 16px 0 0 0;">💡 Try: "Rate Inception 5 stars in [group]"</p>
</div>\n\n"""

TOOLS_REQUIRING_GROUP = [
    "rate_movie", "add_to_watchlist", "get_watchlist", "mark_as_watched",
    "remove_from_watchlist", "get_group_ratings", "get_my_ratings",
    "get_group_preferences", "get_group_recommendations",
    "save_group_recommendation", "add_group_member", "get_group_members"
]

TOOLS_REQUIRING_EMAIL = [
    "rate_movie", "add_to_watchlist", "mark_as_watched",
    "remove_from_watchlist", "get_my_ratings",
    "save_group_recommendation", "get_user_dashboard_stats",
    "create_group", "list_user_groups", "get_personalized_recommendation"
]

# Tools where the email should ALWAYS be overridden with the current user's email.
# These tools operate AS the current user — the LLM's default email must never be used.
# get_my_ratings is excluded because the user might ask about another person's ratings
# (e.g., "what does alice like?").
TOOLS_ALWAYS_CURRENT_USER = {
    "create_group", "list_user_groups", "add_to_watchlist",
    "mark_as_watched", "remove_from_watchlist", "rate_movie",
    "save_group_recommendation", "get_user_dashboard_stats",
    "get_personalized_recommendation"
}

TOOLS_NEEDING_MOVIE_ID = [
    "add_to_watchlist", "mark_as_watched", "rate_movie",
    "get_movie_details", "remove_from_watchlist", "get_movie_ratings",
    "save_group_recommendation"
]

ROUTER_TOOLS = [
    "semantic_search_movies",
    "search_movies",
    "get_movie_details",
    "compare_movies",
    "get_current_user",
    "create_user",
    "create_group",
    "list_my_groups",
    "list_user_groups",
    "list_all_groups",
    "get_group_by_name",
    "get_group_members",
    "add_group_member",
    "add_to_watchlist",
    "get_watchlist",
    "remove_from_watchlist",
    "mark_as_watched",
    "rate_movie",
    "get_movie_ratings",
    "get_group_ratings",
    "get_my_ratings",
    "get_group_preferences",
    "get_explained_group_recommendations",
    "get_group_recommendations",
    "save_group_recommendation",
    "get_personalized_recommendation",
]

# Cache helper function (must be defined before sidebar code uses it)
@st.cache_data(ttl=15)
def get_cached_group_members(group_id: str) -> Dict[str, Any]:
    """Fetch group members with 15-second cache for responsive UX while reducing API calls."""
    return movie_mcp_server.get_group_members(group_id=group_id)

st.set_page_config(page_title="AI Movie Planner", page_icon="🍿", layout="wide")
with st.sidebar:
    st.title("🎬 Movie Planner")
    st.markdown("---")
    
    # User Dropdown
    try:
        users_result = movie_mcp_server.list_all_users()
        
        if users_result.get('status') == 'success' and users_result.get('users'):
            users = users_result['users']
            
            # Filter out system/test users and deduplicate by email (unique identifier)
            system_users = {'agent', 'agent_identity', 'system', 'admin', 'test', 'demo'}
            seen_emails = set()  # Track emails for deduplication (email is the unique key)
            unique_users = []
            
            for u in users:
                username = u['username']
                email = u['email']
                username_lower = username.lower()
                
                # Skip system/test users
                if username_lower in system_users:
                    continue
                
                # Skip if we've already seen this email (deduplicate by email, not username)
                if email not in seen_emails:
                    seen_emails.add(email)
                    unique_users.append(u)
            
            users = unique_users  # Replace with filtered and deduplicated list
            user_list = [u['username'] for u in users]
            
            current_user = None
            if st.session_state.get('current_user_override'):
                current_user = st.session_state.current_user_override
            else:
                try:
                    cwd = os.getcwd()
                    if '/Users/' in cwd:
                        user_match = re.search(r'/Users/([^/]+@[^/]+)/', cwd)
                        if user_match:
                            current_user = user_match.group(1).split('@')[0]
                except Exception:
                    pass
            
            if not current_user and user_list:
                current_user = user_list[0]
            
            default_index = user_list.index(current_user) if current_user in user_list else 0
            
            selected_user = st.selectbox(
                "👤 User",
                options=user_list,
                index=default_index,
                key="user_switcher_dropdown"
            )
            
            selected_user_obj = next((u for u in users if u['username'] == selected_user), None)
            if selected_user_obj:
                if st.session_state.get('current_user_email') != selected_user_obj['email']:
                    st.session_state.current_user_override = selected_user_obj['username']
                    st.session_state.current_user_email = selected_user_obj['email']
                    if selected_user != current_user:
                        st.rerun()
        else:
            st.info("👥 No users found in system. Add users to your groups first.")
    except Exception as e:
        logger.error(f"Failed to load user switcher: {e}")
    
    # Create New User (below user section)
    with st.expander("➕ Create New User", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_user_name = st.text_input(
                "👤 Username",
                placeholder="Enter username...",
                key="new_user_name_input"
            )
        with col2:
            new_user_email = st.text_input(
                "📧 Email",
                placeholder="user@example.com",
                key="new_user_email_input"
            )
        
        st.markdown('<div style="margin: 0.5rem 0;"></div>', unsafe_allow_html=True)
        if st.button("➕ Create User", use_container_width=True) and new_user_name and new_user_email:
            if not movie_mcp_server.validate_email(new_user_email):
                st.error("❌ Please enter a valid email address (e.g., user@example.com)")
            else:
                try:
                    result = movie_mcp_server.create_user(
                        user_name=new_user_name,
                        user_email=new_user_email
                    )
                    
                    if result.get('status') == 'success':
                        st.success(f"✅ Created user {new_user_name} successfully")
                        time.sleep(1)
                        st.rerun()
                    else:
                        error_msg = result.get('message', 'Failed to create user')
                        st.error(f"❌ {error_msg}")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    
    st.markdown("---")
    
    # Groups Dropdown
    try:
        current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
        groups_result = movie_mcp_server.list_user_groups(email=current_user_email)
        
        if groups_result.get('groups'):
            groups = groups_result['groups']
            
            group_display_list = []
            group_name_list = []
            for g in groups:
                group_name = g['group_name']
                group_name_list.append(group_name)
                try:
                    members_result = movie_mcp_server.get_group_members(group_id=g['group_id'])
                    member_count = len(members_result.get('members', []))
                    member_text = "member" if member_count == 1 else "members"
                    group_display_list.append(f"{group_name} ({member_count} {member_text})")
                except Exception as member_err:
                    logger.warning(f"Failed to get member count for {group_name}: {member_err}")
                    group_display_list.append(group_name)
            
            current_group = st.session_state.get('current_group_selection')
            if not current_group and group_name_list:
                current_group = group_name_list[0]
            
            default_index = group_name_list.index(current_group) if current_group in group_name_list else 0
            
            selected_group_display = st.selectbox(
                "👥 Groups",
                options=group_display_list,
                index=default_index,
                key="group_switcher_dropdown"
            )
            
            # Extract the actual group name from the display string (remove member count)
            selected_group = group_name_list[group_display_list.index(selected_group_display)]
            
            if selected_group != st.session_state.get('current_group_selection') or not st.session_state.get('current_group_object'):
                st.session_state.current_group_selection = selected_group
                for group in groups:
                    if group['group_name'] == selected_group:
                        st.session_state.current_group_object = group
                        break
                if selected_group != current_group:
                    st.rerun()
        else:
            st.info("👥 No groups yet. Create one below!")
            # Clear stale group selection when user has no groups
            if st.session_state.get('current_group_object'):
                st.session_state.current_group_object = None
                st.session_state.current_group_selection = None
    except Exception as e:
        logger.error(f"Failed to load groups: {e}")
        # Clear stale group selection on error
        if st.session_state.get('current_group_object'):
            st.session_state.current_group_object = None
            st.session_state.current_group_selection = None
    
    # Add Group Creation (collapsible)
    with st.expander("➕ Create New Group", expanded=False):
        new_group = st.text_input("Group name", placeholder="Enter group name...", key="new_group_input", label_visibility="collapsed")
        if st.button("Create Group", use_container_width=True) and new_group:
            st.session_state.quick_query = f"create group {new_group}"
            st.rerun()
    
    st.markdown("---")
    
    # Add Member to Current Group (requires a group to be selected)
    if st.session_state.get('current_group_object'):
        current_group = st.session_state.current_group_object
        group_name = current_group.get('group_name', 'Unknown')
        group_id = current_group.get('group_id')
        
        # Expander 1: Add existing user to group
        with st.expander(f"➕ Add Member to {group_name}", expanded=False):
            # Show current members first
            try:
                members_result = get_cached_group_members(group_id=group_id)
                current_members = members_result.get('members', [])
                
                if current_members:
                    st.markdown("**👥 Current Members:**")
                    for i, member in enumerate(current_members):
                        username = member.get('username', 'Unknown')
                        email = member.get('email', '')
                        if i < len(current_members) - 1:
                            st.markdown(f'<p style="margin: 0 0 0.25rem 0; font-size: 0.875em; color: #e2e8f0;">👤 {username} ({email})</p>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<p style="margin: 0; font-size: 0.875em; color: #e2e8f0;">👤 {username} ({email})</p>', unsafe_allow_html=True)
                    st.markdown('<div style="margin: 0.4rem 0 0.3rem 0;"></div>', unsafe_allow_html=True)
                    st.markdown("---")
            except Exception as e:
                logger.error(f"Failed to load current members: {e}")
            
            # Select existing user to add
            try:
                users_result = movie_mcp_server.list_all_users()
                
                if users_result.get('status') == 'success' and users_result.get('users'):
                    all_users = users_result['users']
                    
                    # Get current group members to filter them out
                    members_result = get_cached_group_members(group_id=group_id)
                    existing_member_emails = set()
                    if members_result.get('members'):
                        existing_member_emails = {m.get('email') for m in members_result['members']}
                    
                    available_users = [u for u in all_users if u['email'] not in existing_member_emails]
                    
                    if available_users:
                        user_options = [f"{u['username']} ({u['email']})" for u in available_users]
                        selected_existing_user = st.selectbox(
                            "Select existing user",
                            options=['-- Select user --'] + user_options,
                            key="existing_user_selector"
                        )
                        
                        st.markdown('<div style="margin: 0.25rem 0;"></div>', unsafe_allow_html=True)
                        if st.button("➕ Add Selected User", use_container_width=True, disabled=(selected_existing_user == '-- Select user --')):
                            if selected_existing_user != '-- Select user --':
                                selected_email = selected_existing_user.split('(')[1].rstrip(')')
                                selected_user_obj = next(u for u in available_users if u['email'] == selected_email)
                                
                                try:
                                    result = movie_mcp_server.add_group_member(
                                        group_id=group_id,
                                        user_id=selected_email
                                    )
                                    
                                    if result.get('status') == 'success':
                                        st.success(f"✅ Added {selected_user_obj['username']} to {group_name}")
                                        # Clear the cached group members so the list refreshes
                                        st.cache_data.clear()
                                        logger.info(f"✅ Cleared cache after adding member to group {group_name}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {result.get('message', 'Failed to add member')}")
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                    else:
                        st.info("ℹ️ All existing users are already members of this group.")
                else:
                    st.info(f"ℹ️ No users found. Create a new user below.")
                    logger.warning(f"list_all_users returned: {users_result}")
            except Exception as e:
                st.error(f"❌ Failed to load users: {str(e)}")
                logger.error(f"Failed to load users for member selection: {e}")
    else:
        with st.expander("➕ Add Member", expanded=False):
            st.info("💡 Select a group above to add members")
    
    st.markdown("---")
    
    active_filters = []
    if st.session_state.get('lang_filter', 'All') != 'All':
        active_filters.append('Language')
    if st.session_state.get('genre_filter', 'All') != 'All':
        active_filters.append('Genre')
    if st.session_state.get('year_range', (2000, 2026)) != (2000, 2026):
        active_filters.append('Year')
    
    filter_count = len(active_filters)
    if filter_count > 0:
        expander_title = f"🔍 Advanced Filters ({filter_count}) 🟢"
    else:
        expander_title = "🔍 Advanced Filters"
    
    with st.expander(expander_title, expanded=False):
        # Show active filter details inside
        if active_filters:
            st.caption(f"**Active:** {', '.join(active_filters)}")
            st.markdown('<div style="margin: 0.5rem 0;"></div>', unsafe_allow_html=True)
        
        languages = ['All', 'English', 'Hindi', 'Telugu', 'Tamil', 'Spanish', 'French', 'Japanese', 'Korean', 'Chinese']
        selected_lang = st.selectbox("🌐 Language", languages, key="lang_filter")
        
        st.markdown('<div style="margin: 0.25rem 0;"></div>', unsafe_allow_html=True)
        genres = ['All', 'Action', 'Comedy', 'Drama', 'Horror', 'Romance', 'Sci-Fi', 'Thriller', 'Animation']
        selected_genre = st.selectbox("🎭 Genre", genres, key="genre_filter")
        
        st.markdown('<div style="margin: 0.25rem 0;"></div>', unsafe_allow_html=True)
        year_range = st.slider(
            "📅 Year Range",
            min_value=1950,
            max_value=2026,
            value=(2000, 2026),
            key="year_range"
        )
        
        st.markdown('<div style="margin: 0.5rem 0;"></div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("🔎 Search with Filters", use_container_width=True):
                filter_query = f"movies"
                if selected_genre != 'All':
                    filter_query = f"{selected_genre} {filter_query}"
                if selected_lang != 'All':
                    filter_query = f"{selected_lang} {filter_query}"
                filter_query += f" from {year_range[0]} to {year_range[1]}"
                st.session_state.filter_query = filter_query
        
        with col2:
            if st.button("🗑️", use_container_width=True, help="Clear all filters"):
                st.session_state.lang_filter = 'All'
                st.session_state.genre_filter = 'All'
                st.session_state.year_range = (2000, 2026)
                st.rerun()
    
    st.markdown("---")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .main .block-container {
        padding: 1.5rem 3rem 8rem 3rem !important;
        max-width: 1400px;
        color: #2d3748;
        background: #f7fafc;
    }
    
    /* Light gray background */
    [data-testid="stAppViewContainer"] {
        background: #f7fafc;
    }
    
    /* Chat input positioning - no overlap with content */
    [data-testid="stBottomBlockContainer"] {
        position: static !important;
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
        margin-top: 2rem !important;
        background: transparent !important;
    }
    
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a202c 0%, #2d3748 100%);
    }
    
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    
    [data-testid="stSidebar"] .stButton button {
        background: #4a5568;
        color: white !important;
        border: 1px solid #718096;
        border-radius: 8px;
        padding: 0.65rem 1.2rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    [data-testid="stSidebar"] .stButton button:hover {
        background: #2d3748;
        border-color: #cbd5e0;
        transform: translateY(-1px);
    }
    
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] .stSelectbox select,
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
        background: rgba(26, 32, 44, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] .stNumberInput input {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] .stTextInput input::placeholder,
    [data-testid="stSidebar"] .stNumberInput input::placeholder {
        color: rgba(255, 255, 255, 0.5) !important;
    }
    
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div,
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] span {
        color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] .stSelectbox [role="button"] {
        color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] .stTextInput input:focus,
    [data-testid="stSidebar"] .stNumberInput input:focus,
    [data-testid="stSidebar"] .stSelectbox select:focus,
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"]:focus-within {
        border-color: #718096 !important;
        background: rgba(26, 32, 44, 0.8) !important;
        box-shadow: 0 0 0 2px rgba(113, 128, 150, 0.2) !important;
        color: #ffffff !important;
    }
    
    [data-testid="stSidebar"] hr {
        margin: 1.5rem 0;
        border-color: rgba(255, 255, 255, 0.1);
    }
    
    /* Sidebar subheaders spacing */
    [data-testid="stSidebar"] .element-container h3 {
        margin-top: 0;
        margin-bottom: 0.75rem;
    }
    
    /* Sidebar captions spacing */
    [data-testid="stSidebar"] .element-container [data-testid="stCaptionContainer"] {
        margin: 0.5rem 0;
    }
    
    .movie-card {
        border: 1px solid rgba(124, 58, 237, 0.2);
        border-radius: 16px;
        padding: 0;
        margin: 20px 0;
        background: white;
        box-shadow: 0 4px 16px rgba(124, 58, 237, 0.12);
        overflow: hidden;
        transition: all 0.3s ease;
    }
    
    .movie-card:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 0 12px 32px rgba(124, 58, 237, 0.25);
        border-color: rgba(124, 58, 237, 0.4);
    }
    
    .movie-card-content {
        padding: 24px;
    }
    
    .star-rating {
        color: #f59e0b;
        font-size: 1.2em;
        font-weight: 700;
        text-shadow: 0 2px 4px rgba(245, 158, 11, 0.3);
    }
    
    .badge {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.8em;
        font-weight: 600;
        margin: 4px 4px 4px 0;
        transition: transform 0.2s ease;
    }
    
    .badge:hover {
        transform: scale(1.05);
    }
    
    .badge-watched { 
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
    }
    
    .badge-unwatched { 
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        color: white;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
    }
    
    .badge-high { 
        background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
        color: white;
        box-shadow: 0 2px 8px rgba(124, 58, 237, 0.3);
    }
    
    .stChatMessage {
        background: white;
        border-radius: 16px;
        padding: 24px;
        margin: 16px 0;
        box-shadow: 0 4px 16px rgba(124, 58, 237, 0.12);
        border: 1px solid rgba(124, 58, 237, 0.15);
        color: #1e293b !important;
    }
    
    [data-testid="stChatMessageContent"] {
        padding: 8px 0;
        color: #1a202c !important;
    }
    
    [data-testid="stChatMessageContent"] * {
        color: #1a202c !important;
    }
    
    .main-title {
        color: #1a202c;
        font-size: 2.5em;
        font-weight: 700;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        letter-spacing: -0.01em;
        text-align: center;
    }
    
    .welcome-banner {
        padding: 24px 28px;
        background: #2d3748;
        border-radius: 12px;
        color: white;
        margin-bottom: 32px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        border: 1px solid #4a5568;
    }
    
    .welcome-banner p {
        margin: 0;
        line-height: 1.6;
    }
    
    .stButton button {
        background: #2d3748;
        color: white;
        border: 1px solid #4a5568;
        border-radius: 8px;
        padding: 0.65rem 1.2rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .stButton button:hover {
        background: #1a202c;
        border-color: #718096;
        transform: translateY(-1px);
    }
    
    /* Main area metrics - dark text on light background */
    [data-testid="stMetric"] {
        padding: 0.5rem;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.8em;
        font-weight: 700;
        color: #1a202c !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #1a202c !important;
    }
    
    [data-testid="stMetricLabel"] > div {
        color: #1a202c !important;
    }
    
    /* Force main content area metrics to be dark */
    div:not([data-testid="stSidebar"]) [data-testid="stMetricLabel"] {
        color: #1a202c !important;
    }
    
    div:not([data-testid="stSidebar"]) [data-testid="stMetricValue"] {
        color: #1a202c !important;
    }
    
    /* Sidebar metrics use light colors */
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color: #e2e8f0 !important;
    }
    
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] > div {
        color: #e2e8f0 !important;
    }
    
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #ffffff !important;
    }
    
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        border-radius: 12px;
        border: 2px solid rgba(124, 58, 237, 0.2);
        padding: 0.75rem 1.2rem;
        transition: all 0.3s ease;
        background: rgba(255, 255, 255, 0.9);
    }
    
    .stTextInput input:focus, .stNumberInput input:focus, .stSelectbox select:focus {
        border-color: #7c3aed;
        box-shadow: 0 0 0 4px rgba(124, 58, 237, 0.15);
        transform: translateY(-1px);
    }
    
    /* Sidebar chat input styling */
    [data-testid="stSidebar"] .stChatInput textarea {
        background: rgba(26, 32, 44, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
        min-height: 52px !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
    }
    
    [data-testid="stSidebar"] .stChatInput textarea::placeholder {
        color: rgba(255, 255, 255, 0.5) !important;
    }
    
    [data-testid="stSidebar"] .stChatInput textarea:focus {
        border-color: #718096 !important;
        background: rgba(26, 32, 44, 0.8) !important;
        box-shadow: 0 0 0 2px rgba(113, 128, 150, 0.2) !important;
    }
    
    /* Sidebar chat section heading */
    [data-testid="stSidebar"] h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    

    
    .streamlit-expanderHeader {
        background: #f7fafc;
        border-radius: 8px;
        padding: 12px 16px;
        font-weight: 500;
        border: 1px solid #e2e8f0;
        margin-bottom: 0.5rem;
    }
    
    /* Sidebar expanders in dark theme */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        background: rgba(26, 32, 44, 0.6);
        border-color: rgba(255, 255, 255, 0.2);
    }
    
    [data-testid="stSidebar"] .streamlit-expanderContent {
        padding: 0.5rem 0;
    }
    
    table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background: white;
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(124, 58, 237, 0.12);
        border: 1px solid rgba(124, 58, 237, 0.2);
    }
    
    thead th {
        background: #2d3748;
        color: white;
        font-weight: 600;
        padding: 18px;
        text-align: left;
    }
    
    tbody tr {
        border-bottom: 1px solid rgba(124, 58, 237, 0.1);
        transition: all 0.3s ease;
    }
    
    tbody tr:hover {
        background: linear-gradient(90deg, rgba(224, 231, 255, 0.4) 0%, rgba(255, 255, 255, 0.6) 100%);
        transform: scale(1.01);
    }
    
    tbody td {
        padding: 14px 16px;
    }
    
    .stSpinner > div {
        border-top-color: #4a5568;
        border-right-color: #2d3748;
    }
    
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f7fafc;
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #cbd5e0;
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #a0aec0;
    }
    
    .dashboard-header {
        color: #1a202c !important;
        font-size: 1.75em;
        font-weight: 600;
        margin-top: 0;
        margin-bottom: 0.75rem;
    }
    
    .dashboard-header * {
        color: #1a202c !important;
    }
    
    .empty-state {
        padding: 48px;
        background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%);
        border-radius: 20px;
        text-align: center;
        margin: 20px 0;
        border: 2px dashed rgba(124, 58, 237, 0.4);
        box-shadow: 0 2px 8px rgba(124, 58, 237, 0.08);
    }
    
    .empty-state-icon {
        font-size: 3em;
        margin-bottom: 16px;
        opacity: 0.7;
    }
    
    .getting-started {
        background: white;
        border-radius: 12px;
        padding: 32px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
        border: 1px solid #e2e8f0;
    }
    
    .getting-started h3 {
        color: #2d3748;
        margin-bottom: 24px;
        font-weight: 600;
    }
    
    .getting-started ul {
        list-style: none;
        padding: 0;
    }
    
    .getting-started li {
        padding: 8px 0;
        color: #4a5568;
        font-size: 0.95em;
    }
    
    .getting-started li::before {
        content: "▸";
        color: #4a5568;
        font-weight: bold;
        margin-right: 8px;
    }
    
    [data-testid="stAlert"], .stAlert {
        background: #2d3748 !important;
        color: #ffffff !important;
        border: 1px solid #4a5568 !important;
        border-radius: 8px !important;
    }
    
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] div,
    [data-testid="stAlert"] span,
    .stAlert p,
    .stAlert div,
    .stAlert span {
        color: #ffffff !important;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .stChatMessage {
        animation: fadeIn 0.3s ease;
    }
    
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem;
        }
        
        .main-title {
            font-size: 2em;
        }
        
        .welcome-banner {
            padding: 16px;
        }
    }
    
    /* Print Styles - Keep UI as-is but make text readable */
    @media print {
        /* FORCE print color adjustment globally - NUCLEAR OPTION */
        * {
            -webkit-print-color-adjust: exact !important;
            color-adjust: exact !important;
            print-color-adjust: exact !important;
        }
        
        /* Force the entire app container */
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] * {
            background: white !important;
            color: #000000 !important;
        }
        
        /* Force body and html */
        html, body {
            background: white !important;
            color: #000000 !important;
        }
        
        /* Keep sidebar visible with white background - NUCLEAR OPTION */
        [data-testid="stSidebar"] {
            background: #ffffff !important;
            background-color: #ffffff !important;
            background-image: none !important;
            border-right: 2px solid #000000 !important;
            filter: none !important;
            -webkit-filter: none !important;
        }
        
        /* NUCLEAR OPTION: Force ALL sidebar content to black text on white background */
        [data-testid="stSidebar"] *,
        [data-testid="stSidebar"] *::before,
        [data-testid="stSidebar"] *::after {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            background: #ffffff !important;
            background-color: #ffffff !important;
            background-image: none !important;
            filter: none !important;
            -webkit-filter: none !important;
            text-shadow: none !important;
            box-shadow: none !important;
        }
        
        /* Extra force for specific elements */
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] h5,
        [data-testid="stSidebar"] h6,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] a,
        [data-testid="stSidebar"] li,
        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] [role="button"] {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        
        /* Sidebar inputs and selects - FORCE white background, black text, borders */
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stNumberInput input,
        [data-testid="stSidebar"] .stSelectbox select,
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"],
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] *,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] select,
        [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            background-color: #ffffff !important;
            background-image: none !important;
            border: 1px solid #000000 !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            filter: none !important;
        }
        
        /* Sidebar buttons - FORCE outlined style with black text */
        [data-testid="stSidebar"] .stButton button,
        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] [role="button"] {
            background: #ffffff !important;
            background-color: #ffffff !important;
            background-image: none !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            border: 1px solid #000000 !important;
            filter: none !important;
        }
        
        /* Sidebar titles and headers */
        [data-testid="stSidebar"] .element-container h1,
        [data-testid="stSidebar"] .element-container h2,
        [data-testid="stSidebar"] .element-container h3 {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        
        /* Main content area - FORCE white background with dark text */
        .main .block-container,
        .main .block-container * {
            background: white !important;
            background-color: white !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            filter: none !important;
        }
        
        .main .block-container {
            padding: 1rem !important;
        }
        
        /* Chat messages - ensure dark text */
        .stChatMessage,
        [data-testid="stChatMessageContent"],
        [data-testid="stChatMessageContent"] * {
            color: #000000 !important;
            background: white !important;
        }
        
        /* Movie cards - white background, dark text, visible borders */
        .movie-card {
            background: white !important;
            border: 2px solid #000000 !important;
            color: #000000 !important;
            page-break-inside: avoid;
        }
        
        .movie-card-content {
            color: #000000 !important;
        }
        
        /* Tables - black text with borders */
        table {
            background: white !important;
            border: 1px solid #000000 !important;
            color: #000000 !important;
        }
        
        thead th {
            background: white !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
            font-weight: bold;
        }
        
        tbody td {
            color: #000000 !important;
            border: 1px solid #cccccc !important;
        }
        
        tbody tr {
            background: white !important;
        }
        
        /* Badges - add border and background */
        .badge {
            color: #000000 !important;
            border: 1px solid #000000 !important;
            background: white !important;
        }
        
        /* Dashboard elements */
        .dashboard-header,
        .dashboard-header * {
            color: #000000 !important;
        }
        
        /* Welcome banner */
        .welcome-banner,
        .welcome-banner p {
            background: white !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
        }
        
        /* Empty state */
        .empty-state {
            background: white !important;
            border: 2px dashed #000000 !important;
            color: #000000 !important;
        }
        
        /* Buttons - outline style for print */
        .stButton button {
            background: white !important;
            color: #000000 !important;
            border: 1px solid #000000 !important;
        }
        
        /* Headings */
        h1, h2, h3, h4, h5, h6 {
            color: #000000 !important;
        }
        
        /* Paragraphs and text */
        p, span, div, li, td, th {
            color: #000000 !important;
        }
        
        /* Page breaks for better pagination */
        .stChatMessage {
            page-break-inside: avoid;
        }
        
        /* Remove shadows and transitions for print */
        * {
            box-shadow: none !important;
            transition: none !important;
            transform: none !important;
        }
        
        /* Keep images visible */
        img {
            max-width: 100%;
            page-break-inside: avoid;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">🍿 AI Movie Planner</h1>', unsafe_allow_html=True)


@st.cache_data
def build_dynamic_tool_descriptions() -> str:
    """Inspect movie_mcp_server functions directly to generate schema descriptions."""
    descriptions = []
    for tool_name in ROUTER_TOOLS:
        func = getattr(movie_mcp_server, tool_name, None)
        if not func:
            continue
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or "No description provided."
        summary = doc.strip().split("\n\n")[0].replace("\n", " ")
        descriptions.append(f'- "{tool_name}": signature {tool_name}{sig}\n  Description: {summary}')
    return "\n".join(descriptions)


def post_to_llm_with_retry(payload: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
    """Execute Databricks Model Serving requests with exponential backoff on 429."""
    headers = w.config.authenticate()
    headers["Content-Type"] = "application/json"

    for attempt in range(max_retries):
        response = requests.post(MODEL_ENDPOINT, headers=headers, json=payload, timeout=25)
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()


def call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the specified MCP tool with arguments."""
    try:
        tool_func = getattr(movie_mcp_server, tool_name, None)
        if tool_func is None:
            return {"error": f"Unknown tool: {tool_name}"}
        result = tool_func(**arguments)
        return movie_mcp_server.make_json_serializable(result)
    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name} - {e}")
        return {"error": str(e)}


def render_star_rating(rating: Optional[float]) -> str:
    """Render star rating visualization."""
    if not rating:
        return "☆☆☆☆☆ (no rating)"
    
    full_stars = int(rating)
    half_star = 1 if (rating - full_stars) >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    stars = "⭐" * full_stars + "🌟" * half_star + "☆" * empty_stars
    return f"{stars} ({rating:.1f}/5.0)"


def get_genre_color(genre: str) -> str:
    """Get color for genre badge."""
    return GENRE_COLORS.get(genre, '#808080')


def get_language_name(lang_code: str) -> str:
    """Convert language code to full language name safely."""
    if not lang_code or not isinstance(lang_code, str):
        return "Unknown"
    
    return LANGUAGE_MAP.get(lang_code, LANGUAGE_MAP.get(lang_code.lower(), lang_code.capitalize()))


def render_movie_card(movie: Dict[str, Any], show_poster: bool = True) -> str:
    """Render a beautiful movie card with poster, language badge, and genre tags."""
    title = movie.get('title') or movie.get('original_title') or movie.get('name') or 'Unknown Movie'
    year = movie.get('release_year')
    if not year and movie.get('release_date'):
        year = movie.get('release_date')[:4] if len(movie.get('release_date', '')) >= 4 else None
    if not year:
        year = 'N/A'
    
    rating = movie.get('tmdb_rating') or movie.get('vote_average', 'N/A')
    overview = movie.get('overview', 'No description available.')
    poster_url = movie.get('poster_url', '')
    language = movie.get('original_language', '')
    runtime = movie.get('runtime')
    director = movie.get('director', '')
    
    genres = movie.get('genres', [])
    if isinstance(genres, str):
        try:
            genres = json.loads(genres)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse genres for movie: {title}")
            genres = []
    
    genre_names = [g.get('name', '') if isinstance(g, dict) else g for g in genres]
    genre_names = [g for g in genre_names if g]
    
    if year and year != 'N/A':
        card_text = f"### 🎬 {title} ({year})\n\n"
    else:
        card_text = f"### 🎬 {title}\n\n"
    
    badges = []
    if language:
        lang_display = get_language_name(language)
        badges.append(f"🌐 **{lang_display}**")
    if runtime and runtime > 0:
        hours = runtime // 60
        mins = runtime % 60
        if hours > 0:
            badges.append(f"⏱️ **{hours}h {mins}m**")
        else:
            badges.append(f"⏱️ **{mins}m**")
    if director:
        badges.append(f"🎬 **{director}**")
    
    if badges:
        card_text += " | ".join(badges) + "\n\n"
    
    if show_poster:
        if poster_url:
            card_text += f'<div style="text-align: center; margin: 16px 0;"><img src="{poster_url}" style="max-width: 300px; width: 100%; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" alt="{title} poster" /></div>\n\n'
        else:
            # Log missing poster for debugging
            logger.warning(f"⚠️ No poster_url found for movie: {title}")
            # Show placeholder
            card_text += f'<div style="text-align: center; margin: 16px 0; padding: 80px 20px; background: linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 100%); border-radius: 12px; border: 2px dashed #999;"><span style="font-size: 3em; opacity: 0.5;">🎬</span><br/><span style="color: #666; font-size: 0.9em;">Poster unavailable</span></div>\n\n'
    
    if rating != 'N/A':
        try:
            rating_float = float(rating)
            stars = render_star_rating(rating_float / 2)  # TMDB is /10, convert to /5
            card_text += f"⭐ **Rating:** {stars}\n\n"
        except ValueError:
            # If rating is not a valid float, try to normalize it if it looks like a number
            try:
                rating_val = float(str(rating).replace('/10', '').strip())
                normalized = round(rating_val / 2, 1)
                card_text += f"⭐ **Rating:** {normalized:.1f}/5\n\n"
            except:
                card_text += f"⭐ **Rating:** {rating}\n\n"
    
    if genre_names and len(genre_names) > 0:
        genre_badges = []
        for genre in genre_names[:MAX_GENRES_DISPLAY]:
            color = get_genre_color(genre)
            genre_badges.append(f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">{genre}</span>')
        card_text += " ".join(genre_badges) + "\n\n"
    
    if len(overview) > MAX_OVERVIEW_LENGTH:
        overview = overview[:MAX_OVERVIEW_LENGTH - 3] + "..."
    
    card_text += f"📝 **Overview:** {overview}\n\n"
    card_text += "---\n\n"
    
    return card_text


def render_watchlist_table(movies: List[Dict[str, Any]]) -> str:
    """Render watchlist as an enhanced Markdown table with better visuals."""
    if not movies:
        return EMPTY_WATCHLIST_HTML
    
    table = "| 🎬 **Title** | 📅 **Year** | ⭐ **Rating** | 🌐 **Language** | 🎯 **Status** |\n"
    table += "|----------------|----------|--------------|--------------|------------|\n"
    
    for movie in movies:
        title = movie.get('title', 'Unknown')[:MAX_TITLE_LENGTH_TABLE]
        year = movie.get('release_year', 'N/A')
        rating = movie.get('tmdb_rating', 'N/A')
        language = movie.get('original_language', 'N/A')
        watched = movie.get('watched', False)
        
        status = '✅ Watched' if watched else '🕒 To Watch'
        
        if rating != 'N/A':
            try:
                rating_val = float(rating) / 2
                rating_stars = "⭐" * int(rating_val) + f" {rating_val:.1f}/5"
            except:
                rating_stars = str(rating)
        else:
            rating_stars = '—'
        
        if language and language != 'N/A':
            lang_display = get_language_name(language)
        else:
            lang_display = '—'
        
        table += f"| {title} | {year} | {rating_stars} | {lang_display} | {status} |\n"
    
    return table


def render_ratings_table(ratings: List[Dict[str, Any]]) -> str:
    """Render ratings as an enhanced Markdown table."""
    if not ratings:
        return EMPTY_RATINGS_HTML
    
    table = "| 🎬 **Movie** | ⭐ **Rating** | 👤 **User** | 📅 **Date** | 💬 **Sentiment** |\n"
    table += "|----------------|-------------|---------|----------|---------------|\n"
    
    for rating in ratings:
        movie_title = rating.get('movie_title', 'Unknown')[:MAX_TITLE_LENGTH_RATING]
        user_rating = rating.get('rating', rating.get('user_rating', 0))
        # Backend returns 'username' and 'email', not 'user_email'
        user = rating.get('username', rating.get('email', 'Anonymous').split('@')[0] if rating.get('email') else 'Anonymous')
        # Backend returns 'created_at', not 'rated_at'
        rated_at = rating.get('created_at', 'N/A')
        
        if isinstance(rated_at, str) and 'T' in rated_at:
            rated_at = rated_at.split('T')[0]
        
        # Ratings are stored on /5 scale (no conversion needed)
        stars = render_star_rating(float(user_rating))
        
        # Sentiment comes from backend (business rule), frontend only maps to emoji for display
        sentiment_map = {
            'loved': '🤩 Loved it!',
            'liked': '😊 Liked it',
            'okay': "😐 It's okay",
            'disliked': "😞 Didn't like"
        }
        sentiment = sentiment_map.get(rating.get('sentiment', ''), '')
        
        table += f"| {movie_title} | {stars} | {user} | {rated_at} | {sentiment} |\n"
    
    return table


def render_personal_dashboard() -> None:
    """Render Variant A: Personal Dashboard with user-specific stats and activity."""
    
    # Compact dashboard CSS
    st.markdown("""
    <style>
        /* Make dashboard compact with minimal spacing */
        .main .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
        }
        
        /* Eliminate vertical spacing in all dashboard elements */
        [data-testid="column"] {
            padding: 0 !important;
            margin: 0 !important;
        }
        
        [data-testid="stHorizontalBlock"] {
            gap: 0.5rem !important;
            margin: 0 0 0.5rem 0 !important;
            padding: 0 !important;
        }
        
        .element-container {
            margin: 0 0 0.25rem 0 !important;
        }
        
        .stMarkdown {
            margin-bottom: 0.25rem !important;
        }
        
        /* Force compact paragraph spacing */
        .stMarkdown p {
            margin-bottom: 0.25rem !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Get current user email from session state
    current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
    current_username = st.session_state.get('current_user_override') or 'User'
    current_group = st.session_state.get('current_group_object')
    
    if not current_group:
        st.info("👋 Welcome! Please select a group from the sidebar to see your personalized dashboard.")
        return
    
    group_name = current_group.get('group_name', 'Unknown Group')
    group_id = current_group.get('group_id')
    
    st.markdown(f'<div class="dashboard-header" style="margin-bottom: 0.75rem;">🎯 {current_username}\'s Activity in <span style="color: #4299e1; font-weight: 600;">{group_name}</span></div>', unsafe_allow_html=True)
    
    # Fetch pre-computed stats from backend + ratings for loved movies display
    try:
        stats_result = movie_mcp_server.get_user_dashboard_stats(group_id=group_id, email=current_user_email)
        ratings_result = movie_mcp_server.get_my_ratings(group_id=group_id, email=current_user_email)
        
        ratings = ratings_result.get('ratings', [])
        
        # Stats come pre-computed from backend (no aggregation in frontend)
        if stats_result.get('status') == 'success':
            movies_watched = stats_result.get('movies_watched', 0)
            unwatched = stats_result.get('movies_pending', 0)
            total_watchlist = stats_result.get('total_watchlist', 0)
            avg_rating_raw = stats_result.get('avg_rating_given', 0.0)
            total_ratings = stats_result.get('total_ratings', 0)
            watched_not_rated = stats_result.get('watched_not_rated', [])
        else:
            movies_watched = 0
            unwatched = 0
            total_watchlist = 0
            avg_rating_raw = 0.0
            total_ratings = 0
            watched_not_rated = []
        
        avg_rating = avg_rating_raw  # Already on /5 scale
        avg_rating_display = f"{avg_rating:.1f}/5" if avg_rating > 0 else "0/5"
        
        # Get personal watchlist FIRST (movies not yet rated by this user)
        to_watch_result = movie_mcp_server.get_watchlist(
            group_id=group_id,
            status='pending',  # Not marked as watched
            filter_by_user=current_user_email,  # ✅ Show only movies this user added
            exclude_rated_by=None  # No need to exclude - already filtered by user
        )
        unwatched_movies = to_watch_result.get('watchlist', [])
        personal_pending_count = len(unwatched_movies)  # Count of movies YOU haven't rated yet
        
        st.markdown(f"""
<p style="margin: 0 0 0.3rem 0; font-size: 0.95em; color: #2d3748;">
    <span style="font-weight: 400;">Movies Watched:</span> 
    <span style="font-weight: 700; font-size: 1.1em; color: #1a202c;">{movies_watched}</span>
</p>
<p style="margin: 0 0 0.3rem 0; font-size: 0.95em; color: #2d3748;">
    <span style="font-weight: 400;">Avg Rating:</span> 
    <span style="font-weight: 700; font-size: 1.1em; color: #1a202c;">{avg_rating_display}</span>
</p>
<p style="margin: 0 0 0.3rem 0; font-size: 0.95em; color: #2d3748;">
    <span style="font-weight: 400;">Watchlist:</span> 
    <span style="font-weight: 700; font-size: 1.1em; color: #1a202c;">{personal_pending_count} pending</span>
</p>
<p style="margin: 0 0 0.5rem 0; font-size: 0.95em; color: #2d3748;">
    <span style="font-weight: 400;">Total Ratings:</span> 
    <span style="font-weight: 700; font-size: 1.1em; color: #1a202c;">{total_ratings}</span>
</p>
        """, unsafe_allow_html=True)
        
        st.markdown('<hr style="margin: 1rem 0; border-color: #e2e8f0;" />', unsafe_allow_html=True)
        
        # Combined Section: My Ratings + Watched (Not Rated) + Want to Watch
        col_left, col_middle, col_right = st.columns(3)  # Streamlit UI layout, not Spark - SCPAP001 false positive
        
        # LEFT: My Ratings (all rated movies)
        with col_left:
            st.markdown('<div style="margin-top: 0; margin-bottom: 0.5rem;"><span style="color: #262730; font-size: 1.17em; font-weight: 600;">⭐ My Ratings</span> <span style="color: #718096; font-size: 0.875em; margin-left: 0.5rem;">🎬 All movies you\'ve rated</span></div>', unsafe_allow_html=True)
            # Show all ratings for this user (no filtering by score)
            # Display is personalized - each user sees only their own ratings
            my_ratings = ratings  # Show all ratings, not just 4+ stars
            
            if my_ratings:
                for rating in my_ratings[:3]:
                    movie_title = rating.get('movie_title') or f"Movie #{rating.get('movie_id', '?')}"
                    user_rating_raw = float(rating.get('rating', 0))
                    user_rating_display = user_rating_raw  # Already on /5 scale
                    stars = "⭐" * round(user_rating_display)
                    
                    st.markdown(f'<p style="margin: 0 0 0.35rem 0; color: #1a202c;"><strong>{movie_title}</strong> <span style="color: #718096; font-size: 0.875em;">{stars} {user_rating_display:.1f}/5.0</span></p>', unsafe_allow_html=True)
                
                if len(my_ratings) > 3:
                    st.caption(f"_...and {len(my_ratings) - 3} more_")
            else:
                st.markdown('<p style="color: #6366f1 !important; font-size: 0.95em; padding: 16px; background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%); border-radius: 12px; border: 2px dashed rgba(124, 58, 237, 0.3); text-align: center; font-weight: 500;">✨ No ratings yet</p>', unsafe_allow_html=True)
        
        # MIDDLE: Watched but Not Rated (movies marked watched in group, but you haven't rated yet)
        with col_middle:
            st.markdown('<div style="margin-top: 0; margin-bottom: 0.5rem;"><span style="color: #262730; font-size: 1.17em; font-weight: 600;">🎬 Watched (Not Rated)</span> <span style="color: #718096; font-size: 0.875em; margin-left: 0.5rem;">⏳ Rate these movies</span></div>', unsafe_allow_html=True)
            
            if watched_not_rated:
                for movie in watched_not_rated[:3]:
                    title = movie.get('title', 'Unknown')
                    year = movie.get('release_year')
                    title_display = f"{title} ({year})" if year else title
                    st.markdown(f'<p style="margin: 0 0 0.35rem 0; color: #1a202c;"><strong>{title_display}</strong></p>', unsafe_allow_html=True)
                
                if len(watched_not_rated) > 3:
                    st.caption(f"_...and {len(watched_not_rated) - 3} more_")
            else:
                # Check if there are actually watched movies before showing "All rated!"
                if movies_watched > 0:
                    st.markdown('<p style="color: #10b981 !important; font-size: 0.95em; padding: 16px; background: linear-gradient(135deg, #f0fdf9 0%, #ecfdf5 100%); border-radius: 12px; border: 2px solid rgba(16, 185, 129, 0.3); text-align: center; font-weight: 500;">✨ All rated!</p>', unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color: #6366f1 !important; font-size: 0.95em; padding: 16px; background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%); border-radius: 12px; border: 2px dashed rgba(124, 58, 237, 0.3); text-align: center; font-weight: 500;">📋 No watched movies yet</p>', unsafe_allow_html=True)
        
        # RIGHT: Want to Watch (unwatched from watchlist)
        with col_right:
            st.markdown('<div style="margin-top: 0; margin-bottom: 0.5rem;"><span style="color: #262730; font-size: 1.17em; font-weight: 600;">Watchlist</span> <span style="color: #718096; font-size: 0.875em; margin-left: 0.5rem;">📝 Movies you want to watch</span></div>', unsafe_allow_html=True)
            
            if unwatched_movies:
                for movie in unwatched_movies[:3]:
                    title = movie.get('title', 'Unknown')
                    st.markdown(f'<p style="margin: 0 0 0.35rem 0; color: #1a202c;"><strong>{title}</strong></p>', unsafe_allow_html=True)
                
                if len(unwatched_movies) > 3:
                    st.caption(f"_...and {len(unwatched_movies) - 3} more_")
            else:
                # Check if watchlist is completely empty or all watched
                if total_watchlist == 0:
                    st.markdown('<p style="color: #6366f1 !important; font-size: 0.95em; padding: 16px; background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%); border-radius: 12px; border: 2px dashed rgba(124, 58, 237, 0.3); text-align: center; font-weight: 500;">📋 Watchlist is empty</p>', unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color: #10b981 !important; font-size: 0.95em; padding: 16px; background: linear-gradient(135deg, #f0fdf9 0%, #ecfdf5 100%); border-radius: 12px; border: 2px solid rgba(16, 185, 129, 0.3); text-align: center; font-weight: 500;">✨ All caught up!</p>', unsafe_allow_html=True)
        

        
    except Exception as e:
        logger.error(f"Failed to load personal dashboard: {e}")
        logger.exception("Full dashboard error traceback:")
        st.error("❌ Unable to load dashboard. Please try again.")
        st.info("💡 **Tip:** Start by asking me to search for movies or show your watchlist!")


def _parse_llm_routing_response(raw_text: str) -> Dict[str, Any]:
    """Parse LLM routing response, handling code blocks and JSON extraction."""
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    
    return json.loads(raw_text.strip())


def _resolve_group_id(tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
    """Resolve group ID via backend. Returns error message if resolution fails, None if success.
    
    Auto-injects selected group from session state if user didn't specify one.
    """
    if tool_name not in TOOLS_REQUIRING_GROUP:
        return None
    
    group_id = tool_args.get("group_id", "")
    current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
    
    # Auto-inject selected group if user didn't specify one
    if group_id in ["", "MISSING_GROUP"]:
        current_group = st.session_state.get('current_group_object')
        if current_group:
            logger.info(f"✅ Auto-injecting selected group: {current_group.get('group_name')}")
            tool_args["group_id"] = current_group.get('group_id')
            return None  # Success - group auto-injected
        else:
            return "⚠️ Please select a group from the sidebar first, or specify the group name in your request."
    
    # User specified a group name/ID - resolve it
    result = movie_mcp_server.resolve_group_id(group_id_or_name=group_id, email=current_user_email)
    
    if result.get('status') == 'success':
        tool_args["group_id"] = result['resolved_id']
        return None
    else:
        return result.get('message', 'Failed to resolve group.')


def _auto_inject_email(tool_name: str, tool_args: Dict[str, Any]) -> None:
    """Auto-inject current user's email for tools that require it.
    
    This ensures the backend knows which user is performing the action.
    For tools in TOOLS_ALWAYS_CURRENT_USER, the email is ALWAYS overridden with
    the current user's session state email — the LLM's default must never be used.
    For get_my_ratings, the email is only injected if missing (user may ask about
    another person's ratings, e.g. "what does alice like?").
    """
    if tool_name not in TOOLS_REQUIRING_EMAIL:
        return
    
    current_email = tool_args.get("email", "")
    current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
    
    # For tools that always operate as the current user, override regardless
    if tool_name in TOOLS_ALWAYS_CURRENT_USER:
        if current_email != current_user_email:
            logger.info(f"✅ Overriding email for {tool_name}: '{current_email}' -> '{current_user_email}'")
            tool_args["email"] = current_user_email
        return
    
    # For other tools (e.g. get_my_ratings), only inject if missing/placeholder
    if current_email in ["", "MISSING_EMAIL", None]:
        logger.info(f"✅ Auto-injecting current user email: {current_user_email}")
        tool_args["email"] = current_user_email


def _resolve_movie_id(tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
    """Resolve movie ID via backend. Returns error message if resolution fails, None if success."""
    # compare_movies accepts titles directly, no resolution needed
    if tool_name == "compare_movies":
        return None
    
    if tool_name not in TOOLS_NEEDING_MOVIE_ID or "movie_id" not in tool_args:
        return None
    
    movie_id = tool_args.get("movie_id", "")
    
    result = movie_mcp_server.resolve_movie_id(movie_id_or_title=movie_id)
    
    if result.get('status') == 'success':
        tool_args["movie_id"] = result['resolved_id']
        return None
    elif result.get('status') == 'multiple_matches':
        # Display all candidate movies and prompt user to clarify
        matches = result.get('matches', [])
        searched_title = result.get('searched_title', movie_id)
        
        output = f"### 🎬 Multiple movies named '{searched_title}'\n\n"
        output += f"I found **{len(matches)} movies** with that title. Which one did you mean?\n\n"
        output += "---\n\n"
        
        for i, movie in enumerate(matches, start=1):
            title = movie.get('title', 'Unknown')
            year = movie.get('release_year', 'N/A')
            poster_url = movie.get('poster_url', '')
            director = movie.get('director', 'N/A')
            
            output += f"### {i}. {title} ({year})\n\n"
            
            # Show poster if available
            if poster_url:
                output += f'<div style="text-align: center; margin: 16px 0;"><img src="{poster_url}" style="max-width: 250px; width: 100%; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" alt="{title} poster" /></div>\n\n'
            
            # Show key movie info: Year and Director only
            output += f"🎬 **Director:** {director}\n\n"
            output += "---\n\n"
        
        output += "\n\n💡 **Please specify which one** by including the year in your request.\n\n"
        output += f"For example: _'{searched_title} ({matches[0].get('year') if matches else 'YYYY'})'_"
        
        return output
    else:
        return result.get('message', 'Failed to resolve movie.')


def _format_tool_result(tool_result: Dict[str, Any], user_query: str, tool_name: str) -> str:
    """Format tool execution results into user-friendly output."""
    if 'movies' in tool_result and tool_result['movies']:
        movies = tool_result['movies']
        if movies:
            logger.info(f"🎥️ First movie data keys: {list(movies[0].keys())}")
        
        output = f"### 🎬 Found {len(movies)} movie(s)\n\n"
        for movie in movies[:MAX_DISPLAY_MOVIES]:
            output += render_movie_card(movie) + "\n"
        return output
    
    if 'watchlist' in tool_result and tool_result['watchlist']:
        group_name = tool_result.get('group_name', 'this group')
        movies = tool_result['watchlist']
        output = f"### 📝 Watchlist for {group_name}\n\n"
        output += f"Total movies: **{len(movies)}**\n\n"
        output += render_watchlist_table(movies)
        return output
    
    if 'ratings' in tool_result and tool_result['ratings']:
        ratings = tool_result['ratings']
        output = f"### ⭐ Ratings\n\n"
        output += f"Total ratings: **{len(ratings)}**\n\n"
        output += render_ratings_table(ratings)
        return output
    
    if 'rated_movies' in tool_result:
        rated_movies = tool_result.get('rated_movies', [])
        group_name = tool_result.get('group_name', 'this group')
        
        if not rated_movies:
            output = f"### ⭐ Group Ratings for {group_name}\n\n"
            output += EMPTY_RATINGS_HTML
            return output
        
        output = f"### ⭐ Group Ratings for {group_name}\n\n"
        output += f"Total movies rated: **{len(rated_movies)}**\n\n"
        # rated_movies has: movie_id, avg_rating, rating_count, last_rated, raters
        output += "<table style='width: 100%;'>\n"
        output += "<thead><tr><th>Movie</th><th>Avg Rating</th><th>Ratings</th><th>Raters</th></tr></thead>\n"
        output += "<tbody>\n"
        for movie in rated_movies:
            movie_title = movie.get('movie_title') or f"Movie #{movie.get('movie_id')}"
            avg_rating_display = f"{float(movie.get('avg_rating', 0)):.1f}/5.0"  # Already on /5 scale
            stars = "⭐" * int(round(float(movie.get('avg_rating', 0))))
            output += f"<tr><td><strong>{movie_title}</strong></td><td>{stars} {avg_rating_display}</td><td>{movie.get('rating_count', 0)}</td><td>{movie.get('raters', 'N/A')}</td></tr>\n"
        output += "</tbody></table>\n"
        return output
    
    if 'groups' in tool_result and tool_result['groups']:
        groups = tool_result['groups']
        output = f"### 👥 Your Groups ({len(groups)})\n\n"
        for group in groups:
            name = group.get('group_name', 'Unnamed')
            created = group.get('created_at', 'N/A')
            if isinstance(created, str) and 'T' in created:
                created = created.split('T')[0]
            output += f"* **{name}** (Created: {created})\n"
        return output
    
    if 'comparisons' in tool_result and tool_result['comparisons']:
        comparisons = tool_result['comparisons']
        movie_count = tool_result.get('movie_count', len(comparisons))
        output = f"### 🎬 Movie Comparison ({movie_count} Movies)\n\n"
        
        # Show movies side-by-side with posters
        if len(comparisons) >= 2:
            # Create side-by-side poster cards
            output += "<div style='display: flex; gap: 20px; flex-wrap: wrap; justify-content: center;'>\n"
            
            for movie in comparisons:
                poster_url = movie.get('poster_url', '')
                title = movie.get('title', 'Unknown')
                year = movie.get('release_year', 'N/A')
                tmdb_rating = movie.get('tmdb_rating') or movie.get('vote_average', 0)
                rating = round(tmdb_rating / 2, 1) if tmdb_rating else 0  # Normalize /10 to /5 scale
                runtime = movie.get('runtime', 0)
                director = movie.get('director', 'N/A')
                
                # Format runtime
                hours = runtime // 60 if runtime else 0
                mins = runtime % 60 if runtime else 0
                runtime_str = f"{hours}h {mins}m" if hours > 0 else (f"{mins}m" if mins > 0 else "N/A")
                
                # Format genres
                genres = movie.get('genres', [])
                if isinstance(genres, str):
                    genres_display = genres
                elif isinstance(genres, list):
                    genre_names = [g.get('name', g) if isinstance(g, dict) else g for g in genres]
                    genres_display = ', '.join(genre_names[:3])
                else:
                    genres_display = 'N/A'
                
                # Movie card
                output += f"""
<div style='flex: 1; min-width: 280px; max-width: 400px; border: 1px solid #ddd; border-radius: 8px; padding: 15px; background: #f9f9f9;'>
    <div style='text-align: center;'>
        {'<img src="' + poster_url + '" style="width: 100%; max-width: 300px; border-radius: 8px; margin-bottom: 15px;" />' if poster_url else ''}
    </div>
    <h4 style='margin: 10px 0; text-align: center;'>{title} ({year})</h4>
    <div style='line-height: 1.8;'>
        <div><strong>⭐ Rating:</strong> {rating:.1f}/5</div>
        <div><strong>⏱️ Runtime:</strong> {runtime_str}</div>
        <div><strong>🎭 Genres:</strong> {genres_display}</div>
        <div><strong>🎬 Director:</strong> {director}</div>
    </div>
</div>
"""
            
            output += "</div>\n\n"
            
            # PERSONALIZED RECOMMENDATION - Backend handles scoring, frontend handles presentation
            output += "---\n\n"
            
            # Call backend to get personalized recommendation (business logic lives there)
            try:
                current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
                current_group = st.session_state.get('current_group_object')
                group_id = current_group.get('group_id') if current_group else None
                
                rec_result = movie_mcp_server.get_personalized_recommendation(
                    comparisons=comparisons,
                    email=current_user_email,
                    group_id=group_id
                )
            except Exception as e:
                logger.warning(f"Could not get personalized recommendation: {e}")
                rec_result = {'status': 'error', 'message': str(e)}
            
            # Format the structured recommendation as markdown (presentation only)
            if rec_result.get('status') == 'success' and rec_result.get('winner'):
                winner = rec_result['winner']
                has_history = rec_result.get('has_history', False)
                total_ratings = rec_result.get('total_ratings', 0)
                alternatives = rec_result.get('alternatives', [])
                movie_count = len(comparisons)
                
                winner_title = winner.get('title', 'Unknown')
                winner_rating = winner.get('rating', 0)
                winner_reasons = winner.get('reasons', [])
                
                if has_history:
                    if movie_count == 2:
                        output += f"### 🎯 **Watch {winner_title}**\n\n"
                        output += f"Based on your rating history ({total_ratings} movies rated), this is the perfect match for you.\n\n"
                    else:
                        output += f"### 🎯 **Watch {winner_title}**\n\n"
                        output += f"Based on your rating history ({total_ratings} movies rated), this is the best match among the {movie_count} options.\n\n"
                    
                    output += f"**Why this recommendation:**\n"
                    for reason in winner_reasons:
                        output += f"* {reason}\n"
                    output += f"\n**Rating:** {winner_rating:.1f}/5\n\n"
                    
                    if movie_count == 2 and alternatives:
                        alt = alternatives[0]
                        alt_title = alt.get('title', 'Unknown')
                        alt_rating = alt.get('rating', 0)
                        score_diff = winner.get('score', 0) - alt.get('score', 0)
                        if score_diff > 5:
                            output += f"_(While {alt_title} ({alt_rating:.1f}/5) is also strong, {winner_title} aligns much better with your taste profile.)_\n\n"
                        else:
                            output += f"_(Both are great choices, but {winner_title} edges ahead based on your preferences.)_\n\n"
                    elif alternatives:
                        output += f"**Other strong options (ranked by your preferences):**\n"
                        for i, alt in enumerate(alternatives, start=2):
                            alt_title = alt.get('title', 'Unknown')
                            alt_rating = alt.get('rating', 0)
                            output += f"{i}. *{alt_title}* ({alt_rating:.1f}/5)\n"
                        output += "\n"
                else:
                    if movie_count == 2:
                        output += f"### 🎯 **Watch {winner_title}**\n\n"
                        output += f"Since you haven't rated movies yet, here's my recommendation based on overall quality and acclaim.\n\n"
                    else:
                        output += f"### 🎯 **Watch {winner_title}**\n\n"
                        output += f"Among {movie_count} strong options, here's my recommendation based on overall quality.\n\n"
                    
                    output += f"**Why {winner_title}:**\n"
                    for reason in winner_reasons:
                        output += f"* {reason}\n"
                    output += f"\n**Rating:** {winner_rating:.1f}/5\n\n"
                    
                    if alternatives:
                        output += f"**Other strong options:**\n"
                        for i, alt in enumerate(alternatives, start=2):
                            alt_title = alt.get('title', 'Unknown')
                            alt_rating = alt.get('rating', 0)
                            output += f"{i}. *{alt_title}* ({alt_rating:.1f}/5)\n"
                        output += "\n"
                    
                    output += f"💡 _**Tip:** Rate movies in your watchlist to get personalized recommendations that match your taste!_\n\n"
            else:
                output += "### 🎯 **Recommendation unavailable**\n\n"
                output += "Could not generate a personalized recommendation at this time.\n\n"

        
        return output
    
    if 'movie' in tool_result:
        output = "### 🎬 Movie Details\n\n"
        output += render_movie_card(tool_result['movie'])
        return output
    
    # Handler for get_group_preferences results
    if 'liked_movies' in tool_result and tool_result.get('status') == 'success':
        group_id = tool_result.get('group_id', 'Unknown')
        liked_movie_ids = tool_result.get('liked_movies', [])
        disliked_movie_ids = tool_result.get('disliked_movies', [])
        stats = tool_result.get('statistics', {})
        
        # Get group name for display
        try:
            group_name_result = movie_mcp_server.get_group_by_name(group_name=group_id)
            if group_name_result.get('group'):
                group_name = group_name_result['group'].get('group_name', group_id)
            else:
                # Try getting by group_id directly
                members_result = movie_mcp_server.get_group_members(group_id=group_id)
                group_name = group_id  # Fallback
        except Exception:
            group_name = "Your Group"
        
        output = f"### 🎯 {group_name}'s Movie Preferences\n\n"
        
        # Show statistics
        avg_rating = stats.get('avg_rating', 0)
        movies_rated = stats.get('movies_rated', 0)
        active_members = stats.get('active_members', 0)
        
        if movies_rated == 0:
            output += "📊 **No ratings yet!** Start rating movies to discover your group's preferences.\n\n"
            return output
        
        output += f"📊 **Statistics:**\n"
        output += f"* **Average Rating:** {avg_rating:.1f}/5.0\n"
        output += f"* **Movies Rated:** {movies_rated}\n"
        output += f"* **Active Members:** {active_members}\n\n"
        output += "---\n\n"
        
        # Fetch details for top 10 liked movies to analyze genres/themes
        if liked_movie_ids:
            genre_counts = {}
            director_counts = {}
            liked_movies_details = []
            
            for movie_id in liked_movie_ids[:10]:  # Analyze top 10
                try:
                    details_result = movie_mcp_server.get_movie_details(movie_id=str(movie_id))
                    if details_result.get('status') == 'success' and details_result.get('movie'):
                        movie = details_result['movie']
                        liked_movies_details.append(movie)
                        
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
                except Exception as e:
                    logger.warning(f"Failed to fetch movie {movie_id} for preferences: {e}")
            
            # Display favorite genres
            if genre_counts:
                sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
                output += f"### 🎭 **Favorite Genres**\n\n"
                for genre, count in sorted_genres[:5]:
                    output += f"* **{genre}** ({count} movie{'s' if count > 1 else ''})\n"
                output += "\n"
            
            # Display favorite directors
            if director_counts:
                sorted_directors = sorted(director_counts.items(), key=lambda x: x[1], reverse=True)
                top_directors = [d for d, c in sorted_directors if c >= 2]  # Only directors with 2+ movies
                if top_directors:
                    output += f"### 🎬 **Favorite Directors**\n\n"
                    for director in top_directors[:3]:
                        output += f"* {director}\n"
                    output += "\n"
            
            # Show example liked movies
            output += f"### ⭐ **Movies You Loved**\n\n"
            for movie in liked_movies_details[:5]:
                title = movie.get('title', 'Unknown')
                year = movie.get('release_year')
                tmdb_rating = movie.get('tmdb_rating', 0)
                rating = round(tmdb_rating / 2, 1) if tmdb_rating else 0  # Normalize to /5 scale
                title_display = f"{title} ({year})" if year else title
                output += f"* **{title_display}** - {rating:.1f}/5\n"
            
            if len(liked_movie_ids) > 5:
                output += f"\n_...and {len(liked_movie_ids) - 5} more highly-rated movies_\n"
            output += "\n"
        
        # Show disliked movies if any
        if disliked_movie_ids:
            output += f"### 👎 **Movies to Avoid**\n\n"
            for movie_id in disliked_movie_ids[:3]:
                try:
                    details_result = movie_mcp_server.get_movie_details(movie_id=str(movie_id))
                    if details_result.get('status') == 'success' and details_result.get('movie'):
                        movie = details_result['movie']
                        title = movie.get('title', 'Unknown')
                        output += f"* {title}\n"
                except Exception:
                    pass
            output += "\n"
        
        return output
    
    # Handler for get_explained_group_recommendations results
    if 'recommendations' in tool_result and 'group_profile' in tool_result and tool_result.get('status') == 'success':
        group_name = tool_result.get('group_name', 'Your Group')
        group_profile = tool_result.get('group_profile', {})
        recommendations = tool_result.get('recommendations', [])
        
        output = f"### 🎯 Personalized Recommendations for {group_name}\n\n"
        output += f"Based on your group's movie ratings, here are my top picks:\n\n"
        
        # Show group profile
        output += f"📊 **Your Group's Profile:**\n"
        output += f"* **Favorite Genres:** {', '.join(group_profile.get('favorite_genres', []))}\n"
        if group_profile.get('favorite_directors'):
            output += f"* **Favorite Directors:** {', '.join(group_profile['favorite_directors'])}\n"
        output += f"* **Average Rating:** {group_profile.get('avg_rating', 0):.1f}/5.0\n"
        if group_profile.get('preferred_runtime'):
            output += f"* **Preferred Runtime:** ~{group_profile['preferred_runtime']} minutes\n"
        output += "\n---\n\n"
        
        # Display recommended movies with explanations
        output += f"### 🎬 Recommended Movies\n\n"
        
        for i, rec in enumerate(recommendations, start=1):
            movie = rec.get('movie', {})
            explanation = rec.get('explanation', '')
            
            title = movie.get('title', 'Unknown')
            year = movie.get('release_year')
            
            output += f"**{i}. {title}**"
            if year:
                output += f" ({year})"
            output += f"\n\n**Why this matches:** {explanation}\n\n"
            
            # Render full movie card
            output += render_movie_card(movie, show_poster=True) + "\n\n"
        
        output += f"💡 **Tip:** These recommendations are based on {group_name}'s {group_profile.get('movies_rated', 0)} rated movies. Keep rating to improve future suggestions!\n\n"
        
        return output
    
    if tool_result.get('status') == 'success':
        message = tool_result.get('message', 'Operation completed successfully!')
        
        # Special handling for create_group: auto-select the newly created group
        if tool_name == 'create_group' and 'group_id' in tool_result:
            group_id = tool_result.get('group_id')
            group_name = tool_result.get('group_name', 'Unknown')
            
            # Fetch the full group object to ensure consistency
            try:
                current_user_email = st.session_state.get('current_user_email') or 'rajesh@gmail.com'
                groups_result = movie_mcp_server.list_user_groups(email=current_user_email)
                if groups_result.get('groups'):
                    # Find the newly created group
                    new_group_obj = next((g for g in groups_result['groups'] if g['group_id'] == group_id), None)
                    if new_group_obj:
                        st.session_state.current_group_selection = new_group_obj['group_name']
                        st.session_state.current_group_object = new_group_obj
                        logger.info(f"✅ Auto-selected newly created group: {new_group_obj['group_name']} ({group_id})")
                    else:
                        # Fallback if group not found in list (shouldn't happen)
                        st.session_state.current_group_selection = group_name
                        st.session_state.current_group_object = {
                            'group_id': group_id,
                            'group_name': group_name
                        }
                        logger.warning(f"⚠️ Group {group_id} not found in list_user_groups result")
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch full group object: {e}")
                # Fallback to minimal object
                st.session_state.current_group_selection = group_name
                st.session_state.current_group_object = {
                    'group_id': group_id,
                    'group_name': group_name
                }
        
        # Special handling for add_to_watchlist: show movie details + poster
        if tool_name == 'add_to_watchlist' and 'movie_title' in tool_result:
            movie_title = tool_result.get('movie_title', 'Unknown')
            movie_id = tool_result.get('movie_id')
            
            # Fetch full movie details to show poster
            if movie_id:
                try:
                    movie_details_result = movie_mcp_server.get_movie_details(movie_id=str(movie_id))
                    if movie_details_result.get('status') == 'success' and movie_details_result.get('movie'):
                        movie_obj = movie_details_result['movie']
                        # Debug: Log poster URL status
                        poster_url = movie_obj.get('poster_url', '')
                        if not poster_url:
                            logger.warning(f"⚠️ Movie {movie_id} has no poster_url in backend response. Movie keys: {list(movie_obj.keys())}")
                        else:
                            logger.info(f"✅ Poster URL found: {poster_url[:50]}...")
                        
                        output = f"✅ {message}\n\n"
                        output += render_movie_card(movie_obj)
                        return output
                except Exception as e:
                    logger.warning(f"Failed to fetch movie details for watchlist addition: {e}")
        
        # Special handling for rate_movie: show user's original rating scale + movie details
        if tool_name == 'rate_movie' and 'rating' in tool_result:
            rating_display = tool_result.get('rating', 0)  # Backend returns /5 scale directly
            movie_title = tool_result.get('movie_title', 'Unknown')
            movie_id = tool_result.get('movie_id')
            
            # Format stars
            stars = "⭐" * round(rating_display)
            
            # Enhanced message - show ONLY /5 scale (user-friendly)
            enhanced_message = f"✅ Rated '{movie_title}' with {stars} **{rating_display:.1f}/5.0**"
            
            # Optionally show movie details
            if movie_id:
                try:
                    movie_details_result = movie_mcp_server.get_movie_details(movie_id=str(movie_id))
                    if movie_details_result.get('status') == 'success' and movie_details_result.get('movie'):
                        output = enhanced_message + "\n\n"
                        output += render_movie_card(movie_details_result['movie'])
                        return output
                except Exception as e:
                    logger.warning(f"Failed to fetch movie details for rating: {e}")
            
            return enhanced_message
        
        return f"✅ {message}"
    
    if tool_result.get('status') == 'not_found':
        message = tool_result.get('message', 'Item not found.')
        return f"{message}"
    
    if 'error' in tool_result:
        return f"❌ **Error:** {tool_result['error']}"
    
    formatter_prompt = f"""User query: "{user_query}"
Executed tool: {tool_name}
Result: {json.dumps(tool_result)}

Present these results clearly and concisely using Markdown formatting."""
    
    formatter_payload = {
        "messages": [{"role": "user", "content": formatter_prompt}],
        "max_tokens": 1000,
        "temperature": 0.3
    }
    formatted_result = post_to_llm_with_retry(formatter_payload)
    return formatted_result["choices"][0]["message"]["content"]


def process_and_display_message(prompt: str, display_prefix: str = "") -> None:
    """Process a user message and display the response (reduces code duplication)."""
    display_text = f"{display_prefix}{prompt}" if display_prefix else prompt
    st.chat_message("user").markdown(display_text)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    spinner_text = "🔍 Searching with filters..." if display_prefix else "🎬 Processing your request..."
    with st.spinner(spinner_text):
        response = agent_loop(prompt)
    
    with st.chat_message("assistant"):
        st.markdown(response, unsafe_allow_html=True)
    
    st.session_state.messages.append({"role": "assistant", "content": response})


def agent_loop(user_query: str):
    """Dynamically route user query to tool and format response."""
    tools_manifest = build_dynamic_tool_descriptions()

    router_prompt = f"""You are an AI movie assistant router. Analyze the user query and select the appropriate tool.

Available Tools:
{tools_manifest}

User Query: "{user_query}"

**CRITICAL CONTEXT EXTRACTION RULES:**

⚠️ **MOST IMPORTANT: When user mentions director, year, or actor with a movie title, YOU MUST include that context in the movie_id field!**

Examples:
- "Titanic directed by James Cameron" → movie_id: "Titanic James Cameron"
- "Titanic 1997" → movie_id: "Titanic 1997"
- "Avatar by James Cameron" → movie_id: "Avatar James Cameron"

1. **Group Context Extraction** (for watchlist/rating/group tools):
   - Carefully scan the user query for group indicators:
     * Pattern: "for [group name]" -> extract everything after "for" as group_id
     * Pattern: "in [group name]" -> extract everything after "in" as group_id  
     * Pattern: "[name]'s watchlist" or "[name] watchlist" -> extract the name before "'s" or before "watchlist"
     * Pattern: "group: [name]" or "group [name]" -> extract everything after "group:" or "group"
   - Multi-word group names are COMMON ("Friday Night Flicks", "Movie Club", "Family Group")
   - Extract the FULL multi-word phrase, including spaces
   - Examples:
     * "Show watchlist for Friday Night Flicks" -> group_id = "Friday Night Flicks"
     * "What movies are in Movie Club?" -> group_id = "Movie Club"
   - If NO group is mentioned in the query, use "MISSING_GROUP" (the system will auto-inject the user's selected group from the sidebar)
   - DO NOT invent placeholders like "current_group", "my_group", or "default"

2. **Movie Title Extraction (CRITICAL - Include Disambiguating Context):**
   - Extract movie titles exactly as mentioned
   - **If user provides director, year, or lead actor**, INCLUDE it in the movie_id to help disambiguation:
     * "Titanic directed by James Cameron" -> movie_id: "Titanic James Cameron"
     * "Titanic 1997" or "Titanic (1997)" -> movie_id: "Titanic 1997"
     * "Titanic with Leonardo DiCaprio" -> movie_id: "Titanic Leonardo DiCaprio"
     * "Avatar by James Cameron" -> movie_id: "Avatar James Cameron"
   - This helps the backend find the EXACT movie the user means when multiple movies share the same title
   - Never use placeholders like "MISSING_MOVIE" or "{{movie_id_...}}"

3. **Ratings vs Search (IMPORTANT - DO NOT CONFUSE):**
   - "show ratings", "what did we rate", "our ratings", "group ratings" -> use "get_group_ratings"
   - "my ratings", "what did I rate" -> use "get_my_ratings"
   - These are NOT movie searches - they fetch existing ratings from the database
   - DO NOT use "semantic_search_movies" for ratings queries

4. **Recommendation Workflow & Search Rules:**
   - **USER-BASED RECOMMENDATIONS (check first):**
     * If user says "for the user [username]" or "for user [username]" or "what does [username] like", this is a USER-BASED request
     * Extract the username and use "get_my_ratings" to show what that user has rated
     * Example: "Recommend movies for the user rajesh" -> {{"tool": "get_my_ratings", "arguments": {{"email": "rajesh@gmail.com", "group_id": "MISSING_GROUP"}}}}
     * Example: "What movies does alice like?" -> {{"tool": "get_my_ratings", "arguments": {{"email": "alice@gmail.com", "group_id": "MISSING_GROUP"}}}}
   - **MOVIE SEARCH WITH GENRES/THEMES (check second - PRIORITY):**
     * If user specifies ANY genre, theme, keyword, or movie type (e.g., "love story", "action", "thriller", "comedy", "sci-fi") → use "semantic_search_movies"
     * This applies EVEN IF they mention a group name (e.g., "for Sunday Films", "for the group")
     * The presence of a genre/theme means they want movie search results, NOT preference analysis
     * Extract the movie criteria (genres, themes, keywords, year) from the query
     * Example: "Recommend love story movies for the group" -> {{"tool": "semantic_search_movies", "arguments": {{"query": "love story romance movies", "limit": 10}}}}
     * Example: "Suggest action movies for Sunday Films" -> {{"tool": "semantic_search_movies", "arguments": {{"query": "action movies", "limit": 10}}}}
     * Example: "Find thriller movies for my group" -> {{"tool": "semantic_search_movies", "arguments": {{"query": "thriller movies", "limit": 10}}}}
   - **GROUP PREFERENCE QUESTIONS (check third - ONLY when NO genres mentioned):**
     * ONLY use "get_group_preferences" when user explicitly asks ABOUT preferences WITHOUT mentioning specific genres
     * Patterns: "what does [group] like?", "what are [group]'s preferences?", "show [group]'s taste", "analyze [group]'s interests"
     * Do NOT use this when user specifies a genre/theme - that's a search request (see above rule)
     * Example: "What kind of movies does Sunday Films like?" -> {{"tool": "get_group_preferences", "arguments": {{"group_id": "Sunday Films"}}}}
     * Example: "Show me Friday Night Flicks preferences" -> {{"tool": "get_group_preferences", "arguments": {{"group_id": "Friday Night Flicks"}}}}

   - "save_group_recommendation" is ONLY for saving a specific movie the user already chose
   - If user says "recommend AND save", use the appropriate tool first - saving comes after they pick one

5. **User Switching:**
   - If user asks about switching users ("switch to [name]", "change user"), politely direct them: "You can switch users using the '👤 User' dropdown in the sidebar."

**RATING EXTRACTION (CRITICAL):**
The database uses a 1-5 scale. Extract the rating as a number on the /5 scale:
- "5 stars", "5/5", "5 out of 5" -> rating: 5
- "4.5 stars", "4.5/5" -> rating: 4.5
- "4 stars", "4/5" -> rating: 4
- "3.5 stars", "3.5/5" -> rating: 3.5
- "3 stars", "3/5" -> rating: 3
- "2.5 stars", "2.5/5" -> rating: 2.5
- "2 stars", "2/5" -> rating: 2
- "1.5 stars", "1.5/5" -> rating: 1.5
- "1 star", "1/5" -> rating: 1
- If user says just a number (e.g., "4"), use it directly on the /5 scale
- **IMPORTANT: When user says "X/5", extract ONLY the number before the slash. DO NOT perform division.**
  * "4/5" -> rating: 4 (NOT 0.8)
  * "3.5/5" -> rating: 3.5 (NOT 0.7)
  * "10/5" -> rating: 10 (backend will reject as invalid, which is correct)
- **ONLY for "/10" scale:** If user explicitly says "out of 10" or "/10", divide by 2 to convert:
  * "8/10" -> rating: 4
  * "7/10" -> rating: 3.5
  * "10/10" -> rating: 5

**ROUTING EXAMPLES:**
Query: "Show watchlist for Friday Night Flicks"
Response: {{"tool": "get_watchlist", "arguments": {{"group_id": "Friday Night Flicks"}}}}

Query: "Add Inception to watchlist"
Response: {{"tool": "add_to_watchlist", "arguments": {{"group_id": "MISSING_GROUP", "movie_id": "Inception"}}}}

Query: "Rate Inception 5 stars"
Response: {{"tool": "rate_movie", "arguments": {{"movie_id": "Inception", "rating": 5, "group_id": "MISSING_GROUP"}}}}

Query: "Rate Titanic 3.5 out of 5"
Response: {{"tool": "rate_movie", "arguments": {{"movie_id": "Titanic", "rating": 3.5, "group_id": "MISSING_GROUP"}}}}

Query: "Rate Interstellar 7 out of 10"
Response: {{"tool": "rate_movie", "arguments": {{"movie_id": "Interstellar", "rating": 3.5, "group_id": "MISSING_GROUP"}}}}

Query: "Rate The Dark Knight 4/5"
Response: {{"tool": "rate_movie", "arguments": {{"movie_id": "The Dark Knight", "rating": 4, "group_id": "MISSING_GROUP"}}}}

Query: "Add Titanic movie directed by James Cameron to watchlist"
Response: {{"tool": "add_to_watchlist", "arguments": {{"group_id": "MISSING_GROUP", "movie_id": "Titanic James Cameron"}}}}

Query: "Rate Avatar by James Cameron 5 stars"
Response: {{"tool": "rate_movie", "arguments": {{"movie_id": "Avatar James Cameron", "rating": 5, "group_id": "MISSING_GROUP"}}}}

Query: "Show me details of Titanic 1997"
Response: {{"tool": "get_movie_details", "arguments": {{"movie_id": "Titanic 1997"}}}}

Query: "Show all ratings for My Movie Club"
Response: {{"tool": "get_group_ratings", "arguments": {{"group_id": "My Movie Club"}}}}

Query: "What did we rate highly in Sunday films?"
Response: {{"tool": "get_group_ratings", "arguments": {{"group_id": "Sunday films"}}}}

Query: "Show me my ratings"
Response: {{"tool": "get_my_ratings", "arguments": {{"group_id": "MISSING_GROUP"}}}}

Query: "Recommend movies for the user rajesh"
Response: {{"tool": "get_my_ratings", "arguments": {{"email": "rajesh@gmail.com", "group_id": "MISSING_GROUP"}}}}

Query: "What movies does alice like?"
Response: {{"tool": "get_my_ratings", "arguments": {{"email": "alice@gmail.com", "group_id": "MISSING_GROUP"}}}}

Query: "Recommend love story movies for the group"
Response: {{"tool": "semantic_search_movies", "arguments": {{"query": "love story romance movies", "limit": 10}}}}

Query: "Suggest action movies for Sunday Films"
Response: {{"tool": "semantic_search_movies", "arguments": {{"query": "action movies", "limit": 10}}}}

Query: "Find thriller movies for my group"
Response: {{"tool": "semantic_search_movies", "arguments": {{"query": "thriller movies", "limit": 10}}}}

Query: "What kind of movies does Sunday Films like?"
Response: {{"tool": "get_group_preferences", "arguments": {{"group_id": "Sunday Films"}}}}

Query: "Show me Friday Night Flicks group's preferences"
Response: {{"tool": "get_group_preferences", "arguments": {{"group_id": "Friday Night Flicks"}}}}

Query: "Recommend best movies released last month"
Response: {{"tool": "semantic_search_movies", "arguments": {{"query": "best movies released last month", "limit": 10}}}}

Query: "Compare Inception and Interstellar"
Response: {{"tool": "compare_movies", "arguments": {{"movie_title1": "Inception", "movie_title2": "Interstellar"}}}}

Query: "Compare The Matrix, Blade Runner, and Minority Report"
Response: {{"tool": "compare_movies", "arguments": {{"movie_title1": "The Matrix", "movie_title2": "Blade Runner", "movie_title3": "Minority Report"}}}}

Respond ONLY with valid JSON:
{{
    "tool": "<tool_name>",
    "arguments": {{<required_params>}}
}}"""

    try:
        # Early exit: Check for user creation/switching requests
        user_creation_keywords = ["create user", "new user", "add user", "create a user", "switch user", "change user"]
        if any(keyword in user_query.lower() for keyword in user_creation_keywords):
            return "👤 **User Management**: Please use the **👤 User** dropdown in the sidebar to switch users. User creation is not available via chat."
        
        # PRE-VALIDATION: Catch invalid ratings before LLM routing
        # Pattern: "rate X Y/5" where Y > 5 (e.g., "rate Inception 10/5", "rate movie 6/5")
        invalid_rating_pattern = re.search(r'rate.*?([6-9]|\d{2,})/5', user_query.lower())
        if invalid_rating_pattern:
            invalid_value = invalid_rating_pattern.group(1)
            return f"❌ Invalid rating: {invalid_value}/5. Ratings must be between 1 and 5 stars. Please try again with a valid rating (e.g., '4/5' or '3.5/5')."
        
        # SPECIAL WORKFLOW: Group-based recommendations with explanations
        # Detect: "Recommend movies for [group]" with "explain why" or similar intent
        recommend_with_explain_pattern = re.search(
            r'recommend.*?(for|in)\s+([\w\s]+?)(?:\s+and\s+explain|\s+explain|\?|$)',
            user_query.lower()
        )
        
        if recommend_with_explain_pattern:
            # Extract group name
            group_name_match = recommend_with_explain_pattern.group(2).strip()
            logger.info(f"🎯 Detected group recommendation request with explanation for: '{group_name_match}'")
            
            # Resolve group ID
            try:
                group_result = movie_mcp_server.get_group_by_name(group_name=group_name_match)
                if group_result.get('status') != 'success' or not group_result.get('group'):
                    return f"❌ **Group '{group_name_match}' not found.** Please check the group name and try again."
                
                group_id = group_result['group']['group_id']
                group_name_display = group_result['group']['group_name']
                
                # Call backend for complete recommendation workflow (business logic lives there)
                logger.info(f"🎯 Calling backend for explained recommendations: {group_id}")
                result = movie_mcp_server.get_explained_group_recommendations(
                    group_id=group_id,
                    limit=5
                )
                
                # Check for errors
                if result.get('status') != 'success':
                    return f"❌ {result.get('message', 'Failed to generate recommendations.')}"
                
                # Format structured backend response as markdown (presentation only)
                group_profile = result.get('group_profile', {})
                recommendations = result.get('recommendations', [])
                
                output = f"### 🎯 Personalized Recommendations for {group_name_display}\n\n"
                output += f"Based on your group's movie ratings, here are my top picks:\n\n"
                
                # Show group profile
                output += f"📊 **Your Group's Profile:**\n"
                output += f"* **Favorite Genres:** {', '.join(group_profile.get('favorite_genres', []))}\n"
                if group_profile.get('favorite_directors'):
                    output += f"* **Favorite Directors:** {', '.join(group_profile['favorite_directors'])}\n"
                output += f"* **Average Rating:** {group_profile.get('avg_rating', 0):.1f}/5.0\n"
                if group_profile.get('preferred_runtime'):
                    output += f"* **Preferred Runtime:** ~{group_profile['preferred_runtime']} minutes\n"
                output += "\n---\n\n"
                
                # Display recommended movies with explanations
                output += f"### 🎬 Recommended Movies\n\n"
                
                for i, rec in enumerate(recommendations, start=1):
                    movie = rec.get('movie', {})
                    explanation = rec.get('explanation', '')
                    
                    title = movie.get('title', 'Unknown')
                    year = movie.get('release_year')
                    
                    output += f"**{i}. {title}**"
                    if year:
                        output += f" ({year})"
                    output += f"\n\n**Why this matches:** {explanation}\n\n"
                    
                    # Render full movie card
                    output += render_movie_card(movie, show_poster=True) + "\n\n"
                
                output += f"💡 **Tip:** These recommendations are based on {group_name_display}'s {group_profile.get('movies_rated', 0)} rated movies. Keep rating to improve future suggestions!\n\n"
                
                return output
                
            except Exception as e:
                logger.exception(f"Failed to process group recommendation with explanation: {e}")
                # Return error instead of falling through to avoid misrouting
                return f"❌ **Failed to generate recommendations for {group_name_match}.** {str(e)}"
        
        # Step 1: Tool Routing
        logger.info(f"🔍 Routing user query: '{user_query[:50]}...'")
        
        router_payload = {
            "messages": [{"role": "user", "content": router_prompt}],
            "max_tokens": 300,
            "temperature": 0.2
        }
        result = post_to_llm_with_retry(router_payload)
        raw_text = result["choices"][0]["message"]["content"].strip()
        
        logger.info(f"📝 LLM routing response: {raw_text[:100]}...")

        decision = _parse_llm_routing_response(raw_text)
        tool_name = decision.get("tool")
        tool_args = decision.get("arguments", {})
        
        logger.info(f"🛠️  Selected tool: {tool_name} with args: {tool_args}")

        # Step 2: Resolve group ID if needed
        group_error = _resolve_group_id(tool_name, tool_args)
        if group_error:
            return group_error
        logger.info(f"✅ After group resolution: {tool_args}")

        # Step 3: Resolve movie ID if needed
        movie_error = _resolve_movie_id(tool_name, tool_args)
        if movie_error:
            return movie_error
        logger.info(f"✅ After movie resolution: {tool_args}")

        # Step 3.5: Auto-inject current user's email if needed
        _auto_inject_email(tool_name, tool_args)
        logger.info(f"✅ After email injection: {tool_args}")

        # Step 4: Tool Execution
        logger.info(f"⚙️  Executing tool: {tool_name}({tool_args})")
        tool_result = call_tool(tool_name, tool_args)
        logger.info(f"✅ Tool execution completed: {str(tool_result)[:100]}...")

        # Step 5: Format and return results using helper
        return _format_tool_result(tool_result, user_query, tool_name)

    except Exception as e:
        logger.exception(f"❌ Agent loop failed for query '{user_query}': {str(e)}")
        # Fallback to direct semantic search if LLM routing fails
        try:
            logger.info(f"🔄 Attempting fallback to semantic search...")
            fallback_res = movie_mcp_server.semantic_search_movies(query=user_query, limit=5)
            if fallback_res.get("movies"):
                out = f"### 🎬 Search Results for '{user_query}'\n\n"
                out += "*Note: Using fallback search due to processing issue*\n\n"
                for m in fallback_res["movies"]:
                    out += render_movie_card(m) + "\n"
                return out
        except Exception as fallback_error:
            logger.error(f"Fallback search also failed: {fallback_error}")
        
        error_msg = """
        <div style="padding: 28px; background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); border-left: 5px solid #ffa500; border-radius: 16px; margin: 20px 0; box-shadow: 0 4px 16px rgba(255, 165, 0, 0.2);">
            <div style="display: flex; align-items: center; margin-bottom: 16px;">
                <span style="font-size: 2em; margin-right: 12px;">⚠️</span>
                <h3 style="margin: 0; font-size: 1.3em; color: #cc8800; font-weight: 700;">Oops! Something went wrong</h3>
            </div>
            <p style="margin: 0 0 16px 0; color: #856404; font-size: 1.05em; line-height: 1.6;">
                I encountered an issue processing your request. Here are some suggestions:
            </p>
            <ul style="color: #856404; margin: 16px 0; padding-left: 20px; line-height: 1.8;">
                <li style="margin: 8px 0;">Try rephrasing your query</li>
                <li style="margin: 8px 0;">Check if you specified the correct group name</li>
                <li style="margin: 8px 0;">Make sure movie titles are spelled correctly</li>
                <li style="margin: 8px 0;">Use the sidebar quick actions for common tasks</li>
            </ul>
            <details style="margin-top: 20px; cursor: pointer;">
                <summary style="color: #cc8800; font-weight: 600; padding: 8px; background: rgba(255,255,255,0.5); border-radius: 8px; display: inline-block;">Technical Details</summary>
                <p style="margin: 12px 0 0 0; font-size: 0.9em; color: #856404; font-family: monospace; background: rgba(255,255,255,0.7); padding: 12px; border-radius: 8px;">{}</p>
            </details>
        </div>
        """.format(str(e)[:150])
        
        return error_msg

if "messages" not in st.session_state:
    st.session_state.messages = []

if "quick_query" not in st.session_state:
    st.session_state.quick_query = None
if "filter_query" not in st.session_state:
    st.session_state.filter_query = None
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

if "current_user_override" not in st.session_state:
    st.session_state.current_user_override = None
if "current_user_email" not in st.session_state:
    st.session_state.current_user_email = None
if "current_group_selection" not in st.session_state:
    st.session_state.current_group_selection = None
if "current_group_object" not in st.session_state:
    st.session_state.current_group_object = None

# A/B Test Variant Assignment (50/50 split based on user email hash)
if "ab_variant" not in st.session_state:
    # Currently set to "A" for all users - change to B for testing Variant B
    # Variant A: Personal Dashboard (individual focus)
    # Variant B: Social Activity Feed (collaborative focus - not yet implemented)
    user_email = st.session_state.get('current_user_email', '')
    # For true A/B testing, use: st.session_state.ab_variant = "A" if hash(user_email) % 2 == 0 else "B"
    st.session_state.ab_variant = "A"  # Force Variant A for now

if len(st.session_state.messages) > 0:
    col1, col2, col3 = st.columns([4, 1, 1])
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    with col3:
        st.metric("Messages", len(st.session_state.messages))

# ===== VARIANT A: PERSONAL DASHBOARD (A/B TEST) =====
# Personalized user-specific dashboard showing activity, watchlist preview, and recent ratings
if len(st.session_state.messages) == 0:
    render_personal_dashboard()

else:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

if st.session_state.quick_query:
    prompt = st.session_state.quick_query
    st.session_state.quick_query = None
    process_and_display_message(prompt)
    st.rerun()

if st.session_state.filter_query:
    prompt = st.session_state.filter_query
    st.session_state.filter_query = None
    process_and_display_message(prompt, display_prefix="🔎 Filtered search: ")
    st.rerun()

# Handle pending prompt from sidebar
if st.session_state.get('pending_prompt'):
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    process_and_display_message(prompt)
    st.rerun()

# Main chat input - anchored to bottom of viewport
if prompt := st.chat_input("🎬 Ask me anything about movies, groups, or your watchlist..."):
    process_and_display_message(prompt)
    st.rerun()