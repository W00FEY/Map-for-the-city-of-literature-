# Adelaide City of Literature – Events Map

An interactive map showing all upcoming events from [cityofliterature.com.au/whats-on/](https://cityofliterature.com.au/whats-on/).

## How it works

```
scraper/scraper.py   →   events.json   →   index.html (Leaflet map)
```

1. **Scraper** – Python + Playwright headless browser fetches the events listing page(s), visits each event detail page to grab the venue address, then geocodes addresses via [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap). Results are saved to `events.json`.
2. **Map** – A static HTML/CSS/JS page using [Leaflet.js](https://leafletjs.com/) reads `events.json` and renders pins on an OpenStreetMap base layer. Markers are clustered for readability.
3. **Automation** – A GitHub Actions workflow re-runs the scraper daily and commits updated `events.json` back to the repo. A second workflow deploys the site to GitHub Pages.

---

## Local setup

### Run the scraper

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
python scraper.py
```

This writes `events.json` to the project root.

### View the map locally

Serve the project root with any static server (browsers block `fetch()` for local `file://` URLs):

```bash
# Python
python -m http.server 8080

# Node
npx serve .

# VS Code Live Server extension also works
```

Then open http://localhost:8080.

---

## GitHub Pages deployment

1. Push to GitHub.
2. Go to **Settings → Pages** and set the source to **GitHub Actions**.
3. The `deploy.yml` workflow will publish the site automatically on every push.

### Auto-refresh events data

The `scrape.yml` workflow runs daily at 06:00 UTC. You can also trigger it manually from the **Actions** tab. It commits a fresh `events.json` which then triggers a re-deploy.

---

## Project structure

```
├── index.html              # Map page
├── style.css               # Styles (dark theme)
├── app.js                  # Leaflet map logic
├── events.json             # Scraped event data (auto-updated)
├── scraper/
│   ├── scraper.py          # Playwright scraper + Nominatim geocoder
│   ├── requirements.txt
│   └── .geocode_cache.json # Cached geocode results (auto-generated)
└── .github/workflows/
    ├── scrape.yml          # Daily scrape job
    └── deploy.yml          # GitHub Pages deploy
```

### events.json schema

```jsonc
[
  {
    "title": "Event Name",
    "url": "https://cityofliterature.com.au/event/...",
    "date": "2025-06-14T18:00:00",   // ISO 8601 or plain text
    "date_end": "",
    "image": "https://...",
    "description": "Short excerpt…",
    "venue_name": "Adelaide Town Hall",
    "venue_address": "128 King William St, Adelaide SA 5000",
    "lat": -34.9285,
    "lng": 138.6007
  }
]
```

---

## Tech stack

| Layer | Tool |
|---|---|
| Scraping | [Playwright](https://playwright.dev/python/) (Chromium) |
| Geocoding | [Nominatim](https://nominatim.openstreetmap.org/) (free, no key) |
| Map | [Leaflet.js](https://leafletjs.com/) + [MarkerCluster](https://github.com/Leaflet/Leaflet.markercluster) |
| Tiles | [OpenStreetMap](https://www.openstreetmap.org/) |
| Hosting | GitHub Pages |
| CI | GitHub Actions |
