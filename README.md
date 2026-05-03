# Melbourne City of Literature — Events Map

An unofficial map of literary events listed at
[cityofliterature.com.au/whats-on](https://cityofliterature.com.au/whats-on/).
A Python scraper pulls every event from the site's public API, extracts the
JSON-LD venue schema from each detail page, geocodes the venue with Nominatim,
and writes `data/events.json`. A static front-end (`index.html` + Leaflet)
renders the events as markers with a searchable sidebar.

## Run it locally

Generate the data, then serve the directory with any static file server:

```sh
python3 scripts/scrape.py            # ~5–10 minutes (rate-limited geocoding)
python3 -m http.server 8000          # then open http://localhost:8000
```

The scraper caches detail-page HTML and geocoding results under
`data/.cache/`, so re-runs are fast and only hit Nominatim for new venues.

## Files

- `index.html`, `assets/style.css`, `assets/app.js` — static map UI (Leaflet
  + MarkerCluster, OpenStreetMap tiles).
- `scripts/scrape.py` — fetches events, parses JSON-LD, geocodes, writes
  `data/events.json`.
- `data/events.json` — generated event list with coordinates.

## Attribution

Event content © the respective organisers, aggregated by Melbourne UNESCO City
of Literature. Map tiles © OpenStreetMap contributors. Geocoding by Nominatim.
