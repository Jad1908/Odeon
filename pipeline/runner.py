"""
Pipeline Runner - Orchestrates scraping and analysis with progress reporting.
"""
import json
import sys
import os
import time
import threading
from datetime import datetime
from queue import Queue
from typing import Callable, Optional

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from movie_scraper import (
    fetch_movies_from_api, 
    parse_movie_data, 
    fetch_showtimes_for_movie,
    save_movies_to_file
)
from movie_analysis import process_movies


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
    
    def run_scraper(self, output_file: str = "week_full.json"):
        """Run the movie scraper with progress reporting."""
        if self.is_running:
            return {"error": "Pipeline already running"}
        
        def _scrape():
            try:
                self.is_running = True
                self.status = "scraping"
                self.error = None
                self.logs = []
                
                self.log("Starting movie scraper (full week with showtimes)...")
                self.current_task = "Fetching movie list from API"
                
                # Fetch movie list
                from datetime import date
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
                
                self.log(f"Scraping complete! Saved {len(movies)} movies")
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
    
    def run_analysis(self, input_file: str = "week_full.json", output_file: str = "newsletter_data.json"):
        """Run the movie analysis to generate newsletter data."""
        if self.is_running:
            return {"error": "Pipeline already running"}
        
        def _analyze():
            try:
                self.is_running = True
                self.status = "analyzing"
                self.error = None
                self.progress = 0
                self.total = 100
                
                self.log("Starting analysis pipeline...")
                self.current_task = "Loading movie data"
                self.progress = 10
                
                # Check if input file exists
                if not os.path.exists(input_file):
                    raise Exception(f"Input file not found: {input_file}. Run scraper first.")
                
                self.log(f"Reading from {input_file}")
                self.progress = 30
                
                self.current_task = "Processing and categorizing movies"
                self.log("Categorizing movies into newsletter sections...")
                self.progress = 50
                
                # Run the analysis
                # We need to temporarily modify the INPUT_FILE and OUTPUT_FILE
                import movie_analysis
                original_input = movie_analysis.INPUT_FILE
                original_output = movie_analysis.OUTPUT_FILE
                
                movie_analysis.INPUT_FILE = input_file
                movie_analysis.OUTPUT_FILE = output_file
                
                try:
                    movie_analysis.process_movies()
                finally:
                    movie_analysis.INPUT_FILE = original_input
                    movie_analysis.OUTPUT_FILE = original_output
                
                self.progress = 90
                self.current_task = "Finalizing"
                
                # Get stats from output
                with open(output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                stats = {k: len(v) for k, v in data.items()}
                self.log(f"Generated newsletter data: {stats}")
                
                self.progress = 100
                self.status = "complete"
                self.current_task = "Analysis complete"
                self.log(f"Analysis complete! Output saved to {output_file}")
                
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
