import json
from datetime import datetime, timedelta

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
INPUT_FILE = 'data/week_full.json'
OUTPUT_FILE = 'data/newsletter_data.json'

# AUTOMATIC DATE DETECTION
# Since your data might be in the future (2026) or now (2025), 
# we set 'TODAY' to the current system date. 
# NOTE: If you are testing with the 2026 json you pasted earlier, 
# uncomment the manual override line below.
TODAY = datetime.now()
# TODAY = datetime(2026, 2, 8) # <--- UNCOMMENT THIS FOR YOUR 2026 SAMPLE DATA

# ---------------------------------------------------------
# LOGIC HELPERS
# ---------------------------------------------------------

def parse_date(date_str):
    """Parses YYYY-MM-DD string to datetime object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

def get_normalized_score(movie):
    """Calculates average score out of 10."""
    ratings = movie.get('ratings', [])
    if not ratings: return 0
    total, count = 0, 0
    for r in ratings:
        if r['max_score'] > 0:
            total += (r['score'] / r['max_score']) * 10
            count += 1
    return round(total / count, 2) if count > 0 else 0

def get_letterboxd_score(movie):
    for r in movie.get('ratings', []):
        if "Letterboxd" in r['source']:
            return (r['score'] / r['max_score']) * 10
    return 0

# ---------------------------------------------------------
# MAIN PROCESSOR
# ---------------------------------------------------------

def process_movies():
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            movies = json.load(f)
    except FileNotFoundError:
        print("File not found.")
        return

    # 1. PRE-CALCULATE METADATA
    # We find the max year in the dataset to define what "Modern" means.
    # (This handles the case where your dataset is from 2026).
    all_years = [m.get('year', 0) for m in movies if m.get('year')]
    current_era_year = max(all_years) if all_years else TODAY.year
    modern_threshold = current_era_year - 2  # Movies produced in last 2 years

    for m in movies:
        m['calculated_score'] = get_normalized_score(m)
        m['parsed_date'] = parse_date(m['release_date'])
        if 'year' not in m or m['year'] is None: m['year'] = 0
        if 'copies_count' not in m: m['copies_count'] = 0

    # 2. INITIALIZE CATEGORIES
    categories = {
        "top_new_releases": [],   # Released < 7 days ago + Modern Year
        "current_landscape": [],  # Released 1-8 weeks ago + Modern Year
        "premieres_events": [],   # is_premiere = True
        "old_classics": [],       # Old Year
        "letterboxd_picks": [],   # Specific source logic
        "niche_gems": []          # Low copies + High score
    }

    # 3. FILTERING LOGIC
    for m in movies:
        # Skip invalid dates
        if not m['parsed_date']: 
            continue

        # Calculate how many days ago it was released
        days_since_release = (TODAY - m['parsed_date']).days
        
        # Is it a "Modern" production? (e.g. Produced in 2024/2025/2026)
        is_modern_production = m['year'] >= modern_threshold

        # --- A. PREMIERES (Priority 1) ---
        if m.get('is_premiere'):
            categories["premieres_events"].append(m)
            # We continue here because a premiere might also fit other cats, 
            # but usually we want it distinct. Let's allow it to flow 
            # or use 'continue' if you want exclusive buckets.
            
        # --- B. TOP NEW RELEASES ---
        # Logic: Released within last 7 days AND is a modern production
        elif 0 <= days_since_release <= 7 and is_modern_production:
            categories["top_new_releases"].append(m)

        # --- C. CURRENT LANDSCAPE ---
        # Logic: Released between 1 week and 8 weeks ago AND is modern
        elif 7 < days_since_release <= 60 and is_modern_production and m['availability_status'] == 'available':
            categories["current_landscape"].append(m)

        # --- D. OLD CLASSICS / RE-RELEASES ---
        # Logic: Not modern production, but currently playing
        # (premieres were already bucketed above; modern movies never land here)
        is_old_classic = (not is_modern_production
                          and m['availability_status'] == 'available'
                          and not m.get('is_premiere'))
        if is_old_classic:
            categories["old_classics"].append(m)

        # --- E. SPECIAL CURATION (Independent of dates) ---

        # Letterboxd Picks (Score > 7/10). Old classics are excluded: they
        # are almost always Letterboxd favourites, which made the two
        # categories near-duplicates of each other.
        lb_score = get_letterboxd_score(m)
        if lb_score >= 7.0 and not is_old_classic:
            m['lb_temp_score'] = lb_score
            categories["letterboxd_picks"].append(m)

        # Niche Gems (Score > 7.5, Copies < 5, Modern)
        if m['calculated_score'] >= 7.5 and 0 < m['copies_count'] <= 5 and is_modern_production:
            categories["niche_gems"].append(m)

    # 4. SORTING & RANKING
    
    # New Releases: Rank by Quality (Score)
    categories["top_new_releases"].sort(
        key=lambda x: x['calculated_score'], 
        reverse=True
    )

    # Current Landscape: Rank by POPULARITY (Copies Count) as requested
    categories["current_landscape"].sort(
        key=lambda x: x['copies_count'], 
        reverse=True
    )

    # Premieres: Rank by Date (Earliest first)
    categories["premieres_events"].sort(
        key=lambda x: x['parsed_date']
    )

    # Classics: Rank by Score
    categories["old_classics"].sort(
        key=lambda x: x['calculated_score'], 
        reverse=True
    )

    # Letterboxd: Rank by Letterboxd Score specifically
    categories["letterboxd_picks"].sort(
        key=lambda x: x.get('lb_temp_score', 0), 
        reverse=True
    )

    # Niche: Rank by Score
    categories["niche_gems"].sort(
        key=lambda x: x['calculated_score'], 
        reverse=True
    )

    # 5. CLEANUP & EXPORT
    # Removing temporary helper keys and dumping to JSON
    final_output = {}
    for key, lst in categories.items():
        clean_lst = []
        for item in lst:
            i_copy = item.copy()
            # Clean up temp fields
            i_copy.pop('parsed_date', None)
            i_copy.pop('lb_temp_score', None)
            clean_lst.append(i_copy)
        final_output[key] = clean_lst

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)

    print(f"Data processed. Found {len(categories['top_new_releases'])} new releases and {len(categories['current_landscape'])} landscape movies.")

if __name__ == "__main__":
    process_movies()