const fs = require('fs');
const ejs = require('ejs');

// --- CONFIGURATION ---
// Logo URLs from Mailjet gallery
const LOGO_MAP = {
    "IMDB": "https://upload.wikimedia.org/wikipedia/commons/6/69/IMDB_Logo_2016.svg",
    "Allociné": "https://1lig1.mjt.lu/img2/1lig1/7d6127a0-473b-4cf3-84f3-7cdbbbaca01f/content",
    "Allociné (Presse)": "https://1lig1.mjt.lu/img2/1lig1/7d6127a0-473b-4cf3-84f3-7cdbbbaca01f/content",
    "Allociné (Spectateurs)": "https://1lig1.mjt.lu/img2/1lig1/7d6127a0-473b-4cf3-84f3-7cdbbbaca01f/content",
    "SensCritique": "https://1lig1.mjt.lu/img2/1lig1/7018f379-ccaa-4f84-a9e7-6de35be3aca1/content",
    "Letterboxd": "https://1lig1.mjt.lu/img2/1lig1/acf0a4e5-df04-4865-8a94-361bfde2bf1e/content",
    "Rotten Tomatoes": "https://upload.wikimedia.org/wikipedia/commons/5/5b/Rotten_Tomatoes.svg",
    "Télérama": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/T%C3%A9l%C3%A9rama_logo.svg/1200px-T%C3%A9l%C3%A9rama_logo.svg.png",
    "Default": "https://cdn-icons-png.flaticon.com/512/1828/1828884.png" // Star icon
};

// Sorting functions for each section type (logic stays in code, text comes from JSON)
const SORT_FUNCTIONS = {
    "top_new_releases": (a, b) => (b.copies_count || 0) - (a.copies_count || 0), // Most copies first
    "current_landscape": (a, b) => (b.copies_count || 0) - (a.copies_count || 0), // Most copies first
    "premieres_events": (a, b) => new Date(a.release_date) - new Date(b.release_date), // Earliest premiere first
    "old_classics": (a, b) => (a.year || 9999) - (b.year || 9999), // Oldest first
    "letterboxd_picks": (a, b) => {
        const ratingA = a.ratings?.find(r => r.source === "Letterboxd")?.score || 0;
        const ratingB = b.ratings?.find(r => r.source === "Letterboxd")?.score || 0;
        return ratingB - ratingA; // Highest Letterboxd rating first
    },
    "niche_gems": (a, b) => (b.calculated_score || 0) - (a.calculated_score || 0) // Best score first
};

// --- HELPER FUNCTIONS ---

// 1. Process Showtimes: Find the main cinema and summarize the rest
function processShowtimes(showtimes) {
    if (!showtimes || showtimes.length === 0) return { main: null, summary: "Aucune séance prévue." };

    // Group by Cinema
    const cinemaCounts = {};
    showtimes.forEach(s => {
        if (!cinemaCounts[s.cinema_name]) cinemaCounts[s.cinema_name] = 0;
        cinemaCounts[s.cinema_name]++;
    });

    // Sort cinemas by number of screenings (descending)
    const sortedCinemas = Object.keys(cinemaCounts).sort((a, b) => cinemaCounts[b] - cinemaCounts[a]);

    const mainCinema = sortedCinemas[0];
    const mainCount = cinemaCounts[mainCinema];
    
    // Calculate remainder
    const totalCinemas = sortedCinemas.length;
    const otherCinemasCount = totalCinemas - 1;
    const totalScreenings = showtimes.length;
    const otherScreeningsCount = totalScreenings - mainCount;

    let summaryText = "";
    if (otherCinemasCount > 0) {
        const s_cinemas = otherCinemasCount > 1 ? 's' : '';
        const s_seances = otherScreeningsCount > 1 ? 's' : '';
        summaryText = `+ ${otherCinemasCount} autre${s_cinemas} cinéma${s_cinemas} (${otherScreeningsCount} séance${s_seances})`;
    }

    return {
        main_cinema: mainCinema,
        main_count: mainCount,
        remainder_text: summaryText
    };
}

// 2. Map Logo URLs to ratings and format Allocine ratings
function processRatings(ratings) {
    if (!ratings) return [];
    return ratings.map(r => {
        // Determine short label for Allocine ratings
        let shortLabel = null;
        if (r.source === "Allociné (Presse)") {
            shortLabel = "Presse";
        } else if (r.source === "Allociné (Spectateurs)") {
            shortLabel = "Spectateurs";
        }
        
        return {
            ...r,
            logo_url: LOGO_MAP[r.source] || LOGO_MAP["Default"],
            short_label: shortLabel
        };
    });
}

// 3. Reorganize movies by source_tab into sections
function reorganizeBySourceTab(moviesData, sectionsConfig) {
    const sections = {};
    
    // Collect all movies from all categories
    const allMovies = [];
    Object.keys(moviesData).forEach(category => {
        moviesData[category].forEach(movie => {
            allMovies.push(movie);
        });
    });
    
    // Group by source_tab
    allMovies.forEach(movie => {
        const tab = movie.source_tab || "other";
        if (!sections[tab]) {
            sections[tab] = [];
        }
        sections[tab].push(movie);
    });
    
    // Sort each section according to its sort function
    Object.keys(sections).forEach(tab => {
        const sortFn = SORT_FUNCTIONS[tab];
        if (sortFn) {
            sections[tab].sort(sortFn);
        }
    });
    
    // Return sections in configured order (from text_content.json)
    const orderedSections = {};
    Object.keys(sectionsConfig)
        .sort((a, b) => (sectionsConfig[a].order || 99) - (sectionsConfig[b].order || 99))
        .forEach(tab => {
            if (sections[tab] && sections[tab].length > 0) {
                orderedSections[tab] = sections[tab];
            }
        });
    
    // Add any remaining sections not in config
    Object.keys(sections).forEach(tab => {
        if (!orderedSections[tab] && sections[tab].length > 0) {
            orderedSections[tab] = sections[tab];
        }
    });
    
    return orderedSections;
}

// --- MAIN EXECUTION ---

// Read from movies.json if it exists and has source_tab, otherwise fallback to parent newsletter_selection.json
let moviesRaw;
const moviesJsonPath = 'movies.json';
const selectionJsonPath = '../data/newsletter_selection.json';

if (fs.existsSync(moviesJsonPath)) {
    moviesRaw = JSON.parse(fs.readFileSync(moviesJsonPath, 'utf8'));
    // Check if source_tab exists in the first movie of any category
    const firstCategory = Object.keys(moviesRaw)[0];
    if (firstCategory && moviesRaw[firstCategory][0] && !moviesRaw[firstCategory][0].source_tab) {
        // movies.json doesn't have source_tab, try newsletter_selection.json
        if (fs.existsSync(selectionJsonPath)) {
            console.log('Using newsletter_selection.json (source_tab found there)');
            moviesRaw = JSON.parse(fs.readFileSync(selectionJsonPath, 'utf8'));
        }
    }
} else if (fs.existsSync(selectionJsonPath)) {
    moviesRaw = JSON.parse(fs.readFileSync(selectionJsonPath, 'utf8'));
} else {
    throw new Error('No movies data file found');
}
const textData = JSON.parse(fs.readFileSync('text_content.json', 'utf8'));

// Get sections config from text_content.json
const sectionsConfig = textData.sections || {};

// Reorganize movies by source_tab
const sectionedMovies = reorganizeBySourceTab(moviesRaw, sectionsConfig);

// Process each movie with UI helpers
Object.keys(sectionedMovies).forEach(sectionKey => {
    sectionedMovies[sectionKey] = sectionedMovies[sectionKey].map(movie => {
        movie.ui_showtimes = processShowtimes(movie.showtimes);
        movie.ui_ratings = processRatings(movie.ratings);
        return movie;
    });
});

const template = fs.readFileSync('template.ejs', 'utf8');

const html = ejs.render(template, { 
    sections: sectionedMovies,
    sectionsConfig: sectionsConfig,
    text: textData 
});

fs.writeFileSync('output/newsletter_output_v2.html', html);
console.log('Version 2 Generated: output/newsletter_output_v2.html');