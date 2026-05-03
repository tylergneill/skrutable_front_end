# Mobile-Friendly Overhaul — batch_meter_results.html

## Context

On narrow screens (iPhone, ~375px), the batch correction mode page is broken:
- `.bcm-panel` (fixed, left-column) overlaps card content because the 17% left column collapses to ~64px, which is too narrow to contain the panel
- `.bcm-nav-col` (nav arrows, same left column) is partially clipped off-screen
- `.bcm-stats-block` has `padding-left: calc(18% + 1em)` that eats into narrow width
- `.verse-raw` at 34% min-width 160px forces a horizontal overflow in the card body

The fix is a new `@media (max-width: 768px)` block that:
1. Kills the desktop fixed-left-column geometry
2. Replaces the floating panel with a bottom sheet drawer (opened via a ⚙ button in each card header)
3. Moves nav arrows to a fixed bottom bar
4. Stacks the raw-text column above the scansion column in each card

All changes are in **one file only**: `templates/batch_meter_results.html`

---

## Critical File

`/Users/tyler/Git/skrutable/skrutable_front_end/templates/batch_meter_results.html` (2197 lines)

Three insertion points inside the file:
- **A** — `<style>` block, after the `@media (max-width: 1100px)` block closing `}` at line 54
- **B** — `<body>`, after closing `</div>` of `#bcm-panel` at line 613
- **C** — inside `(function(){...})()` IIFE, before final `})();` at line 2194

---

## Part 1 — CSS (insertion point A)

Add immediately after line 54:

```css
/* Elements that only exist at mobile; hidden on desktop */
#bcm-sheet-overlay,
#bcm-bottom-sheet,
#bcm-mobile-nav-bar { display: none; }

@media (max-width: 768px) {

    /* 1a. Kill desktop left-column geometry */
    .bcm-panel    { display: none !important; }   /* replaced by bottom sheet */
    .bcm-nav-col  { display: none !important; }   /* replaced by mobile nav bar */
    .bcm-verses   { margin-left: 0; padding: 0 0.5em 5em; }   /* 5em clears nav bar */
    .bcm-stats-block { padding-left: 0.5em; overflow-x: auto; }

    /* 1b. Stats grid: let it scroll horizontally at narrow widths */
    .bcm-unified  { max-width: none; min-width: max-content; }

    /* 1c. Card body: stack raw above scansion */
    .verse-card-body { flex-direction: column; }
    .verse-raw {
        width: 100%; max-width: 100%; min-width: 0;
        border-right: none;
        border-bottom: 1px solid var(--input-border);
    }
    .verse-scansion { padding: 0.4em 0.5em; }

    /* 1d. Gear button injected into card headers */
    .bcm-panel-trigger {
        display: inline-flex; align-items: center; justify-content: center;
        background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.3);
        color: inherit; border-radius: 3px; padding: 0.1em 0.45em;
        font-size: 0.85em; cursor: pointer; flex-shrink: 0; line-height: 1.4;
        margin-left: auto;   /* push to right before verse-num */
    }
    .bcm-panel-trigger:hover { background: rgba(255,255,255,0.3); }
    /* When card is focused (gold header), gear button adapts */
    .verse-card.focused .bcm-panel-trigger {
        background: rgba(0,0,0,0.12); border-color: rgba(0,0,0,0.2); color: #1a1a1a;
    }

    /* 1e. Bottom sheet overlay */
    #bcm-sheet-overlay {
        display: none; position: fixed; inset: 0;
        background: rgba(0,0,0,0.45); z-index: 200;
    }
    #bcm-sheet-overlay.open { display: block; }

    #bcm-bottom-sheet {
        position: fixed; left: 0; right: 0; bottom: 0; z-index: 201;
        background: var(--sidebar-bg); color: var(--sidebar-text);
        border-radius: 12px 12px 0 0;
        box-shadow: 0 -4px 24px rgba(0,0,0,0.35);
        transform: translateY(100%);
        transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
        max-height: 70vh; overflow-y: auto;
    }
    #bcm-bottom-sheet.open { display: block; transform: translateY(0); }

    .bcm-sheet-handle {
        width: 36px; height: 4px;
        background: rgba(255,255,255,0.3); border-radius: 999px;
        margin: 10px auto 0;
    }
    .bcm-sheet-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.5em 1em 0.4em;
        border-bottom: 1px solid rgba(255,255,255,0.12);
    }
    .bcm-sheet-title { font-size: 0.9em; font-weight: 600; opacity: 0.85; }
    .bcm-sheet-close {
        background: none; border: none; color: var(--sidebar-text);
        font-size: 1.3em; cursor: pointer; padding: 0 0.2em; line-height: 1; opacity: 0.7;
    }
    .bcm-sheet-close:hover { opacity: 1; }

    .bcm-sheet-body { padding: 0.75em 1em 1em; }
    .bcm-sheet-body .checkbox-group {
        display: grid; grid-template-columns: 1fr 1fr; gap: 0.4em 1em;
        font-size: 0.95em; margin-bottom: 0.75em;
    }
    .bcm-sheet-body .checkbox-group label {
        display: flex; align-items: center; gap: 0.4em; white-space: nowrap; cursor: pointer;
    }
    .bcm-sheet-body .panel-mode-toggle { display: flex; gap: 0.5em; margin-bottom: 0.6em; }
    .bcm-sheet-body .panel-mode-btn {
        flex: 1; padding: 0.55rem 0.4rem; font-size: 1rem; font-weight: 500;
        border: 1px solid rgba(255,255,255,0.25); border-radius: 4px;
        background: var(--btn-bg); color: var(--btn-text); cursor: pointer;
    }
    #sheet-resplit {
        width: 100%; font-size: 0.95em;
        background: var(--input-bg); color: var(--main-text);
        border: 1px solid var(--input-border); border-radius: 3px; padding: 0.4em 0.5em;
    }

    /* 1f. Fixed bottom nav bar */
    #bcm-mobile-nav-bar {
        display: flex; position: fixed; bottom: 0; left: 0; right: 0;
        z-index: 100; background: var(--sidebar-bg);
        border-top: 1px solid var(--input-border);
        padding: 0.4em 1em; gap: 0.75em;
        justify-content: center; align-items: center;
    }
    #bcm-mobile-nav-bar .btn-nav {
        flex: 1; max-width: 10em; padding: 0.6em 1em; font-size: 1em; text-align: center;
    }

} /* end @media (max-width: 768px) */
```

---

## Part 2 — HTML (insertion point B)

Add after line 613 (closing `</div>` of `#bcm-panel`), before `<script>`:

```html
<!-- Mobile overlay backdrop -->
<div id="bcm-sheet-overlay"></div>

<!-- Mobile bottom sheet (mirrors panel content with sheet-* IDs) -->
<div id="bcm-bottom-sheet" role="dialog" aria-modal="true" aria-label="Verse options">
    <div class="bcm-sheet-handle"></div>
    <div class="bcm-sheet-header">
        <span class="bcm-sheet-title">verse options</span>
        <button class="bcm-sheet-close" id="bcm-sheet-close-btn" aria-label="Close">&#x2715;</button>
    </div>
    <div class="bcm-sheet-body">
        <div class="checkbox-group">
            <label><input type="checkbox" id="sheet-weights" checked> lglgl</label>
            <label><input type="checkbox" id="sheet-morae"> {mora}</label>
            <label><input type="checkbox" id="sheet-garas" checked> [ga&#7751;a]</label>
            <label><input type="checkbox" id="sheet-align"> align</label>
        </div>
        <div class="panel-mode-toggle">
            <button class="panel-mode-btn" id="sheet-btn-scan">Scan</button>
            <button class="panel-mode-btn" id="sheet-btn-identify">Identify</button>
        </div>
        <select id="sheet-resplit">
            <option value="none">don't resplit</option>
            <option value="resplit_lite">resplit lite</option>
            <option value="resplit_lite_keep_mid" selected>resplit lite keep mid</option>
            <option value="resplit_max">resplit max</option>
            <option value="resplit_max_keep_mid">resplit max keep mid</option>
        </select>
    </div>
</div>

<!-- Mobile bottom nav bar (buttons injected by JS) -->
<div id="bcm-mobile-nav-bar"></div>
```

---

## Part 3 — JavaScript (insertion point C)

Add before the final `})();` at line 2194. All existing functions (`focusCard`, `navigateNeeds`, `getPanelOpts`, `setPanelOpts`, `panelScan`, `panelReidentify`, `updateCardScansion`) are in scope because this code is inside the same IIFE.

### 3a. Mobile detection
```js
function isMobileLayout() {
    return window.matchMedia('(max-width: 768px)').matches;
}
```

### 3b. Sync helpers (panel ↔ sheet)
```js
var SHEET_FIELD_MAP = [
    ['panel-weights', 'sheet-weights'],
    ['panel-morae',   'sheet-morae'],
    ['panel-garas',   'sheet-garas'],
    ['panel-align',   'sheet-align'],
];
function syncPanelToSheet() {
    SHEET_FIELD_MAP.forEach(function(pair) {
        var p = document.getElementById(pair[0]), s = document.getElementById(pair[1]);
        if (p && s) s.checked = p.checked;
    });
    var pr = document.getElementById('panel-resplit'), sr = document.getElementById('sheet-resplit');
    if (pr && sr) sr.value = pr.value;
}
function syncSheetToPanel() {
    SHEET_FIELD_MAP.forEach(function(pair) {
        var p = document.getElementById(pair[0]), s = document.getElementById(pair[1]);
        if (p && s) p.checked = s.checked;
    });
    var pr = document.getElementById('panel-resplit'), sr = document.getElementById('sheet-resplit');
    if (pr && sr) pr.value = sr.value;
}
```

### 3c. Bottom sheet open/close
```js
var sheetOverlay  = document.getElementById('bcm-sheet-overlay');
var bottomSheet   = document.getElementById('bcm-bottom-sheet');
var sheetCloseBtn = document.getElementById('bcm-sheet-close-btn');

function openBottomSheet(idx) {
    focusCard(idx);          // ensures panel opts are loaded for this card
    syncPanelToSheet();
    sheetOverlay.classList.add('open');
    bottomSheet.classList.add('open');
}
function closeBottomSheet() {
    syncSheetToPanel();
    if (focusedIndex !== null) {
        verseOpts[focusedIndex] = getPanelOpts();
        updateCardScansion(focusedIndex);
    }
    sheetOverlay.classList.remove('open');
    bottomSheet.classList.remove('open');
}
sheetOverlay.addEventListener('click', closeBottomSheet);
sheetCloseBtn.addEventListener('click', closeBottomSheet);
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && bottomSheet.classList.contains('open')) closeBottomSheet();
});
bottomSheet.addEventListener('click', function(e) { e.stopPropagation(); });
```

### 3d. Sheet action buttons
```js
document.getElementById('sheet-btn-scan').addEventListener('click', function() {
    syncSheetToPanel();
    if (focusedIndex !== null) verseOpts[focusedIndex] = getPanelOpts();
    closeBottomSheet();
    panelScan();
});
document.getElementById('sheet-btn-identify').addEventListener('click', function() {
    syncSheetToPanel();
    if (focusedIndex !== null) verseOpts[focusedIndex] = getPanelOpts();
    closeBottomSheet();
    panelReidentify();
});
```

### 3e. Sheet checkbox/select live preview (mirrors into panel, triggers re-render)
```js
SHEET_FIELD_MAP.forEach(function(pair) {
    var s = document.getElementById(pair[1]), p = document.getElementById(pair[0]);
    if (!s || !p) return;
    s.addEventListener('change', function() {
        p.checked = s.checked;
        p.dispatchEvent(new Event('change'));   // triggers existing re-render logic
    });
});
document.getElementById('sheet-resplit').addEventListener('change', function() {
    var pr = document.getElementById('panel-resplit');
    if (pr) pr.value = this.value;
});
```

### 3f. Mobile nav bar — inject buttons
```js
var mobileNavBar = document.getElementById('bcm-mobile-nav-bar');
if (mobileNavBar) {
    var btnMUp = document.createElement('button');
    btnMUp.className = 'btn-nav'; btnMUp.textContent = '↑';
    btnMUp.title = 'Previous verse needing correction';
    var btnMDown = document.createElement('button');
    btnMDown.className = 'btn-nav'; btnMDown.textContent = '↓';
    btnMDown.title = 'Next verse needing correction';

    btnMUp.addEventListener('click', function() {
        navigateNeeds(-1);
        if (bottomSheet.classList.contains('open')) syncPanelToSheet();
    });
    btnMDown.addEventListener('click', function() {
        navigateNeeds(1);
        if (bottomSheet.classList.contains('open')) syncPanelToSheet();
    });
    mobileNavBar.appendChild(btnMUp);
    mobileNavBar.appendChild(btnMDown);
}
```

### 3g. Gear button injection into card headers (idempotent, MutationObserver re-runs)
```js
function injectGearButtons() {
    if (!isMobileLayout()) return;
    document.querySelectorAll('.verse-card').forEach(function(card) {
        var hdr = card.querySelector('.verse-card-header');
        if (!hdr || hdr.querySelector('.bcm-panel-trigger')) return;
        var idx = parseInt(card.dataset.idx, 10);
        var btn = document.createElement('button');
        btn.className = 'bcm-panel-trigger';
        btn.title = 'Verse options';
        btn.setAttribute('aria-label', 'Open verse options');
        btn.textContent = '⚙';   // ⚙
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            openBottomSheet(idx);
        });
        // Insert before .verse-num (always last child of header)
        var numSpan = hdr.querySelector('.verse-num');
        numSpan ? hdr.insertBefore(btn, numSpan) : hdr.appendChild(btn);
    });
}
injectGearButtons();   // run once for already-rendered cards

new MutationObserver(function() {
    injectGearButtons();
}).observe(document.getElementById('bcm-verses'), { childList: true });
```

---

## Verification

1. Load the page locally on a narrow viewport (DevTools → 375px iPhone width)
2. Confirm: no floating panel visible, full-width cards, stacked raw/scansion, bottom nav bar present
3. Tap a card header — ⚙ button should be visible
4. Tap ⚙ — bottom sheet slides up with checkboxes/Scan/Identify/resplit
5. Toggle a checkbox — scansion re-renders live behind the sheet
6. Tap Scan or Identify — sheet closes, action fires
7. Tap ↑/↓ in nav bar — navigates to next imperfect verse
8. On desktop (>768px): confirm zero visual change — panel, nav col, card side-by-side layout all unchanged
