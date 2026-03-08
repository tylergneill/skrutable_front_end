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

**Single-file Flask app** (`flask_app.py`) — all routes, form processing, and skrutable integration live here. No blueprints, no separate route modules.

Key patterns:
- Uses `flask.session` to persist UI state (selected action, schemes, checkboxes, settings) across requests
- `flask.g` holds per-request `text_input` and `text_output`
- Four skrutable objects are instantiated once at module level: `T` (Transliterator), `S` (Scanner), `MI` (MeterIdentifier), `Spl` (Splitter)
- `CustomFlask`/`CustomRequest` subclasses override `max_form_memory_size` to handle large uploads (128 MB)

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
- `templates/` — Jinja2 templates; `main.html` is the primary UI with inline JS for swap/melody logic
- `assets/` — static CSS (Bootstrap + Bulma), JS libraries, melody MP3s, meter analysis data

**GitHub Actions:** `.github/workflows/clean_bucket.yml` — daily cleanup of stale GCS objects (>10 min old).

## Conventions

- Tabs for indentation in Python (not spaces) — match the existing style in `flask_app.py`
- Session variable names are tracked in `SESSION_VARIABLE_NAMES` and related lists at the top of `flask_app.py`; any new session variable must be added there
- Static files served via the `/assets/<path:name>` route, not Flask's default static handler
