"""
Paris Ciné Info Movie Scraper
Scrapes movie data from paris-cine.info API and organizes it into structured JSON.
"""

import json
import requests
import time
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class Rating:
    """Movie rating from various sources"""
    source: str
    score: Optional[float]
    max_score: float
    url: Optional[str] = None


@dataclass 
class Showtime:
    """A single movie showtime"""
    cinema_id: str
    cinema_name: str
    datetime: str  # ISO format: YYYY-MM-DDTHH:MM:SS
    version: Optional[str] = None  # VF, VO, VOSTFR, etc.
    screen_name: Optional[str] = None
    format: Optional[str] = None  # 3D, IMAX, Dolby, etc.
    booking_url: Optional[str] = None
    has_seat_reservation: bool = False


@dataclass
class Movie:
    """Complete movie data structure"""
    # Basic info
    id: int
    title: str
    original_title: Optional[str]
    director: Optional[str]
    actors: Optional[str]
    year: Optional[int]
    genre: Optional[str]
    language: Optional[str]
    
    # Duration (in minutes)
    duration_minutes: Optional[int]
    
    # Release info
    release_date: Optional[str]
    availability_status: str  # "available", "upcoming", "premiere"
    is_new_release: bool
    is_premiere: bool
    is_retrospective: bool
    
    # Image
    poster_url: Optional[str]
    
    # Ratings
    ratings: list[Rating]
    
    # Screening info
    copies_count: int  # Number of copies/screenings in Paris
    showtimes: list[Showtime]


# Cinema mapping from the HTML
CINEMAS = {
    # Paris Centre
    "106": "Centre Georges-Pompidou",
    "101": "Forum des images",
    "246": "Jeu de Paume",
    "103": "Le Grand Rex",
    "107": "Luminor Hôtel de Ville",
    "105": "MK2 Beaubourg",
    "104": "Pathé BNP Paribas",
    "245": "Pathé Palace",
    "102": "UGC Ciné Cité Les Halles",
    # Paris 05
    "108": "Champo",
    "112": "Épée de bois",
    "110": "Filmothèque du Quartier Latin",
    "111": "Grand Action",
    "113": "Le Desperado",
    "114": "Reflet Medicis",
    "115": "Espace Saint-Michel",
    "116": "Studio des Ursulines",
    "117": "Studio Galande",
    "118": "UGC Ciné Cité Bercy",
    "119": "UGC Odéon",
    # Paris 06
    "120": "Christine Cinema Club",
    "122": "L'Arlequin",
    "123": "Les 3 Luxembourg",
    "124": "Lucernaire",
    "125": "MK2 Odéon (St Germain)",
    "126": "MK2 Odéon (St Michel)",
    "127": "MK2 Parnasse",
    "128": "Nouvel Odéon",
    "129": "Saint-André des Arts",
    "131": "UGC Danton",
    "132": "UGC Montparnasse",
    "133": "UGC Odéon",
    "134": "UGC Rotonde",
    # Paris 08
    "135": "Elysées Lincoln",
    "137": "Le Balzac",
    "139": "Publicis Cinémas",
    # Paris 09
    "142": "Les 5 Caumartin",
    "143": "Max Linder Panorama",
    "144": "UGC Opéra",
    # Paris 10
    "145": "L'Archipel",
    "146": "Le Brady",
    "147": "Le Louxor",
    # Paris 11
    "148": "Majestic Bastille",
    "149": "MK2 Bastille (Beaumarchais)",
    "150": "MK2 Bastille (Fg St Antoine)",
    # Paris 12
    "151": "La Cinémathèque française",
    "152": "MK2 Nation",
    "153": "UGC Ciné Cité Bercy",
    "154": "UGC Lyon Bastille",
    # Paris 13
    "155": "Escurial",
    "156": "Fondation Jerome Seydoux - Pathé",
    "157": "MK2 Bibliothèque",
    "158": "Pathé Les Fauvettes",
    "159": "UGC Gobelins",
    # Paris 14
    "160": "Chaplin Denfert",
    "162": "L'Entrepôt",
    "248": "Le Miramar",
    "163": "Les 7 Parnassiens",
    "164": "Pathé Alésia",
    "161": "Pathé Montparnos",
    "165": "Pathé Parnasse",
    # Paris 15
    "166": "Chaplin Saint Lambert",
    "167": "Pathé Aquaboulevard",
    "169": "Pathé Beaugrenelle",
    "168": "Pathé Convention",
    # Paris 16
    "170": "Le Ranelagh",
    "171": "Majestic Passy",
    # Paris 17
    "172": "7 Batignolles",
    "173": "Club de l'étoile",
    "174": "Le Cinéma des Cinéastes",
    "175": "Mac-Mahon",
    "176": "UGC Maillot",
    # Paris 18
    "178": "Pathé Wepler",
    "177": "Studio 28",
    # Paris 19
    "249": "La Géode",
    "179": "MK2 Quai de Loire",
    "180": "MK2 Quai de Seine",
    "181": "Parc de la Villette",
    "182": "Pathé La Villette",
    "183": "UGC Ciné Cité Paris 19",
    # Paris 20
    "184": "CGR Paris Lilas",
    "185": "MK2 Gambetta",
}


def get_availability_status(release_date_str: Optional[str], today: date) -> str:
    """
    Determine if a movie is available, upcoming, or in premiere.
    Returns: "available", "upcoming", or "premiere"
    """
    if not release_date_str:
        return "available"  # Default if no release date
    
    try:
        # Try different date formats
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"]:
            try:
                release_date = datetime.strptime(release_date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            return "available"  # Default if parsing fails
        
        if release_date > today:
            return "upcoming"
        else:
            return "available"
    except Exception:
        return "available"


def parse_rating(value: Optional[str], source: str, max_score: float, url: Optional[str] = None) -> Optional[Rating]:
    """Parse a rating value and return a Rating object."""
    if value is None or value == "" or value == "0":
        return None
    
    try:
        score = float(value)
        if score <= 0:
            return None
        return Rating(source=source, score=score, max_score=max_score, url=url)
    except (ValueError, TypeError):
        return None


def parse_movie_data(raw_data: dict, today: date = None) -> Movie:
    """
    Parse raw API movie data into a structured Movie object.
    
    API field mappings:
    - ti: title
    - o_ti: original title
    - di: director
    - ac: actors
    - ye: year
    - ge: genre
    - la: language
    - du: duration (if available)
    - rel: release date
    - ne: new flag (1 = new release, 2 = premiere/avant-première)
    - ret: retrospective flag
    - co: copies count
    - im_r, i_id: IMDB rating and ID
    - sc_r, sc_u: SensCritique rating and URL
    - ap_r: Allociné press rating
    - as_r: Allociné spectator rating  
    - lb_r, lb_u: Letterboxd rating and URL
    - mc_r, mc_u: Metacritic rating and URL
    - rt_r, rt_u: Rotten Tomatoes rating and URL
    - id: Allociné ID
    """
    if today is None:
        today = date.today()
    
    # Parse ratings
    ratings = []
    
    # IMDB (scale 0-10)
    imdb_url = None
    if raw_data.get("i_id"):
        imdb_url = f"https://www.imdb.com/title/tt{raw_data['i_id']}"
    rating = parse_rating(raw_data.get("im_r"), "IMDB", 10.0, imdb_url)
    if rating:
        ratings.append(rating)
    
    # SensCritique (scale 0-10)
    sc_url = None
    if raw_data.get("sc_u"):
        sc_url = f"https://www.senscritique.com/film/{raw_data['sc_u']}"
    rating = parse_rating(raw_data.get("sc_r"), "SensCritique", 10.0, sc_url)
    if rating:
        ratings.append(rating)
    
    # Allociné Press (scale 0-5)
    allo_url = None
    if raw_data.get("id"):
        allo_url = f"http://www.allocine.fr/film/fichefilm_gen_cfilm={raw_data['id']}.html"
    rating = parse_rating(raw_data.get("ap_r"), "Allociné (Presse)", 5.0, allo_url)
    if rating:
        ratings.append(rating)
    
    # Allociné Spectateurs (scale 0-5)
    rating = parse_rating(raw_data.get("as_r"), "Allociné (Spectateurs)", 5.0, allo_url)
    if rating:
        ratings.append(rating)
    
    # Letterboxd (scale 0-5)
    lb_url = None
    if raw_data.get("lb_u"):
        lb_url = f"https://letterboxd.com/film/{raw_data['lb_u']}"
    rating = parse_rating(raw_data.get("lb_r"), "Letterboxd", 5.0, lb_url)
    if rating:
        ratings.append(rating)
    
    # Metacritic (scale 0-100)
    mc_url = None
    if raw_data.get("mc_u"):
        mc_url = f"https://www.metacritic.com/movie/{raw_data['mc_u']}"
    rating = parse_rating(raw_data.get("mc_r"), "Metacritic", 100.0, mc_url)
    if rating:
        ratings.append(rating)
    
    # Rotten Tomatoes (scale 0-100)
    rt_url = None
    if raw_data.get("rt_u"):
        rt_url = f"https://www.rottentomatoes.com/m/{raw_data['rt_u']}"
    rating = parse_rating(raw_data.get("rt_r"), "Rotten Tomatoes", 100.0, rt_url)
    if rating:
        ratings.append(rating)
    
    # Parse new/premiere flags
    ne_flag = str(raw_data.get("ne", "0"))
    is_new_release = ne_flag == "1"
    is_premiere = ne_flag == "2"
    
    # Parse release date and determine availability
    release_date = raw_data.get("rel")
    availability_status = get_availability_status(release_date, today)
    
    # Override status if premiere flag is set
    if is_premiere:
        availability_status = "premiere"
    
    # Parse year
    year = None
    if raw_data.get("ye"):
        try:
            year = int(raw_data["ye"])
        except (ValueError, TypeError):
            pass
    
    # Parse copies count
    copies_count = 0
    if raw_data.get("co"):
        try:
            copies_count = int(raw_data["co"])
        except (ValueError, TypeError):
            pass
    
    # Parse duration if available (format: "1h30m" or "2h5m")
    duration = None
    if raw_data.get("du"):
        try:
            du_str = raw_data["du"]
            hours = 0
            minutes = 0
            
            if "h" in du_str:
                parts = du_str.split("h")
                hours = int(parts[0])
                if len(parts) > 1 and parts[1]:
                    minutes = int(parts[1].replace("m", ""))
            elif "m" in du_str:
                minutes = int(du_str.replace("m", ""))
            
            duration = hours * 60 + minutes if (hours or minutes) else None
        except (ValueError, TypeError):
            pass
    
    # Build poster URL from movie ID
    movie_id = raw_data.get("id", 0)
    poster_url = f"https://paris-cine.info/get_poster.php?id={movie_id}" if movie_id else None
    
    return Movie(
        id=movie_id,
        title=raw_data.get("ti", ""),
        original_title=raw_data.get("o_ti"),
        director=raw_data.get("di"),
        actors=raw_data.get("ac"),
        year=year,
        genre=raw_data.get("ge"),
        language=raw_data.get("la"),
        duration_minutes=duration,
        release_date=release_date,
        availability_status=availability_status,
        is_new_release=is_new_release,
        is_premiere=is_premiere,
        is_retrospective=str(raw_data.get("ret", "0")) == "1",
        poster_url=poster_url,
        ratings=ratings,
        copies_count=copies_count,
        showtimes=[]  # Showtimes are fetched separately per movie
    )


def fetch_movies_from_api(
    day: str = "week",
    card: str = "all", 
    location: str = "75000",
    timeout: int = 30
) -> list[dict]:
    """
    Fetch movies from the Paris Ciné Info API.
    
    Args:
        day: "week", "today", or specific date
        card: Card filter (e.g., "all", "ugc", "pass")
        location: Zip code filter (e.g., "75000" for Paris)
        timeout: Request timeout in seconds
    
    Returns:
        List of raw movie data dictionaries
    """
    base_url = "https://paris-cine.info/get_movies.php"
    
    params = {
        "selday": day,
        "seldayid": "",
        "selcard": card,
        "selformat": "all",
        "seladdr": location,
        "selcine": "",
        "selevent": "",
        "seltime": "all",
        "sellang": "all",
        "init": "true",
        "watchtype": "",
        "debug": "false"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except requests.RequestException as e:
        print(f"Error fetching data from API: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        return []


def fetch_showtimes_for_movie(
    movie_id: int,
    movie_language: str = "",
    day: str = "week",
    card: str = "all",
    location: str = "75000",
    timeout: int = 15,
    max_retries: int = 3
) -> list[Showtime]:
    """
    Fetch showtimes for a specific movie from the Paris Ciné Info API.
    
    Args:
        movie_id: The Allociné movie ID
        movie_language: The movie's language (for filtering)
        day: "week", "today", or specific date
        card: Card filter
        location: Zip code filter
        timeout: Request timeout in seconds
        max_retries: Number of retries on rate limit (429) errors
    
    Returns:
        List of Showtime objects
    """
    base_url = "https://paris-cine.info/get_showtimes.php"
    
    params = {
        "mov_id": movie_id,
        "selday": day,
        "selcard": card,
        "seladdr": location,
        "seltime": "all",
        "selcine": "",
        "selformat": "all",
        "selevent": "",
        "sellang": "all",
        "movlang": movie_language,
        "debug": "false"
    }
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(base_url, params=params, timeout=timeout)
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                if attempt < max_retries:
                    wait_time = 5 * (attempt + 1)  # 5s, 10s, 15s
                    print(f"\n  Rate limited, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"\n  Rate limit exceeded for movie {movie_id} after {max_retries} retries")
                    return []
            
            response.raise_for_status()
            data = response.json()
            
            showtimes = []
            for st in data.get("showtimes", []):
                showtime = Showtime(
                    cinema_id=st.get("tid", ""),
                    cinema_name=st.get("title", ""),
                    datetime=st.get("start", ""),
                    version=st.get("type") if st.get("type") else None,
                    screen_name=st.get("screen_name") if st.get("screen_name") else None,
                    format=st.get("format") if st.get("format") else None,
                    booking_url=st.get("book") if st.get("book") else None,
                    has_seat_reservation=str(st.get("seat_res")) == "1"
                )
                showtimes.append(showtime)
            
            return showtimes
            
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(3)
                continue
            print(f"\nError fetching showtimes for movie {movie_id}: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"\nError parsing showtimes JSON for movie {movie_id}: {e}")
            return []
    
    return []


def scrape_movies(
    day: str = "week",
    card: str = "all",
    location: str = "75000",
    include_showtimes: bool = False,
    max_movies_with_showtimes: int = None
) -> list[Movie]:
    """
    Main function to scrape and parse movie data.
    
    Args:
        day: "week", "today", or specific date
        card: Card filter 
        location: Zip code filter
        include_showtimes: If True, fetch showtimes for each movie (slower)
        max_movies_with_showtimes: Limit number of movies to fetch showtimes for
    
    Returns:
        List of parsed Movie objects
    """
    today = date.today()
    raw_movies = fetch_movies_from_api(day, card, location)
    
    movies = []
    for idx, raw_movie in enumerate(raw_movies):
        try:
            movie = parse_movie_data(raw_movie, today)
            
            # Fetch showtimes if requested
            if include_showtimes:
                if max_movies_with_showtimes is None or idx < max_movies_with_showtimes:
                    print(f"  [{idx+1}] Fetching showtimes for: {movie.title}...".ljust(80), end="\r")
                    movie.showtimes = fetch_showtimes_for_movie(
                        movie_id=movie.id,
                        movie_language=movie.language or "",
                        day=day,
                        card=card,
                        location=location
                    )
                    # Add delay to avoid rate limiting (429 errors)
                    time.sleep(1.5)
            
            movies.append(movie)
        except Exception as e:
            print(f"Error parsing movie: {e}")
            continue
    
    if include_showtimes:
        print()  # Clear the progress line
    
    return movies


def movies_to_json(movies: list[Movie], indent: int = 2) -> str:
    """Convert list of movies to JSON string."""
    def rating_to_dict(r: Rating) -> dict:
        return {
            "source": r.source,
            "score": r.score,
            "max_score": r.max_score,
            "url": r.url
        }
    
    def showtime_to_dict(s: Showtime) -> dict:
        return {
            "cinema_id": s.cinema_id,
            "cinema_name": s.cinema_name,
            "datetime": s.datetime,
            "version": s.version,
            "screen_name": s.screen_name,
            "format": s.format,
            "booking_url": s.booking_url,
            "has_seat_reservation": s.has_seat_reservation
        }
    
    def movie_to_dict(m: Movie) -> dict:
        return {
            "id": m.id,
            "title": m.title,
            "original_title": m.original_title,
            "director": m.director,
            "actors": m.actors,
            "year": m.year,
            "genre": m.genre,
            "language": m.language,
            "duration_minutes": m.duration_minutes,
            "release_date": m.release_date,
            "availability_status": m.availability_status,
            "is_new_release": m.is_new_release,
            "is_premiere": m.is_premiere,
            "is_retrospective": m.is_retrospective,
            "poster_url": m.poster_url,
            "ratings": [rating_to_dict(r) for r in m.ratings],
            "copies_count": m.copies_count,
            "showtimes": [showtime_to_dict(s) for s in m.showtimes]
        }
    
    movies_list = [movie_to_dict(m) for m in movies]
    return json.dumps(movies_list, indent=indent, ensure_ascii=False)


def save_movies_to_file(movies: list[Movie], filepath: str) -> None:
    """Save movies to a JSON file."""
    json_str = movies_to_json(movies)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_str)
    print(f"Saved {len(movies)} movies to {filepath}")


# JSON Schema for the output
JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Paris Cinema Movies",
    "description": "Schema for movie data scraped from Paris Ciné Info",
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "title", "availability_status"],
        "properties": {
            "id": {
                "type": "integer",
                "description": "Unique movie identifier (Allociné ID)"
            },
            "title": {
                "type": "string",
                "description": "Movie title in French"
            },
            "original_title": {
                "type": ["string", "null"],
                "description": "Original title if different from French title"
            },
            "director": {
                "type": ["string", "null"],
                "description": "Director name(s)"
            },
            "actors": {
                "type": ["string", "null"],
                "description": "Main actors"
            },
            "year": {
                "type": ["integer", "null"],
                "description": "Release year"
            },
            "genre": {
                "type": ["string", "null"],
                "description": "Movie genre(s)"
            },
            "language": {
                "type": ["string", "null"],
                "description": "Language (VF, VO, English, etc.)"
            },
            "duration_minutes": {
                "type": ["integer", "null"],
                "description": "Movie duration in minutes"
            },
            "release_date": {
                "type": ["string", "null"],
                "description": "Release date (format: YYYY-MM-DD)"
            },
            "availability_status": {
                "type": "string",
                "enum": ["available", "upcoming", "premiere"],
                "description": "Whether movie is currently available, upcoming, or in premiere"
            },
            "is_new_release": {
                "type": "boolean",
                "description": "True if this is a new release this week"
            },
            "is_premiere": {
                "type": "boolean",
                "description": "True if this is an avant-première (preview screening)"
            },
            "is_retrospective": {
                "type": "boolean",
                "description": "True if part of a director retrospective"
            },
            "poster_url": {
                "type": ["string", "null"],
                "description": "URL to the movie poster image"
            },
            "ratings": {
                "type": "array",
                "description": "Movie ratings from various sources",
                "items": {
                    "type": "object",
                    "required": ["source", "score", "max_score"],
                    "properties": {
                        "source": {
                            "type": "string",
                            "enum": [
                                "IMDB",
                                "SensCritique", 
                                "Allociné (Presse)",
                                "Allociné (Spectateurs)",
                                "Letterboxd",
                                "Metacritic",
                                "Rotten Tomatoes"
                            ],
                            "description": "Rating source name"
                        },
                        "score": {
                            "type": ["number", "null"],
                            "description": "Rating score"
                        },
                        "max_score": {
                            "type": "number",
                            "description": "Maximum possible score for this source"
                        },
                        "url": {
                            "type": ["string", "null"],
                            "description": "URL to the movie page on this rating source"
                        }
                    }
                }
            },
            "copies_count": {
                "type": "integer",
                "description": "Number of screenings/copies in Paris area"
            },
            "showtimes": {
                "type": "array",
                "description": "List of showtimes (empty unless --showtimes flag is used)",
                "items": {
                    "type": "object",
                    "required": ["cinema_id", "cinema_name", "datetime"],
                    "properties": {
                        "cinema_id": {
                            "type": "string",
                            "description": "Cinema identifier (e.g., 'C0050')"
                        },
                        "cinema_name": {
                            "type": "string",
                            "description": "Cinema name (e.g., 'MK2 Beaubourg')"
                        },
                        "datetime": {
                            "type": "string",
                            "description": "Showtime in ISO format (YYYY-MM-DDTHH:MM:SS)"
                        },
                        "version": {
                            "type": ["string", "null"],
                            "description": "Version (VO, VF, VOSTFR, etc.)"
                        },
                        "screen_name": {
                            "type": ["string", "null"],
                            "description": "Screen/room name"
                        },
                        "format": {
                            "type": ["string", "null"],
                            "description": "Special format (3D, IMAX, Dolby, etc.)"
                        },
                        "booking_url": {
                            "type": ["string", "null"],
                            "description": "URL to book tickets"
                        },
                        "has_seat_reservation": {
                            "type": "boolean",
                            "description": "True if seat reservation is available"
                        }
                    }
                }
            }
        }
    }
}


def print_schema():
    """Print the JSON schema."""
    print(json.dumps(JSON_SCHEMA, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape movie data from Paris Ciné Info")
    parser.add_argument("--day", default="week", help="Day filter: 'week', 'today', or specific date")
    parser.add_argument("--location", default="75000", help="Location zip code (default: 75000 for Paris)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--schema", action="store_true", help="Print JSON schema and exit")
    parser.add_argument("--showtimes", action="store_true", help="Include showtimes for each movie (slower)")
    parser.add_argument("--max-showtimes", type=int, default=None, 
                        help="Limit number of movies to fetch showtimes for (use with --showtimes)")
    
    args = parser.parse_args()
    
    if args.schema:
        print_schema()
    else:
        print("Fetching movies from Paris Ciné Info...")
        if args.showtimes:
            print("(Including showtimes - this may take a while...)")
        
        movies = scrape_movies(
            day=args.day, 
            location=args.location,
            include_showtimes=args.showtimes,
            max_movies_with_showtimes=args.max_showtimes
        )
        
        if movies:
            print(f"\nFound {len(movies)} movies\n")
            
            if args.output:
                save_movies_to_file(movies, args.output)
            else:
                # Print first 3 movies as sample
                print("Sample output (first 3 movies):")
                print(movies_to_json(movies[:3]))
                print(f"\n... and {len(movies) - 3} more movies")
        else:
            print("No movies found or error occurred.")
