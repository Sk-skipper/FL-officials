// Page behaviour. Each page's <body data-page="..."> selects what runs.
import {
  LEVEL_LABELS,
  LEVELS,
  SOURCE_STATUS_LABELS,
  SORTABLE,
  VERIFICATION_LABELS,
  countyCounts,
  countyRoster,
  describe,
  districtLabel,
  escapeHtml as esc,
  exportPayload,
  filterOptions,
  filterRecords,
  fold,
  formatDate,
  formatDateTime,
  formatNumber,
  inCounty,
  initials,
  paginate,
  photoUrl,
  plural,
  safeUrl,
  sortRecords,
  telHref,
  toCsv,
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
  landmark:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 22h18M6 18v-7m4 7v-7m4 7v-7m4 7v-7M12 2l8 5H4l8-5Z"/></svg>',
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
        <td class="tabular">${r.district ? esc(districtLabel(r.district)) : '<span class="muted">—</span>'}</td>
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
            <button type="button" class="button outline small" data-page="${page.page - 1}"${page.page <= 1 ? " disabled" : ""}>Previous</button>
            <span class="tabular">Page ${page.page} of ${page.pages}</span>
            <button type="button" class="button outline small" data-page="${page.page + 1}"${page.page >= page.pages ? " disabled" : ""}>Next</button>
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
      const pageButton = event.target.closest("[data-page]");
      if (pageButton && !pageButton.disabled) {
        state.page = Number(pageButton.dataset.page);
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
        <section class="panel">
          <h2>Office details</h2>
          <dl class="rows">
            ${row("Full name", esc(r.full_name))}
            ${row("Official title", esc(r.office_title))}
            ${row("Government level", esc(LEVEL_LABELS[r.government_level] || r.government_level))}
            ${row("Jurisdiction", esc(r.jurisdiction))}
            ${row(counties.length > 1 ? "Counties represented" : "County", countyLinks)}
            ${r.municipality ? row("Municipality", esc(r.municipality)) : ""}
            ${row("District", esc(districtLabel(r.district)))}
            ${row("Political party", esc(r.party || ""))}
            ${row("Last verified", esc(formatDate(r.last_verified, "")))}
          </dl>
        </section>
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
            </dl>
            <p class="small fine">See something wrong? ${report}<br><span class="muted">Record id: <code>${esc(r.id)}</code></span></p>
          </section>
        </div>
      </div>`;
  }, "Loading profile");
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

function personCard(r) {
  return `<li class="person"><a href="${profileHref(r)}">${avatar(r, "lg")}<span>
    <span class="person-name">${esc(r.full_name)}</span>
    <span class="muted small">${esc(r.office_title)}${r.district ? ` · ${esc(districtLabel(r.district))}` : ""}</span>
    ${r.party ? `<span class="badge outline">${esc(r.party)}</span>` : ""}
  </span></a></li>`;
}

function counties() {
  const app = $("#app");
  withData(app, [loadOfficials, loadMeta, loadMap], (records, meta, map) => {
    const counts = countyCounts(records, meta.counties);
    const statewide = countyRoster(records, "").statewide;

    // One portrait per county on the map: the first county-level official who has a photo.
    const pins = map.counties
      .map((c) => {
        const official = countyRoster(records, c.name).local.find((r) => photoUrl(r.photo_url));
        if (!official) return "";
        const left = ((c.cx / map.width) * 100).toFixed(2);
        const top = ((c.cy / map.height) * 100).toFixed(2);
        return `<button type="button" class="pin" data-county="${esc(c.name)}" style="left:${left}%;top:${top}%"
          aria-label="${esc(official.full_name)}, ${esc(c.name)} County">${avatar(official, "xs")}</button>`;
      })
      .join("");

    const shapes = map.counties
      .map(
        (c) => `<path class="county-shape${counts[c.name] ? " has-officials" : ""}" data-county="${esc(c.name)}" d="${c.d}"
          tabindex="0" role="button" aria-pressed="false"
          aria-label="${esc(c.name)} County, ${plural(counts[c.name], "local official")}"><title>${esc(c.name)} County</title></path>`,
      )
      .join("");

    app.innerHTML = `
      <div class="map-layout">
        <section class="panel map-card" aria-label="Map of Florida counties">
          <div class="map-wrap">
            <svg viewBox="0 0 ${map.width} ${map.height}" role="group" aria-label="Florida's 67 counties. Select a county to see its officials.">${shapes}</svg>
            <div class="pins">${pins}</div>
          </div>
          <p class="muted small map-note">Select a county. Darker blue counties have officials listed. A portrait on the map is that county's
          elected official, where their source publishes a photo.</p>
        </section>
        <section class="panel map-panel" id="map-panel" aria-live="polite"></section>
      </div>
      <h2 class="section-title">All counties</h2>
      <div class="field narrow"><label for="county-filter">Find a county</label>
        <div class="input-icon">${ICON.search}<input id="county-filter" type="search" placeholder="Type a county name"></div></div>
      <div id="county-list"></div>`;

    const grid = (list) => `<ul class="people">${list.map(personCard).join("")}</ul>`;
    const panel = $("#map-panel");
    let selected = "";

    function showPanel() {
      for (const shape of app.querySelectorAll(".county-shape")) {
        const on = shape.dataset.county === selected;
        shape.classList.toggle("selected", on);
        shape.setAttribute("aria-pressed", String(on));
      }
      if (!selected) {
        panel.innerHTML = `
          <h2>Statewide officials</h2>
          <p class="muted small">These officials represent all 67 counties. Select a county on the map to add the officials tied to it.</p>
          ${statewide.length ? grid(statewide) : empty("No statewide officials yet", "None have been collected from an official source.")}`;
        return;
      }
      const { local } = countyRoster(records, selected);
      panel.innerHTML = `
        <div class="panel-top">
          <h2>${esc(selected)} County</h2>
          <span class="panel-actions">
            <a class="details" href="county.html?name=${encodeURIComponent(selected)}">Full county page${ICON.arrow}</a>
            <button type="button" class="link-button" data-clear>Show statewide</button>
          </span>
        </div>
        <h3 class="group">Elected in ${esc(selected)} County</h3>
        ${local.length ? grid(local) : `<p class="muted small">No county-level officials are listed for ${esc(selected)} County yet.</p>`}
        <h3 class="group">Represent all of Florida</h3>
        ${grid(statewide)}
        <p class="muted small fine">U.S. House and Florida Legislature members are not placed on the map, because their sources do not say
        which counties each district covers.</p>`;
    }

    function select(name) {
      selected = selected === name ? "" : name;
      showPanel();
    }

    const mapCard = $(".map-card");
    mapCard.addEventListener("click", (event) => {
      const target = event.target.closest("[data-county]");
      if (target) select(target.dataset.county);
    });
    mapCard.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = event.target.closest(".county-shape");
      if (!target) return;
      event.preventDefault();
      select(target.dataset.county);
    });
    panel.addEventListener("click", (event) => {
      if (event.target.closest("[data-clear]")) {
        selected = "";
        showPanel();
      }
    });
    showPanel();

    const summary = meta.counties.map((name) => {
      const here = records.filter((r) => inCounty(r, name));
      return { name, officials: here.length, towns: new Set(here.map((r) => r.municipality).filter(Boolean)).size };
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
const PAGES = { home, directory, profile, counties, county, sources, about };
const page = document.body.dataset.page;
renderChrome(page === "profile" ? "official" : page);
PAGES[page]?.();
