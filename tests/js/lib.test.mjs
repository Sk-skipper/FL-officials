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

test("countyGroups places district members, statewide officials and vacancies in the right bodies", async () => {
  const { countyGroups, seatText, formatPartialDate } = await import("../../site/assets/lib.js");
  const people = [
    { id: "s", full_name: "Sen A", last_name: "A", office_title: "U.S. Senator", government_level: "federal", statewide: true },
    { id: "h", full_name: "Rep B", last_name: "B", office_title: "U.S. Representative", government_level: "federal", district: "25", district_number: 25, counties: ["Broward"] },
    { id: "j", full_name: "Judge C", last_name: "C", office_title: "Circuit Judge", government_level: "county", county: "Broward", district: "5", seat_label: "Group 5" },
    { id: "m", full_name: "Mayor D", last_name: "D", office_title: "Mayor", government_level: "municipal", county: "Broward", municipality: "West Park" },
    { id: "c", full_name: "Comm E", last_name: "E", office_title: "Commissioner", government_level: "municipal", county: "Broward", municipality: "West Park" },
    { id: "x", full_name: "Elsewhere", last_name: "X", office_title: "Mayor", government_level: "municipal", county: "Leon", municipality: "Tallahassee" },
  ];
  const groups = countyGroups(people, "Broward", [{ office_title: "U.S. Representative", government_level: "federal", district: "20", counties: ["Broward"] }]);
  const federal = groups.find((g) => g.level === "federal");
  assert.equal(federal.count, 2);
  assert.deepEqual(federal.sections.map((s) => s.name), ["U.S. Senate", "U.S. House of Representatives"]);
  assert.ok(federal.sections[1].items.some((i) => i.vacant));
  const town = groups.find((g) => g.level === "municipal").sections;
  assert.deepEqual(town.map((s) => s.name), ["West Park"]);
  assert.deepEqual(town[0].items.map((i) => i.office_title), ["Mayor", "Commissioner"]);
  assert.equal(seatText(people[2]), "Group 5");
  assert.equal(formatPartialDate("2018-11"), "Nov 2018");
});

import { districtKey, featureAt, labelPoint, pointInGeometry, representativesFor } from "../../site/assets/lib.js";

const square = (x, y, size = 1) => [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]];

test("pointInGeometry handles polygons, holes and multipolygons", () => {
  const withHole = { type: "Polygon", coordinates: [square(0, 0, 10)[0], square(4, 4, 2)[0]] };
  assert.equal(pointInGeometry(1, 1, withHole), true);
  assert.equal(pointInGeometry(5, 5, withHole), false);
  const multi = { type: "MultiPolygon", coordinates: [square(0, 0), square(5, 5)] };
  assert.equal(pointInGeometry(5.5, 5.5, multi), true);
  assert.equal(pointInGeometry(3, 3, multi), false);
  assert.equal(featureAt({ features: [{ properties: { district: "7" }, geometry: multi }] }, 0.5, 0.5).properties.district, "7");
});

test("districtKey treats '04', 'District 4' and '4' as the same seat", () => {
  assert.equal(districtKey("04"), "4");
  assert.equal(districtKey("District 4"), "4");
  assert.equal(districtKey("District b"), "B");
  assert.equal(districtKey(null), "");
});

test("labelPoint stays inside an L-shaped district", () => {
  const shape = { type: "Polygon", coordinates: [[[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10], [0, 0]]] };
  const [x, y] = labelPoint(shape);
  assert.equal(pointInGeometry(x, y, shape), true);
});

test("representativesFor picks each district's member and every at-large or countywide seat", () => {
  const people = [
    { id: "s", full_name: "Sen A", last_name: "A", office_title: "U.S. Senator", government_level: "federal", statewide: true },
    { id: "h1", full_name: "Rep One", last_name: "One", office_title: "U.S. Representative", government_level: "federal", district: "23" },
    { id: "h2", full_name: "Rep Two", last_name: "Two", office_title: "U.S. Representative", government_level: "federal", district: "25" },
    { id: "g", full_name: "Gov G", last_name: "G", office_title: "Governor", government_level: "state", statewide: true },
    { id: "c3", full_name: "Comm Three", last_name: "Three", office_title: "County Commissioner", government_level: "county", county: "Broward", district: "3" },
    { id: "c4", full_name: "Comm Four", last_name: "Four", office_title: "County Commissioner", government_level: "county", county: "Broward", district: "4" },
    { id: "sb2", full_name: "School Two", last_name: "Two", office_title: "School Board Member", government_level: "county", county: "Broward", district: "2" },
    { id: "sb9", full_name: "School Nine", last_name: "Nine", office_title: "School Board Member", government_level: "county", county: "Broward", district: "9" },
    { id: "sh", full_name: "Sheriff S", last_name: "S", office_title: "Sheriff", government_level: "county", county: "Broward" },
    { id: "j", full_name: "Judge J", last_name: "J", office_title: "Circuit Judge", government_level: "county", county: "Broward", district: "5" },
    { id: "m", full_name: "Mayor M", last_name: "M", office_title: "Mayor", government_level: "municipal", county: "Broward", municipality: "Hollywood", district: "At-Large" },
    { id: "d1", full_name: "City One", last_name: "One", office_title: "Commissioner", government_level: "municipal", county: "Broward", municipality: "Hollywood", district: "1" },
    { id: "d2", full_name: "City Two", last_name: "Two", office_title: "Commissioner", government_level: "municipal", county: "Broward", municipality: "Hollywood", district: "2" },
    { id: "x", full_name: "Elsewhere", last_name: "E", office_title: "Mayor", government_level: "municipal", county: "Broward", municipality: "Davie" },
  ];
  const place = { county: "Broward", municipality: "Hollywood", congress: "25", commission: "04", school: "2",
    schoolDistricts: ["1", "2", "3"], cityDistricts: ["1", "2"], cityDistrict: "2" };
  const vacancies = [{ office_title: "U.S. Representative", government_level: "federal", district: "25", counties: ["Broward"] }];
  const { groups, judges } = representativesFor(people, place, vacancies);
  const ids = groups.flatMap((g) => g.sections.flatMap((s) => s.items.map((i) => i.id)));
  assert.deepEqual(new Set(ids), new Set(["s", "h2", "vacant-U.S. Representative-25", "g", "c4", "sb2", "sb9", "sh", "m", "d2"]));
  assert.deepEqual(judges.map((j) => j.id), ["j"]);
});

test("special district boards appear only for their own area, countywide boards everywhere in the county", () => {
  const people = [
    { id: "w", full_name: "Water W", last_name: "W", office_title: "Chair, Drain District", government_level: "county", county: "Broward", special_district: "South Broward", jurisdiction: "Drain District" },
    { id: "o", full_name: "Other O", last_name: "O", office_title: "Chair, Other District", government_level: "county", county: "Broward", special_district: "Sunshine", jurisdiction: "Other District" },
    { id: "c", full_name: "Council C", last_name: "C", office_title: "Member, Kids Council", government_level: "county", county: "Broward", special_district: "csc", jurisdiction: "Kids Council" },
  ];
  const ids = (place) => representativesFor(people, { county: "Broward", ...place }).groups.flatMap((g) => g.sections.flatMap((s) => s.items.map((i) => i.id)));
  assert.deepEqual(new Set(ids({ special: "South Broward", countywideSpecial: ["csc"] })), new Set(["w", "c"]));
  assert.deepEqual(ids({ special: null, countywideSpecial: ["csc"] }), ["c"]);
});
