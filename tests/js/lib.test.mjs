// Run with: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  districtLabel,
  escapeHtml,
  exportPayload,
  filterOptions,
  filterRecords,
  formatDate,
  paginate,
  safeUrl,
  sortRecords,
  telHref,
  toCsv,
} from "../../site/assets/lib.js";

// Fictional officials.
const records = [
  { id: "a", full_name: "Ana M. Rivera", first_name: "Ana", last_name: "Rivera", office_title: "State Senator",
    government_level: "state", party: "Democratic", district: "12", district_number: 12, jurisdiction: "Florida",
    counties: ["Broward", "Palm Beach"], county: null, municipality: null, verification_status: "source_verified" },
  { id: "b", full_name: "Thomas Whitfield", first_name: "Thomas", last_name: "Whitfield", office_title: "State Senator",
    government_level: "state", party: "Republican", district: "3", district_number: 3, jurisdiction: "Florida",
    counties: ["Leon"], county: null, municipality: null, verification_status: "source_verified" },
  { id: "c", full_name: "Linda Nguyễn", first_name: "Linda", last_name: "Nguyễn", office_title: "Supervisor of Elections",
    government_level: "county", party: null, district: null, district_number: null, jurisdiction: "Broward County",
    counties: [], county: "Broward", municipality: null, verification_status: "manual" },
  { id: "d", full_name: "Samuel Brooks", first_name: "Samuel", last_name: "Brooks", office_title: "Mayor",
    government_level: "municipal", party: "Nonpartisan", district: null, district_number: null, jurisdiction: "West Park",
    counties: [], county: "Broward", municipality: "West Park", verification_status: "manual" },
  { id: "e", full_name: "Maria Castillo", first_name: "Maria", last_name: "Castillo", office_title: "U.S. Senator",
    government_level: "federal", party: "Republican", district: null, district_number: null, jurisdiction: "Florida",
    counties: [], county: null, municipality: null, statewide: true, verification_status: "source_verified" },
];
const ids = (list) => list.map((r) => r.id);

test("search matches partial names, places and districts, ignoring case and accents", () => {
  assert.deepEqual(ids(filterRecords(records, { q: "riv" })), ["a"]);
  assert.deepEqual(ids(filterRecords(records, { q: "ANA rivera" })), ["a"]);
  assert.deepEqual(ids(filterRecords(records, { q: "nguyen" })), ["c"]);
  assert.deepEqual(ids(filterRecords(records, { q: "palm beach" })), ["a"]);
  assert.deepEqual(ids(filterRecords(records, { q: "west park" })), ["d"]);
  assert.deepEqual(ids(filterRecords(records, { q: "district 3" })), ["b"]);
  assert.deepEqual(ids(filterRecords(records, { q: "zzz" })), []);
});

test("filters combine", () => {
  assert.deepEqual(ids(filterRecords(records, { level: "state", party: "Republican" })), ["b"]);
  assert.deepEqual(ids(filterRecords(records, { county: "Broward" })), ["a", "c", "d"]); // statewide excluded here
  assert.deepEqual(ids(filterRecords(records, { municipality: "West Park" })), ["d"]);
  assert.deepEqual(ids(filterRecords(records, { office_title: "State Senator", district: "12" })), ["a"]);
});

test("sorting is numeric for districts and puts empty values last both ways", () => {
  assert.deepEqual(ids(sortRecords(records, "name")), ["d", "e", "c", "a", "b"]);
  assert.deepEqual(ids(sortRecords(records, "name", "desc")), ["b", "a", "c", "e", "d"]);
  assert.deepEqual(ids(sortRecords(records, "district")).slice(0, 2), ["b", "a"]);
  assert.deepEqual(ids(sortRecords(records, "party", "desc")).at(-1), "c");
  assert.deepEqual(ids(sortRecords(records, "level")), ["e", "a", "b", "c", "d"]);
});

test("pagination clamps the page number", () => {
  const page = paginate(records, 9, 2);
  assert.equal(page.page, 3);
  assert.equal(page.pages, 3);
  assert.deepEqual(ids(page.items), ["e"]);
});

test("filter options are distinct and ordered", () => {
  const options = filterOptions(records);
  assert.deepEqual(options.levels, ["federal", "state", "county", "municipal"]);
  assert.deepEqual(options.parties, ["Democratic", "Nonpartisan", "Republican"]);
  assert.deepEqual(options.districts, ["3", "12"]);
});

test("CSV export escapes values and leaves missing fields empty", () => {
  const csv = toCsv([{ ...records[0], full_name: 'Ana "Annie" Rivera, Jr.' }], ["id", "full_name", "email", "counties"]);
  assert.equal(csv, 'id,full_name,email,counties\na,"Ana ""Annie"" Rivera, Jr.",,Broward; Palm Beach\n');
});

test("JSON export carries metadata", () => {
  const payload = exportPayload(records.slice(0, 3), { level: "", county: "Broward" }, new Date("2026-11-10T12:00:00Z"));
  assert.equal(payload.metadata.record_count, 3);
  assert.equal(payload.metadata.export_timestamp, "2026-11-10T12:00:00.000Z");
  assert.deepEqual(payload.metadata.filters, { county: "Broward" });
  assert.deepEqual(payload.metadata.verification_status, { source_verified: 2, manual: 1 });
  assert.equal(payload.officials[2].email, null);
});

test("formatting never invents values and blocks unsafe links", () => {
  assert.equal(escapeHtml('<img src=x onerror="a">'), "&lt;img src=x onerror=&quot;a&quot;&gt;");
  assert.equal(safeUrl("javascript:alert(1)"), null);
  assert.equal(safeUrl("https://www.flsenate.gov"), "https://www.flsenate.gov");
  assert.equal(telHref("(850) 487-5012 ext. 4"), "tel:+18504875012");
  assert.equal(districtLabel("12"), "District 12");
  assert.equal(formatDate(null), "Not recorded");
  assert.equal(formatDate("2026-11-10"), "Nov 10, 2026");
});
