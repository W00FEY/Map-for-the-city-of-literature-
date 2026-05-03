#!/usr/bin/env python3
"""Scrape events from cityofliterature.com.au and geocode their venues.

Output: data/events.json — list of events with location coords for the map.
Caches: data/.cache/venues.json so re-runs only geocode new venues.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE_DIR = DATA / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LIST_URL = "https://cityofliterature.com.au/wp-json/colit/v1/city_whatson_events"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Polite identification for both sites — Nominatim's policy requires it.
USER_AGENT = (
    "city-of-literature-map/1.0 (https://github.com/w00fey/"
    "map-for-the-city-of-literature-)"
)

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://cityofliterature.com.au/whats-on/",
}


def http_get(url: str, headers: dict | None = None, retries: int = 3) -> bytes:
    req_headers = {**BASE_HEADERS, **(headers or {})}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as exc:
            last_err = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed for {url}: {last_err}")


def fetch_list_page(page: int) -> dict:
    qs = urllib.parse.urlencode({"filter[current_page]": page})
    body = http_get(
        f"{LIST_URL}?{qs}",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    return json.loads(body.decode("utf-8"))


def parse_listing_html(snippet: str) -> list[dict]:
    """Pull the basic event tuples (url, title, date, organiser, blurb) from
    the listing fragment. Detail-page fetch fills in venue + coords."""
    cards = re.findall(r'<div class="event-card">(.*?)</div>\s*</div>', snippet, re.S)
    out: list[dict] = []
    for card in cards:
        link = re.search(
            r'<h2 class="event-title"><a href="([^"]+)"[^>]*>(.*?)</a></h2>', card, re.S
        )
        if not link:
            continue
        date = _inner(card, "event-date")
        organiser = _inner(card, "event-name")
        author = _inner(card, "event-author")
        blurb = _inner(card, "event-description")
        out.append({
            "url": html.unescape(link.group(1)).strip(),
            "title": _clean(link.group(2)),
            "dateLabel": _clean(date),
            "organiser": _clean(organiser),
            "author": _clean(author),
            "blurb": _clean(blurb),
        })
    return out


def _inner(card: str, cls: str) -> str:
    m = re.search(rf'<div class="{cls}">(.*?)</div>', card, re.S)
    return m.group(1) if m else ""


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_detail(url: str) -> dict | None:
    """Pull JSON-LD Event schema from a detail page."""
    body = http_get(url).decode("utf-8", errors="replace")
    blocks = re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', body, re.S
    )
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph") if isinstance(data, dict) else None
        if not graph:
            continue
        for node in graph:
            if node.get("@type") == "Event":
                return node
    return None


def address_string(loc: dict) -> str | None:
    """Compose a single-line address from a JSON-LD Place node, if usable."""
    if not loc:
        return None
    addr = loc.get("address") or {}
    parts = [
        addr.get("streetAddress"),
        addr.get("addressLocality"),
        addr.get("addressRegion"),
        addr.get("postalCode"),
        addr.get("addressCountry"),
    ]
    parts = [p for p in parts if p]
    if parts:
        return ", ".join(parts)
    name = loc.get("name")
    if name and name.strip().lower() not in {"", "online", "virtual"}:
        return f"{name}, Melbourne, Australia"
    return None


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def geocode(address: str, cache: dict) -> tuple[float, float] | None:
    if address in cache:
        cached = cache[address]
        if cached is None:
            return None
        return cached["lat"], cached["lon"]
    qs = urllib.parse.urlencode({
        "q": address,
        "format": "json",
        "limit": "1",
        "countrycodes": "au",
    })
    try:
        body = http_get(
            f"{NOMINATIM_URL}?{qs}",
            headers={"User-Agent": USER_AGENT, "Referer": ""},
        )
        results = json.loads(body)
    except Exception as exc:
        print(f"  geocode error for {address!r}: {exc}", file=sys.stderr)
        results = []
    # Nominatim usage policy: at most 1 req/sec.
    time.sleep(1.1)
    if not results:
        cache[address] = None
        return None
    hit = results[0]
    lat, lon = float(hit["lat"]), float(hit["lon"])
    cache[address] = {"lat": lat, "lon": lon, "display_name": hit.get("display_name")}
    return lat, lon


def main() -> int:
    detail_cache_path = CACHE_DIR / "details.json"
    geo_cache_path = CACHE_DIR / "venues.json"
    detail_cache: dict = load_json(detail_cache_path, {})
    geo_cache: dict = load_json(geo_cache_path, {})

    print("Fetching listing page 1…")
    first = fetch_list_page(1)
    max_page = int(first["data"]["max_page"])
    print(f"  {max_page} listing pages.")

    all_events: list[dict] = []
    listings = parse_listing_html(first["data"]["html"])
    all_events.extend(listings)
    for page in range(2, max_page + 1):
        print(f"Fetching listing page {page}/{max_page}…")
        try:
            data = fetch_list_page(page)
            all_events.extend(parse_listing_html(data["data"]["html"]))
        except Exception as exc:
            print(f"  page {page} failed: {exc}", file=sys.stderr)
        time.sleep(0.4)

    # De-dupe identical event URLs.
    seen: set[str] = set()
    unique: list[dict] = []
    for ev in all_events:
        if ev["url"] in seen:
            continue
        seen.add(ev["url"])
        unique.append(ev)
    print(f"{len(unique)} unique events.")

    enriched: list[dict] = []
    for i, ev in enumerate(unique, 1):
        url = ev["url"]
        print(f"[{i}/{len(unique)}] {ev['title'][:70]}")
        detail = detail_cache.get(url)
        if detail is None:
            try:
                detail = fetch_detail(url)
            except Exception as exc:
                print(f"  detail fetch failed: {exc}", file=sys.stderr)
                detail = {}
            detail_cache[url] = detail or {}
            time.sleep(0.3)
        loc = (detail or {}).get("location") or {}
        addr_text = address_string(loc)
        coords: tuple[float, float] | None = None
        if addr_text:
            coords = geocode(addr_text, geo_cache)

        enriched.append({
            **ev,
            "venueName": (loc.get("name") or "").strip() or None,
            "venueUrl": loc.get("url"),
            "address": addr_text,
            "startDate": (detail or {}).get("startDate"),
            "endDate": (detail or {}).get("endDate"),
            "lat": coords[0] if coords else None,
            "lon": coords[1] if coords else None,
        })

        # Persist caches every 20 events so partial runs aren't lost.
        if i % 20 == 0:
            save_json(detail_cache_path, detail_cache)
            save_json(geo_cache_path, geo_cache)

    save_json(detail_cache_path, detail_cache)
    save_json(geo_cache_path, geo_cache)
    save_json(DATA / "events.json", {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://cityofliterature.com.au/whats-on/",
        "events": enriched,
    })

    placed = sum(1 for e in enriched if e["lat"] is not None)
    print(f"Done. {placed}/{len(enriched)} events have coordinates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
