/**
 * Build the Skrutable browser extension for one browser.
 *
 *   node build.cjs <chrome|firefox>
 *
 * Output goes to extension/dist/<browser>/, ready for "Load unpacked"
 * (Chrome) or "Load Temporary Add-on" (Firefox), or for zipping for a
 * store submission (see `make extension-zip-*` in the top-level Makefile).
 *
 * Steps:
 *   1. Merge manifest.common.json with manifest.<browser>.json.
 *   2. Copy js/, ui/ and assets/.
 *   3. Copy the skrutable-js library bundle to lib/skrutable.bundle.js,
 *      which ui/sidepanel.html loads. The bundle always ships inside the
 *      extension: Manifest V3 forbids loading scripts from a CDN.
 *   4. Strip the other browser's blocks from js/background.js.
 *
 * The bundle normally comes from the skrutable-js version pinned in
 * package.json (node_modules/skrutable-js). To try an unreleased library
 * build, point SKRUTABLE_JS_BUNDLE at it, e.g.
 *   SKRUTABLE_JS_BUNDLE=../../skrutable/js/dist/skrutable.bundle.js node build.cjs chrome
 * Never submit a build made that way to a store.
 */
const fs = require('fs-extra');
const path = require('path');
const deepmerge = require('deepmerge');

const extensionRoot = __dirname;
const BROWSERS = ['chrome', 'firefox'];

const targetBrowser = process.argv[2];
if (!BROWSERS.includes(targetBrowser)) {
  console.error('Usage: node build.cjs <chrome|firefox>');
  process.exit(1);
}
const targetDistDir = path.join(extensionRoot, 'dist', targetBrowser);

/**
 * Keep only the lines meant for this browser.
 *
 * background.js marks browser-specific code like this:
 *   // #if_build_is CHROME
 *   ...chrome-only lines...
 *   // #endif
 * Lines inside another browser's block are dropped; everything else is kept.
 */
function processBackgroundJs(content, browser) {
  const outputLines = [];
  let inOther = false;
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith('// #if_build_is ')) {
      const tag = trimmed.substring('// #if_build_is '.length).trim().toLowerCase();
      if (!BROWSERS.includes(tag)) {
        console.warn(`Warning: unrecognized preprocessor target '${tag}' in background.js; its block is kept.`);
      }
      inOther = BROWSERS.includes(tag) && tag !== browser;
      continue;
    }
    if (trimmed === '// #endif') { inOther = false; continue; }
    if (!inOther) outputLines.push(line);
  }
  return outputLines.join('\n');
}

/** Find the library bundle to ship: the override if set, else the pinned npm package. */
async function resolveBundle() {
  const override = process.env.SKRUTABLE_JS_BUNDLE;
  if (override) {
    const p = path.resolve(override);
    if (!await fs.pathExists(p)) throw new Error(`SKRUTABLE_JS_BUNDLE points to ${p}, which doesn't exist.`);
    return { file: p, label: `${p} (SKRUTABLE_JS_BUNDLE override; not for store submission)` };
  }
  const pkgDir = path.join(extensionRoot, 'node_modules', 'skrutable-js');
  const file = path.join(pkgDir, 'dist', 'skrutable.bundle.js');
  if (!await fs.pathExists(file)) throw new Error(`${file} not found. Run 'npm ci' in extension/ first.`);
  const { version } = await fs.readJson(path.join(pkgDir, 'package.json'));
  return { file, label: `skrutable-js ${version} from npm` };
}

async function build() {
  // The extension's own version lives in both package.json and the manifest;
  // the stores read the manifest, so the two must match.
  const { version: pkgVersion } = await fs.readJson(path.join(extensionRoot, 'package.json'));
  const commonManifest = await fs.readJson(path.join(extensionRoot, 'manifest.common.json'));
  if (pkgVersion !== commonManifest.version) {
    throw new Error(`package.json version (${pkgVersion}) differs from manifest.common.json version (${commonManifest.version}).`);
  }

  const bundle = await resolveBundle();

  await fs.emptyDir(targetDistDir);

  const browserManifest = await fs.readJson(path.join(extensionRoot, `manifest.${targetBrowser}.json`));
  await fs.writeJson(path.join(targetDistDir, 'manifest.json'), deepmerge(commonManifest, browserManifest), { spaces: 2 });

  for (const dir of ['js', 'ui', 'assets']) {
    await fs.copy(path.join(extensionRoot, dir), path.join(targetDistDir, dir));
  }

  await fs.copy(bundle.file, path.join(targetDistDir, 'lib', 'skrutable.bundle.js'));

  const bgPath = path.join(targetDistDir, 'js', 'background.js');
  await fs.writeFile(bgPath, processBackgroundJs(await fs.readFile(bgPath, 'utf-8'), targetBrowser), 'utf-8');

  console.log(`Built extension ${pkgVersion} for ${targetBrowser} in ${targetDistDir}`);
  console.log(`Library bundle: ${bundle.label}`);
}

build().catch((error) => {
  console.error(`Build failed: ${error.message}`);
  process.exit(1);
});
