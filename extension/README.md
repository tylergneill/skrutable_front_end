# Skrutable Sanskrit Tools (browser extension)

A browser extension that brings Skrutable's transliteration, scansion, meter identification and word splitting to any web page. Select some text, then click the toolbar icon or right-click and choose "Process with Skrutable": the text opens in a side panel with the same workbench as [skrutable.info](https://www.skrutable.info).

- **Chrome:** [Chrome Web Store](https://chromewebstore.google.com/detail/skrutable-sanskrit-tools/mgkkdjpbbpalpombplgeecggakdglfnp)
- **Firefox:** builds and runs, but not yet submitted to addons.mozilla.org (to do).

The extension was written by Antariksh Bokale in [linguistrix/skrutable-js](https://github.com/linguistrix/skrutable-js) and continued in Tyler's fork, [tylergneill/skrutable-js](https://github.com/tylergneill/skrutable-js). It moved here, with its history, in November 2026.

## How it works

Everything except word splitting runs inside the browser. The side panel loads the [skrutable-js](https://www.npmjs.com/package/skrutable-js) library bundle, the JavaScript port of the Python [skrutable](https://github.com/tylergneill/skrutable) library, which lives in that repo under `js/`. The bundle ships inside the extension, because Manifest V3 doesn't allow loading scripts from a CDN. Word splitting calls the same splitter servers as the web app, and meter melodies play from skrutable.info.

Settings are kept in the browser's synced extension storage, not on a server.

| Path | What it is |
|------|------------|
| `manifest.common.json` | Manifest fields shared by both browsers, including the extension's version |
| `manifest.chrome.json`, `manifest.firefox.json` | Browser-specific fields (Chrome side panel, Firefox sidebar) |
| `js/background.js` | Toolbar icon and right-click menu; opens the panel and passes it the selected text. `// #if_build_is CHROME` / `FIREFOX` blocks are kept or dropped at build time |
| `js/sidepanel/index.js` | The side panel's workbench, ported from the web app's JS |
| `ui/` | Side panel HTML and CSS |
| `build.cjs` | Builds one browser's extension into `dist/<browser>/` |
| `package.json` | Pins the skrutable-js version and the build tools. Not published anywhere |

### Permissions

- `activeTab` and `scripting`: read the selected text in the current tab when the toolbar icon is clicked. Only the tab's main frame is read, so the extension needs no access to all sites; text selected inside an embedded frame still works through the right-click menu.
- `contextMenus` (and `menus` on Firefox): the right-click menu item.
- `storage`: remember settings.
- `sidePanel` (Chrome): the side panel.
- Host access to the two splitter servers (Dharmamitra and the 2018 EMNLP splitter), for word splitting.

## Building and trying it out

From the repo root:

```bash
make extension-build      # npm ci, then build Chrome and Firefox into extension/dist/
```

- **Chrome:** open `chrome://extensions`, turn on Developer mode, click Load unpacked and pick `extension/dist/chrome`.
- **Firefox:** open `about:debugging#/runtime/this-firefox`, click Load Temporary Add-on and pick `extension/dist/firefox/manifest.json`.

After a rebuild, click the reload icon on the extension's card (Chrome) or Reload (Firefox).

To try an unreleased build of the library, build it in the skrutable repo (`cd js && npm run build`) and point the extension at it:

```bash
cd extension
SKRUTABLE_JS_BUNDLE=../../skrutable/js/dist/skrutable.bundle.js node build.cjs chrome
```

Don't submit a build made this way; `make extension-zip` always uses the pinned npm version.

## Releasing

1. To pick up a new library release, change the `skrutable-js` version in `package.json` and run `npm install` here to update `package-lock.json`.
2. Bump the extension's own version in both `package.json` and `manifest.common.json` (the build stops if they differ). It is separate from the library's version.
3. From the repo root, run `make extension-zip`. It writes `extension/dist/skrutable-extension-chrome-<version>.zip` and the Firefox one.
4. Load the unzipped build once more and check all four actions.
5. Upload the Chrome zip in the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole). Firefox is still to do: [addons.mozilla.org developer hub](https://addons.mozilla.org/developers/), with the gecko id `skrutable@tylergneill.com` from `manifest.firefox.json`.
