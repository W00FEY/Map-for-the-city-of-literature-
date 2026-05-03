/* ── Config ─────────────────────────────────────────────────── */
const EVENTS_JSON = "events.json";

// Adelaide CBD
const DEFAULT_CENTER = [-34.9285, 138.6007];
const DEFAULT_ZOOM   = 13;

/* ── Map init ───────────────────────────────────────────────── */
const map = L.map("map", {
  center: DEFAULT_CENTER,
  zoom: DEFAULT_ZOOM,
  zoomControl: true,
});

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

/* ── Custom marker icon ─────────────────────────────────────── */
const pinIcon = L.divIcon({
  className: "",
  html: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">
    <path fill="#e8c96b" stroke="#0f1117" stroke-width="1.5"
      d="M14 1C7.373 1 2 6.373 2 13c0 9.5 12 22 12 22S26 22.5 26 13C26 6.373 20.627 1 14 1z"/>
    <circle cx="14" cy="13" r="5" fill="#0f1117"/>
  </svg>`,
  iconSize: [28, 36],
  iconAnchor: [14, 36],
  popupAnchor: [0, -38],
});

/* ── Cluster group ──────────────────────────────────────────── */
const clusterGroup = L.markerClusterGroup({
  maxClusterRadius: 50,
  spiderfyOnMaxZoom: true,
  showCoverageOnHover: false,
});
map.addLayer(clusterGroup);

/* ── State ──────────────────────────────────────────────────── */
let allEvents   = [];
let markers     = [];   // parallel to allEvents
let activeIndex = -1;

/* ── DOM refs ───────────────────────────────────────────────── */
const eventList   = document.getElementById("event-list");
const statsText   = document.getElementById("stats-text");
const searchInput = document.getElementById("search");
const dateInput   = document.getElementById("filter-date");
const btnClearDate = document.getElementById("btn-clear-date");
const btnFit      = document.getElementById("btn-fit");
const emptyState  = document.getElementById("empty-state");

/* ── Helpers ────────────────────────────────────────────────── */
function formatDate(raw) {
  if (!raw) return "";
  // ISO datetime
  const d = new Date(raw);
  if (!isNaN(d)) {
    return d.toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  }
  return raw;
}

function parseEventDate(raw) {
  if (!raw) return null;
  const d = new Date(raw);
  return isNaN(d) ? null : d;
}

function makePopupHTML(ev) {
  return `
    <div class="popup-content">
      ${ev.image ? `<img class="popup-img" src="${ev.image}" alt="" loading="lazy" onerror="this.style.display='none'">` : ""}
      <div class="popup-title">${ev.title}</div>
      ${ev.date ? `<div class="popup-date">📅 ${formatDate(ev.date)}</div>` : ""}
      ${ev.venue_name ? `<div class="popup-venue">📍 ${ev.venue_name}</div>` : ""}
      ${ev.description ? `<div class="popup-desc">${ev.description}</div>` : ""}
      ${ev.url ? `<a class="popup-link" href="${ev.url}" target="_blank" rel="noopener">More info →</a>` : ""}
    </div>`;
}

function makeListItem(ev, index) {
  const li = document.createElement("li");
  li.className = "event-item" + (ev.lat == null ? " no-coords" : "");
  li.dataset.index = index;

  const thumb = ev.image
    ? `<img class="event-thumb" src="${ev.image}" alt="" loading="lazy" onerror="this.closest('.event-item').querySelector('.event-thumb').style.display='none'">`
    : `<div class="event-thumb-placeholder">📖</div>`;

  li.innerHTML = `
    ${thumb}
    <div class="event-info">
      <div class="event-title">${ev.title}</div>
      ${ev.date ? `<div class="event-date">${formatDate(ev.date)}</div>` : ""}
      ${ev.venue_name ? `<div class="event-venue">📍 ${ev.venue_name}</div>` : ""}
      ${ev.lat == null ? `<div class="event-no-location">Location not mapped</div>` : ""}
    </div>`;

  if (ev.lat != null) {
    li.addEventListener("click", () => activateEvent(index));
  }

  return li;
}

/* ── Activate / deactivate ──────────────────────────────────── */
function activateEvent(index) {
  // Deactivate previous
  if (activeIndex >= 0) {
    const prev = eventList.querySelector(`[data-index="${activeIndex}"]`);
    if (prev) prev.classList.remove("active");
  }

  activeIndex = index;
  const ev = allEvents[index];
  const marker = markers[index];

  // Highlight list item
  const li = eventList.querySelector(`[data-index="${index}"]`);
  if (li) {
    li.classList.add("active");
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Pan map and open popup
  if (marker) {
    // Ensure marker is visible (it may be in a cluster)
    clusterGroup.zoomToShowLayer(marker, () => {
      marker.openPopup();
    });
    map.setView([ev.lat, ev.lng], Math.max(map.getZoom(), 15), { animate: true });
  }
}

/* ── Filter logic ───────────────────────────────────────────── */
function getFilteredEvents() {
  const q    = searchInput.value.trim().toLowerCase();
  const from = dateInput.value ? new Date(dateInput.value) : null;

  return allEvents.map((ev, i) => {
    let visible = true;
    if (q && !ev.title.toLowerCase().includes(q) &&
              !ev.venue_name.toLowerCase().includes(q) &&
              !ev.description.toLowerCase().includes(q)) {
      visible = false;
    }
    if (from) {
      const d = parseEventDate(ev.date);
      if (!d || d < from) visible = false;
    }
    return { ev, i, visible };
  });
}

function applyFilters() {
  const filtered = getFilteredEvents();
  const visible  = filtered.filter(x => x.visible);

  // Clear and rebuild list
  eventList.innerHTML = "";

  visible.forEach(({ ev, i }) => {
    eventList.appendChild(makeListItem(ev, i));
  });

  // Show/hide markers
  clusterGroup.clearLayers();
  visible.forEach(({ ev, i }) => {
    if (markers[i]) clusterGroup.addLayer(markers[i]);
  });

  // Stats
  const withCoords = visible.filter(x => x.ev.lat != null).length;
  statsText.textContent = `${visible.length} event${visible.length !== 1 ? "s" : ""} · ${withCoords} mapped`;

  // Active state
  if (activeIndex >= 0 && !visible.find(x => x.i === activeIndex)) {
    activeIndex = -1;
  }
}

/* ── Fit bounds ─────────────────────────────────────────────── */
btnFit.addEventListener("click", () => {
  const pts = allEvents.filter(e => e.lat != null).map(e => [e.lat, e.lng]);
  if (pts.length === 0) return;
  if (pts.length === 1) { map.setView(pts[0], 15); return; }
  map.fitBounds(L.latLngBounds(pts), { padding: [40, 40] });
});

/* ── Search / filter events ─────────────────────────────────── */
searchInput.addEventListener("input", applyFilters);
dateInput.addEventListener("change", applyFilters);
btnClearDate.addEventListener("click", () => { dateInput.value = ""; applyFilters(); });

/* ── Load data ──────────────────────────────────────────────── */
async function loadEvents() {
  let data;
  try {
    const res = await fetch(EVENTS_JSON);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    console.error("Failed to load events.json:", err);
    statsText.textContent = "Failed to load events";
    showEmptyState();
    return;
  }

  if (!Array.isArray(data) || data.length === 0) {
    statsText.textContent = "No events found";
    showEmptyState();
    return;
  }

  allEvents = data;

  // Build markers (once, for all events)
  markers = allEvents.map((ev, i) => {
    if (ev.lat == null || ev.lng == null) return null;

    const m = L.marker([ev.lat, ev.lng], { icon: pinIcon });
    m.bindPopup(makePopupHTML(ev), { maxWidth: 280 });
    m.on("click", () => activateEvent(i));
    return m;
  });

  applyFilters();

  // Initial fit
  const pts = allEvents.filter(e => e.lat != null).map(e => [e.lat, e.lng]);
  if (pts.length === 1) {
    map.setView(pts[0], 15);
  } else if (pts.length > 1) {
    map.fitBounds(L.latLngBounds(pts), { padding: [40, 40] });
  }
}

function showEmptyState() {
  const empty = document.createElement("li");
  empty.id = "empty-state";
  empty.innerHTML = `
    <h3>No events loaded</h3>
    <p>Run the scraper to populate event data:</p>
    <code>cd scraper && pip install -r requirements.txt && playwright install chromium && python scraper.py</code>
  `;
  empty.style.display = "block";
  empty.style.listStyle = "none";
  empty.style.padding = "32px 20px";
  empty.style.textAlign = "center";
  empty.style.color = "#7a7e96";
  eventList.appendChild(empty);
}

loadEvents();
