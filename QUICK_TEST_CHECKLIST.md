
# 🎬 AI Movie Night Planner - Quick Testing Checklist

## ✅ Assignment Requirements Verification

### 1️⃣ Search and Explain Recommendations
**Test Query:** "Find a funny sci-fi movie that isn't too violent and is under two hours"
- [ ] Returns comedy + sci-fi movies
- [ ] Runtime < 120 minutes
- [ ] Provides explanations for recommendations

### 2️⃣ Compare Several Movies
**Test Query:** "Compare Inception and Interstellar"
- [ ] Displays both movies side-by-side
- [ ] Shows: title, year, rating, director, genres, runtime, plot
- [ ] Highlights similarities and differences

### 3️⃣ Add to Watchlist
**Test Query:** "Add Inception to watchlist for [group name]"
- [ ] Movie successfully added to group watchlist
- [ ] Appears in watchlist view
- [ ] Status shows as 'To Watch'

### 4️⃣ Record Ratings
**Test Query:** "Rate Inception 5 stars - Amazing movie!"
- [ ] Rating saved successfully
- [ ] Review text captured
- [ ] Shows in group ratings
- [ ] Watchlist status updates to 'Watched'

### 5️⃣ Avoid Watched/Disliked Movies
**Test Query:** "Recommend movies for [group name]"
- [ ] Does NOT recommend already watched movies
- [ ] Does NOT recommend low-rated movies (< 2 stars)
- [ ] Matches group preferences (genres they like)

---

## 🔧 System Capabilities Verification

### User & Group Management
- [ ] Create new user
- [ ] Switch between users
- [ ] Create new group
- [ ] Add members to group
- [ ] View group members

### Movie Discovery
- [ ] Search by genre: "action movies"
- [ ] Search by actor: "movies with Tom Hanks"
- [ ] Search by year: "best movies from 2023"
- [ ] Semantic search with complex criteria

### Watchlist Management
- [ ] Add movie to watchlist
- [ ] View group watchlist
- [ ] Remove from watchlist
- [ ] Mark as watched

### Rating System
- [ ] Rate movie (1-5 stars)
- [ ] Add review text
- [ ] View my ratings
- [ ] View group ratings (all members)
- [ ] See average ratings

### Recommendations
- [ ] Get group preferences
- [ ] Get personalized recommendations
- [ ] Recommendations explain reasoning
- [ ] Filter out watched/disliked movies

---

## 🎯 Quick 10-Step Test

Run these in order to verify everything works:

1. "Create group Friday Movie Night"
2. "Find action movies from 2023"
3. "Add The Matrix to watchlist for Friday Movie Night"
4. "Show watchlist for Friday Movie Night"
5. "Rate The Matrix 5 stars - Absolutely loved it!"
6. "Show ratings for Friday Movie Night"
7. "What kind of movies does Friday Movie Night like?"
8. "Recommend movies for Friday Movie Night"
9. "Compare Inception and Interstellar"
10. "Find a funny sci-fi movie under 2 hours"

---

## 📊 Expected Data in Lakebase Tables

After testing, verify these tables contain data:

- **users** - At least 1 user
- **groups** - At least 1 group
- **group_members** - At least 1 membership
- **movies** - Movies from TMDB cached
- **ratings** - At least 1 rating
- **watchlist_items** - At least 1 watchlist entry
- **recommendations** - (Optional) Saved recommendations

---

## 🎥 Demo Video Script (6 minutes)

**Segment 1: Setup (1 min)**
- Show user dropdown
- Show group creation
- Add a member

**Segment 2: Search (1.5 min)**
- Simple search: "action movies"
- Complex semantic: "funny sci-fi movie under 2 hours"
- Show movie cards with details

**Segment 3: Watchlist (1 min)**
- Add movie to watchlist
- Show watchlist table
- Explain status (To Watch/Watched)

**Segment 4: Ratings (1 min)**
- Rate a movie
- Show it updates watchlist status
- Show group ratings

**Segment 5: Recommendations (1 min)**
- Show group preferences
- Get recommendations
- Point out it avoids watched movies

**Segment 6: Compare (30 sec)**
- Compare 2 movies side-by-side
- Show all metadata

---

## 🐛 Common Issues to Check

### If search doesn't work:
- Check TMDB API key is set
- Verify compute is running
- Check lakebase connection

### If watchlist doesn't work:
- Ensure group is selected in dropdown
- Verify movie_id is correct
- Check group_id is valid UUID

### If ratings don't work:
- Check user is logged in
- Verify group context
- Ensure movie exists in database

### If recommendations are empty:
- Group needs at least 1 rating
- Check group_preferences returns data
- Verify embeddings are generated

---

## 📝 Submission Checklist

Before submitting:

- [ ] All 5 core capabilities work
- [ ] Semantic search handles complex queries
- [ ] Watchlist adds/removes movies
- [ ] Ratings save correctly (1-10 scale internally, 1-5 UI)
- [ ] Recommendations exclude watched/disliked
- [ ] Compare movies works
- [ ] UI is clean and intuitive
- [ ] Error handling is graceful
- [ ] All 7 Lakebase tables created
- [ ] TMDB API integration works
- [ ] Code is commented
- [ ] Demo video recorded

---

## 🚀 You're Ready!

Your agent implements all required capabilities:
✅ Search with semantic understanding
✅ Compare multiple movies
✅ Manage group watchlists
✅ Record ratings and reviews
✅ Smart recommendations avoiding watched/disliked
✅ Context engineering (embeddings)
✅ Clean Streamlit UI
✅ Lakebase data persistence

**Good luck with your submission! 🍿✨**
