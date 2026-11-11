// Run with: node --test tests/js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { countyCounts, countyRoster, initials, photoUrl } from "../../site/assets/lib.js";

test("photoUrl only allows https", () => {
  assert.equal(photoUrl("https://example.gov/a.jpg"), "https://example.gov/a.jpg");
  for (const bad of ["http://example.gov/a.jpg", "javascript:alert(1)", "data:image/png;base64,AA", "", null, undefined, 5]) {
    assert.equal(photoUrl(bad), null);
  }
});

test("initials", () => {
  assert.equal(initials("Maria G. Castillo"), "MC");
  assert.equal(initials("Ashley Moody"), "AM");
  assert.equal(initials("Rick Scott Jr."), "RS");
  assert.equal(initials("Madonna"), "M");
  assert.equal(initials("Contact your"), "CY");
  assert.equal(initials(""), "?");
  assert.equal(initials(null), "?");
});

const records = [
  { id: "a", full_name: "A", last_name: "Zed", government_level: "federal", statewide: true },
  { id: "b", full_name: "B", last_name: "Abel", government_level: "federal", statewide: true },
  { id: "c", full_name: "C", last_name: "Lee", government_level: "county", county: "Leon" },
  { id: "d", full_name: "D", last_name: "Kim", government_level: "municipal", county: "Leon" },
  { id: "e", full_name: "E", last_name: "Roe", government_level: "state", counties: ["Leon", "Wakulla"] },
  { id: "f", full_name: "F", last_name: "Poe", government_level: "county", county: "Duval" },
];

test("countyRoster separates county officials from statewide ones, sorted by level then name", () => {
  const { local, statewide } = countyRoster(records, "Leon");
  assert.deepEqual(local.map((r) => r.id), ["e", "c", "d"]); // state, county, municipal
  assert.deepEqual(statewide.map((r) => r.id), ["b", "a"]); // by surname
});

test("countyRoster does not mutate its input", () => {
  const before = records.map((r) => r.id).join();
  countyRoster(records, "Leon");
  assert.equal(records.map((r) => r.id).join(), before);
});

test("countyCounts excludes statewide officials", () => {
  assert.deepEqual(countyCounts(records, ["Leon", "Duval", "Baker"]), { Leon: 3, Duval: 1, Baker: 0 });
});

test("the map file covers exactly Florida's 67 counties and matches the county list", () => {
  const map = JSON.parse(readFileSync("site/assets/florida-counties.json", "utf8"));
  assert.equal(map.counties.length, 67);
  assert.equal(new Set(map.counties.map((c) => c.name)).size, 67);
  for (const c of map.counties) {
    assert.match(c.d, /^M[\d.,LZ-]+Z/);
    assert.ok(c.cx > 0 && c.cx < map.width && c.cy > 0 && c.cy < map.height, `${c.name} anchor is inside the map`);
  }
  // meta.json lists the same names, from collector/geo.py
  const geo = readFileSync("collector/geo.py", "utf8");
  for (const c of map.counties) assert.ok(geo.includes(`"${c.name}"`), `${c.name} is a known county`);
});
