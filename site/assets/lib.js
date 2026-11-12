// Pure helpers: search, filtering, sorting, formatting and export.
// No DOM access here, so these can be tested with `node --test`.

export const LEVELS = ["federal", "state", "county", "municipal"];

export const LEVEL_LABELS = {
  federal: "Federal",
  state: "State",
  county: "County",
  municipal: "Municipal",
};

export const VERIFICATION_LABELS = {
  source_verified: "Verified against the source",
  corrected: "Corrected by the editors",
  manual: "Added by hand from an official page",
};

export const SOURCE_STATUS_LABELS = {
  success: "Healthy",
  partial: "Partly collected",
  failed: "Failing",
};

export function fold(text) {
  return String(text ?? "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

const haystacks = new WeakMap();

function haystack(record) {
  let text = haystacks.get(record);
  if (text === undefined) {
    text = fold(
      [
        record.full_name,
        record.office_title,
        record.jurisdiction,
        record.district ? `district ${record.district}` : "",
        record.seat_label,
        record.county,
        ...(record.counties || []),
        record.municipality,
        record.party,
      ].join(" | "),
    );
    haystacks.set(record, text);
  }
  return text;
}

/** Every word must appear somewhere in the name, office, place or district. */
export function matchesQuery(record, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const text = haystack(record);
  return words.every((word) => text.includes(word));
}

export function inCounty(record, county, includeStatewide = false) {
  return (
    record.county === county ||
    (record.counties || []).includes(county) ||
    (includeStatewide && Boolean(record.statewide))
  );
}

export function filterRecords(records, criteria = {}) {
  const { q = "", level, county, municipality, party, office_title, district } = criteria;
  return records.filter(
    (r) =>
      matchesQuery(r, q) &&
      (!level || r.government_level === level) &&
      (!county || inCounty(r, county)) &&
      (!municipality || r.municipality === municipality) &&
      (!party || r.party === party) &&
      (!office_title || r.office_title === office_title) &&
      (!district || r.district === district),
  );
}

const SORT_KEYS = {
  name: (r) => [r.last_name, r.first_name],
  position: (r) => [r.office_title, r.last_name],
  level: (r) => [LEVELS.indexOf(r.government_level), r.last_name],
  jurisdiction: (r) => [r.jurisdiction, r.last_name],
  district: (r) => [r.district_number ?? null, r.district ?? null, r.last_name],
  party: (r) => [r.party ?? null, r.last_name],
};

export const SORTABLE = Object.keys(SORT_KEYS);

function compareValues(a, b) {
  const aMissing = a === null || a === undefined || a === "";
  const bMissing = b === null || b === undefined || b === "";
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : null; // null = "missing sorts last"
  if (typeof a === "number" && typeof b === "number") return a - b;
  return fold(a).localeCompare(fold(b));
}

/** Sort a copy. Empty values always go last, in either direction. */
export function sortRecords(records, key = "name", order = "asc") {
  const get = SORT_KEYS[key] || SORT_KEYS.name;
  const direction = order === "desc" ? -1 : 1;
  return [...records].sort((x, y) => {
    const a = get(x);
    const b = get(y);
    for (let i = 0; i < a.length; i += 1) {
      const result = compareValues(a[i], b[i]);
      if (result === null) return a[i] === null || a[i] === undefined || a[i] === "" ? 1 : -1;
      if (result !== 0) return result * direction;
    }
    return String(x.id).localeCompare(String(y.id));
  });
}

export function paginate(items, page, pageSize) {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, page), pages);
  const start = (current - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), page: current, pages, total, start };
}

function distinct(values) {
  return [...new Set(values.filter((v) => v !== null && v !== undefined && v !== ""))];
}

export function filterOptions(records) {
  const byText = (a, b) => fold(a).localeCompare(fold(b));
  const districts = distinct(records.map((r) => r.district)).sort((a, b) => {
    const na = /^\d+$/.test(a) ? Number(a) : Infinity;
    const nb = /^\d+$/.test(b) ? Number(b) : Infinity;
    return na - nb || byText(a, b);
  });
  return {
    levels: LEVELS.filter((level) => records.some((r) => r.government_level === level)),
    parties: distinct(records.map((r) => r.party)).sort(byText),
    office_titles: distinct(records.map((r) => r.office_title)).sort(byText),
    municipalities: distinct(records.map((r) => r.municipality)).sort(byText),
    districts,
  };
}

export const EXPORT_COLUMNS = [
  "id", "full_name", "first_name", "middle_name", "last_name", "office_title", "government_level",
  "selection_method", "party", "district", "jurisdiction", "county", "municipality", "counties",
  "phone", "email", "official_website", "verification_status", "last_verified", "source_name", "source_url",
];

function csvCell(value) {
  const text = Array.isArray(value) ? value.join("; ") : value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(records, columns = EXPORT_COLUMNS) {
  const lines = [columns.join(",")];
  for (const record of records) lines.push(columns.map((c) => csvCell(record[c])).join(","));
  return `${lines.join("\n")}\n`;
}

export function exportPayload(records, filters, now = new Date()) {
  const statuses = {};
  for (const r of records) statuses[r.verification_status] = (statuses[r.verification_status] || 0) + 1;
  const activeFilters = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
  return {
    metadata: {
      export_timestamp: now.toISOString(),
      data_source: "Florida Government Officials Directory, compiled from official government websites",
      record_count: records.length,
      verification_status: statuses,
      filters: activeFilters,
      note: "Empty fields mean the source did not publish that information.",
    },
    officials: records.map((r) => Object.fromEntries(EXPORT_COLUMNS.map((c) => [c, r[c] ?? null]))),
  };
}

// -- formatting ---------------------------------------------------------------
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

/** Only http(s) links are ever rendered. */
export function safeUrl(url) {
  return typeof url === "string" && /^https?:\/\/[^\s]+$/i.test(url) ? url : null;
}

export function telHref(phone) {
  const digits = String(phone).split(/ext/i)[0].replace(/\D/g, "");
  const national = digits.length === 11 && digits.startsWith("1") ? digits.slice(1) : digits;
  return `tel:+1${national}`;
}

export function districtLabel(district) {
  if (!district) return "";
  return /^\d+$/.test(district) ? `District ${district}` : district;
}

/** The seat as people know it: "Group 5" for a judge, "Seat 4" for a city seat, else "District 12". */
export function seatText(record) {
  return record?.seat_label || districtLabel(record?.district);
}

export function describe(record) {
  const place = record.municipality && record.jurisdiction === record.municipality ? `City of ${record.municipality}` : record.jurisdiction;
  return [record.office_title, place, seatText(record)].filter(Boolean).join(" · ");
}

export function formatDate(value, fallback = "Not recorded") {
  if (!value) return fallback;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  // A bare date is a calendar day, not midnight UTC; build it locally so it never shifts a day.
  const date = match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

/** Bio dates can be a full date, a year and month, or a year: "2018-11" -> "Nov 2018". */
export function formatPartialDate(value, fallback = "") {
  if (!value) return fallback;
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return formatDate(text, fallback);
  const month = /^(\d{4})-(\d{2})$/.exec(text);
  if (month) {
    return new Date(Number(month[1]), Number(month[2]) - 1, 1).toLocaleDateString("en-US", { year: "numeric", month: "short" });
  }
  return /^\d{4}$/.test(text) ? text : fallback || text;
}

/** Whole years between a YYYY-MM-DD date and `now`. */
export function yearsSince(value, now = new Date()) {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(String(value || ""));
  if (!match) return null;
  const [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3] || 1)];
  let years = now.getFullYear() - y;
  if (now.getMonth() + 1 < m || (now.getMonth() + 1 === m && now.getDate() < d)) years -= 1;
  return years >= 0 ? years : null;
}

export function formatDateTime(value, fallback = "Never") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function formatNumber(value) {
  return typeof value === "number" ? value.toLocaleString("en-US") : "—";
}

export function plural(count, singular, pluralForm = `${singular}s`) {
  return `${formatNumber(count)} ${count === 1 ? singular : pluralForm}`;
}

/** Portraits are only shown from https addresses, so a page never mixes secure and insecure content. */
export function photoUrl(url) {
  return typeof url === "string" && /^https:\/\/[^\s]+$/i.test(url) ? url : null;
}

/** "Maria G. Castillo" -> "MC", used when a photo is missing or fails to load. */
export function initials(name) {
  const words = String(name || "")
    .replace(/\b(?:jr|sr|ii|iii|iv)\b\.?/gi, "")
    .split(/[\s,]+/)
    .filter((word) => /^[A-Za-zÀ-ɏ]/.test(word));
  if (!words.length) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/**
 * Who to show for a county on the map: officials tied to that county (`local`) and
 * officials who represent the whole state (`statewide`). Each group is sorted by level, then name.
 */
export function countyRoster(records, county) {
  const byLevel = (a, b) =>
    LEVELS.indexOf(a.government_level) - LEVELS.indexOf(b.government_level) ||
    String(a.last_name).localeCompare(String(b.last_name), "en");
  return {
    local: records.filter((r) => !r.statewide && inCounty(r, county)).sort(byLevel),
    statewide: records.filter((r) => r.statewide).sort(byLevel),
  };
}

/** How many officials are tied to each county (statewide officials are not counted). */
export function countyCounts(records, counties) {
  return Object.fromEntries(counties.map((name) => [name, records.filter((r) => !r.statewide && inCounty(r, name)).length]));
}

// -- county roster grouping ------------------------------------------------------------

const TITLE_RANK = [
  "governor", "lieutenant governor", "attorney general", "chief financial officer", "commissioner of agriculture",
  "mayor", "vice mayor", "deputy mayor", "assistant deputy mayor", "commissioner", "councilmember",
  "county commissioner", "sheriff", "state attorney", "public defender", "clerk", "property appraiser", "tax collector",
  "supervisor of elections",
];

function titleRank(title) {
  const t = fold(title);
  const exact = TITLE_RANK.indexOf(t);
  if (exact !== -1) return exact;
  const partial = TITLE_RANK.findIndex((rank) => t.startsWith(rank));
  return partial === -1 ? TITLE_RANK.length : partial;
}

function seatNumber(record) {
  if (typeof record.district_number === "number") return record.district_number;
  const match = /\d+/.exec(record.seat_label || record.district || "");
  return match ? Number(match[0]) : 0;
}

export function rosterOrder(a, b) {
  return (
    titleRank(a.office_title) - titleRank(b.office_title) ||
    seatNumber(a) - seatNumber(b) ||
    String(a.last_name).localeCompare(String(b.last_name), "en")
  );
}

const CONSTITUTIONAL = /^(sheriff|clerk|property appraiser|tax collector|supervisor of elections|state attorney|public defender)/i;

/** Which part of a county's roster a record belongs in. */
export function rosterSection(record) {
  const title = record.office_title || "";
  switch (record.government_level) {
    case "federal":
      return /senator/i.test(title) ? "U.S. Senate" : "U.S. House of Representatives";
    case "state":
      if (/^state senator/i.test(title)) return "Florida Senate";
      if (/^state representative/i.test(title)) return "Florida House of Representatives";
      return "Governor and Cabinet";
    case "county":
      if (/county commissioner/i.test(title)) return "County Commission";
      if (CONSTITUTIONAL.test(title)) return "Constitutional officers";
      if (/school board/i.test(title)) return "School Board";
      if (/circuit judge/i.test(title)) return "Circuit Court judges";
      if (/county court judge/i.test(title)) return "County Court judges";
      return "Other county offices";
    case "municipal":
      return record.municipality || "Municipal";
    default:
      return "Other";
  }
}

const SECTION_ORDER = [
  "U.S. Senate", "U.S. House of Representatives", "Governor and Cabinet", "Florida Senate", "Florida House of Representatives",
  "County Commission", "Constitutional officers", "School Board", "Circuit Court judges", "County Court judges", "Other county offices",
];

/**
 * Everyone who represents a county, grouped by level and then by body:
 * [{ level, sections: [{ name, items: [...records and vacancies] }] }]. Vacancies carry `vacant: true`.
 */
export function countyGroups(records, county, vacancies = []) {
  const members = records.filter((r) => r.statewide || inCounty(r, county));
  const empty = vacancies
    .filter((v) => (v.counties || []).includes(county))
    .map((v) => ({ ...v, vacant: true, full_name: "Vacant seat", last_name: "", id: `vacant-${v.office_title}-${v.district}` }));
  return LEVELS.map((level) => {
    const bySection = new Map();
    for (const item of [...members, ...empty].filter((r) => r.government_level === level)) {
      const name = rosterSection(item);
      if (!bySection.has(name)) bySection.set(name, []);
      bySection.get(name).push(item);
    }
    const sections = [...bySection.entries()]
      .map(([name, items]) => ({ name, items: items.sort(rosterOrder) }))
      .sort((a, b) => {
        const ia = SECTION_ORDER.indexOf(a.name);
        const ib = SECTION_ORDER.indexOf(b.name);
        if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
        return a.name.localeCompare(b.name, "en");
      });
    return { level, count: sections.reduce((n, s) => n + s.items.filter((i) => !i.vacant).length, 0), sections };
  }).filter((group) => group.sections.length);
}

/** Officials tied to each county, including district-based members whose district reaches into it. */
export function countyTotals(records, counties) {
  return Object.fromEntries(counties.map((name) => [name, records.filter((r) => !r.statewide && inCounty(r, name)).length]));
}
