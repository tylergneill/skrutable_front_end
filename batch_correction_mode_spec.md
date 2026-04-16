# Batch Correction Mode — Design Spec

Modeled on https://sanskritmetres.appspot.com/fulltext (source at ../../shreevatsa/sanskrit).

## Status: IMPLEMENTED (as of April 2026)

Core feature is fully working. See "What's Implemented" section below for details.
Outstanding items from original spec that were deferred or modified are noted inline.

---

## Overview

A new mode for batch meter identification that renders results as an interactive HTML page instead of a plain-text download, allowing the user to inspect, iterate on, and save research results verse by verse.

## Trigger / Entry Point ✅

- New extra setting (checkbox), lives on the **settings page** (like `avoid_virama_indic_scripts`)
- Appears contextually in the **upload file UI** only when "Identify Meter" is the selected action (silently ignored otherwise)
- If checked: clicking "Upload and Process" takes the user to the new HTML result view
- If unchecked: existing plain-text download behavior unchanged
- Uses the **existing `POST /upload_file` route** with a flag; when flag is set, renders `batch_meter_results.html` directly via `render_template()` with JSON embedded via Jinja (`{{ batch_data_json | safe }}`)
  - **Not** returning JSON + redirect: server-side rendering avoids localStorage 5 MB quota issues (tested with 19354-verse Ramayana)

## Input Format ✅

- Unchanged: one verse per line (same as existing batch upload)

## Backend: What Data to Return ✅

From each verse's skrutable `Verse` object, returned per verse:
- `text_raw` — original input line
- `text_syllabified` — space-separated syllables per pāda (newline between pādas)
- `syllable_weights` — string of L/G chars per pāda (newline between pādas), aligned 1:1 with syllabified
- `morae_per_line` — list of ints
- `gaRa_abbreviations` — string per pāda (newline between pādas)
- `meter_label` — string (e.g. "anuṣṭubh (...)", "na kiṃcid adhyavasitam")
- `identification_score` — int; perfect threshold is **9** (not 100 — all meters score max 9)
- `summary` — the existing plain-text summarize() output (for txt export)
- `diagnostic` — serialized anuṣṭubh diagnostic namedtuple dict; see Diagnostic section below

Session settings also embedded: `resplit_option`, `from_scheme`, `weights`/`morae`/`gaRas`/`alignment` checkboxes.

### Diagnostic structure

For anuṣṭubh verses, `diagnostic` is a dict:
```json
{
  "ab": {
    "perfect_id_label": "pathyā",
    "imperfect_id_label": null,
    "failure_code": null,
    "problem_syllables": {"odd": [], "even": []}
  },
  "cd": {
    "perfect_id_label": null,
    "imperfect_id_label": "asamīcīnā, na prathamāt snau",
    "failure_code": "hahn_general_2",
    "problem_syllables": {"odd": [], "even": [1, 2]}
  }
}
```
- `failure_code`: `'hypermetric'` / `'hypometric'` = length error (highlight whole row); `'hahn_general_*'` etc. = rule failure (highlight specific syllables)
- `problem_syllables`: 0-indexed positions within the pāda within each half (`'odd'` = pāda 1 or 3, `'even'` = pāda 2 or 4)
- Non-anuṣṭubh meters: `diagnostic` is `null`

## Result Page (`templates/batch_meter_results.html`) ✅

- Standalone page (does NOT extend `base.html` sidebar layout)
- Data embedded as `var batchData = {{ batch_data_json | safe }};` in a `<script>` block
- Sticky header with: ← workbench link, page title, export .txt / export .csv buttons, dark mode toggle

## Stats Block ✅

- Summary bar: total verse count, perfect count (green), error count (red), unidentified count, processing duration
- Collapsible meter-type breakdown table (ranked by frequency, with count and percentage)
- View toggle: "errors & unknown only" (default) vs "all (perfect shown compactly)"

## Verse Cards ✅

Scrollable list of verse cards, one per input line:

**Card header** (clickable — focuses card and shows floating panel):
- Background: green (perfect, score ≥ 9), red (imperfect), gray (unknown)
- Shows only the **base meter name** (parenthetical diagnostic stripped from header)
- Verse number shown on right

**Card body** — two columns:
- **Left**: original verse text (`text_raw`), click anywhere to make editable (contenteditable textarea), auto-saves on blur. Esc cancels.
- **Right**: L/G scansion display (see below)

## L/G Scansion Display ✅

- One row per pāda
- Each syllable: small box with L/G marker on top, syllable text below
- **L** = bold blue; **G** = bold darkred; background #CCC
- **Gaṇa groups** (when `gaRa_abbreviations` present): triṣyllabic groups have a `border-top` bracket line with gaṇa letter label below; remainder single chars aligned consistently
- **Length errors** (`hypermetric`/`hypometric`): entire pāda row tinted red
- **Problem syllables** (rule failures): individual syllable boxes highlighted pink (`.syl-box.problem`)
- **Imperfect label**: shown inline to the RIGHT of the relevant pāda row (pādas 1 and 3, i.e. the second pāda of each half), larger italic red text
- **Mora annotation**: shown only for jāti meters

## Floating Tool Panel ✅

- Position: fixed, **left side** of screen (`left: 1em`)
- Appears when a card is focused; slides vertically to align with the focused card using `getBoundingClientRect() + scrollY`; repositions on scroll
- Toggle: clicking the focused card's header again dismisses the panel
- Panel UI (two rows):
  - Row 1: **Scan** button + 4 checkboxes (lglgl, {mora}, [gaṇa], align)
  - Row 2: **Identify Meter** button + resplit dropdown
- Panel seeded from session settings at page load
- After running: card scansion/header updates in place; stale state shown at reduced opacity during fetch

**Not yet implemented** from original spec:
- ~~Split Words button~~ — deferred
- Sidebar settings sync (panel reflects settings at page load but does not watch for live sidebar changes)

## Persistence ✅ / ⚠️

- Verse text edits are held in JS `verseState` for the session (in-memory)
- **localStorage persistence** was deferred: large corpora (19k verses) hit the 5 MB quota, so the current approach stores data server-side in the rendered page. If the user closes the tab, edits are lost.
- Export to .txt or .csv preserves current `verseState` (including edits)

## Global Export ✅

- **txt**: one verse block per verse: raw text + summarize() output, ending with "samāptam: N padyāni"
- **csv**: verse number, verse text, meter label, syllable weights, identification score

## API Enhancements ✅

Both `/api/scan` and `/api/identify-meter` were extended to return the extra fields needed by the panel's re-run actions:
- `/api/scan` now returns: `text_syllabified`, `syllable_weights`, `morae_per_line`, `gaRa_abbreviations`
- `/api/identify-meter` now returns: `meter_label_full`, `identification_score`, `text_syllabified`, `syllable_weights`, `morae_per_line`, `gaRa_abbreviations`, `diagnostic`

## Mismatch Highlighting Notes (background research, not from spec)

### Notes on mismatch highlighting

Techniques observed in reference systems:

- **Shreevatsa** (samavṛtta/ardhasamavṛtta only): edit-distance realignment produces `[-]` deletion markers inline with the syllabified text, in red. Shows where the fit broke down structurally but is not a correction oracle — the suggested realignment can be garbled (e.g. splitting a word across a phantom syllable boundary). Does **not** show L/G display for anuṣṭubh at all — a gap that skrutable fills.
- **Ambuda** (`ambuda.org/proofing`): syllable-grid display (syllable text row + L/G weight row per pāda), with a **pink/red background on the entire column** of the offending syllable. Visually clean and direct when correct. However, ambuda's "odd syllable" detection (`MeterCheck._mark_odd_aksharas`) uses a "golden line" heuristic (lines that individually match a known meter become the reference; deviations in other lines are flagged). For anuṣṭubh this is unreliable — it can highlight the wrong pādas entirely (e.g. flagging the two correct pathyā pādas when the error is in pāda 1). **False-positive highlights are worse than no highlights.**
- **Chandojnanam**: separate Laghu-Guru table row per pāda, no color differentiation, fuzzy candidates in a ranked table. Unreadable in practice.

**Skrutable's approach** (implemented): uses `diagnostic` from the library, which reports exact `problem_syllables` positions and `failure_code` for anuṣṭubh. Length errors highlight the whole row; rule-failure errors highlight specific syllables. Non-anuṣṭubh meters: `diagnostic` is null and no highlighting is applied (samavṛtta positional diff is a potential future enhancement).

## Reference Systems Reviewed

- **shreevatsa/sanskrit** (`fulltext.html`): primary visual inspiration — L/G box grid layout, green/red card headers, "possibly X" prefix. Strong on display, weak on anuṣṭubh (no scansion shown) and on mismatch diagnosis (edit-distance realignment can be misleading).
- **hrishikeshrt/chandojnanam** (`sanskrit.iitk.ac.in/jnanasangraha/chanda/file`): richer data model (verse-level scoring, `match_extent` 0–1, ranked fuzzy candidates, jāti classification, Show/Hide Scansion toggle). Display is inferior — flat table rows, no color differentiation, fuzzy table shows raw Python repr. Not adopted for display; data model noted for possible future reference.
- **ambuda-org/ambuda** (`ambuda.org/proofing/...`): proofing tool for OCR correction of Sanskrit texts — opposite direction from ours (text is canonical, errors are transcription mistakes). Uses vidyut's Chandas library (Rust) for meter checking. Shows syllable-grid display with pink column highlight on "odd" syllables. Highlighting algorithm is unreliable for anuṣṭubh (majority-vote / golden-line heuristic can flag the wrong pādas). Visual approach noted; algorithm not adopted. See mismatch highlighting notes above.

## Implementation Notes

- The six-layer wiring for new extra settings (per CLAUDE.md) applies: `flask_app.py` (4 spots), `settings.html` (4 spots), `main.html` (3 spots), `settings.js` (2 spots)
- `do_scan()` was modified to return `(summary, V)` tuple (was `summary` only) so `/api/scan` can access `V` attributes
- `serialize_diagnostic()` helper in `flask_app.py` converts the anuṣṭubh `Diagnostic` namedtuple to a JSON-serializable dict
- Perfect score threshold is `9` (not 100) — all skrutable meters score on a 0–9 scale (`meter_scores["max score"] = 9`)
- No dependency on shreevatsa's codebase at runtime — all alignment data comes from skrutable's own `Verse` object attributes
