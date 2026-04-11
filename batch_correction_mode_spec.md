# Batch Correction Mode — Design Spec

Modeled on https://sanskritmetres.appspot.com/fulltext (source at ../../shreevatsa/sanskrit).

## Overview

A new mode for batch meter identification that renders results as an interactive HTML page instead of a plain-text download, allowing the user to inspect, iterate on, and save research results verse by verse.

## Trigger / Entry Point

- New extra setting (checkbox), lives on the **settings page** (like `avoid_virama_indic_scripts`)
- Appears contextually in the **upload file UI** only when "Identify Meter" is the selected action (silently ignored otherwise — never shown for other actions)
- If checked: clicking "Upload and Process" takes the user to the new HTML result view
- If unchecked: existing plain-text download behavior unchanged
- Uses the **existing `POST /upload_file` route** with a flag (not a new route); when flag is set, returns JSON of structured verse data instead of a plain-text file download

## Input Format

- Unchanged: one verse per line (same as existing batch upload)

## Backend: What Data to Return

From each verse's skrutable `Verse` object, return per verse:
- `text_raw` — original input line
- `text_syllabified` — space-separated syllables per pāda (newline between pādas)
- `syllable_weights` — string of L/G chars per pāda (newline between pādas), aligned 1:1 with syllabified
- `morae_per_line` — list of ints
- `gaRa_abbreviations` — string per pāda (newline between pādas)
- `meter_label` — string (e.g. "anuṣṭubh (...)", "na kiṃcid adhyavasitam")
- `identification_score` — int (used to determine perfect vs. imperfect for green/red)
- `summary` — the existing plain-text summarize() output (for txt export)

Also return the session settings used (resplit_option, from_scheme, weights/morae/gaRas/alignment checkboxes) so the result page knows what was applied.

## Result Page

- New standalone page (e.g. `/batch-meter-results` or rendered directly)
- Does NOT extend `base.html` sidebar layout — behaves very differently from the rest of the site
- Has its own minimal header with a **global export button** (top-right): export all verses to **txt** (same format as existing batch download) or **csv** (columns: verse text, meter label, syllable weights — exact columns TBD)

## Verse Cards — Conveyor Belt

Scrollable list of verse cards, one per input line, modeled on shreevatsa's visual display:

Each card shows:
- **Header**: meter name, colored green (perfect/high score) or red (imperfect/unknown)
  - "possibly X" prefix when imperfect (matching shreevatsa style)
- **Left column**: original verse text (`text_raw`), preserved whitespace/newlines
- **Right column**: syllable-by-syllable L/G alignment
  - Each syllable is a small box rendered as an inline-grid element
  - Top cell: L or G marker (L = blue/lighter, G = darkred/bolder, background #CCC)
  - Bottom cell: syllable text (larger font)
  - Mismatches (when re-running against a known metre): `<abbr>` in red with tooltip
  - Line breaks between pādas

CSS to emulate from shreevatsa's `fulltext.html`:
```css
.scansion2 .L { color: blue; font-weight: lighter; }
.scansion2 .G { color: darkred; font-weight: bolder; }
.scansion2 .L, .scansion2 .G { background: #CCC; display: inline-grid; border: 1px ridge #fff; }
.syl { grid-row: 2; font-size: larger; }
.scan { grid-row: 1; text-align: center; }
.metreName { font-size: 150%; text-align: center; }
abbr { border-bottom: 1px dotted black; color: red; }
```

### Notes on mismatch highlighting (not yet committed)

Techniques observed in reference systems:

- **Shreevatsa** (samavṛtta/ardhasamavṛtta only): edit-distance realignment produces `[-]` deletion markers inline with the syllabified text, in red. Shows where the fit broke down structurally but is not a correction oracle — the suggested realignment can be garbled (e.g. splitting a word across a phantom syllable boundary). Does **not** show L/G display for anuṣṭubh at all — a gap that skrutable fills.
- **Ambuda** (`ambuda.org/proofing`): syllable-grid display (syllable text row + L/G weight row per pāda), with a **pink/red background on the entire column** of the offending syllable. Visually clean and direct when correct. However, ambuda's "odd syllable" detection (`MeterCheck._mark_odd_aksharas`) uses a "golden line" heuristic (lines that individually match a known meter become the reference; deviations in other lines are flagged). For anuṣṭubh this is unreliable — it can highlight the wrong pādas entirely (e.g. flagging the two correct pathyā pādas when the error is in pāda 1). **False-positive highlights are worse than no highlights.**
- **Chandojnanam**: separate Laghu-Guru table row per pāda, no color differentiation, fuzzy candidates in a ranked table. Unreadable in practice.

**Skrutable's position**: already produces `syllable_weights` aligned 1:1 with `text_syllabified` for all meter types including anuṣṭubh. The L/G box CSS (blue/lighter for L, darkred/bolder for G) gives visual weight distinction without needing extra color.

**Highlighting strategy by meter type (not yet committed):**

- **Samavṛtta / ardhasamavṛtta**: skrutable already identifies which pāda(s) fail to match the expected LG pattern. A positional column-by-column diff against the expected pattern can pinpoint diverging syllables with low false-positive risk. Optionally: distinguish wrong-weight (L vs G swap) from extra/missing syllables.
- **Anuṣṭubh**: skrutable currently reports asamīcīna at the half-verse level but does *not* report *which rule* caused the failure. Safe highlighting requires knowing whether the failure is due to Piṅgala rule 1 (syllables 2–3 both light), Piṅgala rule 2 (syllables 2–4 ra-gaṇa), a Hahn vipulā rule, or syllable count mismatch — each implicates different positions. **This requires a backend enhancement before anuṣṭubh highlighting can be implemented.** See `../skrutable/anustubh_diagnostics_spec.md`.

## Floating Tool Panel

- Clicking a verse card **focuses** it; a floating panel slides to that card (leaves any previously focused card)
- Panel contains:
  - **Scan** button — re-runs scan on this verse's text with current settings
  - **Identify Meter** button — re-runs meter identification with current settings
  - **Split Words** button — runs word splitting on this verse's text
  - **Edit** — makes verse text editable inline
  - **Save** — saves the edited text + current result for this verse
- After running a function: result updates the card; the **previous result is greyed out** until the new run completes, to signal invalidation
- Settings used by panel actions: carried from the original upload session (resplit_option, from_scheme, etc.) but should reflect any sidebar changes made since

## Persistence

- All verse state (original text, current text, current result, saved status, edit history) stored in **localStorage**
- Key: something like `skrutable_batch_<hash_of_input>` so multiple sessions can coexist
- User can close browser and return to find their work intact

## Global Export (top-right)

- **txt**: same format as existing batch identify-meter download (one verse block per verse: raw text + summarize() output)
- **csv**: one row per verse — columns TBD, at minimum: verse number, verse text, meter label, syllable weights

## Reference Systems Reviewed

- **shreevatsa/sanskrit** (`fulltext.html`): primary visual inspiration — L/G box grid layout, green/red card headers, "possibly X" prefix. Strong on display, weak on anuṣṭubh (no scansion shown) and on mismatch diagnosis (edit-distance realignment can be misleading).
- **hrishikeshrt/chandojnanam** (`sanskrit.iitk.ac.in/jnanasangraha/chanda/file`): richer data model (verse-level scoring, `match_extent` 0–1, ranked fuzzy candidates, jāti classification, Show/Hide Scansion toggle). Display is inferior — flat table rows, no color differentiation, fuzzy table shows raw Python repr. Not adopted for display; data model noted for possible future reference.
- **ambuda-org/ambuda** (`ambuda.org/proofing/...`): proofing tool for OCR correction of Sanskrit texts — opposite direction from ours (text is canonical, errors are transcription mistakes). Uses vidyut's Chandas library (Rust) for meter checking. Shows syllable-grid display with pink column highlight on "odd" syllables. Highlighting algorithm is unreliable for anuṣṭubh (majority-vote / golden-line heuristic can flag the wrong pādas). Visual approach noted; algorithm not adopted. See mismatch highlighting notes below.

## Implementation Notes

- The six-layer wiring for new extra settings (per CLAUDE.md) applies: `flask_app.py` (4 spots), `settings.html` (4 spots), `main.html` (3 spots), `settings.js` (2 spots)
- The upload file UI shows this option contextually — look at how `avoid_virama_indic_scripts` is shown for transliterate to understand the pattern, but apply it to identify meter
- No dependency on shreevatsa's codebase at runtime — all alignment data comes from skrutable's own `Verse` object attributes
- The visual rendering (L/G boxes) is done purely in frontend JS from the JSON payload
