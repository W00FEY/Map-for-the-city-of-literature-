/* Melbourne City of Literature events map.
   Loads data/events.json (built by scripts/scrape.py) and renders markers
   on a Leaflet map with a synced sidebar list. */

const MELBOURNE = [-37.8136, 144.9631];
const map = L.map("map", { zoomControl: true }).setView(MELBOURNE, 13);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const cluster = L.markerClusterGroup({
  showCoverageOnHover: false,
  spiderfyOnMaxZoom: true,
  maxClusterRadius: 45,
});
map.addLayer(cluster);

const els = {
  list: document.getElementById("event-list"),
  search: document.getElementById("search"),
  hideUnmapped: document.getElementById("hide-unmapped"),
  count: document.getElementById("event-count"),
  generated: document.getElementById("generated-at"),
};

const state = {
  events: [],
  markersByIndex: new Map(),
  activeIndex: null,
};

fetch("data/events.json", { cache: "no-cache" })
  .then((r) => {
    if (!r.ok) throw new Error("events.json not found — run scripts/scrape.py first");
    return r.json();
  })
  .then((payload) => {
    state.events = payload.events || [];
    if (payload.generatedAt) {
      const d = new Date(payload.generatedAt);
      els.generated.textContent = "updated " + d.toLocaleString();
    } else {
      els.generated.textContent = "";
    }
    buildMarkers();
    render();
  })
  .catch((err) => {
    els.list.innerHTML = `<li class="empty">Could not load events: ${escapeHtml(err.message)}</li>`;
    els.count.textContent = "0 events";
  });

function buildMarkers() {
  state.events.forEach((ev, idx) => {
    if (ev.lat == null || ev.lon == null) return;
    const marker = L.marker([ev.lat, ev.lon]);
    marker.bindPopup(popupHtml(ev), { maxWidth: 320 });
    marker.on("click", () => {
      setActive(idx, { pan: false });
    });
    state.markersByIndex.set(idx, marker);
    cluster.addLayer(marker);
  });
}

function popupHtml(ev) {
  return `
    <h3>${escapeHtml(ev.title)}</h3>
    ${ev.venueName ? `<div class="row"><strong>${escapeHtml(ev.venueName)}</strong></div>` : ""}
    ${ev.address ? `<div class="row">${escapeHtml(ev.address)}</div>` : ""}
    ${ev.dateLabel ? `<div class="row">${escapeHtml(ev.dateLabel)}</div>` : ""}
    ${ev.organiser ? `<div class="row">Organiser: ${escapeHtml(ev.organiser)}</div>` : ""}
    <a class="btn" href="${escapeAttr(ev.url)}" target="_blank" rel="noopener">View event ↗</a>
  `;
}

function render() {
  const q = els.search.value.trim().toLowerCase();
  const hideUnmapped = els.hideUnmapped.checked;
  const matches = state.events
    .map((ev, idx) => ({ ev, idx }))
    .filter(({ ev }) => {
      if (hideUnmapped && (ev.lat == null || ev.lon == null)) return false;
      if (!q) return true;
      const hay = [ev.title, ev.venueName, ev.organiser, ev.address, ev.blurb]
        .filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    });

  const placedTotal = state.events.filter((e) => e.lat != null).length;
  els.count.textContent =
    `${matches.length} of ${state.events.length} events` +
    (placedTotal < state.events.length ? ` (${placedTotal} on map)` : "");

  if (matches.length === 0) {
    els.list.innerHTML = `<li class="empty">No events match.</li>`;
    return;
  }

  const frag = document.createDocumentFragment();
  for (const { ev, idx } of matches) {
    const li = document.createElement("li");
    li.dataset.index = idx;
    if (ev.lat == null) li.classList.add("no-coords");
    if (idx === state.activeIndex) li.classList.add("active");
    li.innerHTML = `
      <div class="title">${escapeHtml(ev.title)}</div>
      <div class="meta-line">
        ${ev.venueName ? `<span class="venue">${escapeHtml(ev.venueName)}</span>` : `<span class="venue">No venue</span>`}
        ${ev.dateLabel ? `<span class="date">${escapeHtml(ev.dateLabel)}</span>` : ""}
      </div>
    `;
    li.addEventListener("click", () => {
      if (ev.lat == null) return;
      setActive(idx, { pan: true });
    });
    frag.appendChild(li);
  }
  els.list.replaceChildren(frag);
}

function setActive(idx, { pan }) {
  state.activeIndex = idx;
  document.querySelectorAll(".event-list li.active").forEach((el) => el.classList.remove("active"));
  const li = els.list.querySelector(`li[data-index="${idx}"]`);
  if (li) {
    li.classList.add("active");
    li.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  const marker = state.markersByIndex.get(idx);
  if (!marker) return;
  if (pan) {
    cluster.zoomToShowLayer(marker, () => {
      marker.openPopup();
    });
  } else {
    marker.openPopup();
  }
}

els.search.addEventListener("input", render);
els.hideUnmapped.addEventListener("change", render);

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
