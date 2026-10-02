/**
 * Build step: stage the edition data into web/public/newsletter.json.
 *
 * If ../data/newsletter.json exists (real pipeline output), it wins.
 * Otherwise the bundled sample edition (src/sample-newsletter.json) is staged
 * so the app always has something to read. The frontend ALSO ships the
 * sample as a bundled fallback, so this is belt and suspenders.
 */
const fs = require('fs');
const path = require('path');

const scriptsDir = __dirname;
const webDir = path.resolve(scriptsDir, '..');

const realData = path.resolve(webDir, '..', 'data', 'newsletter.json');
const sampleData = path.resolve(webDir, 'src', 'sample-newsletter.json');
const target = path.resolve(webDir, 'public', 'newsletter.json');

const source = fs.existsSync(realData) ? realData : sampleData;
if (!fs.existsSync(source)) {
  console.error(`prepare-public: no data found (looked for ${realData} and ${sampleData})`);
  process.exit(1);
}

fs.mkdirSync(path.dirname(target), { recursive: true });
fs.copyFileSync(source, target);
console.log(`prepare-public: staged ${path.basename(source)} -> public/newsletter.json`);
