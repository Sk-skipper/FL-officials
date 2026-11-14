# Florida Government Officials Directory (static edition)

A searchable directory of elected officials in Florida, built as a static website. It needs no
server and no database, and hosting on GitHub Pages is free.

- **GitHub Actions** collects the official government sources once a day.
- **You approve changes.** When a source shows something new, you get a pull request listing every
  change. Merging it publishes the update; closing it discards it.
- **GitHub Pages** hosts the site at `https://YOUR-NAME.github.io/REPO-NAME/`.

The site has a homepage with search and statistics, a **Your representatives** map (enter an address, use
your location or click the map to see everyone who represents that spot, or show every district with its
member's photo), a directory with search, filters, sorting and CSV/JSON downloads, a profile page for each
official (with a portrait where one is available), a clickable county map, a data sources status page, and a
methodology page.

## Set it up (about 10 minutes)

1. **Create a repository.** On GitHub choose *New repository*, give it a name, and make it
   **Public** (GitHub Pages is free for public repositories).
2. **Upload the files.** Unzip this project and upload *everything inside the folder*, including the
   hidden `.github` folder, which holds the automation. The easiest way is
   [GitHub Desktop](https://desktop.github.com/), or from a terminal:
   ```bash
   cd fl-officials-static
   git init -b main && git add . && git commit -m "First version"
   git remote add origin https://github.com/YOUR-NAME/REPO-NAME.git
   git push -u origin main
   ```
   If you drag files into the GitHub website instead, make sure `.github` comes along (on a Mac,
   press Cmd+Shift+. in Finder to show hidden folders).
3. **Turn on Pages.** In the repository go to *Settings > Pages* and under *Source* choose
   **GitHub Actions**.
4. **Let the collector open pull requests.** Go to *Settings > Actions > General > Workflow
   permissions*. Choose **Read and write permissions** and tick **Allow GitHub Actions to create and
   approve pull requests**. Save.
5. **Run the first collection.** Open the *Actions* tab, choose **Collect officials**, then
   **Run workflow**. It takes a few minutes.
6. **Review and publish.** A pull request called "Data update" appears, listing everyone found.
   Look it over and press **Merge**. The *Deploy site* workflow then publishes it, and your link is
   shown under *Settings > Pages*.

After that it runs by itself every day. You only act when a pull request appears.

Optional: under *Settings > Secrets and variables > Actions > Variables*, add `SCRAPER_CONTACT`
with an email address or web page. It is sent to government sites so they can reach you; without
it, your repository's address is sent.

## Read this after the first run

The five source readers were written from the known layout of each government page and tested
against sample pages. They have not yet run against the live sites, so the first run is the real
test. Check the pull request's table, or the *Data sources* page on the site:

| Source | Expected records |
|---|---|
| United States Senate | 2 |
| United States House of Representatives | 28 |
| Florida Senate | 40 |
| Florida House of Representatives | up to 120 |
| Supervisors of Elections | 67 |
| Broward County GIS: district seats (County Commission, School Board, city commission districts) | 57 |

If a source says **Failed**:

- *"No valid records were found"* means the page layout differs from what the reader expects. The
  fix goes in that source's file in `collector/scrapers/`. Save the live page's HTML, put it in the
  matching test in `tests/test_scrapers.py`, and adjust the reader until the test passes.
- *"HTTP 403"* or *"robots.txt disallows"* means the site does not allow automated collection, or
  blocks GitHub's servers. The collector will not work around that. Add those officials by hand
  instead (see below).

A failing source never wipes data: its previous records stay published.

## Everyday edits

All edits are small JSON files in `data/`. You can edit them on the GitHub website: open the file,
click the pencil icon, and commit. The site redeploys by itself. If an edit is invalid, the deploy
stops with a clear message and the live site stays as it was.

### Fix a wrong detail: `data/corrections.json`

Each profile shows its **record id** at the bottom. Add an entry under that id with only the
fields to change. Use `null` to remove a wrong value:

```json
{
  "state-senator-district-12-jane-doe": {
    "phone": "(850) 487-5000",
    "email": null,
    "note": "Confirmed with the senator's office on 2026-11-10"
  }
}
```

Corrections always win over collected data, and the profile is labelled "Corrected by the editors".
You can correct `full_name`, `first_name`, `middle_name`, `last_name`, `office_title`, `party`,
`district`, `jurisdiction`, `municipality`, `phone`, `email`, `official_website`, `photo_url` and
`selection_method`. A `photo_url` must start with `https://`; use `null` to remove a wrong photo.

### Hand-added officials: `data/manual_officials.json` (kept empty)

Every official comes from an automated source, so each record can be re-checked on every run and links to the
page it came from. The file stays in place (publish still reads it) but is empty on purpose. To cover a new
office, add a source instead (next section). Only use it as a last resort, with a `source_url` and a note on
why no source can be collected; the README history shows the entry format.

### Collect a county, city or special district automatically: `data/sources.json`

Most local sources use one of these scrapers:

| Scraper | For | Notes |
|---|---|---|
| `broward_soe` | Broward Supervisor of Elections, every office on the ballot | judges, constitutional officers, state executives |
| `miamidade_soe` | Miami-Dade Supervisor of Elections PDFs | officials list plus `config.judges_url` |
| `broward_districts` | Broward County GIS district seats | `config.mayor_cities`: cities whose mayor is taken from GIS |
| `city_roster` | a city's or board's own roster page | see below |
| `county_directory` / `municipal_directory` | a page with a regular table | CSS selectors per field |

`city_roster` reads a "Mayor and Commission" page the way a person would: it recognises "Mayor Jane Doe",
"Jane Doe, Vice Mayor", a name above (or below) a title, and the member cards used by Granicus OpenCities
sites (with photo, phone and email). For a city:

```json
{
  "key": "city_broward_example",
  "name": "Example (Broward County): mayor and commission",
  "url": "https://www.example.gov/commission",
  "level": "municipal",
  "scraper": "city_roster",
  "config": {"county": "Broward", "municipality": "Example", "member_title": "Commissioner", "seats": 5}
}
```

Optional config: `extra_urls` (more pages, e.g. one per member), `menu_links` (names listed only in the site
menu), `loose` (a name followed by an email address counts), `selector` (read only part of the page) and
`exclude` (names to ignore). For a special district board add `jurisdiction`, `special_district` (a key in
`special_districts.json`), `title_suffix` (", South Broward Drainage District") and `role_pattern` (a regex the
line under each name must match). If the page yields more than two people fewer or more than `seats`, the
source fails and the previous records stay published.

To find a city's roster page, list the cities in a JSON file and run
`python tools/find_council_pages.py cities.json`; it follows each homepage's links and reports the page that
names the most members. Check its suggestion before adding the source.

Sites that refuse automated requests (HTTP 403) or disallow them in robots.txt are never worked around; they
stay under "Not yet covered" on the methodology page.

### Portraits and bio facts: `data/profiles.json`

Generated by `tools/enrich.py` from two public-domain datasets: the
[congress-legislators](https://github.com/unitedstates/congress-legislators) data for Members of Congress
and [Open States](https://github.com/openstates/people) for the Legislature. Clone both, then run:

```bash
python tools/enrich.py --congress ../congress-legislators --openstates ../people
```

An entry is used only when the district and surname both match, and it only fills empty fields. Scrapers can
also return term facts (`next_election`, `term_ends`) published by their source.

### Wikipedia gap-filling: `data/wikipedia.json`

Generated by `tools/wikipedia.py`. For officials with no photo or birth date from an official source, it looks
for a Wikipedia article that names the same person, office and place, then takes a freely licensed Wikimedia
Commons portrait (credited on the profile), the Wikidata birth date and the article link. Official values always
win. To reject a wrong match, add its record id to `_rejected`.

```bash
pip install -r tools/requirements.txt
python -m collector.publish && python tools/wikipedia.py --review
```

### District maps: `site/assets/boundaries/`

Built by `tools/build_boundaries.py` from the Census Bureau (Congress, Florida Senate and House, counties,
cities), Broward County GIS (County Commission, School Board, city commission and water control districts,
city limits), Miami-Dade County GIS (County Commission, School Board, community development districts) and City
of Miami GIS (its commission districts). It also adds Miami-Dade's community development districts to
`data/special_districts.json`. Run
it again after a redistricting; `--counties` also rewrites the Florida House county lists in `districts.json`
and checks the method against the Senate roster and the congressional statute.

Florida redrew its congressional districts for the members elected in November 2026. Until they take office
in January 2027 the map uses the 2022 districts; then switch `build_boundaries.py` to the 120th Congress layer.

### Districts and vacancies: `data/districts.json`, `data/vacancies.json`

`districts.json` says which counties each congressional and Florida House district covers, so those members
appear on the county map. The Florida House lists for all 120 districts are worked out from the district maps. `vacancies.json` lists empty seats so they show as vacant rather than missing.

### Reports of errors from visitors

Each profile has a **Report an error** link. It opens a GitHub issue form with the record id filled
in. To send reports somewhere else, set `report_url` (or `contact_email`) in `data/site.json`.

## How data quality is protected

- Names, phone numbers, emails and links are validated. Invalid values are dropped, not repaired,
  and vacant seats are skipped.
- Nothing collected goes live without your review. Every pull request lists new officials,
  officials no longer listed, changed details, unreadable rows and possible duplicates.
- A source that fails, or suddenly returns fewer than half its usual records, keeps its previous
  data.
- Each record keeps a link to its source page and the date it was last confirmed there.
- The coverage figure counts only offices with a source, and the site lists what is not covered.
- The collector identifies itself, obeys robots.txt, waits two seconds between requests to the same
  site, retries only temporary errors, and never tries to get around logins or blocks.

## Preview on your computer

Requires Python 3.11 or newer.

```bash
pip install -r requirements.txt
python -m collector.collect        # fetches the live sources (optional)
python -m collector.publish        # builds site/data/
python -m http.server 8000 -d site
```

Then open http://localhost:8000. Opening the HTML files directly from disk does not work, because
browsers block data loading from `file://` pages.

Tests: `python -m pytest` and `node --test tests/js/*.test.mjs`.

## Hosting on Netlify instead

Connect the repository in Netlify (*Add new site > Import an existing project*). The included
`netlify.toml` sets everything up. Collection still runs in GitHub Actions, and Netlify rebuilds
whenever the repository changes. Set `report_url` in `data/site.json`, since the automatic GitHub
issue link only works with GitHub Pages. You can then delete `.github/workflows/deploy.yml`.

## Files

```
site/                  the website (HTML, CSS, JavaScript; no build step)
  assets/lib.js        search, filters, sorting, exports
  assets/app.js        page behaviour
  assets/florida-counties.json   county outlines for the map (Census Bureau data)
  assets/boundaries/   district shapes for the "Your representatives" map
  assets/vendor/leaflet/  map library (Leaflet 1.9.4, BSD licence)
  representatives.html address lookup and district map
data/
  sources.json         which pages to collect
  collected.json       written by the collector; don't edit by hand
  corrections.json     your fixes
  manual_officials.json  kept empty: every official comes from a source
  profiles.json        portraits and bio facts (tools/enrich.py)
  special_districts.json  special districts: details, sources, and which are mapped
  wikipedia.json       last-resort portraits, birth dates and article links (tools/wikipedia.py)
  site.json            report link and contact email
collector/             Python: source readers, validation, collect and publish steps
tools/build-map.mjs    rebuilds the county map file (only needed if you want to change the map)
tools/build_boundaries.py  downloads district shapes for the representatives map
tools/wikipedia.py     fills missing photos and birth dates from Wikipedia/Wikidata
tools/find_council_pages.py  suggests each city's council roster page
tests/                 Python and JavaScript tests
.github/workflows/     daily collection, deploy to Pages, tests
```

## Known limits

- No phone numbers for state legislators: the Senate and House roster pages don't list them.
- U.S. House and Florida House members appear on a county's page only if their source lists the
  counties in their district.
- The county map places U.S. House members using the counties in their district's legal description and
  Florida House members using the district maps. The representatives map matches by exact district.
- Local offices (county commission, constitutional officers, school board, judges, city officials, special
  districts) are covered for Broward and Miami-Dade counties, from each county's Supervisor of Elections, county
  GIS and each city's own website. A few cities' sites refuse automated requests; the methodology page lists them.
- The representatives map suggests addresses with Esri's ArcGIS World Geocoder (no key needed for searches that
  aren't stored) and falls back to the Census Bureau geocoder.
- Portraits are linked from their source, not copied. Members of Congress come from a public-domain
  image set matched by state, district and surname. Florida House photos are read from the roster page
  and have not been checked against the live site; the "With photo" column in each collection report
  shows how many records got one.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. If daily
  collection stops, re-enable it on the *Actions* tab.

This is an independent project and is not affiliated with any government agency.
