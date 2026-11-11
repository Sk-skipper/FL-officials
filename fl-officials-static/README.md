# Florida Government Officials Directory (static edition)

A searchable directory of elected officials in Florida, built as a static website. It needs no
server and no database, and hosting on GitHub Pages is free.

- **GitHub Actions** collects the official government sources once a day.
- **You approve changes.** When a source shows something new, you get a pull request listing every
  change. Merging it publishes the update; closing it discards it.
- **GitHub Pages** hosts the site at `https://YOUR-NAME.github.io/REPO-NAME/`.

The site has a homepage with search and statistics, a directory with search, filters, sorting and
CSV/JSON downloads, a profile page for each official, a county explorer, a data sources status page,
and a methodology page.

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
`district`, `jurisdiction`, `municipality`, `phone`, `email`, `official_website` and
`selection_method`.

### Add officials no source covers: `data/manual_officials.json`

Use this for county commissioners, city councils and similar. Every entry needs the official page
you took it from:

```json
{
  "officials": [
    {
      "name": "Jane Q. Public",
      "office_title": "Mayor",
      "government_level": "municipal",
      "selection_method": "elected",
      "party": "Nonpartisan",
      "jurisdiction": "West Park",
      "county": "Broward",
      "municipality": "West Park",
      "phone": "954-555-0100",
      "email": "mayor@example.gov",
      "official_website": "https://www.example.gov/mayor",
      "source_url": "https://www.example.gov/commission",
      "source_name": "City of West Park",
      "last_verified": "2026-11-10"
    }
  ]
}
```

`government_level` is `federal`, `state`, `county` or `municipal`. A `municipal` entry needs both
`county` and `municipality`. Use `"selection_method": "appointed"` for appointed posts such as a
city manager, so they are labelled correctly.

### Collect a county or city page automatically: `data/sources.json`

If a local government lists its officials in a regular table or list, you can add it as a source
with CSS selectors that describe where each field is:

```json
{
  "key": "west_park_commission",
  "name": "City of West Park: City Commission",
  "url": "https://www.example.gov/commission",
  "level": "municipal",
  "scraper": "municipal_directory",
  "config": {
    "row_selector": "table.commission tbody tr",
    "fields": {
      "name": "td:nth-of-type(1)",
      "title": "td:nth-of-type(2)",
      "district": "td:nth-of-type(3)",
      "phone": "td:nth-of-type(4)",
      "email": "a[href^='mailto:']"
    },
    "title_must_contain": ["Mayor", "Commissioner"],
    "county": "Broward",
    "municipality": "West Park",
    "selection_method": "elected"
  }
}
```

Use `"scraper": "county_directory"` and leave out `municipality` for a county page. Check the site's
terms of use first. Pages that only show their content with JavaScript can't be collected this way,
so add those officials by hand.

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
data/
  sources.json         which pages to collect
  collected.json       written by the collector; don't edit by hand
  corrections.json     your fixes
  manual_officials.json  officials you add yourself
  site.json            report link and contact email
collector/             Python: source readers, validation, collect and publish steps
tests/                 Python and JavaScript tests
.github/workflows/     daily collection, deploy to Pages, tests
```

## Known limits

- No phone numbers for state legislators: the Senate and House roster pages don't list them.
- U.S. House and Florida House members appear on a county's page only if their source lists the
  counties in their district.
- Counties are shown as a list, not a map.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. If daily
  collection stops, re-enable it on the *Actions* tab.

This is an independent project and is not affiliated with any government agency.
