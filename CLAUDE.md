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
| `flask.session` (server-side cookie) | Per-user, persists across requests | Sidebar settings: `skrutable_action`, `from_scheme`, `to_scheme`, `resplit_option`, scan detail checkboxes (`weights`, `morae`, `gaRas`, `alignment`), extra settings (`avoid_virama_indic_scripts`, `preserve_compound_hyphens`, `preserve_punctuation`, `splitter_model`), melody state (`meter_label`, `melody_options`). All tracked in `SESSION_VARIABLE_NAMES` at top of `flask_app.py`. Saved to server via `POST /api/save-settings`. |
| `localStorage` (browser) | Per-browser, persists across sessions | `text_input`, `text_output` (workbench textarea contents), `theme` (dark/light mode preference). |
| `flask.g` (request context) | Single request only | `text_input` — used during form POST processing in `flask_app.py`, not persisted. |

**Core actions** (selected via hidden `skrutable_action` form field):
- **transliterate** — convert between writing systems (IAST, HK, SLP, DEV, etc.)
- **scan** — metrical scansion showing weights, morae, gaṇas, alignment
- **identify meter** — scansion + meter identification with resplit options
- **split** — Sanskrit compound word splitting (via external splitter models)

**File upload processing** (`/upload_file`) — upload a file, process it with the selected action, return result as download.

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
