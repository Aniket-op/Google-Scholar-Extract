# 📚 Scholar Extract — Google Scholar Profile Data Extractor

Extract publications, h-index, citations, and all metadata from any Google Scholar profile. Export results as CSV and JSON with a single click.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [REST API Reference](#rest-api-reference)
  - [POST /api/extract](#post-apiextract)
  - [GET /api/status/\<job\_id\>](#get-apistatusjob_id)
  - [GET /api/result/\<job\_id\>](#get-apiresultjob_id)
  - [GET /api/download/\<job\_id\>/publications\_csv](#get-apidownloadjob_idpublications_csv)
  - [GET /api/download/\<job\_id\>/profile\_csv](#get-apidownloadjob_idprofile_csv)
  - [GET /api/download/\<job\_id\>/publications\_json](#get-apidownloadjob_idpublications_json)
- [Data Schemas](#data-schemas)
  - [Profile Schema](#profile-schema)
  - [Publication Schema](#publication-schema)
- [Backend Modules](#backend-modules)
  - [scraper.py — fetch\_profile()](#scraperpy--fetch_profile)
  - [formatter.py — classify\_publication(), format\_publications(), format\_profile()](#formatterpy--classify_publication-format_publications-format_profile)
  - [csv\_exporter.py — publications\_to\_csv(), profile\_to\_csv()](#csv_exporterpy--publications_to_csv-profile_to_csv)
- [Frontend Functions (app.js)](#frontend-functions-appjs)
  - [Form and Input](#form-and-input)
  - [Extraction Flow](#extraction-flow)
  - [Polling and Status](#polling-and-status)
  - [Rendering](#rendering)
  - [Publication List](#publication-list)
  - [Download](#download)
  - [UI Helpers](#ui-helpers)
- [Job Status Lifecycle](#job-status-lifecycle)
- [Stage Pipeline](#stage-pipeline)
- [Dependencies](#dependencies)

---

## Overview

Scholar Extract is a full-stack web application with:

- **Backend** — a Flask REST API that scrapes Google Scholar via the `scholarly` library in background threads
- **Frontend** — a vanilla HTML/CSS/JS SPA that drives the form, polls job progress, and renders results

Extraction runs as an **async background job**: the client gets a `job_id` immediately and polls for updates every 1.5 seconds, making the UI fully non-blocking.

---

## Project Structure

```
google scholar extraction/
├── backend/
│   ├── app.py            # Flask REST API (routes + background worker)
│   ├── scraper.py        # scholarly-based profile fetcher
│   ├── formatter.py      # publication type classifier & profile formatter
│   ├── csv_exporter.py   # CSV serialisation helpers
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── index.html        # SPA shell with form & results layout
│   ├── app.js            # All frontend logic (form, polling, rendering)
│   └── style.css         # Styles
├── start_server.bat      # Windows launcher
└── Google_Scholar_Scraper.ipynb  # Original notebook reference
```

---

## Quick Start

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Start the server
python app.py
# or double-click start_server.bat on Windows

# 3. Open the app
# http://localhost:5000/
```

---

## REST API Reference

**Base URL:** `http://localhost:5000/api`

All request and response bodies are **JSON** unless stated otherwise.

---

### POST /api/extract

Start a new extraction job. The job runs in a background thread; the response returns immediately with a `job_id`.

**Request Body**

| Field             | Type      | Required | Default      | Description |
|-------------------|-----------|----------|--------------|-------------|
| `profile_url`     | `string`  | Yes      | —            | Full Scholar URL (`https://scholar.google.com/citations?user=XXXX`) or bare user ID |
| `fill_all`        | `boolean` | No       | `true`       | Whether to fetch full details for each individual publication (slower, more complete) |
| `scraper_api_key` | `string`  | No       | built-in key | ScraperAPI key to bypass IP blocking |
| `use_free_proxy`  | `boolean` | No       | `false`      | Use a free proxy pool if Scholar blocks the IP |

**Example Request**

```json
POST /api/extract
Content-Type: application/json

{
  "profile_url": "https://scholar.google.com/citations?user=JicYPdAAAAAJ",
  "fill_all": true,
  "use_free_proxy": false
}
```

**Success Response — 202 Accepted**

```json
{ "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
```

**Error Response — 400 Bad Request**

```json
{ "error": "profile_url is required" }
```

---

### GET /api/status/\<job\_id\>

Poll the current status and progress of a running or completed extraction job.

**Path Parameters**

| Param    | Description                          |
|----------|--------------------------------------|
| `job_id` | UUID returned by `/api/extract`      |

**Response Fields**

| Field               | Type     | Description |
|---------------------|----------|-------------|
| `status`            | `string` | `pending` / `running` / `done` / `error` |
| `stage`             | `string` | Current pipeline stage key (see [Stage Pipeline](#stage-pipeline)) |
| `progress`          | `number` | Publications fetched so far |
| `total`             | `number` | Total publications in profile |
| `message`           | `string` | Human-readable status message |
| `profile`           | `object` | *(only when `done`)* Summary profile object |
| `publication_count` | `number` | *(only when `done`)* Total publications found |
| `error`             | `string` | *(only when `error`)* Error description |

**Example Response (running)**

```json
{
  "status": "running",
  "stage": "fetching_pubs",
  "progress": 42,
  "total": 130,
  "message": "Fetched 42 of 130 publications..."
}
```

**Example Response (done)**

```json
{
  "status": "done",
  "stage": "done",
  "progress": 130,
  "total": 130,
  "message": "Extraction complete.",
  "publication_count": 130,
  "profile": { "name": "Jane Doe", "hindex": 45 }
}
```

**Error Responses**

| Code  | Meaning          |
|-------|------------------|
| `404` | `job_id` not found |

---

### GET /api/result/\<job\_id\>

Retrieve the complete structured result — full profile and all publications — once extraction is finished.

**Path Parameters**

| Param    | Description                     |
|----------|---------------------------------|
| `job_id` | UUID returned by `/api/extract` |

**Success Response — 200 OK**

```json
{
  "profile": { ... },
  "publications": [ { ... }, ... ]
}
```

**Error Responses**

| Code  | Condition                                     |
|-------|-----------------------------------------------|
| `404` | Job not found                                 |
| `409` | Job not yet complete (`status` field included) |

---

### GET /api/download/\<job\_id\>/publications\_csv

Download all publications as a CSV file with typed columns.

- **Content-Type:** `text/csv`
- **Filename:** `{author_name}_publications.csv`
- **Columns:** `type, title, authors, year, doi, journal, volume, pages, articleNumber, impactFactor, publisher, conference, location, date, patentNumber, applicationNumber, inventors, ResearchPublications, citation`

**Error Responses**

| Code  | Condition                    |
|-------|------------------------------|
| `409` | Job not found or not yet done |

---

### GET /api/download/\<job\_id\>/profile\_csv

Download the author profile summary as a single-row CSV file.

- **Content-Type:** `text/csv`
- **Filename:** `{author_name}_profile_summary.csv`
- **Columns:** `name, affiliation, email, interests, homepage, citedby, citedby5y, hindex, hindex5y, i10index, i10index5y, total_publications`

**Error Responses**

| Code  | Condition                    |
|-------|------------------------------|
| `409` | Job not found or not yet done |

---

### GET /api/download/\<job\_id\>/publications\_json

Download all publications as a structured JSON file following the typed Publication schema.

- **Content-Type:** `application/json`
- **Filename:** `{author_name}_publications.json`

**Error Responses**

| Code  | Condition                    |
|-------|------------------------------|
| `409` | Job not found or not yet done |

---

## Data Schemas

### Profile Schema

```json
{
  "name":               "string",
  "affiliation":        "string",
  "email":              "string",
  "interests":          ["string"],
  "homepage":           "string",
  "citedby":            0,
  "citedby5y":          0,
  "hindex":             0,
  "hindex5y":           0,
  "i10index":           0,
  "i10index5y":         0,
  "total_publications": 0,
  "cites_per_year":     { "2020": 10, "2021": 25 },
  "coauthors": [
    {
      "name":        "string",
      "affiliation": "string",
      "scholar_id":  "string"
    }
  ]
}
```

### Publication Schema

Publications are **discriminated by `type`**. Each type carries its own specific fields in addition to the common ones.

**Common Fields (all types)**

| Field     | Type       | Description        |
|-----------|------------|--------------------|
| `type`    | `string`   | Publication type   |
| `title`   | `string`   | Publication title  |
| `authors` | `string[]` | List of author names |
| `year`    | `number`   | Publication year   |
| `doi`     | `string`   | DOI (if available) |

**Type Variants**

| `type`                  | Extra Fields |
|-------------------------|--------------|
| `journal`               | `journal`, `volume`, `pages`, `articleNumber`, `publisher` |
| `conference`            | `conference`, `location`, `date`, `publisher` |
| `book-authored`         | `pages`, `publisher` |
| `book-edited`           | `pages`, `publisher` |
| `patent-granted`        | `patentNumber`, `applicationNumber`, `inventors`, `publisher` |
| `patent-published`      | `patentNumber`, `applicationNumber`, `inventors`, `publisher` |
| `Research-Publications` | `ResearchPublications` (venue/journal name) |
| *(fallback)*            | `citation` — raw text string; no `type` field |

---

## Backend Modules

### scraper.py — `fetch_profile()`

Fetches a complete Google Scholar author profile using the `scholarly` library.

```python
fetch_profile(
    profile_url: str,
    fill_all: bool = True,
    scraper_api_key: str | None = None,
    use_free_proxy: bool = False,
    progress_callback = None,   # called as: callback(current: int, total: int)
    stage_callback = None,      # called as: callback(stage_key: str, message: str)
) -> dict
```

**Parameters**

| Parameter           | Description |
|---------------------|-------------|
| `profile_url`       | Full Scholar URL or bare user ID |
| `fill_all`          | If `True`, fetches full bib details for every publication individually |
| `scraper_api_key`   | ScraperAPI key for proxy routing; falls back to free proxies or direct connection |
| `use_free_proxy`    | Use a free proxy pool via `ProxyGenerator.FreeProxies()` |
| `progress_callback` | Called after each publication is fetched with `(current, total)` |
| `stage_callback`    | Called at each pipeline stage change with `(stage_key, human_message)` |

**Raises**

- `Exception("Google Scholar is rate-limiting this IP...")` — on 429 / MaxTriesExceeded
- `Exception("Could not fetch profile: ...")` — on other search failures
- `Exception("Failed to load profile sections: ...")` — on `scholarly.fill()` failure

**Internal helper**

```python
extract_user_id(raw: str) -> str
```

Extracts the Scholar `user=` query parameter from a full URL, or returns the raw string as-is for bare user IDs.

---

### formatter.py — `classify_publication()`, `format_publications()`, `format_profile()`

Maps raw `scholarly` dicts to the typed Publication schema.

#### `classify_publication(pub: dict) -> dict`

Classifies a single raw publication dict into the typed schema. Classification runs in priority order:

1. **Patent** — `ENTRYTYPE=="patent"`, or publisher/title/URL contains "patent"
2. **Book** — `ENTRYTYPE` in `{book, inbook, incollection, booklet}`
3. **Conference** — `ENTRYTYPE` in `{inproceedings, proceedings, conference}`, or venue keywords (IEEE, ACM, CVPR, NeurIPS, ICCV, AAAI, etc.)
4. **Journal** — presence of `journal` field, or `ENTRYTYPE=="article"`
5. **Research Publication** — generic fallback for any titled entry
6. **Citation fallback** — raw citation string when no other info is available

#### `format_publications(author: dict) -> list[dict]`

Applies `classify_publication()` to every publication in the author dict.

```python
format_publications(author: dict) -> list[dict]
```

#### `format_profile(author: dict) -> dict`

Extracts the flat profile summary from the raw `scholarly` author dict, returning the [Profile Schema](#profile-schema) object.

```python
format_profile(author: dict) -> dict
```

**Internal helpers**

| Function | Description |
|----------|-------------|
| `_parse_authors(raw: str) -> list[str]` | Splits `"A and B and C"` style scholarly author strings |
| `_parse_year(raw) -> int or None` | Safely casts year to `int`, returns `None` on failure |
| `_contains(haystack, *needles) -> bool` | Case-insensitive substring search across multiple needles |

---

### csv\_exporter.py — `publications_to_csv()`, `profile_to_csv()`

Serialises formatted dicts to UTF-8 CSV strings for file download.

#### `publications_to_csv(publications: list[dict]) -> str`

Converts a list of Publication dicts to a multi-row CSV string.

- Uses `PUBLICATION_COLUMNS` as the fixed column order
- List values (e.g. `authors`, `inventors`) are joined as `"; "`-separated strings
- Unrecognised fields are silently ignored (`extrasaction="ignore"`)

#### `profile_to_csv(profile: dict) -> str`

Converts a single Profile dict to a one-row CSV string.

- Uses `PROFILE_COLUMNS` as the fixed column order
- The `interests` list is joined as a `"; "`-separated string

**Internal helper**

```python
_join_list(value) -> str
```

Converts a list to a `"; "`-separated string; passes non-list values through unchanged.

---

## Frontend Functions (app.js)

All functions are globally scoped. The frontend polls the API every **1500 ms** (`POLL_MS`) and renders publications in pages of **20** (`PAGE_SIZE`).

### Form and Input

#### `isScholarUrl(url: string) -> boolean`

Validates the Scholar URL input. Accepts:
- URLs containing `scholar.google.com/citations`
- Bare user IDs matching `/^[A-Za-z0-9_-]{10,}$/`

The URL input field gets `.valid` or `.invalid` CSS classes on every `input` event. Pressing `Enter` triggers `startExtraction()`.

---

### Extraction Flow

#### `startExtraction() -> Promise<void>`

Main entry point called by the Extract button and the `Enter` key.

1. Validates the URL with `isScholarUrl()`
2. Clears previous errors and results
3. Resets the stage pipeline via `resetPipeline()`
4. Sets the button to busy state via `setBusy(true)`
5. Saves the ScraperAPI key to `localStorage`
6. POSTs to `/api/extract` with `{ profile_url, fill_all, use_free_proxy, scraper_api_key }`
7. Stores the returned `job_id` and starts polling via `startPolling()`

---

### Polling and Status

#### `startPolling() -> void`

Clears any existing poll interval, sets a new `setInterval(pollStatus, POLL_MS)`, and fires `pollStatus()` immediately for a fast first update.

#### `pollStatus() -> Promise<void>`

Called every 1.5 s. GETs `/api/status/<job_id>` and handles each status:

| Status              | Action |
|---------------------|--------|
| `pending` / `running` | Updates pipeline stage and progress bar |
| `done`              | Stops polling, sets progress to 100%, fetches full result, calls `renderResults()` |
| `error`             | Stops polling, calls `showError()` |

**Progress bar calculation:**

| Stage                            | Progress % |
|----------------------------------|:----------:|
| `connecting` / `proxy`           | 5% |
| `loading` / `profile_done`       | 20% |
| `fetching_pubs` / `pub_progress` | `20 + round((current / total) × 78)%` |
| `done`                           | 100% |

---

### Rendering

#### `renderResults(profile: object, publications: array) -> void`

Populates the results section with:

- Author name, affiliation, and interest tags
- Metric boxes: Citations, h-index, i10-index, Publications
- Calls `applyFilter('all')` to render the full publication list
- Calls `showResults()` to reveal the section

---

### Publication List

#### `applyFilter(type: string) -> void`

Filters `allPublications` by the selected type and re-renders the list from scratch.

| Filter value      | Included `type` values |
|-------------------|------------------------|
| `all`             | All publications |
| `patent`          | `patent-granted`, `patent-published` |
| `book-authored`   | `book-authored`, `book-edited` |
| *(anything else)* | Exact `type` match |

Resets `shownCount` to `0`, clears `#pub-list`, then calls `showMore()`.

#### `filterPubs(btn: HTMLElement) -> void`

Click handler for filter buttons. Reads `btn.dataset.type` and delegates to `applyFilter()`.

#### `showMore() -> void`

Appends the next batch of `PAGE_SIZE` (20) publications to `#pub-list`. Updates the `#show-more-btn` visibility and remaining count label.

#### `buildPubItem(pub: object) -> HTMLElement`

Builds a single `<div class="pub-item">` DOM node containing:

- A coloured type badge (via `badgeClass()` and `typeLabel()`)
- Title, first 3 authors (with "et al." when there are more), year, venue, and DOI

#### `getVenue(pub: object) -> string`

Returns the first non-empty venue string from `pub.journal`, `pub.conference`, or `pub.ResearchPublications`.

#### `typeLabel(type: string) -> string`

Maps type keys to human-readable display labels:

| Key | Label |
|-----|-------|
| `journal` | Journal |
| `conference` | Conference |
| `book-authored` | Book |
| `book-edited` | Edited Book |
| `patent-granted` | Patent (Granted) |
| `patent-published` | Patent (Published) |
| `Research-Publications` | Research |
| `other` | Other |

#### `badgeClass(type: string) -> string`

Maps type keys to CSS badge class names (e.g. `badge-journal`, `badge-conference`, `badge-patent-granted`, etc.).

---

### Download

#### `downloadFile(type: string, event: Event) -> void`

Triggers a browser file download by navigating to `/api/download/<job_id>/<type>`.

| `type` value         | File downloaded |
|----------------------|-----------------|
| `publications_csv`   | `{name}_publications.csv` |
| `publications_json`  | `{name}_publications.json` |
| `profile_csv`        | `{name}_profile_summary.csv` |

No-ops silently if `currentJobId` is not set.

---

### UI Helpers

#### `setBusy(busy: boolean) -> void`

Disables/enables the Extract button and swaps its icon between a CSS spinner and the 🔍 emoji.

#### `showProgress(label: string, pct: number, countText: string) -> void`

Makes `#progress-section` visible, sets the status label and count text, and animates the progress bar fill to `pct`%.

#### `hideProgress() -> void`

Hides `#progress-section`.

#### `showError(msg: string) -> void`

Shows `#error-box` with the error message. Automatically detects **rate-limit / CAPTCHA** errors by scanning for keywords (`rate-limit`, `429`, `CAPTCHA`, `blocked`, `unusual traffic`) and, when found:
- Displays a hint to obtain a ScraperAPI key
- Starts a 15-minute countdown timer with a **Retry Now** button

#### `hideError() -> void`

Hides the error box and cancels any active countdown timer.

#### `showResults() -> void`

Makes `#results-section` visible by adding the `.visible` class.

#### `hideResults() -> void`

Hides `#results-section`, clears the publication list DOM, and resets `allPublications`.

#### `fmt(n: any) -> string`

Formats a number using `toLocaleString()`. Returns `"—"` for `null` or `undefined`.

#### `esc(str: string) -> string`

HTML-escapes a string (`&`, `<`, `>`, `"`) to prevent XSS when inserting into `innerHTML`.

---

## Job Status Lifecycle

```
POST /api/extract
       │
       ▼
  status: "pending"
       │
       ▼  (background thread starts)
  status: "running"
    stage: connecting → loading → profile_done → fetching_pubs → pub_progress
       │
       ├─ success ──▶  status: "done"
       └─ failure ──▶  status: "error"
```

---

## Stage Pipeline

| Backend Stage Key           | Step | Description |
|-----------------------------|:----:|-------------|
| `connecting` / `proxy`      | 0    | Configuring proxy, connecting to Google Scholar |
| `loading` / `profile_done`  | 1    | Loading author profile sections |
| `fetching_pubs` / `pub_progress` | 2 | Fetching full details per publication |
| `done`                      | 3    | Extraction complete |

---

## Dependencies

### Python (backend/requirements.txt)

| Package        | Version   | Purpose |
|----------------|-----------|---------|
| `flask`        | >= 3.0.0  | REST API server |
| `flask-cors`   | >= 4.0.0  | CORS headers for the frontend |
| `scholarly`    | >= 1.7.11 | Google Scholar scraper |
| `pandas`       | >= 2.0.0  | Data utilities |
| `httpx`        | < 0.28    | HTTP client (pinned for `scholarly` proxy compatibility) |
| `requests`     | >= 2.31.0 | HTTP requests |
| `beautifulsoup4` | >= 4.12.0 | HTML parsing |
| `lxml`         | >= 5.0.0  | XML/HTML parser backend |

### JavaScript (frontend)

No external dependencies — pure vanilla HTML, CSS, and JavaScript.

---

> **Tip:** If Google Scholar blocks your IP, get a free ScraperAPI key at [scraperapi.com](https://www.scraperapi.com/) and paste it into the ScraperAPI Key field in the UI.
