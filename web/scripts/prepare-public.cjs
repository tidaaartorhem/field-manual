/**
 * Build step: stage the edition data into web/public/manual.json.
 *
 * If ../data/manual.json exists (real pipeline output), it wins.
 * Otherwise the bundled sample edition (src/sample-manual.json) is staged
 * so the app always has something to read. The frontend ALSO ships the
 * sample as a bundled fallback, so this is belt and suspenders.
 */
const fs = require('fs');
const path = require('path');

const scriptsDir = __dirname;
const webDir = path.resolve(scriptsDir, '..');

const realData = path.resolve(webDir, '..', 'data', 'manual.json');
const sampleData = path.resolve(webDir, 'src', 'sample-manual.json');
const target = path.resolve(webDir, 'public', 'manual.json');

const source = fs.existsSync(realData) ? realData : sampleData;
if (!fs.existsSync(source)) {
  console.error(`prepare-public: no data found (looked for ${realData} and ${sampleData})`);
  process.exit(1);
}

fs.mkdirSync(path.dirname(target), { recursive: true });
fs.copyFileSync(source, target);
console.log(`prepare-public: staged ${path.basename(source)} -> public/manual.json`);
