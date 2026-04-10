# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask web front end for [skrutable](https://github.com/tylergneill/skrutable), a Sanskrit text processing toolkit. Deployed at [skrutable.info](https://skrutable.info). The `skrutable` backend library is installed as a pip dependency — it is **not** in this repo (it's in `.gitignore`).

## Running Locally

```bash
# activate virtualenv (Python 3.11)
source venv3.11/bin/activate

# install/update dependencies
pip-compile requirements.in   # regenerate requirements.txt from requirements.in
pip install -r requirements.txt

# run dev server on port 4999
./launch.sh
# or equivalently:
FLASK_APP=flask_app.py flask --debug run --port=4999
```

## Deployment

Docker-based (Digital Ocean). Two Dockerfiles:
- `Dockerfile` — production (port 5010)
- `Dockerfile.stg` — staging (port 5012)

Both use `gunicorn` with 1200s timeout and multithreading. Production runs 4 workers / 4 threads; staging runs 1 worker / 4 threads. The app version is in `VERSION` (format: `__version__ = "X.Y.Z"`).

## Architecture

**Single-file Flask app** (`flask_app.py`) — all routes, form processing, and `skrutable` package integration live here. No blueprints, no separate route modules.

Key patterns:
- Four `skrutable` objects are instantiated once at module level: `T` (Transliterator), `S` (Scanner), `MI` (MeterIdentifier), `Spl` (Splitter)
- `CustomFlask`/`CustomRequest` subclasses override `max_form_memory_size` to handle large uploads (128 MB)

**State management** — UI state is split across three layers:

| Layer | Scope | What it stores |
|-------|-------|----------------|
| `flask.session` (server-side cookie) | Per-user, persists across requests | Sidebar settings: `skrutable_action`, `from_scheme`, `to_scheme`, `resplit_option`, scan detail checkboxes (`weights`, `morae`, `gaRas`, `alignment`), extra settings (`avoid_virama_indic_scripts`, `avoid_virama_non_indic_scripts`, `preserve_anunasika`, `preserve_compound_hyphens`, `preserve_punctuation`, `splitter_model`), melody state (`meter_label`, `melody_options`). All tracked in `SESSION_VARIABLE_NAMES` at top of `flask_app.py`. Saved to server via `POST /api/save-settings`. |
| `localStorage` (browser) | Per-browser, persists across sessions | `text_input`, `text_output` (workbench textarea contents), `theme` (dark/light mode preference). |
| `flask.g` (request context) | Single request only | `text_input` — used during form POST processing in `flask_app.py`, not persisted. |

**Core actions** (selected via hidden `skrutable_action` form field):
- **transliterate** — convert between writing systems (IAST, HK, SLP, DEV, etc.)
- **scan** — metrical scansion showing weights, morae, gaṇas, alignment
- **identify meter** — scansion + meter identification with resplit options
- **split** — Sanskrit compound word splitting (via external splitter models)

**File upload and processing** — the workbench (`main.html`) has a toggleable upload view; submits to `POST /upload_file` which processes the file and returns it as a download.

**OCR endpoint** (`/ocr`) — accepts PDF + Google Vision API key, runs async OCR via `ocr_service.py`, which uses Google Cloud Vision and Cloud Storage (bucket: `vision_multilang_ocr`, project: `sanskrit-ocr-219110`).

**REST API** (`/api/*`) — POST-only endpoints for programmatic access: `/api/transliterate`, `/api/scan`, `/api/identify-meter`, `/api/split`. Accept form data, JSON, or file upload.

**Supporting files:**
- `ocr_service.py` — Google Vision OCR wrapper (upload PDF to GCS, run async OCR, collect results, clean up)
- `bulk_vision_runner.py` — standalone CLI script for batch OCR processing of many PDFs with parallelism
- `templates/` — Jinja2 templates; `base.html` layout with `sidebar.html`/`sidebar_actions.html` includes; `main.html` is the workbench UI
- `assets/` — custom CSS (`css/skrutable.css`), shared JS (`js/settings.js`, `js/sidebar.js`), melody MP3s, meter analysis data

**GitHub Actions:** `.github/workflows/clean_bucket.yml` — daily cleanup of stale GCS objects (>10 min old).

## Conventions

- Tabs for indentation in Python (not spaces) — match the existing style in `flask_app.py`
- Session variable names are tracked in `SESSION_VARIABLE_NAMES` and related lists at the top of `flask_app.py`; any new session variable must be added there
- Static files served via the `/assets/<path:name>` route, not Flask's default static handler

## How to add a new extra setting (checkbox or select)

Extra settings (e.g. `avoid_virama_indic_scripts`, `preserve_anunasika`) flow through **six distinct layers**. All six must be updated together or the setting will silently have no effect.

### 1. `flask_app.py` — backend wiring (4 spots)

- **`extra_option_names`** list (top of file): add the variable name. This drives `process_form()`, `api_save_settings()`, and the settings page `render_template` call automatically.
- **`_init_session_defaults()`**: add the default value (`0`/`1` for checkboxes, string for selects).
- **`do_transliterate()` / `do_split()` etc.**: add the parameter to the helper function signature and pass it through to the underlying `skrutable` call.
- **Call sites** for that helper (upload flow at `POST /upload_file`, and the API endpoint e.g. `api_transliterate()`): add `param=session["param"]` or `param=inputs["param"]`. For API endpoints also add the key to `optional_args` in the `get_inputs()` call.

### 2. `templates/settings.html` — settings page UI (4 spots)

- Add the `<input type="checkbox">` (or `<select>`) element with the Jinja `{% if var|default(0)|int %}checked{% endif %}` pattern.
- Add `fd.append("var_name", ...)` in `saveAll()`.
- Add `document.getElementById("var_name").checked = <default>` in `resetExtra()`.
- Add a `document.getElementById("var_name").addEventListener("change", ...)` call.

### 3. `templates/main.html` — workbench page (3 spots)

- Declare a JS global: `var currentMyVar = {{ my_var|default(0)|int }} === 1;` alongside the other `current*` globals near the top of the `<script>` block.
- Add `fd.append("my_var", currentMyVar)` in the fetch call for whichever action(s) use it (e.g. the `/api/transliterate` fetch).
- Add `addHidden("my_var", currentMyVar)` in `syncHiddenInputs()` (used by the file upload form path).

### 4. `assets/js/settings.js` — shared JS (2 spots)

- Add `fd.append("my_var", currentMyVar)` in `saveSettingsToSession()` so the session stays in sync whenever sidebar settings are saved.
- Update the comment at the top listing expected globals.

### 5. `skrutable` library (`transliteration.py` or relevant module)

- Add the parameter to the relevant method signature (e.g. `Transliterator.transliterate()`).
- Implement the behavior.

### 6. `skrutable` library (`scheme_maps.py` / `phonemes.py` etc.)

- Add any required character mappings or character-set entries in the library.

> **Why the setting can appear to do nothing:** The most common failure mode is wiring steps 1–4 in the front end but forgetting to pass the value through at one call site — typically the JS fetch in `main.html` (step 3) or the `saveSettingsToSession` in `settings.js` (step 4). The session may be correct, but the value is never sent with the API request, so the backend always sees the default.
