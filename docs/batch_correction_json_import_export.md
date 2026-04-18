# Batch Correction Mode: JSON Export/Import (Resume Session)

## Motivation

After working in batch correction mode, a user may want to save their progress and resume later — or share a session with someone else — without re-running the expensive identify-meter pipeline on upload. The existing `.txt` and `.csv` exports don't carry enough structured data to reconstruct the full UI state.

## Design

### Export

Add an **export .json** button alongside the existing export buttons in the header. It dumps `verseState` directly:

```js
window.exportJson = function() {
    exported = true;
    var payload = {
        version: 1,
        settings: settings,           // original session settings (from_scheme, resplit_option, etc.)
        verses: verseState,           // full array: text_raw, meter_label, identification_score,
                                      // text_syllabified, syllable_weights, morae_per_line,
                                      // gaRa_abbreviations, diagnostic, summary
    };
    downloadFile(JSON.stringify(payload, null, 2), 'batch_meter_results.json', 'application/json');
};
```

### Import

Add an **import .json** button (or drag-and-drop zone) in the header. On file select:

1. Parse the JSON
2. Replace `verseState` with `payload.verses`
3. Re-initialize `verseOpts` from `payload.settings` (or per-verse if saved)
4. Re-initialize `meterCounts`, `perfectCount`, `needsCount` from the loaded data
5. Call `renderCards()` and `updateFilterUI()`

No server round-trip needed — all data is already in the JSON.

```js
// Rough sketch
document.getElementById('btn-import-json').addEventListener('change', function(e) {
    var file = e.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function(ev) {
        var payload = JSON.parse(ev.target.result);
        verseState = payload.verses;
        verses = payload.verses;  // keep in sync for filter counts
        settings = payload.settings || settings;
        // re-init verseOpts, counts, meterList, then renderCards()
    };
    reader.readAsText(file);
});
```

### UI placement

Header right-side, between the existing export buttons and the theme toggle:

```
← workbench   batch meter correction mode   [import .json] [export .json] [export .txt] [export .csv] [🌙]
```

The import button can be a `<label>` wrapping a hidden `<input type="file" accept=".json">` so it looks like a button.

## Notes

- `verseOpts` (per-card panel settings) are not currently in `verseState` — if we want full per-card option persistence across sessions, add them to the JSON payload separately as a parallel array
- The `duration_secs` field in the original payload is irrelevant on import (it was the original processing time); omit or zero it out
- Version field allows future schema migrations
