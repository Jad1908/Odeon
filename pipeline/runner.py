"""
Pipeline Runner - Orchestrates scraping and analysis with progress reporting.
"""
import json
import os
import time
import threading
from datetime import datetime, date, timedelta
from queue import Queue
from typing import Callable, Optional

from .scraper import (
    fetch_movies_from_api,
    parse_movie_data,
    fetch_showtimes_for_movie,
    save_movies_to_file
)
from .analysis import process_movies

SCRAPE_META_FILE = "data/scrape_meta.json"


def cinema_week_start(day: date = None) -> str:
    """The French cinema week runs Wednesday to Tuesday; return its start date."""
    if day is None:
        day = date.today()
    monday_offset = (day.weekday() - 2) % 7  # days since last Wednesday
    return (day - timedelta(days=monday_offset)).isoformat()


def get_cache_info(data_file: str = "data/week_full.json") -> dict:
    """Describe the cached scrape: when it ran and whether it's still current."""
    info = {"exists": False, "fresh": False, "scraped_at": None,
            "week_start": None, "movie_count": None}
    if not os.path.exists(data_file):
        return info
    info["exists"] = True
    try:
        with open(SCRAPE_META_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
        info["scraped_at"] = meta.get("scraped_at")
        info["week_start"] = meta.get("week_start")
        info["movie_count"] = meta.get("movie_count")
        info["fresh"] = meta.get("week_start") == cinema_week_start()
    except (FileNotFoundError, json.JSONDecodeError):
        # Data predates cache metadata: usable but of unknown age
        pass
    return info


def write_scrape_meta(movie_count: int):
    os.makedirs(os.path.dirname(SCRAPE_META_FILE), exist_ok=True)
    with open(SCRAPE_META_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "week_start": cinema_week_start(),
            "movie_count": movie_count
        }, f, indent=2)


class PipelineRunner:
    """Manages the scraping and analysis pipeline with progress reporting."""
    
    def __init__(self):
        self.status = "idle"  # idle, scraping, analyzing, complete, error
        self.progress = 0
        self.total = 0
        self.current_task = ""
        self.logs = []
        self.error = None
        self.is_running = False
        self._lock = threading.Lock()
        
    def log(self, message: str):
        """Add a log message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.logs.append(f"[{timestamp}] {message}")
            # Keep only last 100 logs
            if len(self.logs) > 100:
                self.logs = self.logs[-100:]
    
    def get_state(self) -> dict:
        """Get current pipeline state."""
        with self._lock:
            return {
                "status": self.status,
                "progress": self.progress,
                "total": self.total,
                "current_task": self.current_task,
                "logs": self.logs[-20:],  # Last 20 logs
                "error": self.error,
                "is_running": self.is_running
            }
    
    def reset(self):
        """Reset pipeline state."""
        with self._lock:
            self.status = "idle"
            self.progress = 0
            self.total = 0
            self.current_task = ""
            self.logs = []
            self.error = None
            self.is_running = False
    
    def _do_scrape(self, output_file: str):
        """Blocking scrape of the full week with showtimes."""
        self.status = "scraping"
        self.log("Starting movie scraper (full week with showtimes)...")
        self.current_task = "Fetching movie list from API"

        today = date.today()
        raw_movies = fetch_movies_from_api(day="week", card="all", location="75000")

        if not raw_movies:
            raise Exception("No movies returned from API")

        self.total = len(raw_movies)
        self.log(f"Found {self.total} movies to process")

        movies = []
        for idx, raw_movie in enumerate(raw_movies):
            try:
                movie = parse_movie_data(raw_movie, today)

                # Update progress
                self.progress = idx + 1
                self.current_task = f"Fetching showtimes: {movie.title[:40]}..."

                # Fetch showtimes
                movie.showtimes = fetch_showtimes_for_movie(
                    movie_id=movie.id,
                    movie_language=movie.language or "",
                    day="week",
                    card="all",
                    location="75000"
                )

                movies.append(movie)

                if (idx + 1) % 10 == 0:
                    self.log(f"Processed {idx + 1}/{self.total} movies")

                # Rate limiting delay
                time.sleep(1.5)

            except Exception as e:
                self.log(f"Error parsing movie: {e}")
                continue

        # Save to file
        self.current_task = "Saving results to file"
        self.log(f"Saving {len(movies)} movies to {output_file}")
        save_movies_to_file(movies, output_file)
        write_scrape_meta(len(movies))
        self.log(f"Scraping complete! Saved {len(movies)} movies")

    def _do_analysis(self, input_file: str, output_file: str):
        """Blocking categorization of the scraped week into newsletter sections."""
        self.status = "analyzing"
        self.current_task = "Categorizing movies into newsletter sections"
        self.log(f"Categorizing {input_file} into newsletter sections...")

        if not os.path.exists(input_file):
            raise Exception(f"Input file not found: {input_file}. Run scraper first.")

        from . import analysis
        original_input = analysis.INPUT_FILE
        original_output = analysis.OUTPUT_FILE

        analysis.INPUT_FILE = input_file
        analysis.OUTPUT_FILE = output_file

        try:
            analysis.process_movies()
        finally:
            analysis.INPUT_FILE = original_input
            analysis.OUTPUT_FILE = original_output

        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stats = {k: len(v) for k, v in data.items()}
        self.log(f"Generated newsletter data: {stats}")

    def run_fetch(self, force: bool = False,
                  data_file: str = "data/week_full.json",
                  analysis_file: str = "data/newsletter_data.json"):
        """Fetch the week's movies, reusing the cached scrape when still current."""
        if self.is_running:
            return {"error": "Pipeline already running"}

        cache = get_cache_info(data_file)
        use_cache = cache["fresh"] and not force

        # Mark busy before the thread spawns so a status poll racing the
        # thread start never sees a stale 'complete' state
        self.is_running = True
        self.status = "starting"
        self.error = None
        self.logs = []

        def _fetch():
            try:
                if use_cache:
                    self.log(f"Using cached scrape from {cache['scraped_at']} "
                             f"(cinema week of {cache['week_start']}, {cache['movie_count']} movies)")
                else:
                    if cache["exists"] and not force:
                        self.log("Cached scrape is from a past cinema week, re-fetching...")
                    self._do_scrape(data_file)

                self.progress = 0
                self.total = 0
                self._do_analysis(data_file, analysis_file)

                self.status = "complete"
                self.current_task = "Fetch complete"
                self.log("Fetch complete! Movie data is ready.")

            except Exception as e:
                self.error = str(e)
                self.status = "error"
                self.log(f"ERROR: {e}")
            finally:
                self.is_running = False

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

        return {"status": "started", "used_cache": use_cache}

    def run_scraper(self, output_file: str = "data/week_full.json"):
        """Run the movie scraper with progress reporting."""
        if self.is_running:
            return {"error": "Pipeline already running"}

        def _scrape():
            try:
                self.is_running = True
                self.error = None
                self.logs = []
                self._do_scrape(output_file)
                self.status = "complete"
                self.current_task = "Scraping complete"
            except Exception as e:
                self.error = str(e)
                self.status = "error"
                self.log(f"ERROR: {e}")
            finally:
                self.is_running = False

        # Run in background thread
        thread = threading.Thread(target=_scrape, daemon=True)
        thread.start()

        return {"status": "started"}
    
    def run_analysis(self, input_file: str = "data/week_full.json", output_file: str = "data/newsletter_data.json"):
        """Run the movie analysis to generate newsletter data."""
        if self.is_running:
            return {"error": "Pipeline already running"}
        
        def _analyze():
            try:
                self.is_running = True
                self.error = None
                self._do_analysis(input_file, output_file)
                self.status = "complete"
                self.current_task = "Analysis complete"
            except Exception as e:
                self.error = str(e)
                self.status = "error"
                self.log(f"ERROR: {e}")
            finally:
                self.is_running = False
        
        # Run in background thread
        thread = threading.Thread(target=_analyze, daemon=True)
        thread.start()
        
        return {"status": "started"}


# Global pipeline instance
pipeline = PipelineRunner()
