const fs = require('fs-extra');
const path = require('path');
const deepmerge = require('deepmerge');

const projectRoot = path.join(__dirname, '..');
const extensionRoot = __dirname;
const distDir = path.join(projectRoot, 'dist');
const extensionDistDir = path.join(distDir, 'extension');

const targetBrowser = process.argv[2];
const releaseMode = process.argv.includes('--release');
if (!targetBrowser || !['chrome', 'firefox'].includes(targetBrowser)) {
  console.error('Usage: node extension/build.cjs <chrome|firefox> [--release]');
  process.exit(1);
}

const targetDistDir = path.join(extensionDistDir, targetBrowser);

function processBackgroundJs(content, targetBrowser) {
  const lines = content.split('\n');
  const outputLines = [];
  let inTarget = false;
  let inOther = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('// #if_build_is ')) {
      const browser = trimmed.substring('// #if_build_is '.length).trim().toLowerCase();
      if (!['chrome', 'firefox'].includes(browser)) {
        console.warn(`Warning: unrecognized preprocessor target '${browser}' in background.js — both branches will be included.`);
      }
      if (targetBrowser === browser) inTarget = true;
      else inOther = true;
      continue;
    }
    if (trimmed === '// #endif') { inTarget = false; inOther = false; continue; }
    if (!inOther) outputLines.push(line);
  }
  return outputLines.join('\n');
}

async function build() {
  try {
    const { version: pkgVersion } = await fs.readJson(path.join(projectRoot, 'package.json'));
    const { version: manifestVersion } = await fs.readJson(path.join(extensionRoot, 'manifest.common.json'));
    if (pkgVersion !== manifestVersion) {
      console.warn(`Warning: package.json version (${pkgVersion}) differs from manifest version (${manifestVersion}).`);
    }

    console.log(`Cleaning ${targetDistDir}...`);
    await fs.emptyDir(targetDistDir);

    const commonManifest = await fs.readJson(path.join(extensionRoot, 'manifest.common.json'));
    const browserManifest = await fs.readJson(path.join(extensionRoot, `manifest.${targetBrowser}.json`));
    const finalManifest = deepmerge(commonManifest, browserManifest);
    await fs.writeJson(path.join(targetDistDir, 'manifest.json'), finalManifest, { spaces: 2 });
    console.log('Manifest written.');

    // Copy extension source files
    for (const dir of ['js', 'ui', 'assets']) {
      const src = path.join(extensionRoot, dir);
      if (await fs.pathExists(src)) {
        await fs.copy(src, path.join(targetDistDir, dir));
        console.log(`Copied ${dir}/`);
      }
    }

    // Resolve __SKRUTABLE_BUNDLE_SRC__ in sidepanel.html
    const sidepanelPath = path.join(targetDistDir, 'ui', 'sidepanel.html');
    let sidepanelHtml = await fs.readFile(sidepanelPath, 'utf-8');
    if (releaseMode) {
      const { version } = await fs.readJson(path.join(projectRoot, 'package.json'));
      const cdnUrl = `https://cdn.jsdelivr.net/npm/skrutable-js@${version}/dist/skrutable.bundle.js`;
      sidepanelHtml = sidepanelHtml.replaceAll('__SKRUTABLE_BUNDLE_SRC__', cdnUrl);
      console.log(`Bundle src: CDN (${cdnUrl})`);
    } else {
      const bundleSrc = path.join(distDir, 'skrutable.bundle.js');
      if (!await fs.pathExists(bundleSrc)) {
        console.error(`Error: ${bundleSrc} not found. Run 'npm run build' first.`);
        process.exit(1);
      }
      await fs.copy(bundleSrc, path.join(targetDistDir, 'dist', 'skrutable.bundle.js'));
      sidepanelHtml = sidepanelHtml.replaceAll('__SKRUTABLE_BUNDLE_SRC__', '../dist/skrutable.bundle.js');
      console.log('Bundle src: local (../dist/skrutable.bundle.js)');
    }
    await fs.writeFile(sidepanelPath, sidepanelHtml, 'utf-8');

    // Process background.js for browser-specific blocks
    const bgPath = path.join(targetDistDir, 'js', 'background.js');
    if (await fs.pathExists(bgPath)) {
      const content = await fs.readFile(bgPath, 'utf-8');
      await fs.writeFile(bgPath, processBackgroundJs(content, targetBrowser), 'utf-8');
      console.log('Processed background.js');
    }

    console.log(`\nBuild for ${targetBrowser} complete: ${targetDistDir}`);
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build();
