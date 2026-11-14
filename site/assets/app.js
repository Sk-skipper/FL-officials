// Page behaviour. Each page's <body data-page="..."> selects what runs.
import {
  LEVEL_LABELS,
  LEVELS,
  SOURCE_STATUS_LABELS,
  SORTABLE,
  VERIFICATION_LABELS,
  countyGroups,
  countyRoster,
  countyTotals,
  describe,
  districtKey,
  districtLabel,
  escapeHtml as esc,
  exportPayload,
  featureAt,
  filterOptions,
  filterRecords,
  fold,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPartialDate,
  groupRoster,
  inCounty,
  initials,
  labelPoint,
  paginate,
  photoUrl,
  plural,
  pointInGeometry,
  representativesFor,
  safeUrl,
  seatText,
  sortRecords,
  telHref,
  toCsv,
  yearsSince,
} from "./lib.js";

const $ = (selector, root = document) => root.querySelector(selector);
const params = () => new URLSearchParams(window.location.search);

// -- data -----------------------------------------------------------------------
const cache = new Map();

function load(name) {
  if (!cache.has(name)) {
    const request = fetch(`data/${name}`, { cache: "no-cache" }).then((response) => {
      if (!response.ok) throw new Error(`The directory data could not be loaded (${response.status}).`);
      return response.json();
    });
    request.catch(() => cache.delete(name));
    cache.set(name, request);
  }
  return cache.get(name);
}

const loadOfficials = () => load("officials.json").then((payload) => payload.officials);
const loadMeta = () => load("meta.json");
const loadSources = () => load("sources.json");

// -- shared pieces ----------------------------------------------------------------
const ICON = {
  landmark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/></svg>',
  phone:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2Z"/></svg>',
  mail: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
  globe:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 0 20 15.3 15.3 0 0 1 0-20Z"/></svg>',
  external:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
  search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
  pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
  download:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>',
  back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>',
  sort: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 15 5 5 5-5M7 9l5-5 5 5"/></svg>',
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
  menu: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
  flag: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 22V4m0 0c5-3 7 3 12 0v9c-5 3-7-3-12 0"/></svg>',
  building:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/></svg>',
  city: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 22h18M5 22V8l6-4v18M11 22V10h8v12M15 14h.01M15 18h.01M8 10h.01M8 14h.01M8 18h.01"/></svg>',
};

const NAV = [
  { href: "representatives.html", label: "Your representatives", pages: ["reps"] },
  { href: "officials.html", label: "Officials", pages: ["directory", "official"] },
  { href: "counties.html", label: "Counties", pages: ["counties", "county"] },
  { href: "sources.html", label: "Data sources", pages: ["sources"] },
  { href: "about.html", label: "Methodology", pages: ["about"] },
];

function renderChrome(page) {
  const links = NAV.map(
    (item) =>
      `<a href="${item.href}"${item.pages.includes(page) ? ' aria-current="page"' : ""}>${item.label}</a>`,
  ).join("");
  $("#site-header").innerHTML = `
    <div class="topbar" aria-hidden="true"></div>
    <div class="container header-row">
      <a class="brand" href="index.html">
        <span class="brand-mark">${ICON.landmark}</span>
        <span class="brand-name">Florida Government <span class="nowrap">Officials Directory</span></span>
      </a>
      <nav class="nav-desktop" aria-label="Main">${links}</nav>
      <button class="menu-button" type="button" aria-expanded="false" aria-controls="nav-mobile">
        ${ICON.menu}<span class="sr-only">Menu</span>
      </button>
    </div>
    <nav id="nav-mobile" class="nav-mobile" aria-label="Main" hidden><div class="container">${links}</div></nav>`;
  const button = $(".menu-button");
  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    $("#nav-mobile").hidden = open;
  });

  $("#site-footer").innerHTML = `
    <div class="container footer-row">
      <div>
        <p class="footer-title">Florida Government Officials Directory</p>
        <p>An independent directory compiled from official government websites. It is not operated by, or
        affiliated with, any government agency. Always confirm details with the official source linked on each profile.</p>
      </div>
      <nav aria-label="Footer" class="footer-links">
        <a href="about.html">Methodology</a>
        <a href="sources.html">Data sources</a>
        <a href="about.html#corrections">Report an error</a>
        <a href="data/officials.csv" download>Download all (CSV)</a>
      </nav>
    </div>`;
}

function loading(label = "Loading") {
  return `<div class="state" role="status" aria-live="polite"><span class="sr-only">${esc(label)}</span>
    <div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton short"></div></div>`;
}

function empty(title, body = "") {
  return `<div class="state empty"><p class="state-title">${esc(title)}</p>${body ? `<p>${body}</p>` : ""}</div>`;
}

const NOT_COLLECTED_YET =
  "The first collection has not been published yet. The data sources page shows its progress.";

/** Run `render` once data loads; show a retryable error if it fails. */
function withData(container, loaders, render, label) {
  container.innerHTML = loading(label);
  Promise.all(loaders.map((fn) => fn()))
    .then((values) => render(...values))
    .catch((error) => {
      console.error(error);
      container.innerHTML = `<div class="state" role="alert"><p class="state-title">This information could not be loaded</p>
        <p>${esc(error.message || "Check your connection and try again.")}</p>
        <button class="button outline" type="button">Try again</button></div>`;
      $("button", container).addEventListener("click", () => withData(container, loaders, render, label));
    });
}

/** A round portrait. With no photo, or if the photo fails to load, it shows the person's initials. */
function avatar(r, size = "md") {
  const src = photoUrl(r.photo_url);
  const letters = esc(initials(r.full_name));
  if (!src) return `<span class="avatar ${size} blank" aria-hidden="true">${letters}</span>`;
  return `<span class="avatar ${size}" data-initials="${letters}" aria-hidden="true"><img src="${esc(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span>`;
}

// <img> errors don't bubble, so listen in the capture phase.
document.addEventListener(
  "error",
  (event) => {
    const box = event.target instanceof HTMLImageElement ? event.target.closest(".avatar") : null;
    if (!box) return;
    box.classList.add("blank");
    box.textContent = box.dataset.initials || "?";
  },
  true,
);

function levelBadge(level) {
  return `<span class="badge">${esc(LEVEL_LABELS[level] || level)}</span>`;
}

function partyText(party) {
  return party ? `<span class="badge outline">${esc(party)}</span>` : '<span class="muted">Not listed</span>';
}

function contactLinks(r) {
  const parts = [];
  if (r.phone) parts.push(`<a href="${telHref(r.phone)}">${ICON.phone}<span class="tabular">${esc(r.phone)}</span></a>`);
  if (r.email) parts.push(`<a class="break" href="mailto:${esc(r.email)}">${ICON.mail}<span>${esc(r.email)}</span></a>`);
  return parts.length ? `<div class="contact">${parts.join("")}</div>` : '<span class="muted">Not published by source</span>';
}

function profileHref(r) {
  return `official.html?id=${encodeURIComponent(r.id)}`;
}

function officialList(records, dateField) {
  return `<ul class="mini-list">${records
    .map(
      (r) => `<li>${avatar(r, "sm")}<div><a href="${profileHref(r)}">${esc(r.full_name)}</a><p class="muted">${esc(describe(r))}</p></div>
      <span class="muted tabular">${esc(formatDate(r[dateField]))}</span></li>`,
    )
    .join("")}</ul>`;
}

/** Desktop table plus phone cards. `sort` is optional. */
function officialsTable(records, sort) {
  const columns = [
    ["name", "Name"],
    ["position", "Position"],
    ["level", "Level"],
    ["jurisdiction", "Jurisdiction"],
    ["district", "District"],
    ["party", "Party"],
  ];
  const head = columns
    .map(([key, label]) => {
      if (!sort) return `<th scope="col">${label}</th>`;
      const active = sort.key === key;
      const ariaSort = active ? (sort.order === "desc" ? "descending" : "ascending") : "none";
      const icon = active ? (sort.order === "desc" ? ICON.down : ICON.up) : ICON.sort;
      return `<th scope="col" aria-sort="${ariaSort}"><button type="button" class="sort${active ? " active" : ""}" data-sort="${key}">${label}${icon}</button></th>`;
    })
    .join("");
  const rows = records
    .map(
      (r) => `<tr>
        <td class="strong"><span class="name-cell">${avatar(r, "sm")}<a href="${profileHref(r)}">${esc(r.full_name)}</a></span></td>
        <td>${esc(r.office_title)}</td>
        <td>${levelBadge(r.government_level)}</td>
        <td>${esc(r.jurisdiction)}</td>
        <td class="tabular">${seatText(r) ? esc(seatText(r)) : '<span class="muted">—</span>'}</td>
        <td>${partyText(r.party)}</td>
        <td>${contactLinks(r)}</td>
        <td class="right"><a class="details" href="${profileHref(r)}" aria-label="View profile of ${esc(r.full_name)}">View profile${ICON.arrow}</a></td>
      </tr>`,
    )
    .join("");
  const cards = records
    .map(
      (r) => `<li>
        <div class="card-top"><div class="name-cell">${avatar(r, "sm")}<div><a class="card-name" href="${profileHref(r)}">${esc(r.full_name)}</a>
        <p class="muted">${esc(describe(r))}</p></div></div>${levelBadge(r.government_level)}</div>
        <div>${partyText(r.party)}</div>
        <div>${contactLinks(r)}</div>
      </li>`,
    )
    .join("");
  return `<div class="table-wrap"><table><thead><tr>${head}<th scope="col">Contact</th><th scope="col"><span class="sr-only">Details</span></th></tr></thead>
    <tbody>${rows}</tbody></table></div><ul class="cards">${cards}</ul>`;
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// -- home -------------------------------------------------------------------------
function home() {
  const form = $("#home-search");
  const input = $("#home-q");
  const list = $("#suggestions");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const q = input.value.trim();
    window.location.href = q ? `officials.html?q=${encodeURIComponent(q)}` : "officials.html";
  });

  loadOfficials()
    .then((records) => {
      input.addEventListener("input", () => {
        const q = input.value.trim();
        const matches = q.length >= 2 ? sortRecords(filterRecords(records, { q })).slice(0, 6) : [];
        list.hidden = matches.length === 0;
        list.innerHTML = matches
          .map((r) => `<li><a href="${profileHref(r)}"><span class="strong">${esc(r.full_name)}</span><span class="muted">${esc(describe(r))}</span></a></li>`)
          .join("");
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") list.hidden = true;
      });
    })
    .catch(() => undefined);

  const explorer = $("#explorer");
  if (explorer) {
    withData(explorer, [loadOfficials, loadMeta, loadMap], (records, meta, map) => countyExplorer(explorer, records, meta, map), "Loading the county map");
  }

  const stats = $("#stats");
  withData(stats, [loadOfficials, loadMeta], (records, meta) => {
    const tile = (label, value) => `<div class="tile"><dt>${label}</dt><dd class="tabular">${value}</dd></div>`;
    const percent = meta.coverage.tracked_percent;
    stats.innerHTML = `
      <dl class="tiles tiles-5">
        ${tile("Total officials collected", formatNumber(records.length))}
        ${LEVELS.map((level) => tile(`${LEVEL_LABELS[level]} officials`, formatNumber(meta.by_level[level] || 0))).join("")}
      </dl>
      <div class="grid-2 gap-top">
        <div class="tile"><p class="muted">Last database update</p>
          <p class="strong">${esc(formatDateTime(meta.last_data_update, "No records collected yet"))}</p></div>
        <div class="tile">
          <div class="split"><p class="muted">Data coverage of tracked offices</p><p class="strong tabular">${percent}%</p></div>
          <div class="bar" role="progressbar" aria-label="Data coverage of tracked offices" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div>
          <p class="muted small">Measured only against offices that have a source. Many local offices are not covered yet.
          <a href="about.html#coverage">See what is and is not included</a></p>
        </div>
      </div>`;

    for (const level of LEVELS) {
      const count = $(`[data-count="${level}"]`);
      if (count) count.textContent = plural(meta.by_level[level] || 0, "official");
    }

    const verified = sortRecords(records.filter((r) => r.last_verified), "name")
      .sort((a, b) => String(b.last_verified).localeCompare(String(a.last_verified)))
      .slice(0, 6);
    const updated = [...records]
      .filter((r) => r.updated_on)
      .sort((a, b) => String(b.updated_on).localeCompare(String(a.updated_on)) || a.last_name.localeCompare(b.last_name))
      .slice(0, 6);
    $("#recent-verified").innerHTML = verified.length ? officialList(verified, "last_verified") : empty("No records yet", NOT_COLLECTED_YET);
    $("#recent-updated").innerHTML = updated.length ? officialList(updated, "updated_on") : empty("No records yet");
  }, "Loading directory figures");
}

// -- directory --------------------------------------------------------------------
const FILTERS = [
  ["level", "Government level"],
  ["county", "County"],
  ["municipality", "Municipality"],
  ["party", "Political party"],
  ["office_title", "Office title"],
  ["district", "District"],
];
const PAGE_SIZE = 25;

function directory() {
  const app = $("#app");
  withData(app, [loadOfficials, loadMeta], (records, meta) => {
    const query = params();
    const state = {
      q: query.get("q") || "",
      sort: SORTABLE.includes(query.get("sort")) ? query.get("sort") : "name",
      order: query.get("order") === "desc" ? "desc" : "asc",
      page: Math.max(1, Number.parseInt(query.get("page") || "1", 10) || 1),
    };
    for (const [key] of FILTERS) state[key] = query.get(key) || "";

    const options = filterOptions(records);
    const choices = {
      level: options.levels.map((v) => [v, LEVEL_LABELS[v]]),
      county: meta.counties.map((v) => [v, v]),
      municipality: options.municipalities.map((v) => [v, v]),
      party: options.parties.map((v) => [v, v]),
      office_title: options.office_titles.map((v) => [v, v]),
      district: options.districts.map((v) => [v, districtLabel(v)]),
    };

    app.innerHTML = `
      <section class="panel">
        <form role="search" id="directory-search">
          <label for="q">Search the directory</label>
          <div class="input-icon">${ICON.search}<input id="q" type="search" maxlength="100" autocomplete="off"
            placeholder="Search officials, districts, counties, or cities..." value="${esc(state.q)}"></div>
        </form>
        <fieldset class="filters"><legend class="sr-only">Filters</legend>
          ${FILTERS.map(([key, label]) => `<div class="field"><label for="f-${key}">${label}</label>
            <select id="f-${key}" data-filter="${key}"><option value="">All</option>
            ${choices[key].map(([value, text]) => `<option value="${esc(value)}"${value === state[key] ? " selected" : ""}>${esc(text)}</option>`).join("")}
            </select></div>`).join("")}
        </fieldset>
        <button type="button" class="button ghost small" id="clear" hidden>Clear search and filters</button>
      </section>
      <section class="panel flush">
        <div class="results-bar">
          <p id="count" class="muted" role="status" aria-live="polite"></p>
          <div class="actions">
            <button type="button" class="button outline small" id="dl-csv">${ICON.download}Download CSV</button>
            <button type="button" class="button outline small" id="dl-json">${ICON.download}Download JSON</button>
          </div>
        </div>
        <div id="results"></div>
      </section>`;

    const criteria = () => Object.fromEntries([["q", state.q], ...FILTERS.map(([key]) => [key, state[key]])]);
    let current = [];

    function syncUrl() {
      const next = new URLSearchParams();
      for (const [key, value] of Object.entries(criteria())) if (value) next.set(key, value);
      if (state.sort !== "name") next.set("sort", state.sort);
      if (state.order !== "asc") next.set("order", state.order);
      if (state.page > 1) next.set("page", String(state.page));
      const text = next.toString();
      window.history.replaceState(null, "", text ? `?${text}` : window.location.pathname);
    }

    function draw() {
      const active = criteria();
      const hasCriteria = Object.values(active).some(Boolean);
      current = sortRecords(filterRecords(records, active), state.sort, state.order);
      const page = paginate(current, state.page, PAGE_SIZE);
      state.page = page.page;
      syncUrl();
      $("#clear").hidden = !hasCriteria;
      $("#count").textContent = `${plural(page.total, "official")}${hasCriteria ? (page.total === 1 ? " matches your search" : " match your search") : ""}`;

      const results = $("#results");
      if (records.length === 0) {
        results.innerHTML = empty("No records have been collected yet", NOT_COLLECTED_YET);
        return;
      }
      if (page.total === 0) {
        results.innerHTML = empty(
          "No officials match your search",
          "Try a shorter name, check the spelling, or clear some filters. Many county and city offices are not in the directory yet.",
        );
        return;
      }
      results.innerHTML = `${officialsTable(page.items, { key: state.sort, order: state.order })}
        <nav class="pager" aria-label="Pagination">
          <p class="muted tabular">Showing ${formatNumber(page.start + 1)}–${formatNumber(page.start + page.items.length)} of ${formatNumber(page.total)}</p>
          <div class="actions">
            <button type="button" class="button outline small" data-goto="${page.page - 1}"${page.page <= 1 ? " disabled" : ""}>Previous</button>
            <span class="tabular">Page ${page.page} of ${page.pages}</span>
            <button type="button" class="button outline small" data-goto="${page.page + 1}"${page.page >= page.pages ? " disabled" : ""}>Next</button>
          </div>
        </nav>`;
    }

    let timer;
    $("#q").addEventListener("input", (event) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.q = event.target.value.trim();
        state.page = 1;
        draw();
      }, 200);
    });
    $("#directory-search").addEventListener("submit", (event) => event.preventDefault());
    app.addEventListener("change", (event) => {
      const key = event.target.dataset.filter;
      if (!key) return;
      state[key] = event.target.value;
      state.page = 1;
      draw();
    });
    app.addEventListener("click", (event) => {
      const sortButton = event.target.closest("[data-sort]");
      if (sortButton) {
        const key = sortButton.dataset.sort;
        state.order = state.sort === key && state.order === "asc" ? "desc" : "asc";
        state.sort = key;
        state.page = 1;
        draw();
        $(`[data-sort="${key}"]`)?.focus();
        return;
      }
      // Not "[data-page]": <body data-page="directory"> would match every click and set the page to NaN.
      const pageButton = event.target.closest("[data-goto]");
      if (pageButton && !pageButton.disabled) {
        state.page = Number(pageButton.dataset.goto) || 1;
        draw();
        $("#count").scrollIntoView({ block: "start" });
      }
    });
    $("#clear").addEventListener("click", () => {
      state.q = "";
      $("#q").value = "";
      for (const [key] of FILTERS) {
        state[key] = "";
        $(`#f-${key}`).value = "";
      }
      state.page = 1;
      draw();
    });
    const stamp = () => new Date().toISOString().slice(0, 10);
    $("#dl-csv").addEventListener("click", () => download(`florida-officials-${stamp()}.csv`, toCsv(current), "text/csv;charset=utf-8"));
    $("#dl-json").addEventListener("click", () =>
      download(`florida-officials-${stamp()}.json`, JSON.stringify(exportPayload(current, criteria()), null, 2), "application/json"),
    );
    draw();
  }, "Loading officials");
}

// -- profile ----------------------------------------------------------------------
function profile() {
  const app = $("#app");
  const id = params().get("id") || "";
  withData(app, [loadOfficials, loadMeta], (records, meta) => {
    const r = records.find((item) => item.id === id);
    if (!r) {
      app.innerHTML = `<section class="panel">${empty(
        "Official not found",
        'This record does not exist, or the official is no longer listed by their source. <a href="officials.html">Back to the directory</a>',
      )}</section>`;
      return;
    }
    document.title = `${r.full_name} | Florida Government Officials Directory`;
    const missing = '<span class="muted">Not published by the source</span>';
    const row = (label, value) => `<div class="row"><dt>${label}</dt><dd>${value || missing}</dd></div>`;
    const counties = r.county ? [r.county] : r.counties || [];
    const countyLinks = r.statewide
      ? "Statewide (all 67 counties)"
      : counties.map((c) => `<a href="county.html?name=${encodeURIComponent(c)}">${esc(c)}</a>`).join(", ");
    const website = safeUrl(r.official_website);
    const sourceUrl = safeUrl(r.source_url);
    const directoryUrl = safeUrl(r.source_directory_url);
    const selection = {
      elected: '<span class="badge navy">Elected office</span>',
      appointed: '<span class="badge amber">Appointed office</span>',
    }[r.selection_method] || '<span class="badge outline">Selection method not listed</span>';

    let report = "";
    const reportUrl = safeUrl(meta.report_url);
    if (reportUrl) {
      const prefill = reportUrl.includes("template=correction.yml")
        ? `&title=${encodeURIComponent(`Correction: ${r.full_name}`)}&record_id=${encodeURIComponent(r.id)}`
        : "";
      report = `<a href="${esc(reportUrl + prefill)}" target="_blank" rel="noopener noreferrer">Report an error</a>`;
    } else if (meta.contact_email) {
      report = `<a href="mailto:${esc(meta.contact_email)}?subject=${encodeURIComponent(`Correction: ${r.full_name} (${r.id})`)}">Report an error</a>`;
    } else {
      report = '<a href="about.html#corrections">How to report an error</a>';
    }

    app.innerHTML = `
      <a class="back" href="officials.html">${ICON.back}Back to the directory</a>
      <header class="profile-head">
        ${avatar(r, "xl")}
        <div>
          <h1>${esc(r.full_name)}</h1>
          <p class="lede">${esc(describe(r))}</p>
          <div class="badges">${levelBadge(r.government_level)}${selection}
            <span class="badge green">${esc(VERIFICATION_LABELS[r.verification_status] || r.verification_status)}</span></div>
        </div>
      </header>
      <div class="profile-grid">
        <div class="stack">
        ${aboutPanel(r)}
        <section class="panel">
          <h2>Office details</h2>
          <dl class="rows">
            ${row("Full name", esc(r.full_name))}
            ${row("Official title", esc(r.office_title))}
            ${row("Government level", esc(LEVEL_LABELS[r.government_level] || r.government_level))}
            ${row("Jurisdiction", esc(r.jurisdiction))}
            ${row(counties.length > 1 ? "Counties represented" : "County", countyLinks)}
            ${r.municipality ? row("Municipality", esc(r.municipality)) : ""}
            ${row(r.seat_label ? "Seat" : "District", esc(seatText(r)))}
            ${row("Political party", esc(r.party || ""))}
            ${row("Last verified", esc(formatDate(r.last_verified, "")))}
          </dl>
          ${r.counties_source ? `<p class="muted small fine">Counties in this district: ${
            safeUrl(r.counties_source.url)
              ? `<a href="${esc(r.counties_source.url)}" target="_blank" rel="noopener noreferrer">${esc(r.counties_source.name)}</a>`
              : esc(r.counties_source.name)
          }</p>` : ""}
        </section>
        </div>
        <div class="stack">
          <section class="panel">
            <h2>Contact</h2>
            <p class="muted small">Public office contact details only.</p>
            <ul class="contact-list">
              <li>${ICON.phone}<div><p class="muted small">Official phone</p>${r.phone ? `<a class="tabular" href="${telHref(r.phone)}">${esc(r.phone)}</a>` : missing}</div></li>
              <li>${ICON.mail}<div><p class="muted small">Official email</p>${r.email ? `<a class="break" href="mailto:${esc(r.email)}">${esc(r.email)}</a>` : missing}</div></li>
              <li>${ICON.globe}<div><p class="muted small">Official government website</p>${
                website
                  ? `<a class="break" href="${esc(website)}" target="_blank" rel="noopener noreferrer">${esc(website.replace(/^https?:\/\//, "").replace(/\/$/, ""))}${ICON.external}<span class="sr-only">(opens in a new tab)</span></a>`
                  : missing
              }</div></li>
            </ul>
          </section>
          <section class="panel">
            <h2>Source</h2>
            <p class="muted small">Where this record comes from. Empty fields were not published there.</p>
            <dl class="rows compact">
              ${row("Source directory", directoryUrl ? `<a href="${esc(directoryUrl)}" target="_blank" rel="noopener noreferrer">${esc(r.source_name)}</a>` : esc(r.source_name))}
              ${row("Original record", sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">View the government page${ICON.external}<span class="sr-only">(opens in a new tab)</span></a>` : "")}
              ${row("Last verified", esc(formatDate(r.last_verified, "")))}
              ${r.correction_note ? row("Correction", esc(r.correction_note)) : ""}
              ${safeUrl(r.wikipedia_url) ? row("More about them", `<a href="${esc(r.wikipedia_url)}" target="_blank" rel="noopener noreferrer">Wikipedia article${ICON.external}<span class="sr-only">(opens in a new tab)</span></a>`) : ""}
            </dl>
            ${photoCredit(r)}
            <p class="small fine">See something wrong? ${report}<br><span class="muted">Record id: <code>${esc(r.id)}</code></span></p>
          </section>
        </div>
      </div>`;
  }, "Loading profile");
}

/** Credit line for a portrait that did not come from the official source (e.g. Wikimedia Commons). */
function photoCredit(r) {
  const c = r.photo_credit;
  if (!c || !r.photo_url) return "";
  const file = safeUrl(c.file_url) ? `<a href="${esc(c.file_url)}" target="_blank" rel="noopener noreferrer">${esc(c.source || "Photo")}</a>` : esc(c.source || "");
  const licence = safeUrl(c.license_url) ? `<a href="${esc(c.license_url)}" target="_blank" rel="noopener noreferrer">${esc(c.license)}</a>` : esc(c.license || "");
  return `<p class="muted small fine">Photo: ${esc(c.author || "Unknown author")}, ${licence}, via ${file}.</p>`;
}

/** Basic facts about the person: born, time in office, term, earlier offices. */
function aboutPanel(r) {
  const bio = r.bio || {};
  const facts = [];
  if (bio.born) {
    const age = yearsSince(bio.born);
    facts.push(["Born", `${esc(formatPartialDate(bio.born))}${age !== null ? ` <span class="muted">(age ${age})</span>` : ""}`]);
  }
  if (bio.serving_since) {
    const years = yearsSince(bio.serving_since);
    const span = years === null ? "" : years < 1 ? " <span class=\"muted\">(newly in office)</span>" : ` <span class="muted">(${plural(years, "year")})</span>`;
    facts.push(["In this office since", `${esc(formatPartialDate(bio.serving_since))}${span}`]);
  }
  if (bio.term_ends) facts.push(["Current term ends", esc(formatPartialDate(bio.term_ends))]);
  if (bio.next_election) facts.push(["Next election", esc(bio.next_election)]);
  if (bio.previously?.length) facts.push(["Previously", `<ul class="plain">${bio.previously.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`]);
  if (!facts.length && !bio.summary && !bio.note) return "";
  const sources = (r.bio_sources || [])
    .map((s) => (safeUrl(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a>` : esc(s.name)))
    .join(", ");
  return `<section class="panel about">
    <h2>About ${esc(r.first_name || r.full_name)}</h2>
    ${bio.summary ? `<p class="bio-summary">${esc(bio.summary)}</p>` : ""}
    ${facts.length ? `<dl class="rows">${facts.map(([label, value]) => `<div class="row"><dt>${label}</dt><dd>${value}</dd></div>`).join("")}</dl>` : ""}
    ${bio.note ? `<p class="notice small">${esc(bio.note)}</p>` : ""}
    <p class="muted small fine">${sources ? `Bio facts from ${sources}, and the source below.` : "Bio facts from the source below."}</p>
  </section>`;
}

// -- counties ---------------------------------------------------------------------
let mapRequest;
function loadMap() {
  if (!mapRequest) {
    mapRequest = fetch("assets/florida-counties.json").then((response) => {
      if (!response.ok) throw new Error(`The county map could not be loaded (${response.status}).`);
      return response.json();
    });
    mapRequest.catch(() => (mapRequest = undefined));
  }
  return mapRequest;
}

function personCard(r, { contact = false } = {}) {
  if (r.vacant) {
    return `<li class="person vacant"><div><span class="avatar lg blank" aria-hidden="true">—</span><span>
      <span class="person-name">Vacant seat</span>
      <span class="muted small">${esc(r.office_title)}${seatText(r) ? ` · ${esc(seatText(r))}` : ""}</span>
      ${r.note ? `<span class="muted small">${esc(r.note)}</span>` : ""}
    </span></div></li>`;
  }
  const seat = seatText(r);
  const actions = contact ? [
    r.phone ? `<a href="${telHref(r.phone)}" aria-label="Call ${esc(r.full_name)}" title="${esc(r.phone)}">${ICON.phone}</a>` : "",
    r.email ? `<a href="mailto:${esc(r.email)}" aria-label="Email ${esc(r.full_name)}" title="${esc(r.email)}">${ICON.mail}</a>` : "",
    safeUrl(r.official_website) ? `<a href="${esc(r.official_website)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(r.full_name)}'s official website" title="Official website">${ICON.globe}</a>` : "",
  ].filter(Boolean).join("") : "";
  return `<li class="person${actions ? " with-actions" : ""}"><a href="${profileHref(r)}">${avatar(r, "lg")}<span>
    <span class="person-name">${esc(r.full_name)}</span>
    <span class="muted small">${esc(r.office_title)}${seat ? ` · ${esc(seat)}` : ""}</span>
    ${r.party ? `<span class="badge outline">${esc(r.party)}</span>` : ""}
  </span></a>${actions ? `<span class="person-actions">${actions}</span>` : ""}</li>`;
}

const LONG_SECTION = 12;

/**
 * The county explorer: a clickable map of all 67 counties beside a full roster for the
 * selected county, grouped by level and body. Used on the homepage and the Counties page.
 */
function countyExplorer(root, records, meta, map, { initial = "Broward", syncParam = "county" } = {}) {
  const totals = countyTotals(records, meta.counties);
  const vacancies = meta.vacancies || [];
  const requested = params().get(syncParam);
  let selected = meta.counties.find((c) => fold(c) === fold(requested || "")) || initial;
  let level = "";
  let filter = "";

  const tier = (n) => (n >= 50 ? " t4" : n >= 11 ? " t3" : n >= 5 ? " t2" : n > 0 ? " t1" : "");
  const shapes = map.counties
    .map(
      (c) => `<path class="county-shape${tier(totals[c.name])}" data-county="${esc(c.name)}" d="${c.d}"
        tabindex="0" role="button" aria-pressed="false"
        aria-label="${esc(c.name)} County, ${plural(totals[c.name], "official")} tied to the county"><title>${esc(c.name)} County · ${plural(totals[c.name], "official")}</title></path>`,
    )
    .join("");
  const centres = Object.fromEntries(map.counties.map((c) => [c.name, c]));

  root.innerHTML = `
    <div class="map-layout">
      <section class="panel map-card" aria-label="Map of Florida counties">
        <div class="field map-picker"><label for="${syncParam}-pick">County</label>
          <select id="${syncParam}-pick">${meta.counties.map((c) => `<option value="${esc(c)}">${esc(c)} County</option>`).join("")}</select></div>
        <div class="map-wrap">
          <svg viewBox="0 0 ${map.width} ${map.height}" role="group" aria-label="Florida's 67 counties. Select a county to see everyone who represents it.">${shapes}</svg>
          <div class="pins"></div>
        </div>
        <ul class="legend small muted" aria-label="Map shading">
          <li><span class="swatch t1"></span>1–4 officials</li><li><span class="swatch t2"></span>5–10</li><li><span class="swatch t3"></span>11–49</li><li><span class="swatch t4"></span>50 or more</li><li><span class="swatch selected"></span>Selected</li>
        </ul>
        <p class="small map-note"><a href="representatives.html">${ICON.pin} See which representative covers which part of each county on the district map</a></p>
        <p class="muted small map-note">Shading counts officials tied to each county: local offices plus the U.S. House, Florida Senate and Florida House
        members whose districts reach into it. Statewide officials represent every county and are listed in each.</p>
      </section>
      <section class="panel map-panel" aria-live="polite"></section>
    </div>`;

  const panel = $(".map-panel", root);
  const pins = $(".pins", root);
  const picker = $(`#${syncParam}-pick`, root);

  function syncUrl() {
    const next = params();
    if (selected === initial) next.delete(syncParam);
    else next.set(syncParam, selected);
    const text = next.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${text ? `?${text}` : ""}${window.location.hash}`);
  }

  function drawPin() {
    // One portrait marks the selected county: its leading county official with a photo.
    const local = countyRoster(records, selected).local;
    const lead =
      local.find((r) => r.government_level === "county" && /county commissioner/i.test(r.office_title) && photoUrl(r.photo_url)) ||
      local.find((r) => r.government_level === "county" && photoUrl(r.photo_url));
    const c = centres[selected];
    pins.innerHTML =
      lead && c
        ? `<a class="pin marker" href="${profileHref(lead)}" style="left:${((c.cx / map.width) * 100).toFixed(2)}%;top:${((c.cy / map.height) * 100).toFixed(2)}%"
            aria-label="${esc(lead.full_name)}, ${esc(lead.office_title)}, ${esc(selected)} County">${avatar(lead, "sm")}</a>`
        : "";
  }

  function matches(item) {
    if (!filter) return true;
    if (item.vacant) return fold([item.office_title, item.seat_label, item.district, "vacant"].join(" ")).includes(fold(filter));
    return fold([item.full_name, item.office_title, item.municipality, item.jurisdiction, seatText(item), item.party].join(" ")).includes(fold(filter));
  }

  function drawPanel() {
    const groups = countyGroups(records, selected, vacancies);
    const total = groups.reduce((n, g) => n + g.count, 0);
    const open = vacancies.filter((v) => (v.counties || []).includes(selected)).length;
    const towns = groups.find((g) => g.level === "municipal")?.sections.length || 0;
    const shown = groups
      .filter((g) => !level || g.level === level)
      .map((g) => ({ ...g, sections: g.sections.map((s) => ({ ...s, items: s.items.filter(matches) })).filter((s) => s.items.length) }))
      .filter((g) => g.sections.length);

    const body = shown
      .map((g) => {
        const sections = g.sections
          .map((s) => {
            const list = `<ul class="people">${s.items.map(personCard).join("")}</ul>`;
            const head = `${esc(s.name)} <span class="count">${formatNumber(s.items.filter((i) => !i.vacant).length)}</span>`;
            const collapse = g.level === "municipal" || s.items.length > LONG_SECTION;
            return collapse
              ? `<details class="roster-section"${filter ? " open" : ""}><summary><h4>${head}</h4></summary>${list}</details>`
              : `<div class="roster-section"><h4>${head}</h4>${list}</div>`;
          })
          .join("");
        return `<section class="roster-level"><h3 class="group">${esc(LEVEL_LABELS[g.level])} <span class="count">${formatNumber(g.count)}</span></h3>${sections}</section>`;
      })
      .join("");

    const coverage =
      LOCAL_COUNTIES.includes(selected)
        ? ""
        : `<p class="muted small notice">County commissions, judges and city councils are covered for Broward and Miami-Dade counties so far. Here you'll find
           statewide officials, ${esc(selected)} County's members of Congress and Legislature, and its Supervisor of Elections.</p>`;

    panel.innerHTML = `
      <div class="panel-top">
        <div><h2>${esc(selected)} County</h2>
          <p class="muted small tabular">${plural(total, "elected official")}${open ? ` · ${plural(open, "vacant seat")}` : ""}${towns ? ` · ${plural(towns, "city", "cities")} listed` : ""}</p></div>
        <span class="panel-actions"><a class="details" href="representatives.html">District map${ICON.arrow}</a>
        <a class="details" href="county.html?name=${encodeURIComponent(selected)}">Full county page${ICON.arrow}</a></span>
      </div>
      ${coverage}
      <div class="roster-tools">
        <div class="input-icon">${ICON.search}<input type="search" class="roster-filter" aria-label="Filter ${esc(selected)} County officials"
          placeholder="Filter by name, office or city" value="${esc(filter)}"></div>
        <div class="chips" role="group" aria-label="Filter by government level">
          ${["", ...LEVELS].map((value) => {
            const count = value ? groups.find((g) => g.level === value)?.count || 0 : total;
            return `<button type="button" class="chip" data-level="${value}" aria-pressed="${value === level}"${value && !count ? " disabled" : ""}>${value ? LEVEL_LABELS[value] : "All"} <span class="tabular">${formatNumber(count)}</span></button>`;
          }).join("")}
        </div>
      </div>
      <div class="roster">${body || empty("No officials match", "Try a different name or office, or clear the filter.")}</div>`;
  }

  function select(name, { focusPanel = false } = {}) {
    selected = name;
    level = "";
    filter = "";
    for (const shape of root.querySelectorAll(".county-shape")) {
      const on = shape.dataset.county === selected;
      shape.classList.toggle("selected", on);
      shape.setAttribute("aria-pressed", String(on));
    }
    picker.value = selected;
    syncUrl();
    drawPin();
    drawPanel();
    if (focusPanel && window.matchMedia("(max-width: 900px)").matches) panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const mapCard = $(".map-card", root);
  mapCard.addEventListener("click", (event) => {
    const shape = event.target.closest(".county-shape");
    if (shape) select(shape.dataset.county, { focusPanel: true });
  });
  mapCard.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const shape = event.target.closest(".county-shape");
    if (!shape) return;
    event.preventDefault();
    select(shape.dataset.county, { focusPanel: true });
  });
  picker.addEventListener("change", () => select(picker.value));
  panel.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-level]");
    if (!chip || chip.disabled) return;
    level = chip.dataset.level;
    drawPanel();
    $(`[data-level="${level}"]`, panel)?.focus();
  });
  let timer;
  panel.addEventListener("input", (event) => {
    if (!event.target.matches(".roster-filter")) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      filter = event.target.value.trim();
      const caret = event.target.selectionStart;
      drawPanel();
      const box = $(".roster-filter", panel);
      box.focus();
      box.setSelectionRange(caret, caret);
    }, 150);
  });

  select(selected);
}

function counties() {
  const app = $("#app");
  withData(app, [loadOfficials, loadMeta, loadMap], (records, meta, map) => {
    app.innerHTML = `
      <div id="explorer"></div>
      <h2 class="section-title">All counties</h2>
      <div class="field narrow"><label for="county-filter">Find a county</label>
        <div class="input-icon">${ICON.search}<input id="county-filter" type="search" placeholder="Type a county name"></div></div>
      <div id="county-list"></div>`;
    countyExplorer($("#explorer"), records, meta, map);

    const totals = countyTotals(records, meta.counties);
    const summary = meta.counties.map((name) => {
      const here = records.filter((r) => !r.statewide && inCounty(r, name));
      return { name, officials: totals[name], towns: new Set(here.map((r) => r.municipality).filter(Boolean)).size };
    });
    const draw = (text) => {
      const visible = summary.filter((c) => fold(c.name).includes(fold(text.trim())));
      $("#county-list").innerHTML = visible.length
        ? `<ul class="county-grid">${visible
            .map(
              (c) => `<li><a href="county.html?name=${encodeURIComponent(c.name)}">${ICON.pin}<span>
                <span class="county-name">${esc(c.name)} County</span>
                <span class="muted small tabular">${plural(c.officials, "official")}${c.towns ? ` · ${plural(c.towns, "municipality", "municipalities")}` : ""}</span>
              </span></a></li>`,
            )
            .join("")}</ul>`
        : `<section class="panel">${empty("No county matches that name", "Check the spelling, or clear the box to see all 67.")}</section>`;
    };
    $("#county-filter").addEventListener("input", (event) => draw(event.target.value));
    draw("");
  }, "Loading counties");
}

function county() {
  const app = $("#app");
  const requested = (params().get("name") || "").replace(/\s+county$/i, "");
  withData(app, [loadOfficials, loadMeta], (records, meta) => {
    const name = meta.counties.find((c) => fold(c) === fold(requested));
    if (!name) {
      app.innerHTML = `<section class="panel">${empty("County not found", '<a href="counties.html">See all 67 Florida counties</a>')}</section>`;
      return;
    }
    document.title = `${name} County | Florida Government Officials Directory`;
    const all = sortRecords(records.filter((r) => inCounty(r, name, true)), "level");
    const towns = [...new Set(all.map((r) => r.municipality).filter(Boolean))].sort();
    let level = "";

    app.innerHTML = `
      <a class="back" href="counties.html">${ICON.back}All counties</a>
      <h1>${esc(name)} County</h1>
      <section class="panel flush gap-top">
          <div class="panel-head">
            <h2>Officials representing ${esc(name)} County</h2>
            <p class="muted small">Officials whose source names this county, plus statewide officials. U.S. House and
            Florida House members appear only where a source lists the counties in their district.</p>
            <div class="chips" role="group" aria-label="Filter by government level">
              ${["", ...LEVELS].map((value) => `<button type="button" class="chip" data-level="${value}" aria-pressed="${value === ""}">${value ? LEVEL_LABELS[value] : "All levels"}</button>`).join("")}
            </div>
          </div>
          <div id="county-officials"></div>
      </section>
        <div class="grid-2 gap-top">
          <section class="panel">
            <h2>Municipalities</h2>
            ${towns.length
              ? `<ul class="link-list">${towns.map((t) => `<li><a href="officials.html?county=${encodeURIComponent(name)}&municipality=${encodeURIComponent(t)}">${esc(t)}</a></li>`).join("")}</ul>`
              : `<p class="muted small">No municipalities in ${esc(name)} County have been added yet.</p>`}
          </section>
          <section class="panel">
            <h2>Districts and jurisdictions</h2>
            <div id="county-districts"></div>
          </section>
        </div>
      </div>`;

    const draw = () => {
      const shown = level ? all.filter((r) => r.government_level === level) : all;
      $("#county-officials").innerHTML = shown.length
        ? officialsTable(shown)
        : empty("No officials found for this view", level ? "There are no records at this level for this county yet." : "No source currently lists officials for this county.");
      const districts = [...new Set(shown.filter((r) => r.district).map((r) => `${r.office_title}: ${districtLabel(r.district)}`))].sort(
        (a, b) => a.localeCompare(b, "en", { numeric: true }),
      );
      $("#county-districts").innerHTML = districts.length
        ? `<ul class="plain tabular">${districts.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>`
        : '<p class="muted small">No district information for this view.</p>';
      for (const chip of app.querySelectorAll("[data-level]")) chip.setAttribute("aria-pressed", String(chip.dataset.level === level));
    };
    app.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-level]");
      if (!chip) return;
      level = chip.dataset.level;
      draw();
    });
    draw();
  }, "Loading county");
}

// -- your representatives (map) ----------------------------------------------------
const BOUNDARIES = {
  counties: "fl-counties", cities: "fl-cities", congress: "fl-congress", senate: "fl-senate", house: "fl-house",
  commission: "county-commission", school: "school-board", cityDistricts: "city-districts", special: "special-districts",
};
/** The "Show" dropdown, grouped by level of government. */
const LAYER_GROUPS = [
  ["Local (Broward and Miami-Dade)", ["commission", "school", "cityDistricts", "cities", "special"]],
  ["State", ["house", "senate"]],
  ["Federal", ["congress"]],
];
/** Counties mapped down to county, school board, city and special districts. */
const LOCAL_COUNTIES = ["Broward", "Miami-Dade"];
const boundaryRequests = new Map();
function loadBoundary(key) {
  if (!boundaryRequests.has(key)) {
    const request = fetch(`assets/boundaries/${BOUNDARIES[key]}.json`).then((response) => {
      if (!response.ok) throw new Error(`The district map could not be loaded (${response.status}).`);
      return response.json();
    });
    request.catch(() => boundaryRequests.delete(key));
    boundaryRequests.set(key, request);
  }
  return boundaryRequests.get(key);
}

const isSeat = (r, district) => r.district != null && districtKey(r.district) === districtKey(district);
/** The layers a visitor can show on the map, and who holds each district in them. */
const MAP_LAYERS = [
  { key: "commission", label: "County Commission", area: "local", partisan: true, holder: (r, p) => r.office_title === "County Commissioner" && r.county === p.county && isSeat(r, p.district), name: (p) => `${p.county} Commission District ${p.district}` },
  { key: "school", label: "School Board", area: "local", holder: (r, p) => /school board/i.test(r.office_title) && r.county === p.county && isSeat(r, p.district), name: (p) => `${p.county} School Board District ${p.district}` },
  { key: "cityDistricts", label: "City commission districts", area: "local", holder: (r, p) => r.government_level === "municipal" && r.municipality === p.municipality && isSeat(r, p.district), name: (p) => `${p.municipality} District ${p.district}` },
  { key: "cities", label: "Cities (mayors)", area: "local", holder: (r, p) => r.government_level === "municipal" && r.municipality === p.name && /^mayor$/i.test(r.office_title), name: (p) => p.name },
  { key: "house", partisan: true, label: "Florida House", holder: (r, p) => /^state representative/i.test(r.office_title) && isSeat(r, p.district), name: (p) => `Florida House District ${p.district}` },
  { key: "senate", partisan: true, label: "Florida Senate", holder: (r, p) => /^state senator/i.test(r.office_title) && isSeat(r, p.district), name: (p) => `Florida Senate District ${p.district}` },
  { key: "special", label: "Special districts", area: "local", holder: () => false, name: (p) => SPECIAL.get(p.key)?.name || p.key,
    info: (p) => SPECIAL.get(p.key) || { name: p.key, type: "Special district", status: p.status } },
  { key: "congress", partisan: true, label: "U.S. House", holder: (r, p) => r.office_title === "U.S. Representative" && isSeat(r, p.district), name: (p) => `Congressional District ${p.district}` },
];
const BROWARD_VIEW = [[26.33, -80.47], [25.95, -80.07]];
const MIAMI_DADE_VIEW = [[25.98, -80.88], [25.23, -80.12]];
const LOCAL_VIEW = [[26.33, -80.88], [25.23, -80.07]];
const VIEWS = { broward: BROWARD_VIEW, "miami-dade": MIAMI_DADE_VIEW, local: LOCAL_VIEW, florida: [[31.0, -87.6], [24.4, -80.0]] };
let SPECIAL = new Map(); // special district key -> details from meta.json
const FLORIDA_VIEW = [[31.0, -87.6], [24.4, -80.0]];
// Validated with the dataviz palette checker (CVD and contrast) on the light surface.
const PARTY_COLORS = { Republican: "#e34948", Democratic: "#2a78d6", other: "#6250d6", none: "#b9c0cc" };
const DISTRICT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const partyLabel = (party) => party || "Party not listed";
// Outline-only overlays: each layer gets its own ink and dash so it reads without relying on colour alone.
const BORDER_STYLE = {
  commission: { color: "#13294b", dashArray: null, short: (p) => `CC ${p.district}` },
  school: { color: "#1c6a45", dashArray: "8 5", short: (p) => `SB ${p.district}` },
  cityDistricts: { color: "#875800", dashArray: "2 5", short: (p) => `${p.municipality} ${p.district}` },
  cities: { color: "#4a4a4a", dashArray: "10 4 2 4", short: (p) => p.name },
  house: { color: "#6b2a7a", dashArray: "6 4", short: (p) => `House ${p.district}` },
  senate: { color: "#0b6e79", dashArray: "12 6", short: (p) => `Senate ${p.district}` },
  congress: { color: "#b3262e", dashArray: null, short: (p) => `CD ${p.district}` },
  special: { color: "#2457a6", dashArray: "3 4", short: (p) => SPECIAL.get(p.key)?.name.replace(/ (Water Control|Improvement|Drainage|Community Development|Water Management|Irrigation and Soil Conservation) District$/, "") || p.key },
};
function partyColor(party, vacant = false) {
  if (vacant || !party || party === "Party not listed" || party === "Nonpartisan") return PARTY_COLORS.none;
  return PARTY_COLORS[party] || PARTY_COLORS.other;
}

/** Census Bureau geocoder, called with JSONP because it does not send CORS headers. Nothing is stored. */
// Esri's World Geocoder answers browser requests directly (CORS) and needs no key for searches that are
// not stored. It suggests addresses as the visitor types; the Census Bureau's geocoder is the fallback.
const ARCGIS = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer";
const FLORIDA_EXTENT = "-87.7,24.3,-79.8,31.1";
async function suggestAddresses(text, signal) {
  const url = `${ARCGIS}/suggest?f=json&text=${encodeURIComponent(text)}&searchExtent=${FLORIDA_EXTENT}&countryCode=USA&category=Address,Postal,Populated%20Place&maxSuggestions=6`;
  const response = await fetch(url, { signal });
  if (!response.ok) return [];
  const data = await response.json();
  return (data.suggestions || []).filter((s) => /\bFL\b|Florida/.test(s.text));
}
/** Coordinates for an address: Esri first (using the suggestion's key when there is one), then the Census Bureau. */
async function findAddress(text, magicKey) {
  try {
    const url = `${ARCGIS}/findAddressCandidates?f=json&maxLocations=1&countryCode=USA&searchExtent=${FLORIDA_EXTENT}&outSR=4326`
      + `&SingleLine=${encodeURIComponent(text)}${magicKey ? `&magicKey=${encodeURIComponent(magicKey)}` : ""}`;
    const response = await fetch(url);
    const best = response.ok ? (await response.json()).candidates?.[0] : null;
    if (best && best.score >= 80) return { x: best.location.x, y: best.location.y, label: best.address };
  } catch { /* fall through to the Census Bureau */ }
  const census = await geocode(text);
  return census.length ? { x: census[0].coordinates.x, y: census[0].coordinates.y, label: census[0].matchedAddress } : null;
}

function geocode(address) {
  return new Promise((resolve, reject) => {
    const callback = `geocode${Date.now()}`;
    const script = document.createElement("script");
    const done = () => { clearTimeout(timer); delete window[callback]; script.remove(); };
    const timer = setTimeout(() => { done(); reject(new Error("The address service did not answer. Try again, or click your home on the map.")); }, 15000);
    window[callback] = (data) => { done(); resolve(data?.result?.addressMatches || []); };
    script.onerror = () => { done(); reject(new Error("The address service could not be reached. Try again, or click your home on the map.")); };
    const text = /\b(fl|florida)\b/i.test(address) ? address : `${address}, FL`;
    script.src = `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=${encodeURIComponent(text)}&benchmark=Public_AR_Current&format=jsonp&callback=${callback}`;
    document.head.append(script);
  });
}

function reps() {
  const app = $("#app");
  if (!window.L) {
    app.innerHTML = `<section class="panel">${empty("The map could not be loaded", "Check your connection and reload the page.")}</section>`;
    return;
  }
  withData(app, [loadOfficials, loadMeta, () => loadBoundary("counties")], (records, meta, counties) => {
    SPECIAL = new Map((meta.special_districts || []).map((d) => [d.key, d]));
    app.innerHTML = `
      <form class="rep-search panel" id="rep-form" role="search" autocomplete="off">
        <label for="rep-address" class="strong">Your address</label>
        <div class="rep-search-row">
          <div class="input-icon combo">${ICON.search}<input id="rep-address" type="text" maxlength="160" role="combobox"
            aria-autocomplete="list" aria-expanded="false" aria-controls="rep-suggest" spellcheck="false"
            placeholder="Start typing, e.g. 111 NW 1st St, Miami">
            <ul id="rep-suggest" class="suggest" role="listbox" aria-label="Suggested addresses" hidden></ul></div>
          <button class="button" type="submit">Find</button>
          <button class="button outline" type="button" id="rep-locate">${ICON.pin}Use my location</button>
        </div>
        <p class="muted small">Addresses are suggested and placed on the map by Esri's ArcGIS World Geocoder, with the U.S. Census Bureau's
        address finder as a fallback. This site does not store what you type.</p>
      </form>
      <div class="rep-layout">
        <section class="panel flush rep-map-card" aria-label="Map of districts">
          <div class="map-toolbar">
            <label class="map-field"><span>Show</span>
              <select id="rep-layer" aria-label="Districts to colour on the map">
                <option value="">No districts (borders only)</option>
                ${LAYER_GROUPS.map(([group, keys]) => `<optgroup label="${esc(group)}">${keys.map((k) => `<option value="${k}">${esc(MAP_LAYERS.find((l) => l.key === k).label)}</option>`).join("")}</optgroup>`).join("")}
              </select></label>
            <details class="borders-menu" id="rep-borders">
              <summary><span>Borders</span> <span class="count" id="rep-border-count" hidden></span></summary>
              <fieldset class="borders-list"><legend class="sr-only">Show district borders</legend>
                ${MAP_LAYERS.map((l) => `<label class="border-option"><input type="checkbox" data-border="${l.key}">
                  <svg class="line-swatch" viewBox="0 0 24 6" aria-hidden="true"><line x1="1" y1="3" x2="23" y2="3" stroke="${BORDER_STYLE[l.key].color}" stroke-width="2.5" ${BORDER_STYLE[l.key].dashArray ? `stroke-dasharray="${BORDER_STYLE[l.key].dashArray}"` : ""}/></svg>
                  <span>${esc(l.label.replace(" (mayors)", ""))}</span></label>`).join("")}
                <p class="muted small borders-note">The coloured layer already shows its own borders.</p>
              </fieldset>
            </details>
            <label class="switch"><input type="checkbox" role="switch" data-streets><span class="switch-track" aria-hidden="true"></span><span>Street map</span></label>
          </div>
          <div id="rep-map" class="rep-map"></div>
          <p class="muted small rep-map-note">District lines: U.S. Census Bureau (Congress and the Legislature, 2022 plans), Broward County GIS,
          Miami-Dade County GIS and City of Miami GIS (county, school board, city and special districts).
          Florida redrew its congressional districts for members elected in November 2026; until they take office in January 2027 the 2022 districts apply.</p>
        </section>
        <section class="panel rep-panel" aria-live="polite" id="rep-panel"></section>
      </div>`;

    const map = L.map("rep-map", { scrollWheelZoom: false, zoomSnap: 0.5 });
    // A plain background (land, county lines, water) keeps the districts readable; streets are optional.
    const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });
    map.createPane("base").style.zIndex = 250;
    const base = L.geoJSON(counties, {
      pane: "base", interactive: false, attribution: "Boundaries: U.S. Census Bureau, Broward County GIS, Miami-Dade County GIS",
      style: { color: "#c3cad6", weight: 1, fillColor: "#ffffff", fillOpacity: 1 },
    }).addTo(map);
    function setStreets(on) {
      if (on) { streets.addTo(map); base.setStyle({ fillOpacity: 0, opacity: 0.5 }); }
      else { streets.remove(); base.setStyle({ fillOpacity: 1, opacity: 1 }); }
      $("[data-streets]", app).checked = on;
    }
    map.fitBounds(BROWARD_VIEW);
    map.on("focus", () => map.scrollWheelZoom.enable());
    map.on("blur", () => map.scrollWheelZoom.disable());

    const panel = $("#rep-panel");
    const shown = L.layerGroup().addTo(map);
    const yours = L.layerGroup().addTo(map);
    let pin = null;
    let lookupHits = null;
    function showHit(index) {
      yours.clearLayers();
      const hit = lookupHits?.found[index];
      if (hit) L.geoJSON(hit.feature, { style: { color: "#13294b", weight: 3, fill: false }, interactive: false }).addTo(yours);
    }
    let activeLayer = "";

    const portrait = (r) =>
      L.divIcon({ className: "rep-marker", html: avatar(r, "sm"), iconSize: [40, 40], iconAnchor: [20, 20] });

    /** A layer's features; city limits are limited to the counties with city officials. */
    async function layerData(spec) {
      const data = await loadBoundary(spec.key);
      if (spec.key !== "cities") return data;
      const local = (await loadBoundary("counties")).features.filter((f) => LOCAL_COUNTIES.includes(f.properties.name));
      const countyOf = (f) => { const p = labelPoint(f.geometry); return p && local.find((c) => pointInGeometry(p[0], p[1], c.geometry))?.properties.name; };
      return { ...data, features: data.features.map((f) => ({ ...f, properties: { ...f.properties, county: countyOf(f) } })).filter((f) => f.properties.county) };
    }

    // Border overlays, independent of the coloured layer.
    const borders = new Map();
    function drawBorderLabels() {
      for (const entry of borders.values()) {
        const visible = entry.count <= 40 || map.getZoom() >= 9; // 120 House labels would bury the statewide view
        if (visible && !map.hasLayer(entry.labels)) entry.labels.addTo(map);
        if (!visible && map.hasLayer(entry.labels)) entry.labels.remove();
      }
    }
    function updateBorderCount() {
      const badge = $("#rep-border-count");
      badge.textContent = String(borders.size);
      badge.hidden = borders.size === 0;
    }
    async function toggleBorder(key) {
      const button = $(`input[data-border="${key}"]`, app);
      if (borders.has(key)) {
        const entry = borders.get(key);
        entry.lines.remove();
        entry.labels.remove();
        borders.delete(key);
        button.checked = false;
        updateBorderCount();
        return;
      }
      const spec = MAP_LAYERS.find((l) => l.key === key);
      const style = BORDER_STYLE[key];
      const data = await layerData(spec);
      const lines = L.geoJSON(data, { style: { color: style.color, weight: 2.5, opacity: 0.9, fill: false, dashArray: style.dashArray }, interactive: false }).addTo(map);
      const labels = L.layerGroup(data.features.map((f) => {
        const at = labelPoint(f.geometry);
        return at ? L.tooltip({ permanent: true, direction: "center", className: "border-label", interactive: false })
          .setLatLng([at[1], at[0]]).setContent(`<span style="color:${style.color}">${esc(style.short(f.properties))}</span>`) : null;
      }).filter(Boolean));
      borders.set(key, { lines, labels, count: data.features.length });
      button.checked = true;
      updateBorderCount();
      drawBorderLabels();
    }
    map.on("zoomend", drawBorderLabels);

    let colorMode = "party";
    let markers = L.layerGroup();
    let current = null; // { spec, group, rows }

    /** Pick a fill per district: party colours, or (nonpartisan offices) map colouring so neighbours differ. */
    const oneParty = (holders) => new Set(holders.map((h) => h?.party || "")).size <= 1;
    function districtColors(features, holders, partisan) {
      if (partisan && colorMode === "party" && !oneParty(holders)) return features.map((f, i) => partyColor(holders[i]?.party, !holders[i]));
      const boxes = features.map((f) => L.geoJSON(f).getBounds());
      const chosen = [];
      features.forEach((f, i) => {
        const taken = new Set(chosen.filter((c, j) => boxes[j].intersects(boxes[i])).map((c) => c));
        // Least-used colour that no overlapping neighbour has, so small layers get a different colour per district.
        const uses = (c) => chosen.filter((x) => x === c).length;
        const free = DISTRICT_COLORS.filter((c) => !taken.has(c));
        chosen[i] = (free.length ? free : DISTRICT_COLORS).reduce((best, c) => (uses(c) < uses(best) ? c : best));
      });
      return chosen;
    }

    function drawMarkers() {
      if (!current) return;
      const many = current.rows.length > 40;
      const visible = !many || map.getZoom() >= 9;
      if (visible && !map.hasLayer(markers)) markers.addTo(map);
      if (!visible && map.hasLayer(markers)) markers.remove();
    }
    map.on("zoomend", drawMarkers);

    function legendPanel() {
      const { spec, rows } = current;
      const single = oneParty(rows.map((r) => r.holder));
      const partisan = spec.partisan && colorMode === "party" && !single;
      const counts = {};
      for (const row of rows) {
        const key = row.holder ? partyLabel(row.holder.party) : "Vacant or not listed";
        counts[key] = (counts[key] || 0) + 1;
      }
      const legend = partisan
        ? `<ul class="legend-row" aria-label="Party colours">${Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([label, n]) =>
            `<li><span class="swatch-dot" style="background:${partyColor(label === "Vacant or not listed" ? null : label, label === "Vacant or not listed")}"></span>${esc(label)} <span class="muted tabular">${n}</span></li>`).join("")}</ul>`
        : spec.key === "special" ? `<p class="muted small">In Broward, water control, drainage and improvement districts manage canals and stormwater; in Miami-Dade,
            community development districts build and maintain roads, drainage and amenities for a neighbourhood. Countywide and regional districts
            (children's services, water management, hospital and soil and water districts) appear when you look up an address.</p>`
        : `<p class="muted small">Colours only separate neighbouring districts. ${!spec.partisan ? "These offices are nonpartisan."
            : single && rows[0]?.holder?.party ? `Every seat is held by ${esc({ Democratic: "a Democrat", Republican: "a Republican" }[rows[0].holder.party] || "the same party")}, so party colours would paint them all alike.` : ""}</p>`;
      panel.innerHTML = `
        <div class="panel-top"><div><h2>Who represents where</h2>
          <p class="muted small">${esc(spec.label)} · ${plural(rows.length, "district")}</p></div></div>
        <div class="layer-tools">
          ${spec.partisan ? `<div class="chips" role="group" aria-label="Colour districts by">
            <button type="button" class="chip" data-color="party" aria-pressed="${colorMode === "party"}">By party</button>
            <button type="button" class="chip" data-color="district" aria-pressed="${colorMode === "district"}">By district</button></div>` : ""}
          <div class="chips" role="group" aria-label="Zoom the map">
            <button type="button" class="chip" data-zoom="broward">Broward</button>
            <button type="button" class="chip" data-zoom="miami-dade">Miami-Dade</button>
            ${spec.area === "local" ? "" : `<button type="button" class="chip" data-zoom="florida">All of Florida</button>`}</div>
        </div>
        ${legend}
        ${rows.length > 12 ? `<div class="input-icon gap-top">${ICON.search}<input type="search" class="district-filter" aria-label="Filter districts" placeholder="Filter by name, district or party"></div>` : ""}
        <ul class="district-list">${rows.map((row, i) => `<li data-row="${i}">
          <button type="button" class="district-row" data-focus="${i}">
            <span class="swatch-bar" style="background:${row.color}"></span>
            ${row.info ? "" : row.holder ? avatar(row.holder, "sm") : '<span class="avatar sm blank" aria-hidden="true">—</span>'}
            <span><span class="strong">${esc(row.info ? row.info.name : row.holder ? row.holder.full_name : "Vacant or not listed")}</span>
              <span class="muted small">${row.info ? `${esc(row.info.type)} · ${esc(row.info.status)}${row.info.note ? " · name not confirmed" : ""}`
                : `${esc(row.title)}${row.holder?.party ? ` · ${esc(partyLabel(row.holder.party))}` : ""}`}</span></span>
          </button>
          ${row.holder ? `<a class="small" href="${profileHref(row.holder)}">Profile</a>` : safeUrl(row.info?.website) ? `<a class="small" href="${esc(row.info.website)}" target="_blank" rel="noopener noreferrer">Website</a>` : ""}</li>`).join("")}</ul>
        <p class="muted small fine">Click a name here to zoom to that district. Click anywhere on the map, or search an address above, to see everyone who represents that spot.</p>`;
    }

    function highlight(index, on) {
      const row = current?.rows[index];
      if (!row) return;
      row.layer.setStyle(on ? { weight: 3, color: "#13294b", fillOpacity: 0.55 } : { weight: 1.5, color: "#ffffff", fillOpacity: 0.38 });
      if (on) row.layer.bringToFront();
    }

    async function showLayer(key, { keepView = false, select = false } = {}) {
      activeLayer = select || keepView ? key : key === activeLayer ? "" : key;
      $("#rep-layer").value = activeLayer;
      // The coloured layer already draws its own borders; don't stack a second copy on it.
      if (borders.has(activeLayer)) await toggleBorder(activeLayer);
      for (const box of app.querySelectorAll("input[data-border]")) box.disabled = box.dataset.border === activeLayer;
      shown.clearLayers();
      markers.clearLayers();
      current = null;
      if (!activeLayer) { intro(); return; }
      const spec = MAP_LAYERS.find((l) => l.key === activeLayer);
      const data = await layerData(spec);
      const features = [...data.features].sort((a, b) => spec.name(a.properties).localeCompare(spec.name(b.properties), "en", { numeric: true }));
      const holders = features.map((f) => records.find((r) => spec.holder(r, f.properties)) || null);
      const colors = districtColors(features, holders, spec.partisan);
      const rows = features.map((f, i) => ({ feature: f, holder: holders[i], color: colors[i], title: spec.name(f.properties), info: spec.info?.(f.properties) }));
      rows.forEach((row, i) => {
        row.layer = L.geoJSON(row.feature, {
          style: { color: "#ffffff", weight: 1.5, fillColor: row.color, fillOpacity: 0.38, dashArray: row.holder ? null : "4 4" },
        }).addTo(shown);
        const who = row.info ? `${esc(row.info.type)} · ${esc(row.info.status)}`
          : row.holder ? `<strong>${esc(row.holder.full_name)}</strong>${row.holder.party ? ` (${esc(partyLabel(row.holder.party))})` : ""}` : "Vacant or not listed";
        row.layer.bindTooltip(`${esc(row.title)}<br>${who}`, { sticky: true });
        row.layer.on("mouseover", () => highlight(i, true));
        row.layer.on("mouseout", () => highlight(i, false));
        const at = labelPoint(row.feature.geometry);
        if (row.holder && at) {
          L.marker([at[1], at[0]], { icon: portrait(row.holder), title: `${row.holder.full_name}, ${row.title}`, keyboard: true })
            .bindPopup(`<strong>${esc(row.holder.full_name)}</strong><br>${esc(row.holder.office_title)}<br><span class="muted">${esc(row.title)}</span><br><a href="${profileHref(row.holder)}">View profile</a>`)
            .addTo(markers);
        }
      });
      current = { spec, rows };
      if (!pin) {
        legendPanel();
        if (!keepView) map.fitBounds(spec.area === "local" ? LOCAL_VIEW : L.featureGroup(rows.map((r) => r.layer)).getBounds(), { padding: [10, 10] });
      }
      drawMarkers();
    }

    panel.addEventListener("click", (event) => {
      const color = event.target.closest("[data-color]");
      if (color && current) { colorMode = color.dataset.color; showLayer(current.spec.key, { keepView: true }); return; }
      const zoom = event.target.closest("[data-zoom]");
      if (zoom) { map.fitBounds(VIEWS[zoom.dataset.zoom] || FLORIDA_VIEW); return; }
      const focus = event.target.closest("[data-focus]");
      if (focus && current) {
        const row = current.rows[Number(focus.dataset.focus)];
        map.fitBounds(row.layer.getBounds(), { padding: [20, 20], maxZoom: 14 });
        row.layer.openTooltip(row.layer.getBounds().getCenter());
      }
    });
    panel.addEventListener("mouseover", (event) => { const r = event.target.closest("[data-focus]"); if (r) highlight(Number(r.dataset.focus), true); });
    const hitTag = (event) => event.target.closest?.("[data-hit]");
    panel.addEventListener("mouseover", (event) => { const t = hitTag(event); if (t) showHit(Number(t.dataset.hit)); });
    panel.addEventListener("focusin", (event) => { const t = hitTag(event); if (t) showHit(Number(t.dataset.hit)); });
    panel.addEventListener("mouseout", (event) => { if (hitTag(event) && lookupHits) showHit(lookupHits.current); });
    panel.addEventListener("click", (event) => {
      const t = hitTag(event);
      if (!t || !lookupHits) return;
      lookupHits.current = Number(t.dataset.hit);
      for (const tag of panel.querySelectorAll("[data-hit]")) tag.setAttribute("aria-pressed", String(tag === t));
      showHit(lookupHits.current);
      map.fitBounds(L.geoJSON(lookupHits.found[lookupHits.current].feature).getBounds().pad(0.15), { maxZoom: 15 });
    });
    panel.addEventListener("mouseout", (event) => { const r = event.target.closest("[data-focus]"); if (r) highlight(Number(r.dataset.focus), false); });
    panel.addEventListener("input", (event) => {
      if (!event.target.matches(".district-filter") || !current) return;
      const q = fold(event.target.value.trim());
      current.rows.forEach((row, i) => {
        const text = fold([row.title, row.holder?.full_name, row.holder && partyLabel(row.holder.party)].join(" "));
        $(`[data-row="${i}"]`, panel).hidden = Boolean(q) && !text.includes(q);
      });
    });

    function specialSummary(place) {
      const here = SPECIAL.get(place.special);
      const others = [...SPECIAL.values()].filter((d) => d.area !== "mapped" && (!d.county || d.county === place.county));
      const item = (d, lead) => `<li><span class="strong">${esc(d.name)}</span> <span class="muted small">${esc(d.type)}${d.area_note ? ` · ${esc(d.area_note)}` : ""}</span>
        ${lead ? `<br><span class="small">${esc(d.board || "")}</span>` : ""}
        ${d.note ? `<br><span class="muted small">${esc(d.note)}</span>` : ""}
        <span class="small">${[d.phone ? `<a href="${telHref(d.phone)}">${esc(d.phone)}</a>` : "", safeUrl(d.website) ? `<a href="${esc(d.website)}" target="_blank" rel="noopener noreferrer">Website</a>` : "",
          ...(d.sources || []).slice(0, 1).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Source</a>`)].filter(Boolean).join(" · ")}</span></li>`;
      return `<section class="special-box fine"><h3 class="group">Special districts</h3>
        <p class="muted small">${here ? "The special district mapped at this spot:" : "This spot isn't inside a mapped special district."}</p>
        ${here ? `<ul class="plain special-list">${item(here, true)}</ul>` : ""}
        <p class="muted small gap-top">Countywide and regional districts:</p>
        <ul class="plain special-list">${others.map((d) => item(d, false)).join("")}</ul></section>`;
    }

    function intro() {
      panel.innerHTML = `
        <h2>Find who represents you</h2>
        <p class="muted">Search an address, use your location, or click anywhere on the map. You'll see your members of Congress,
        state legislators, statewide officials, county commissioner, school board member and city officials, each matched to the
        district that contains the spot you chose.</p>
        <p class="muted small gap-top">Want the big picture instead? Choose a layer above the map to see every district with its
        representative's photo.</p>`;
    }

    async function lookup(lat, lon, label) {
      if (pin) pin.remove();
      pin = L.marker([lat, lon], { title: label || "Selected location" }).addTo(map);
      panel.innerHTML = loading("Finding your districts");
      const county = featureAt(counties, lon, lat)?.properties.name;
      if (!county) {
        panel.innerHTML = empty("That spot is outside Florida", "Choose a place inside Florida, or check the address.");
        return;
      }
      const [cities, congress, senate, house] = await Promise.all(["cities", "congress", "senate", "house"].map(loadBoundary));
      const place = {
        county,
        municipality: featureAt(cities, lon, lat)?.properties.name || null,
        congress: featureAt(congress, lon, lat)?.properties.district,
        senate: featureAt(senate, lon, lat)?.properties.district,
        house: featureAt(house, lon, lat)?.properties.district,
      };
      const hits = [
        { label: "U.S. House", feature: featureAt(congress, lon, lat) },
        { label: "Florida Senate", feature: featureAt(senate, lon, lat) },
        { label: "Florida House", feature: featureAt(house, lon, lat) },
      ];
      if (LOCAL_COUNTIES.includes(county)) {
        const mine = (layer) => ({ ...layer, features: layer.features.filter((f) => f.properties.county === county) });
        const [commission, school, cityDistricts, specialLayer] = (await Promise.all(["commission", "school", "cityDistricts", "special"].map(loadBoundary))).map(mine);
        const own = cityDistricts.features.filter((f) => f.properties.municipality === place.municipality);
        const cityDistrict = own.find((f) => pointInGeometry(lon, lat, f.geometry));
        Object.assign(place, {
          commission: featureAt(commission, lon, lat)?.properties.district,
          school: featureAt(school, lon, lat)?.properties.district,
          schoolDistricts: school.features.map((f) => f.properties.district),
          cityDistricts: own.map((f) => f.properties.district),
          cityDistrict: cityDistrict?.properties.district,
        });
        hits.push({ label: "County Commission", feature: featureAt(commission, lon, lat) }, { label: "School Board", feature: featureAt(school, lon, lat) });
        const specialHere = featureAt(specialLayer, lon, lat);
        place.special = specialHere?.properties.key || null;
        place.countywideSpecial = [...SPECIAL.values()].filter((d) => d.area !== "mapped" && (!d.county || d.county === county)).map((d) => d.key);
        if (specialHere) hits.push({ label: SPECIAL.get(place.special)?.name || place.special, feature: { ...specialHere, properties: { ...specialHere.properties, district: "" } } });
        if (cityDistrict) hits.push({ label: `${place.municipality} Commission`, feature: cityDistrict });
      }

      // One outline at a time: the most local district, or whichever label the visitor points at.
      const found = hits.filter((h) => h.feature);
      lookupHits = { found, current: found.length - 1 };
      showHit(lookupHits.current);
      const { groups, judges } = representativesFor(records, place, meta.vacancies || []);
      const local = LOCAL_COUNTIES.includes(county);
      // Results are grouped the way ballots and civic tools group them: by level of government, most local last.
      const tabs = [
        ...groups.map((g) => ({ key: g.level, label: LEVEL_LABELS[g.level], count: g.count })),
        ...(local ? [{ key: "special", label: "Special districts", count: null }] : []),
        ...(judges.length ? [{ key: "courts", label: "Courts", count: judges.length }] : []),
      ];
      const total = groups.reduce((n, g) => n + g.count, 0);
      const tags = [
        `<li><span class="badge">${esc(county)} County</span></li>`,
        place.municipality ? `<li><span class="badge">${esc(place.municipality)}</span></li>` : `<li><span class="badge outline">Unincorporated</span></li>`,
        ...found.map((h, i) => `<li><button type="button" class="badge outline hit-tag" data-hit="${i}" aria-pressed="${i === lookupHits.current}"
          title="Show this district on the map">${esc(h.label)} ${esc(districtLabel(h.feature.properties.district))}</button></li>`),
      ].join("");
      const body = groups
        .map((g) => `<section class="roster-level" data-level="${g.level}"><h3 class="group">${esc(LEVEL_LABELS[g.level])} <span class="count">${formatNumber(g.count)}</span></h3>
          ${g.sections.map((s) => `<div class="roster-section"><h4>${esc(s.name)}</h4><ul class="people">${s.items.map((r) => personCard(r, { contact: true })).join("")}</ul></div>`).join("")}</section>`)
        .join("");
      const covered = !place.municipality || records.some((r) => r.municipality === place.municipality);
      const partial = local
        ? (covered ? "" : `<p class="notice small">${esc(place.municipality)}'s council isn't in the directory yet: its website couldn't be collected automatically.</p>`)
        : `<p class="notice small">Outside Broward and Miami-Dade counties there are no district maps for county or city seats yet, so the
           whole county commission${covered && place.municipality ? ` and ${esc(place.municipality)}'s council are` : " is"} listed where the
           directory has them. Coverage of county and city offices is being added county by county.</p>`;
      panel.innerHTML = `
        <div class="panel-top rep-results-top"><div><h2>Your representatives</h2>
          <p class="muted small">${esc(label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`)} · ${plural(total, "official")}</p></div>
          <div class="rep-actions">
            <button type="button" class="button outline small-button" data-copy-link>Copy link</button>
            <a class="details" href="county.html?name=${encodeURIComponent(county)}">${esc(county)} County page${ICON.arrow}</a></div></div>
        <ul class="tag-list">${tags}</ul>
        <div class="chips rep-filter" role="group" aria-label="Show officials by level">
          <button type="button" class="chip" data-level-filter="" aria-pressed="true">All</button>
          ${tabs.map((t) => `<button type="button" class="chip" data-level-filter="${t.key}" aria-pressed="false">${esc(t.label)}${t.count != null ? ` <span class="count">${formatNumber(t.count)}</span>` : ""}</button>`).join("")}
        </div>
        ${partial}
        <div class="roster">${body || empty("No officials found for this spot")}</div>
        ${local ? `<div data-level="special">${specialSummary(place)}</div>` : ""}
        ${judges.length ? `<details class="roster-section fine" data-level="courts"><summary><h4>Courts <span class="count">${formatNumber(judges.length)}</span></h4></summary>
          <p class="muted small">Judges and justices whose courts cover this spot. Most are appointed or elected to serve the whole county, circuit or state.</p>
          ${groupRoster(judges).map((g) => g.sections.map((s) => `<h4 class="gap-top">${esc(s.name)} <span class="count">${formatNumber(s.items.length)}</span></h4>
            ${s.items.length > LONG_SECTION ? `<p class="small"><a href="county.html?name=${encodeURIComponent(county)}">See all ${formatNumber(s.items.length)} on the ${esc(county)} County page</a></p>`
              : `<ul class="people">${s.items.map((r) => personCard(r, { contact: true })).join("")}</ul>`}`).join("")).join("")}
        </details>` : ""}`;
      if (!activeLayer) {
        const local = found.at(-1);
        map.fitBounds((local ? L.geoJSON(local.feature).getBounds() : L.latLngBounds([[lat, lon], [lat, lon]])).pad(0.2), { maxZoom: 15 });
      }
      const next = params();
      next.set("lat", lat.toFixed(5));
      next.set("lon", lon.toFixed(5));
      window.history.replaceState(null, "", `${window.location.pathname}?${next}`);
    }

    // Address box: a combobox (WAI-ARIA pattern) with suggestions as you type.
    const input = $("#rep-address");
    const list = $("#rep-suggest");
    let suggestions = [];
    let active = -1;
    let pending = null;
    let timer = null;
    const closeList = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
    const renderList = () => {
      if (!suggestions.length) { closeList(); return; }
      list.innerHTML = suggestions.map((s, i) => `<li role="option" id="rep-suggest-${i}" data-suggest="${i}" aria-selected="${i === active}">${ICON.pin}<span>${esc(s.text.replace(/, USA$/, ""))}</span></li>`).join("");
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (active >= 0) input.setAttribute("aria-activedescendant", `rep-suggest-${active}`);
      else input.removeAttribute("aria-activedescendant");
    };
    async function go(text, magicKey) {
      closeList();
      if (!text) return;
      panel.innerHTML = loading("Looking up the address");
      try {
        const place = await findAddress(text, magicKey);
        if (!place) {
          panel.innerHTML = empty("That address wasn't found", "Check the spelling and include the city, or click your home on the map.");
          return;
        }
        input.value = place.label.replace(/, USA$/, "");
        lookup(place.y, place.x, input.value);
      } catch (error) {
        panel.innerHTML = empty("The address could not be looked up", esc(error.message));
      }
    }
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const text = input.value.trim();
      if (text.length < 3) { suggestions = []; closeList(); return; }
      timer = setTimeout(async () => {
        pending?.abort();
        pending = new AbortController();
        try {
          suggestions = await suggestAddresses(text, pending.signal);
          active = -1;
          renderList();
        } catch { /* typing again aborts the previous request */ }
      }, 200);
    });
    input.addEventListener("keydown", (event) => {
      if (list.hidden) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        // Down from the last option (or up from the first) returns to what was typed, as native comboboxes do.
        if (event.key === "ArrowDown") active = active + 1 >= suggestions.length ? -1 : active + 1;
        else active = active - 1 < -1 ? suggestions.length - 1 : active - 1;
        renderList();
      } else if (event.key === "Escape") {
        closeList();
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        go(suggestions[active].text, suggestions[active].magicKey);
      }
    });
    input.addEventListener("blur", () => setTimeout(closeList, 150));
    list.addEventListener("mousedown", (event) => {
      const option = event.target.closest("[data-suggest]");
      if (!option) return;
      event.preventDefault();
      const s = suggestions[Number(option.dataset.suggest)];
      go(s.text, s.magicKey);
    });
    $("#rep-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const first = suggestions[0];
      const text = input.value.trim();
      go(text, first && first.text.toLowerCase().startsWith(text.toLowerCase().slice(0, 6)) ? first.magicKey : undefined);
    });
    $("#rep-locate").addEventListener("click", () => {
      if (!navigator.geolocation) {
        panel.innerHTML = empty("Your browser can't share its location", "Search an address or click the map instead.");
        return;
      }
      panel.innerHTML = loading("Finding your location");
      navigator.geolocation.getCurrentPosition(
        (position) => lookup(position.coords.latitude, position.coords.longitude, "Your current location"),
        () => { panel.innerHTML = empty("Your location wasn't shared", "Search an address or click the map instead."); },
        { enableHighAccuracy: false, timeout: 15000 },
      );
    });
    map.on("click", (event) => lookup(event.latlng.lat, event.latlng.lng, "Point chosen on the map"));
    $("#rep-layer").addEventListener("change", (event) => {
      showLayer(event.target.value, { select: true }).catch((error) => { panel.innerHTML = empty("That layer could not be loaded", esc(error.message)); });
    });
    app.addEventListener("change", (event) => {
      if (event.target.matches("[data-streets]")) setStreets(event.target.checked);
      if (event.target.matches("input[data-border]")) {
        toggleBorder(event.target.dataset.border).catch((error) => { panel.innerHTML = empty("Those borders could not be loaded", esc(error.message)); });
      }
    });
    // Close the borders menu when clicking elsewhere, as native menus do.
    document.addEventListener("click", (event) => {
      const menu = $("#rep-borders");
      if (menu?.open && !menu.contains(event.target)) menu.open = false;
    });
    app.addEventListener("click", (event) => {
      const filter = event.target.closest("[data-level-filter]");
      if (filter) {
        const level = filter.dataset.levelFilter;
        for (const chip of panel.querySelectorAll("[data-level-filter]")) chip.setAttribute("aria-pressed", String(chip === filter));
        for (const block of panel.querySelectorAll("[data-level]")) block.hidden = Boolean(level) && block.dataset.level !== level;
        const courts = panel.querySelector('details[data-level="courts"]');
        if (courts && level === "courts") courts.open = true;
      }
      const copy = event.target.closest("[data-copy-link]");
      if (copy) {
        navigator.clipboard?.writeText(window.location.href).then(() => { copy.textContent = "Link copied"; setTimeout(() => { copy.textContent = "Copy link"; }, 2000); },
          () => { copy.textContent = "Copy the address bar"; });
      }
    });

    const lat = Number(params().get("lat"));
    const lon = Number(params().get("lon"));
    if (lat && lon) lookup(lat, lon);
    else showLayer("commission");
  }, "Loading the map");
}

// -- sources ----------------------------------------------------------------------
function sources() {
  const app = $("#app");
  withData(app, [loadSources], (list) => {
    const healthy = list.filter((s) => s.status === "success" || s.status === "partial").length;
    const failing = list.filter((s) => s.status === "failed").length;
    const successes = list.map((s) => s.last_successful_collection).filter(Boolean).sort();
    const tile = (label, value) => `<div class="tile"><dt>${label}</dt><dd class="tabular">${value}</dd></div>`;
    const badgeClass = { success: "green", partial: "amber", failed: "red" };
    app.innerHTML = `
      <dl class="tiles tiles-4">
        ${tile("Sources", formatNumber(list.length))}
        ${tile("Healthy", formatNumber(healthy))}
        ${tile("Failing", formatNumber(failing))}
        ${tile("Last successful collection", esc(formatDateTime(successes.at(-1))))}
      </dl>
      <section class="panel flush gap-top">
        ${list.length === 0
          ? empty("Nothing has been collected yet", "The first collection runs in GitHub Actions. Its results appear here once they are published.")
          : `<div class="table-wrap always"><table><thead><tr><th scope="col">Source</th><th scope="col">Level</th><th scope="col">Status</th>
            <th scope="col">Last successful collection</th><th scope="col" class="right">Records</th><th scope="col">Last error</th></tr></thead><tbody>
            ${list.map((s) => `<tr>
              <td><p class="strong">${esc(s.name)}</p>${safeUrl(s.url) ? `<a class="small break" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url.replace(/^https?:\/\//, ""))}${ICON.external}</a>` : ""}</td>
              <td>${levelBadge(s.level)}</td>
              <td><span class="badge ${badgeClass[s.status] || "outline"}">${esc(SOURCE_STATUS_LABELS[s.status] || "Not collected yet")}</span></td>
              <td class="tabular nowrap">${esc(formatDateTime(s.last_successful_collection))}</td>
              <td class="tabular right">${formatNumber(s.records_collected)}</td>
              <td class="small">${s.last_error ? `<span class="error-text">${esc(s.last_error)}</span>` : '<span class="muted">None</span>'}</td>
            </tr>`).join("")}</tbody></table></div>`}
      </section>`;
  }, "Loading sources");
}

// -- about ------------------------------------------------------------------------
function about() {
  const list = $("#source-list");
  if (list) {
    withData(list, [loadSources], (sources) => {
      const order = ["federal", "state", "county", "municipal"];
      const byLevel = order.map((level) => [level, sources.filter((s) => s.level === level)]).filter(([, items]) => items.length);
      list.innerHTML = byLevel.map(([level, items]) => `<details class="fine source-group"${level === "municipal" ? "" : " open"}>
        <summary><strong>${esc(LEVEL_LABELS[level])}</strong> <span class="muted small">${plural(items.length, "source")} ·
          ${formatNumber(items.reduce((n, s) => n + (s.records_collected || 0), 0))} records</span></summary>
        <ul>${items.map((s) => `<li>${safeUrl(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)}</a>` : esc(s.name)}
          <span class="muted small">· ${plural(s.records_collected || 0, "record")}${s.status === "failed" ? " · last attempt failed" : ""}</span></li>`).join("")}</ul>
      </details>`).join("");
    }, "Loading sources");
  }
  const box = $("#coverage");
  withData(box, [loadMeta], (meta) => {
    const c = meta.coverage;
    box.innerHTML = `
      <div class="panel flush"><div class="table-wrap always"><table>
        <thead><tr><th scope="col">Office</th><th scope="col">Level</th><th scope="col" class="right">Collected</th><th scope="col" class="right">Seats</th><th scope="col" class="right">Coverage</th></tr></thead>
        <tbody>${c.rows.map((r) => `<tr><td class="strong">${esc(r.office_title)}</td><td>${esc(LEVEL_LABELS[r.government_level])}</td>
          <td class="right tabular">${r.collected}</td><td class="right tabular">${r.expected}</td><td class="right tabular">${r.percent}%</td></tr>`).join("")}</tbody>
      </table></div></div>
      <p>${esc(c.explanation)}</p>
      <p class="strong">Not yet covered:</p>
      <ul>${c.not_yet_covered.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;

    const report = $("#report");
    const url = safeUrl(meta.report_url);
    if (url) {
      report.innerHTML = `To report an error, <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">open a correction request</a>
        with a link to the profile and, if you can, to an official page showing the correct information.`;
    } else if (meta.contact_email) {
      report.innerHTML = `To report an error, email <a href="mailto:${esc(meta.contact_email)}">${esc(meta.contact_email)}</a>
        with a link to the profile and, if you can, to an official page showing the correct information.`;
    }
  }, "Loading coverage");
}

// -- start ------------------------------------------------------------------------
const PAGES = { home, directory, profile, counties, county, reps, sources, about };
const page = document.body.dataset.page;
renderChrome(page === "profile" ? "official" : page);
PAGES[page]?.();
