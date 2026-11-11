// Builds site/assets/florida-counties.json: the 67 county outlines used by the map.
// You only need to run this if you want to rebuild the map; the result is already in the repo.
//
//   npm install us-atlas@3.0.1 topojson-client@3.1.0 d3-geo@3.1.1
//   node tools/build-map.mjs
//
// Boundaries come from the U.S. Census Bureau (via the us-atlas package).
import { readFileSync, writeFileSync } from "node:fs";
import { feature } from "topojson-client";
import { geoAlbers, geoPath, geoArea } from "d3-geo";

const topology = JSON.parse(readFileSync("node_modules/us-atlas/counties-10m.json", "utf8"));
const all = feature(topology, topology.objects.counties).features;
const florida = all.filter((f) => String(f.id).startsWith("12"));
if (florida.length !== 67) throw new Error(`Expected 67 Florida counties, found ${florida.length}`);

const WIDTH = 640;
const projection = geoAlbers().rotate([82.5, 0]).center([0, 27.8]).parallels([25.5, 30]);
projection.fitWidth(WIDTH, { type: "FeatureCollection", features: florida });
const path = geoPath(projection).digits(1);

// Centre of a county's biggest piece of land, so a marker never lands in open water.
function anchor(f) {
  if (f.geometry.type === "Polygon") return path.centroid(f);
  let best = null;
  for (const coordinates of f.geometry.coordinates) {
    const part = { type: "Feature", geometry: { type: "Polygon", coordinates } };
    const area = geoArea(part);
    if (!best || area > best.area) best = { part, area };
  }
  return path.centroid(best.part);
}

let height = 0;
const counties = florida
  .map((f) => {
    const [cx, cy] = anchor(f);
    const bounds = path.bounds(f);
    height = Math.max(height, bounds[1][1]);
    return { name: f.properties.name, d: path(f), cx: Math.round(cx * 10) / 10, cy: Math.round(cy * 10) / 10 };
  })
  .sort((a, b) => a.name.localeCompare(b.name));

const out = { width: WIDTH, height: Math.ceil(height) + 4, counties };
writeFileSync("site/assets/florida-counties.json", JSON.stringify(out) + "\n");
console.log(`Wrote ${counties.length} counties, ${out.width}x${out.height}`);
