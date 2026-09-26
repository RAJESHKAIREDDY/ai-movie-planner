# 🎬 AI Movie Night Planner - Testing Scenarios

## Assignment Requirements Coverage

This document provides comprehensive testing scenarios for the AI Movie Night Planner agent, based on the assignment requirements.

---

## 📋 Pre-Test Setup

### 1. Environment Setup
- Ensure Lakebase database is running
- Verify TMDB API key is configured
- Confirm Streamlit app is accessible
- Check that all required tables exist (users, groups, group_members, movies, ratings, watchlist_items, recommendations)

### 2. Create Test Data
```
User 1: Alice (alice@test.com)
User 2: Bob (bob@test.com)
User 3: Charlie (charlie@test.com)
Group: "Friday Movie Night"
```

---

## 🎯 Core Agent Capabilities Testing

### **Scenario 1: Search and Explain Recommendations**

**Objective:** Test semantic search with natural language queries

**Test Cases:**

#### 1.1 Simple Genre Search
- **Query:** "Show me action movies"
- **Expected Result:** List of 5-10 action movies with details (title, year, rating, overview)
- **Validation:** Verify movies are action genre, sorted by relevance

#### 1.2 Complex Semantic Search (Assignment Example)
- **Query:** "Find a funny sci-fi movie that isn't too violent and is under two hours"
- **Expected Result:** 
  - Movies matching: Comedy + Sci-Fi genres
  - Runtime < 120 minutes
  - Lower violence rating (PG-13 or below preferred)
- **Validation:** Check movie metadata matches all criteria

#### 1.3 Search with Actor/Director
- **Query:** "Movies starring Tom Hanks"
- **Expected Result:** List of Tom Hanks movies
- **Validation:** Verify cast information includes Tom Hanks

#### 1.4 Search with Time Period
- **Query:** "Best movies from 2023"
- **Expected Result:** Movies released in 2023, sorted by rating
- **Validation:** Check release_year = 2023

---

### **Scenario 2: Compare Several Movies**

**Objective:** Test movie comparison functionality

**Test Cases:**

#### 2.1 Compare Two Movies
- **Query:** "Compare Inception and Interstellar"
- **Expected Result:** 
  - Side-by-side comparison showing:
    - Title, year, director
    - Genres
    - TMDB ratings
    - Runtime
    - Plot summaries
  - Highlight similarities and differences
- **Validation:** Both movies displayed with complete metadata

#### 2.2 Compare Three Movies
- **Query:** "Compare The Matrix, Blade Runner, and Minority Report"
- **Expected Result:** Three-way comparison table
- **Validation:** All three movies shown with comparable attributes

#### 2.3 Compare with Recommendations
- **Query:** "Compare these movies and tell me which is best for a group that loves Christopher Nolan"
- **Expected Result:** 
  - Comparison data
  - Recommendation based on director preference
- **Validation:** Agent provides reasoning for recommendation

---

### **Scenario 3: Add Movie to Group Watchlist**

**Objective:** Test watchlist management

**Test Cases:**

#### 3.1 Add Single Movie
- **Setup:** Login as Alice, select "Friday Movie Night" group
- **Query:** "Add Inception to watchlist"
- **Expected Result:** 
  - Success message: "✅ Added Inception to Friday Movie Night watchlist"
  - Movie appears in group watchlist
- **Validation:** 
  - Check watchlist_items table has new entry
  - Verify group_id, movie_id, added_by are correct
  - Status = 'pending'

#### 3.2 Add Movie with Group Context
- **Query:** "Add The Dark Knight to watchlist for Friday Movie Night"
- **Expected Result:** Movie added to specified group
- **Validation:** Correct group_id resolved from name

#### 3.3 View Watchlist
- **Query:** "Show watchlist for Friday Movie Night"
- **Expected Result:** Table displaying all movies in watchlist with:
  - Title, Year, Rating, Language, Status
- **Validation:** All previously added movies appear

#### 3.4 Prevent Duplicates
- **Query:** "Add Inception to watchlist" (already added)
- **Expected Result:** Error message: "Movie already in watchlist"
- **Validation:** No duplicate entry created

---

### **Scenario 4: Record Ratings After Watching**

**Objective:** Test rating submission and retrieval

**Test Cases:**

#### 4.1 Rate a Movie
- **Setup:** Login as Alice
- **Query:** "Rate Inception 5 stars in Friday Movie Night - Mind-blowing experience!"
- **Expected Result:** 
  - Success message
  - Rating saved with review
- **Validation:** 
  - Check ratings table: group_id, movie_id, user_email, rating (10/10 scale), review, timestamp
  - Movie status in watchlist changes to 'watched'

#### 4.2 Multiple Users Rate Same Movie
- **Setup:** Bob and Charlie also rate Inception
- **Queries:**
  - Bob: "Rate Inception 4 stars - Great but confusing"
  - Charlie: "Rate Inception 4.5 stars - Amazing visuals"
- **Expected Result:** All ratings saved separately
- **Validation:** 3 rating entries for same movie_id + group_id, different user_emails

#### 4.3 View Group Ratings
- **Query:** "Show all ratings for Friday Movie Night"
- **Expected Result:** Table showing:
  - All rated movies
  - Average rating per movie
  - Number of ratings
  - Individual raters
- **Validation:** Inception shows avg = 4.5/5, 3 ratings, raters: Alice, Bob, Charlie

#### 4.4 View Personal Ratings
- **Setup:** Login as Alice
- **Query:** "Show my ratings"
- **Expected Result:** Only Alice's ratings displayed
- **Validation:** Filter by current_user_email

---

### **Scenario 5: Avoid Movies Already Watched or Disliked**

**Objective:** Test filtering logic in recommendations

**Test Cases:**

#### 5.1 Get Recommendations Excluding Watched
- **Setup:** 
  - Alice, Bob, Charlie rated Inception, The Dark Knight (both high ratings)
  - They disliked (rated < 2 stars): Suicide Squad
- **Query:** "Recommend an action movie for Friday Movie Night"
- **Expected Result:** 
  - Recommendations DO NOT include Inception, The Dark Knight, or Suicide Squad
  - Movies match group preferences (action, high-rated)
- **Validation:** 
  - None of the watched movies appear
  - None of the disliked movies appear

#### 5.2 Get Group Preferences
- **Query:** "What kind of movies does Friday Movie Night like?"
- **Expected Result:** Analysis showing:
  - Favorite genres (Action, Sci-Fi based on ratings)
  - Average rating: 4.5/5
  - Common themes (high-concept, Christopher Nolan-style)
- **Validation:** Preferences calculated from ratings table

#### 5.3 Recommendation with Explanation
- **Query:** "Recommend movies for Friday Movie Night and explain why"
- **Expected Result:** 
  - 3-5 movie recommendations
  - Explanation for each (e.g., "Based on your group's love of mind-bending sci-fi like Inception...")
- **Validation:** 
  - Recommendations align with group preferences
  - Avoid watched/disliked movies

---

## 🔧 Context Engineering Testing

### **Scenario 6: Semantic Search with Rich Context**

**Objective:** Test embedding-based search

**Test Cases:**

#### 6.1 Search by Plot Theme
- **Query:** "Find movies about time travel paradoxes"
- **Expected Result:** Movies with time travel themes (Primer, Tenet, Looper, etc.)
- **Validation:** Plot summaries mention time travel concepts

#### 6.2 Search by Mood/Tone
- **Query:** "Find uplifting movies that make you feel hopeful"
- **Expected Result:** Movies with positive themes, high emotional impact
- **Validation:** Keywords in overview match "uplifting", "hope", "inspiring"

#### 6.3 Search by Specific Constraints
- **Query:** "Family-friendly animated movies under 90 minutes"
- **Expected Result:** 
  - Genre: Animation
  - Rating: G or PG
  - Runtime < 90 minutes
- **Validation:** All movies meet all three criteria

---

## 🛡️ Error Handling & Edge Cases

### **Scenario 7: Error Scenarios**

#### 7.1 Missing Group Context
- **Query:** "Add Inception to watchlist" (no group selected)
- **Expected Result:** Error: "Please specify a group"
- **Validation:** Prompt user to select/specify group

#### 7.2 Movie Not Found
- **Query:** "Add XYZ12345NonexistentMovie to watchlist"
- **Expected Result:** Error: "Movie not found"
- **Validation:** Graceful error handling

#### 7.3 Invalid Rating Value
- **Query:** "Rate Inception 10 stars" (out of 5-star scale)
- **Expected Result:** Error or auto-correct to 5 stars
- **Validation:** Rating stored as 10/10 (internal scale)

#### 7.4 Duplicate Group Name
- **Query:** "Create group Friday Movie Night" (already exists)
- **Expected Result:** Error: "Group name already exists"
- **Validation:** No duplicate group created

---

## 🎭 Integration Testing

### **Scenario 8: Full User Journey**

**Complete Flow:**

1. **User Onboarding**
   - Create new user: "Create user David with email david@test.com"
   - Create group: "Create group 'Weekend Warriors'"
   - Add member: "Add david@test.com to Weekend Warriors"

2. **Movie Discovery**
   - Search: "Find thriller movies from 2023"
   - View details: "Show details for Oppenheimer"
   - Compare: "Compare Oppenheimer and The Killer"

3. **Watchlist Management**
   - Add: "Add Oppenheimer to Weekend Warriors watchlist"
   - View: "Show watchlist for Weekend Warriors"

4. **Watch & Rate**
   - Rate: "Rate Oppenheimer 5 stars - Incredible cinematography and storytelling"
   - View ratings: "Show ratings for Weekend Warriors"

5. **Get Recommendations**
   - Get preferences: "What does Weekend Warriors like?"
   - Get recommendations: "Recommend movies for Weekend Warriors"

**Expected Result:** Complete end-to-end flow works seamlessly

---

## 📊 Database Validation

### **Scenario 9: Data Integrity Checks**

After completing test scenarios, verify:

1. **Users Table**
   - All test users exist
   - Usernames and emails are unique

2. **Groups Table**
   - All test groups exist
   - Group names are unique

3. **Group_Members Table**
   - All memberships recorded
   - No duplicate memberships

4. **Movies Table**
   - Movies fetched from TMDB are cached
   - Embeddings generated for semantic search

5. **Ratings Table**
   - All ratings recorded with correct scale (1-10)
   - Timestamps are valid

6. **Watchlist_Items Table**
   - All watchlist additions recorded
   - Status updates work (pending → watched)

7. **Recommendations Table**
   - Saved recommendations tracked
   - Associations correct (group_id, movie_id)

---

## 🚀 Performance Testing

### **Scenario 10: Load & Response Time**

**Test Cases:**

1. **Search Performance**
   - Query: "Action movies"
   - Expected: Results < 3 seconds

2. **Semantic Search Performance**
   - Query: "Find a movie about..." (complex semantic query)
   - Expected: Results < 5 seconds

3. **Recommendation Performance**
   - Query: "Recommend movies for [group]"
   - Expected: Results < 5 seconds

4. **Concurrent Users**
   - 3 users perform actions simultaneously
   - Expected: No conflicts, all actions complete

---

## ✅ Acceptance Criteria Checklist

Use this checklist to verify assignment completion:

- [ ] **Search and Explain Recommendations** - Agent returns relevant movies with explanations
- [ ] **Compare Several Movies** - Agent can compare 2-3 movies side-by-side
- [ ] **Add to Watchlist** - Users can add movies to group watchlist
- [ ] **Record Ratings** - Users can rate movies after watching
- [ ] **Avoid Watched/Disliked** - Recommendations exclude watched and low-rated movies
- [ ] **Semantic Search Works** - Natural language queries return accurate results
- [ ] **Context Engineering** - Plot summaries, keywords, cast, reviews are embedded
- [ ] **All Tables Created** - users, groups, group_members, movies, ratings, watchlist_items, recommendations
- [ ] **TMDB Integration** - API calls work, data is cached
- [ ] **User Management** - Create, list, switch users
- [ ] **Group Management** - Create groups, add members
- [ ] **Error Handling** - Graceful handling of errors
- [ ] **UI/UX** - Clean Streamlit interface, intuitive navigation

---

## 🎯 Quick Test Script

For rapid testing, run these queries in sequence:

```
1. "Create group Test Group"
2. "Find action movies from 2023"
3. "Add The Matrix to watchlist for Test Group"
4. "Rate The Matrix 5 stars - Classic!"
5. "Show watchlist for Test Group"
6. "Show ratings for Test Group"
7. "Recommend movies for Test Group"
8. "Compare Inception and Interstellar"
9. "Find a funny movie under 2 hours"
10. "Show my ratings"
```

---

## 📝 Test Report Template

After testing, document:

**Test Date:** [Date]  
**Tester:** [Your Name]  
**Environment:** [Databricks workspace URL]

| Scenario | Status | Notes |
|----------|--------|-------|
| Search and Recommendations | ✅ / ❌ | |
| Movie Comparison | ✅ / ❌ | |
| Watchlist Management | ✅ / ❌ | |
| Rating System | ✅ / ❌ | |
| Avoid Watched/Disliked | ✅ / ❌ | |
| Semantic Search | ✅ / ❌ | |
| Error Handling | ✅ / ❌ | |
| Performance | ✅ / ❌ | |

**Issues Found:**
- [List any bugs or issues]

**Recommendations:**
- [Suggestions for improvement]

---

## 🎬 Demo Video Scenarios

For your submission video, demonstrate:

1. **User Creation & Group Setup** (30 sec)
2. **Semantic Search** - "Find a funny sci-fi movie under 2 hours" (1 min)
3. **Add to Watchlist** (30 sec)
4. **Rate a Movie** (30 sec)
5. **Group Preferences Analysis** (1 min)
6. **Get Recommendations** - Show it avoids watched movies (1 min)
7. **Compare Movies** (1 min)

**Total Demo Time:** ~6 minutes

---

## 📚 Additional Resources

- [TMDB API Documentation](https://developers.themoviedb.org/3)
- [Lakebase Documentation](https://docs.databricks.com/lakebase/)
- Assignment Requirements (screenshot reference)

---

**Good luck with your submission! 🍿✨**
