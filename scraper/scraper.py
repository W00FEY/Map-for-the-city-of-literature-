"""
Scraper for City of Literature events (cityofliterature.com.au/whats-on/)

Uses Playwright to render JavaScript and bypass bot detection.
Geocodes venue addresses via Nominatim (OpenStreetMap, no API key needed).
Outputs events.json in the project root.

Usage:
    pip install -r requirements.txt
    playwright install chromium
    python scraper.py
"""

import asyncio
import json
import time
import re
import os
from pathlib import Path
from urllib.parse import urljoin, urlencode
import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


BASE_URL = "https://cityofliterature.com.au"
EVENTS_URL = f"{BASE_URL}/whats-on/"
OUTPUT_FILE = Path(__file__).parent.parent / "events.json"
GEOCODE_CACHE_FILE = Path(__file__).parent / ".geocode_cache.json"

# Nominatim rate limit: 1 request per second
GEOCODE_DELAY = 1.1


def load_geocode_cache() -> dict:
    if GEOCODE_CACHE_FILE.exists():
        return json.loads(GEOCODE_CACHE_FILE.read_text())
    return {}


def save_geocode_cache(cache: dict):
    GEOCODE_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def geocode(address: str, cache: dict) -> tuple[float, float] | None:
    """Return (lat, lng) for an address using Nominatim, with caching."""
    if not address or address.strip() == "":
        return None

    key = address.strip().lower()
    if key in cache:
        return cache[key]

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "au",
    }
    url = f"https://nominatim.openstreetmap.org/search?{urlencode(params)}"
    headers = {"User-Agent": "CityOfLiteratureEventsMap/1.0 (github.com/w00fey/map-for-the-city-of-literature-)"}

    try:
        time.sleep(GEOCODE_DELAY)
        resp = httpx.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            cache[key] = [lat, lng]
            save_geocode_cache(cache)
            return [lat, lng]
    except Exception as e:
        print(f"  Geocode failed for '{address}': {e}")

    cache[key] = None
    save_geocode_cache(cache)
    return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


async def scrape_event_detail(page, url: str) -> dict:
    """Visit an event page and extract venue/address details."""
    details = {"venue_name": "", "venue_address": "", "organizer": ""}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)

        # The Events Calendar plugin uses these selectors
        selectors = {
            "venue_name": [
                ".tribe-venue",
                ".tribe-venue-name",
                ".tribe-events-single-section .tribe-venue",
                "[class*='venue-name']",
                "[class*='venue'] h2",
                "[class*='venue'] h3",
            ],
            "venue_address": [
                ".tribe-venue-location address",
                ".tribe-events-venue-details address",
                ".tribe-venue address",
                "[class*='venue-address']",
                "[class*='venue-location']",
                ".tribe-address",
            ],
        }

        for field, sel_list in selectors.items():
            for sel in sel_list:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        text = clean_text(await el.inner_text())
                        if text:
                            details[field] = text
                            break
                except Exception:
                    continue

        # Fallback: look for structured data
        try:
            ld_json = await page.query_selector('script[type="application/ld+json"]')
            if ld_json:
                raw = await ld_json.inner_text()
                data = json.loads(raw)
                if isinstance(data, list):
                    data = data[0]
                location = data.get("location", {})
                if not details["venue_name"]:
                    details["venue_name"] = location.get("name", "")
                if not details["venue_address"]:
                    addr = location.get("address", {})
                    if isinstance(addr, str):
                        details["venue_address"] = addr
                    elif isinstance(addr, dict):
                        parts = [
                            addr.get("streetAddress", ""),
                            addr.get("addressLocality", ""),
                            addr.get("addressRegion", ""),
                            addr.get("postalCode", ""),
                        ]
                        details["venue_address"] = ", ".join(p for p in parts if p)
        except Exception:
            pass

    except PlaywrightTimeout:
        print(f"  Timeout loading detail page: {url}")
    except Exception as e:
        print(f"  Error loading detail page {url}: {e}")

    return details


async def scrape_events_page(page, url: str) -> list[dict]:
    """Scrape all event cards from a listing page."""
    events = []

    print(f"Loading: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except PlaywrightTimeout:
        print("  Timeout loading events page")
        return events

    # Try multiple selectors for event cards (The Events Calendar plugin patterns)
    card_selectors = [
        ".tribe-event",
        ".tribe-events-calendar-list__event",
        ".tribe-common-g-col",
        "article.tribe-event",
        ".type-tribe_events",
        "[class*='event-card']",
        "[class*='event-item']",
        "article[class*='event']",
        ".events-list article",
        ".event",
    ]

    cards = []
    for sel in card_selectors:
        cards = await page.query_selector_all(sel)
        if cards:
            print(f"  Found {len(cards)} events with selector: {sel}")
            break

    if not cards:
        # Try to get any links that look like event URLs
        print("  No card selectors matched, trying link extraction...")
        all_links = await page.query_selector_all("a[href*='/event/'], a[href*='/events/']")
        print(f"  Found {len(all_links)} event links")
        for link in all_links:
            href = await link.get_attribute("href")
            text = clean_text(await link.inner_text())
            if href and text:
                events.append({
                    "title": text,
                    "url": urljoin(BASE_URL, href),
                    "date": "",
                    "date_end": "",
                    "image": "",
                    "description": "",
                    "venue_name": "",
                    "venue_address": "",
                    "lat": None,
                    "lng": None,
                })
        return events

    for card in cards:
        event = {
            "title": "",
            "url": "",
            "date": "",
            "date_end": "",
            "image": "",
            "description": "",
            "venue_name": "",
            "venue_address": "",
            "lat": None,
            "lng": None,
        }

        # Title
        for sel in [".tribe-event-url", ".tribe-events-calendar-list__event-title-link",
                    "h2 a", "h3 a", ".event-title a", "[class*='title'] a", "a"]:
            try:
                el = await card.query_selector(sel)
                if el:
                    t = clean_text(await el.inner_text())
                    if t:
                        event["title"] = t
                        href = await el.get_attribute("href")
                        if href:
                            event["url"] = urljoin(BASE_URL, href)
                        break
            except Exception:
                continue

        # Date
        for sel in [".tribe-event-date-start", ".tribe-events-calendar-list__event-datetime",
                    "time", "[class*='date']", "[class*='datetime']"]:
            try:
                el = await card.query_selector(sel)
                if el:
                    dt = await el.get_attribute("datetime") or clean_text(await el.inner_text())
                    if dt:
                        event["date"] = dt
                        break
            except Exception:
                continue

        # Image
        for sel in ["img", "[class*='image'] img", "[class*='thumbnail'] img"]:
            try:
                el = await card.query_selector(sel)
                if el:
                    src = await el.get_attribute("src") or await el.get_attribute("data-src")
                    if src:
                        event["image"] = urljoin(BASE_URL, src)
                        break
            except Exception:
                continue

        # Description/excerpt
        for sel in [".tribe-events-calendar-list__event-description",
                    "[class*='excerpt']", "[class*='description']", "p"]:
            try:
                el = await card.query_selector(sel)
                if el:
                    t = clean_text(await el.inner_text())
                    if t and len(t) > 20:
                        event["description"] = t
                        break
            except Exception:
                continue

        # Venue on card
        for sel in [".tribe-events-calendar-list__event-venue",
                    "[class*='venue']", "[class*='location']"]:
            try:
                el = await card.query_selector(sel)
                if el:
                    t = clean_text(await el.inner_text())
                    if t:
                        event["venue_name"] = t
                        break
            except Exception:
                continue

        if event["title"]:
            events.append(event)

    return events


async def get_next_page_url(page) -> str | None:
    """Find the 'next page' link on a listing page."""
    for sel in [
        ".tribe-events-nav-next a",
        ".tribe-events-c-nav__next",
        "[class*='next'] a",
        "a[rel='next']",
        ".pagination .next a",
        "a:has-text('Next')",
        "a:has-text('›')",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                href = await el.get_attribute("href")
                if href:
                    return urljoin(BASE_URL, href)
        except Exception:
            continue
    return None


async def main():
    geocode_cache = load_geocode_cache()
    all_events = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-AU",
        )
        page = await context.new_page()

        # Scrape all listing pages
        current_url = EVENTS_URL
        seen_urls = set()
        page_num = 1

        while current_url and current_url not in seen_urls:
            seen_urls.add(current_url)
            events = await scrape_events_page(page, current_url)
            all_events.extend(events)
            print(f"  Page {page_num}: collected {len(events)} events (total: {len(all_events)})")

            next_url = await get_next_page_url(page)
            if next_url == current_url or next_url in seen_urls:
                break
            current_url = next_url
            page_num += 1

        # Fetch detail pages for events missing venue info
        print(f"\nFetching detail pages for {len(all_events)} events...")
        for i, event in enumerate(all_events):
            if event["url"] and (not event["venue_name"] or not event["venue_address"]):
                print(f"  [{i+1}/{len(all_events)}] {event['title'][:60]}")
                details = await scrape_event_detail(page, event["url"])
                if details["venue_name"]:
                    event["venue_name"] = details["venue_name"]
                if details["venue_address"]:
                    event["venue_address"] = details["venue_address"]
                await asyncio.sleep(0.5)

        await browser.close()

    # Geocode all events
    print(f"\nGeocoding {len(all_events)} events...")
    for i, event in enumerate(all_events):
        address = event.get("venue_address") or event.get("venue_name")
        if not address:
            continue
        # Append Adelaide/Australia if not already specific
        if "australia" not in address.lower() and "south australia" not in address.lower():
            address = f"{address}, Adelaide, South Australia, Australia"
        coords = geocode(address, geocode_cache)
        if coords:
            event["lat"] = coords[0]
            event["lng"] = coords[1]
            print(f"  [{i+1}] {event['title'][:50]} → {coords[0]:.4f}, {coords[1]:.4f}")
        else:
            print(f"  [{i+1}] {event['title'][:50]} → no geocode result")

    # Write output
    OUTPUT_FILE.write_text(json.dumps(all_events, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(all_events)} events to {OUTPUT_FILE}")
    geocoded = sum(1 for e in all_events if e["lat"] is not None)
    print(f"Geocoded: {geocoded}/{len(all_events)}")


if __name__ == "__main__":
    asyncio.run(main())
