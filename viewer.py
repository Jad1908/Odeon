"""
Newsletter Data Viewer - Multi-tab web interface for visualizing newsletter data.
"""
import json
import os
from flask import Flask, render_template_string, jsonify, request

from pipeline.runner import pipeline

app = Flask(__name__)

# Category display names and descriptions
CATEGORIES = {
    "top_new_releases": {
        "name": "Top New Releases",
        "description": "Brand new movies released within the last 7 days"
    },
    "current_landscape": {
        "name": "Current Landscape", 
        "description": "Recent movies still playing in theaters (1-8 weeks old)"
    },
    "premieres_events": {
        "name": "Premieres & Events",
        "description": "Special premiere screenings and events"
    },
    "old_classics": {
        "name": "Old Classics",
        "description": "Classic films returning to the big screen"
    },
    "letterboxd_picks": {
        "name": "Letterboxd Picks",
        "description": "Highly rated on Letterboxd (7.0+)"
    },
    "niche_gems": {
        "name": "Niche Gems",
        "description": "High quality films with limited screenings"
    }
}

# Export categories (can be customized)
EXPORT_CATEGORIES = [
    "featured",
    "recommended", 
    "classics",
    "hidden_gems",
    "premieres"
]

def load_data():
    """Load newsletter data from JSON file."""
    with open('data/newsletter_data.json', 'r', encoding='utf-8') as f:
        return json.load(f)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Newsletter Data Viewer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .tab-btn.active { 
            background-color: rgb(59, 130, 246); 
            color: white; 
        }
        .movie-card {
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .movie-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }
        .movie-card.selected {
            border-color: rgb(34, 197, 94);
            border-width: 2px;
            background-color: rgb(240, 253, 244);
        }
        .rating-badge {
            min-width: 40px;
            text-align: center;
        }
        .showtime-pill {
            font-size: 0.7rem;
        }
        .selection-panel {
            position: fixed;
            right: 0;
            top: 0;
            height: 100vh;
            width: 320px;
            transform: translateX(100%);
            transition: transform 0.3s ease;
            z-index: 50;
        }
        .selection-panel.open {
            transform: translateX(0);
        }
        .panel-toggle {
            position: fixed;
            right: 0;
            top: 50%;
            transform: translateY(-50%);
            z-index: 40;
            transition: right 0.3s ease;
        }
        .panel-toggle.shifted {
            right: 320px;
        }
        .export-category-btn.active {
            background-color: rgb(59, 130, 246);
            color: white;
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Selection Panel Toggle Button -->
    <button id="panelToggle" class="panel-toggle bg-green-600 text-white px-3 py-4 rounded-l-lg shadow-lg hover:bg-green-700">
        <span id="selectionCount">0</span> Selected
    </button>

    <!-- Selection Panel -->
    <div id="selectionPanel" class="selection-panel bg-white shadow-2xl overflow-hidden flex flex-col">
        <div class="bg-green-600 text-white p-4 flex justify-between items-start">
            <div>
                <h3 class="font-bold text-lg">Selected Movies</h3>
                <p class="text-sm opacity-80">Add movies to export categories</p>
            </div>
            <button onclick="closePanel()" class="text-white hover:bg-green-700 p-1 rounded">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
        
        <!-- Export Categories -->
        <div class="p-3 border-b bg-gray-50">
            <p class="text-xs font-medium text-gray-500 mb-2">EXPORT CATEGORY</p>
            <div class="flex flex-wrap gap-1">
                {% for cat in export_categories %}
                <button class="export-category-btn text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-100"
                        data-category="{{ cat }}"
                        onclick="setExportCategory('{{ cat }}')">
                    {{ cat }}
                </button>
                {% endfor %}
            </div>
            <p class="text-xs text-gray-400 mt-2">Current: <span id="currentExportCategory" class="font-medium text-blue-600">featured</span></p>
        </div>

        <!-- Selected Movies List -->
        <div id="selectedMoviesList" class="flex-1 overflow-y-auto p-3">
            <p class="text-gray-400 text-sm text-center py-8">No movies selected yet</p>
        </div>

        <!-- Export Actions -->
        <div class="p-3 border-t bg-gray-50">
            <button onclick="exportSelection()" 
                    class="w-full bg-green-600 text-white py-2 px-4 rounded-lg hover:bg-green-700 font-medium mb-2">
                Export JSON
            </button>
            <button onclick="clearSelection()" 
                    class="w-full bg-gray-200 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-300 text-sm">
                Clear All
            </button>
        </div>
    </div>

    <div class="container mx-auto px-4 py-8 max-w-6xl">
        <!-- Header -->
        <header class="mb-8 text-center">
            <h1 class="text-4xl font-bold text-gray-800 mb-2">Newsletter Data Viewer</h1>
            <p class="text-gray-600">Explore and analyze your movie data across categories</p>
        </header>

        <!-- Stats Summary -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
            {% for key, cat in categories.items() %}
            <div class="bg-white rounded-lg p-3 shadow text-center">
                <div class="text-2xl font-bold text-blue-600">{{ data.get(key, [])|length }}</div>
                <div class="text-xs text-gray-500 truncate" title="{{ cat.name }}">{{ cat.name }}</div>
            </div>
            {% endfor %}
        </div>

        <!-- Tab Navigation -->
        <div class="flex flex-wrap gap-2 mb-6 bg-white p-3 rounded-lg shadow">
            <button 
                class="tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-colors active
                       hover:bg-blue-100 text-gray-700 border-2 border-orange-400"
                data-tab="pipeline">
                Pipeline
            </button>
            {% for key, cat in categories.items() %}
            <button 
                class="tab-btn px-4 py-2 rounded-lg text-sm font-medium transition-colors
                       hover:bg-blue-100 text-gray-700"
                data-tab="{{ key }}">
                {{ cat.name }} ({{ data.get(key, [])|length }})
            </button>
            {% endfor %}
        </div>

        <!-- Tab Contents -->
        
        <!-- Pipeline Tab -->
        <div id="tab-pipeline" class="tab-content active">
            <div class="bg-white rounded-lg shadow p-6 mb-6">
                <h2 class="text-2xl font-bold text-gray-800 mb-1">Data Pipeline</h2>
                <p class="text-gray-500 mb-6">Scrape movie data and generate newsletter reports</p>
                
                <!-- Pipeline Steps -->
                <div class="grid md:grid-cols-2 gap-6 mb-8">
                    <!-- Step 1: Scraper -->
                    <div class="border-2 border-gray-200 rounded-lg p-5">
                        <div class="flex items-center gap-3 mb-3">
                            <span class="bg-blue-100 text-blue-800 font-bold px-3 py-1 rounded-full text-sm">1</span>
                            <h3 class="font-bold text-lg text-gray-800">Scrape Movies</h3>
                        </div>
                        <p class="text-gray-600 text-sm mb-4">
                            Fetch all movies playing in Paris this week with showtimes from paris-cine.info API.
                            This process takes 10-15 minutes.
                        </p>
                        <p class="text-xs text-gray-400 mb-4">Output: data/week_full.json</p>
                        <button onclick="startScraper()" 
                                id="scrapeBtn"
                                class="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                            Start Scraping
                        </button>
                    </div>
                    
                    <!-- Step 2: Analysis -->
                    <div class="border-2 border-gray-200 rounded-lg p-5">
                        <div class="flex items-center gap-3 mb-3">
                            <span class="bg-green-100 text-green-800 font-bold px-3 py-1 rounded-full text-sm">2</span>
                            <h3 class="font-bold text-lg text-gray-800">Generate Report</h3>
                        </div>
                        <p class="text-gray-600 text-sm mb-4">
                            Process scraped data and categorize movies into newsletter sections
                            (new releases, classics, niche gems, etc.).
                        </p>
                        <p class="text-xs text-gray-400 mb-4">Output: data/newsletter_data.json</p>
                        <button onclick="startAnalysis()" 
                                id="analyzeBtn"
                                class="w-full bg-green-600 text-white py-2 px-4 rounded-lg hover:bg-green-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed">
                            Generate Report
                        </button>
                    </div>
                </div>
                
                <!-- Progress Section -->
                <div id="progressSection" class="border-2 border-gray-200 rounded-lg p-5 mb-6 hidden">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-bold text-gray-800">Progress</h3>
                        <span id="statusBadge" class="px-3 py-1 rounded-full text-sm font-medium bg-gray-200 text-gray-700">
                            Idle
                        </span>
                    </div>
                    
                    <!-- Progress Bar -->
                    <div class="mb-3">
                        <div class="flex justify-between text-sm text-gray-600 mb-1">
                            <span id="currentTask">Waiting...</span>
                            <span><span id="progressCount">0</span> / <span id="totalCount">0</span></span>
                        </div>
                        <div class="w-full bg-gray-200 rounded-full h-3">
                            <div id="progressBar" class="bg-blue-600 h-3 rounded-full transition-all duration-300" style="width: 0%"></div>
                        </div>
                    </div>
                    
                    <!-- Error Display -->
                    <div id="errorDisplay" class="hidden bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg mb-3">
                        <span class="font-medium">Error:</span> <span id="errorMessage"></span>
                    </div>
                </div>
                
                <!-- Logs Section -->
                <div class="border-2 border-gray-200 rounded-lg p-5">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-bold text-gray-800">Logs</h3>
                        <button onclick="resetPipeline()" class="text-sm text-gray-500 hover:text-gray-700">
                            Clear / Reset
                        </button>
                    </div>
                    <div id="logsContainer" class="bg-gray-900 text-gray-100 p-4 rounded-lg font-mono text-xs h-48 overflow-y-auto">
                        <p class="text-gray-500">No logs yet. Start a pipeline step to see output.</p>
                    </div>
                </div>
                
                <!-- Refresh Data Button -->
                <div class="mt-6 text-center">
                    <button onclick="window.location.reload()" 
                            class="bg-gray-200 text-gray-700 py-2 px-6 rounded-lg hover:bg-gray-300 font-medium">
                        Reload Page to See New Data
                    </button>
                </div>
            </div>
        </div>

        {% for key, cat in categories.items() %}
        <div id="tab-{{ key }}" class="tab-content">
            <div class="bg-white rounded-lg shadow p-6 mb-6">
                <h2 class="text-2xl font-bold text-gray-800 mb-1">{{ cat.name }}</h2>
                <p class="text-gray-500 mb-4">{{ cat.description }}</p>
                
                {% set movies_list = data.get(key, []) %}
                {% if movies_list|length == 0 %}
                <div class="text-center py-12 text-gray-400">
                    <div class="text-5xl mb-3">-</div>
                    <p>No movies in this category</p>
                </div>
                {% else %}
                <div class="grid gap-4">
                    {% for movie in movies_list %}
                    <div class="movie-card bg-gray-50 rounded-lg p-4 border border-gray-200" 
                         data-movie-id="{{ movie.id }}"
                         data-source-tab="{{ key }}"
                         data-movie='{{ movie | tojson | safe }}'>
                        <div class="flex flex-col lg:flex-row lg:items-start gap-4">
                            <!-- Selection Button -->
                            <div class="flex flex-col items-center gap-2">
                                <button onclick="toggleMovieSelection(this, {{ movie.id }}, '{{ key }}')"
                                        class="select-btn w-10 h-10 rounded-full border-2 border-gray-300 
                                               hover:border-green-500 hover:bg-green-50 flex items-center justify-center
                                               transition-colors"
                                        data-movie-id="{{ movie.id }}">
                                    <svg class="w-5 h-5 text-gray-400 check-icon hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                                    </svg>
                                    <span class="plus-icon text-gray-400 text-xl leading-none">+</span>
                                </button>
                                <span class="text-xs text-gray-400">#{{ loop.index }}</span>
                            </div>

                            <!-- Poster Image -->
                            {% if movie.poster_url %}
                            <div class="flex-shrink-0">
                                <img src="{{ movie.poster_url }}" 
                                     alt="{{ movie.title }}" 
                                     class="w-20 h-28 object-cover rounded shadow-sm"
                                     loading="lazy"
                                     onerror="this.style.display='none'">
                            </div>
                            {% endif %}

                            <!-- Main Info -->
                            <div class="flex-1">
                                <div class="flex items-start gap-3 mb-2">
                                    <div>
                                        <h3 class="text-lg font-bold text-gray-800">{{ movie.title }}</h3>
                                        {% if movie.original_title and movie.original_title != movie.title %}
                                        <p class="text-sm text-gray-500 italic">{{ movie.original_title }}</p>
                                        {% endif %}
                                    </div>
                                </div>
                                
                                <div class="flex flex-wrap gap-2 mb-3 text-sm text-gray-600">
                                    <span class="bg-gray-200 px-2 py-0.5 rounded">{{ movie.director }}</span>
                                    <span class="bg-gray-200 px-2 py-0.5 rounded">{{ movie.year }}</span>
                                    <span class="bg-gray-200 px-2 py-0.5 rounded">{{ movie.duration_minutes }} min</span>
                                    <span class="bg-gray-200 px-2 py-0.5 rounded">{{ movie.language }}</span>
                                    {% if movie.copies_count %}
                                    <span class="bg-purple-100 text-purple-800 px-2 py-0.5 rounded">{{ movie.copies_count }} copies</span>
                                    {% endif %}
                                </div>

                                {% if movie.actors %}
                                <p class="text-sm text-gray-500 mb-2">
                                    <span class="font-medium">Cast:</span> {{ movie.actors }}
                                </p>
                                {% endif %}

                                <div class="flex flex-wrap gap-1 mb-2">
                                    {% for g in movie.genre.split(',') %}
                                    <span class="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded">{{ g.strip() }}</span>
                                    {% endfor %}
                                </div>
                            </div>

                            <!-- Ratings Column -->
                            <div class="lg:w-72">
                                <div class="mb-3">
                                    <div class="flex items-center gap-2 mb-2">
                                        <span class="text-lg font-bold px-3 py-1 rounded text-white {{ 'bg-green-500' if movie.calculated_score >= 7.5 else ('bg-yellow-500' if movie.calculated_score >= 6 else 'bg-orange-500') }}">
                                            {{ "%.1f"|format(movie.calculated_score) }}
                                        </span>
                                        <span class="text-sm text-gray-500">Calculated Score</span>
                                    </div>
                                </div>

                                <div class="grid grid-cols-2 gap-1 text-xs">
                                    {% for rating in movie.ratings %}
                                    <div class="flex items-center gap-1 bg-white p-1 rounded border">
                                        <span class="rating-badge text-white text-xs font-bold px-1.5 py-0.5 rounded {{ 'bg-green-500' if (rating.score / rating.max_score * 10) >= 7 else ('bg-yellow-500' if (rating.score / rating.max_score * 10) >= 5 else 'bg-red-500') }}">
                                            {{ "%.1f"|format(rating.score) }}
                                        </span>
                                        <span class="text-gray-600 truncate" title="{{ rating.source }}">{{ rating.source[:15] }}</span>
                                    </div>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>

                        <!-- Showtimes -->
                        {% if movie.showtimes %}
                        <div class="mt-4 pt-4 border-t border-gray-200">
                            <p class="text-sm font-medium text-gray-700 mb-2">Showtimes ({{ movie.showtimes|length }})</p>
                            <div class="flex flex-wrap gap-2">
                                {% for st in movie.showtimes[:6] %}
                                <a href="{{ st.booking_url }}" target="_blank" 
                                   class="showtime-pill bg-gradient-to-r from-blue-500 to-blue-600 text-white px-2 py-1 rounded-full hover:from-blue-600 hover:to-blue-700 transition-all">
                                    {{ st.cinema_name[:20] }} | {{ st.datetime[11:16] }} | {{ st.version }}
                                </a>
                                {% endfor %}
                                {% if movie.showtimes|length > 6 %}
                                <span class="showtime-pill bg-gray-300 text-gray-700 px-2 py-1 rounded-full">
                                    +{{ movie.showtimes|length - 6 }} more
                                </span>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>

    <script>
        // State management
        let selectedMovies = {}; // { category: [movieData, ...] }
        let currentExportCategory = 'featured';
        let panelOpen = false;

        // Initialize export categories
        const exportCategories = {{ export_categories | tojson | safe }};
        exportCategories.forEach(cat => selectedMovies[cat] = []);

        // Panel toggle
        document.getElementById('panelToggle').addEventListener('click', () => {
            panelOpen = !panelOpen;
            document.getElementById('selectionPanel').classList.toggle('open', panelOpen);
            document.getElementById('panelToggle').classList.toggle('shifted', panelOpen);
        });

        // Close panel
        function closePanel() {
            panelOpen = false;
            document.getElementById('selectionPanel').classList.remove('open');
            document.getElementById('panelToggle').classList.remove('shifted');
        }

        // Set export category
        function setExportCategory(category) {
            currentExportCategory = category;
            document.getElementById('currentExportCategory').textContent = category;
            
            // Update button styles
            document.querySelectorAll('.export-category-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.category === category);
            });
        }

        // Set initial category
        setExportCategory('featured');

        // Source tab display names
        const sourceTabNames = {
            'top_new_releases': 'New Releases',
            'current_landscape': 'Current',
            'premieres_events': 'Premieres',
            'old_classics': 'Classics',
            'letterboxd_picks': 'Letterboxd',
            'niche_gems': 'Niche Gems'
        };

        // Toggle movie selection
        function toggleMovieSelection(btnElement, movieId, sourceTab) {
            const card = btnElement.closest('.movie-card');
            const movieData = JSON.parse(card.dataset.movie);
            
            // Add source_tab to movie data
            movieData.source_tab = sourceTab;
            
            // Check if movie is already selected in current category
            const categoryMovies = selectedMovies[currentExportCategory];
            const existingIndex = categoryMovies.findIndex(m => m.id === movieId);
            
            if (existingIndex > -1) {
                // Remove from selection
                categoryMovies.splice(existingIndex, 1);
            } else {
                // Add to selection with source tab
                categoryMovies.push(movieData);
            }
            
            // Update ALL cards with this movie ID (movie can appear in multiple tabs)
            updateAllCardsForMovie(movieId);
            updateSelectionPanel();
            updateSelectionCount();
        }

        // Update ALL cards with a given movie ID (handles duplicates across tabs)
        function updateAllCardsForMovie(movieId) {
            const cards = document.querySelectorAll(`.movie-card[data-movie-id="${movieId}"]`);
            const isInAnyCategory = Object.values(selectedMovies).some(
                movies => movies.some(m => m.id === movieId)
            );
            
            cards.forEach(card => {
                const btn = card.querySelector('.select-btn');
                if (isInAnyCategory) {
                    card.classList.add('selected');
                    btn.classList.add('bg-green-500', 'border-green-500');
                    btn.querySelector('.check-icon').classList.remove('hidden');
                    btn.querySelector('.check-icon').classList.add('text-white');
                    btn.querySelector('.plus-icon').classList.add('hidden');
                } else {
                    card.classList.remove('selected');
                    btn.classList.remove('bg-green-500', 'border-green-500');
                    btn.querySelector('.check-icon').classList.add('hidden');
                    btn.querySelector('.plus-icon').classList.remove('hidden');
                }
            });
        }

        // Update selection count
        function updateSelectionCount() {
            const total = Object.values(selectedMovies).reduce((sum, arr) => sum + arr.length, 0);
            document.getElementById('selectionCount').textContent = total;
        }

        // Update selection panel
        function updateSelectionPanel() {
            const container = document.getElementById('selectedMoviesList');
            const hasAny = Object.values(selectedMovies).some(arr => arr.length > 0);
            
            if (!hasAny) {
                container.innerHTML = '<p class="text-gray-400 text-sm text-center py-8">No movies selected yet</p>';
                return;
            }

            let html = '';
            for (const [category, movies] of Object.entries(selectedMovies)) {
                if (movies.length === 0) continue;
                
                html += `
                    <div class="mb-4">
                        <h4 class="text-xs font-bold text-gray-500 uppercase mb-2">${category} (${movies.length})</h4>
                        <div class="space-y-2">
                `;
                
                for (const movie of movies) {
                    const sourceLabel = sourceTabNames[movie.source_tab] || movie.source_tab || '?';
                    html += `
                        <div class="flex items-center gap-2 bg-gray-50 p-2 rounded border text-sm">
                            <div class="flex-1 min-w-0">
                                <p class="font-medium text-gray-800 truncate">${movie.title}</p>
                                <p class="text-xs text-gray-500">
                                    ${movie.year} | ${movie.calculated_score.toFixed(1)}
                                    <span class="ml-1 px-1 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px]">${sourceLabel}</span>
                                </p>
                            </div>
                            <button onclick="removeFromCategory('${category}', ${movie.id})" 
                                    class="text-red-500 hover:text-red-700 p-1">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                            </button>
                        </div>
                    `;
                }
                
                html += '</div></div>';
            }
            
            container.innerHTML = html;
        }

        // Remove movie from specific category
        function removeFromCategory(category, movieId) {
            const movies = selectedMovies[category];
            const index = movies.findIndex(m => m.id === movieId);
            if (index > -1) {
                movies.splice(index, 1);
                updateAllCardsForMovie(movieId);
                updateSelectionPanel();
                updateSelectionCount();
            }
        }

        // Clear all selections
        function clearSelection() {
            const allMovieIds = new Set();
            Object.values(selectedMovies).forEach(movies => {
                movies.forEach(m => allMovieIds.add(m.id));
            });
            
            exportCategories.forEach(cat => selectedMovies[cat] = []);
            
            allMovieIds.forEach(id => updateAllCardsForMovie(id));
            updateSelectionPanel();
            updateSelectionCount();
        }

        // Export selection to JSON
        function exportSelection() {
            const hasAny = Object.values(selectedMovies).some(arr => arr.length > 0);
            if (!hasAny) {
                alert('No movies selected for export');
                return;
            }

            // Clean up the export (remove empty categories)
            const exportData = {};
            for (const [category, movies] of Object.entries(selectedMovies)) {
                if (movies.length > 0) {
                    exportData[category] = movies;
                }
            }

            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'newsletter_selection.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        // Tab switching logic
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
            });
        });

        // ============ PIPELINE FUNCTIONS ============
        let pipelinePolling = null;

        function startScraper() {
            fetch('/api/pipeline/scrape', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.error) {
                        alert(data.error);
                    } else {
                        startPolling();
                    }
                });
        }

        function startAnalysis() {
            fetch('/api/pipeline/analyze', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.error) {
                        alert(data.error);
                    } else {
                        startPolling();
                    }
                });
        }

        function resetPipeline() {
            fetch('/api/pipeline/reset', { method: 'POST' })
                .then(() => {
                    stopPolling();
                    updatePipelineUI({
                        status: 'idle',
                        progress: 0,
                        total: 0,
                        current_task: '',
                        logs: [],
                        error: null,
                        is_running: false
                    });
                    document.getElementById('logsContainer').innerHTML = 
                        '<p class="text-gray-500">No logs yet. Start a pipeline step to see output.</p>';
                    document.getElementById('progressSection').classList.add('hidden');
                });
        }

        function startPolling() {
            document.getElementById('progressSection').classList.remove('hidden');
            if (pipelinePolling) clearInterval(pipelinePolling);
            pipelinePolling = setInterval(fetchPipelineStatus, 1000);
            fetchPipelineStatus(); // Immediate first call
        }

        function stopPolling() {
            if (pipelinePolling) {
                clearInterval(pipelinePolling);
                pipelinePolling = null;
            }
        }

        function fetchPipelineStatus() {
            fetch('/api/pipeline/status')
                .then(r => r.json())
                .then(data => {
                    updatePipelineUI(data);
                    if (!data.is_running && (data.status === 'complete' || data.status === 'error')) {
                        stopPolling();
                    }
                });
        }

        function updatePipelineUI(state) {
            // Update buttons
            const scrapeBtn = document.getElementById('scrapeBtn');
            const analyzeBtn = document.getElementById('analyzeBtn');
            scrapeBtn.disabled = state.is_running;
            analyzeBtn.disabled = state.is_running;

            // Update status badge
            const badge = document.getElementById('statusBadge');
            const statusColors = {
                'idle': 'bg-gray-200 text-gray-700',
                'scraping': 'bg-blue-100 text-blue-800',
                'analyzing': 'bg-green-100 text-green-800',
                'complete': 'bg-green-500 text-white',
                'error': 'bg-red-500 text-white'
            };
            badge.className = `px-3 py-1 rounded-full text-sm font-medium ${statusColors[state.status] || statusColors.idle}`;
            badge.textContent = state.status.charAt(0).toUpperCase() + state.status.slice(1);

            // Update progress
            document.getElementById('currentTask').textContent = state.current_task || 'Waiting...';
            document.getElementById('progressCount').textContent = state.progress;
            document.getElementById('totalCount').textContent = state.total;
            
            const percent = state.total > 0 ? (state.progress / state.total * 100) : 0;
            document.getElementById('progressBar').style.width = percent + '%';
            
            // Update progress bar color based on status
            const bar = document.getElementById('progressBar');
            if (state.status === 'error') {
                bar.className = 'bg-red-500 h-3 rounded-full transition-all duration-300';
            } else if (state.status === 'complete') {
                bar.className = 'bg-green-500 h-3 rounded-full transition-all duration-300';
            } else if (state.status === 'analyzing') {
                bar.className = 'bg-green-600 h-3 rounded-full transition-all duration-300';
            } else {
                bar.className = 'bg-blue-600 h-3 rounded-full transition-all duration-300';
            }

            // Update error display
            const errorDisplay = document.getElementById('errorDisplay');
            if (state.error) {
                errorDisplay.classList.remove('hidden');
                document.getElementById('errorMessage').textContent = state.error;
            } else {
                errorDisplay.classList.add('hidden');
            }

            // Update logs
            if (state.logs && state.logs.length > 0) {
                const logsHtml = state.logs.map(log => `<div>${escapeHtml(log)}</div>`).join('');
                document.getElementById('logsContainer').innerHTML = logsHtml;
                // Auto-scroll to bottom
                const container = document.getElementById('logsContainer');
                container.scrollTop = container.scrollHeight;
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Check initial pipeline status on page load
        fetchPipelineStatus();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    data = load_data()
    return render_template_string(
        HTML_TEMPLATE, 
        data=data, 
        categories=CATEGORIES,
        export_categories=EXPORT_CATEGORIES
    )

# Pipeline API endpoints
@app.route('/api/pipeline/status')
def pipeline_status():
    """Get current pipeline status."""
    return jsonify(pipeline.get_state())

@app.route('/api/pipeline/scrape', methods=['POST'])
def start_scraper():
    """Start the movie scraper."""
    result = pipeline.run_scraper(output_file="data/week_full.json")
    return jsonify(result)

@app.route('/api/pipeline/analyze', methods=['POST'])
def start_analysis():
    """Start the analysis to generate newsletter data."""
    result = pipeline.run_analysis(
        input_file="data/week_full.json",
        output_file="data/newsletter_data.json"
    )
    return jsonify(result)

@app.route('/api/pipeline/reset', methods=['POST'])
def reset_pipeline():
    """Reset the pipeline state."""
    pipeline.reset()
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    print("Starting Newsletter Data Viewer...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000, use_reloader=False)
