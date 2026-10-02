/**
 * Build step: stage the edition data into web/public/.
 *
 * - newsletter.json: real pipeline output wins; bundled sample otherwise.
 * - charts.json: staged only when the pipeline computed charts (optional).
 * - Chart PNGs live in web/public/charts/<edition>/, written by the
 *   pipeline before the build; vite copies public/ -> dist/ verbatim.
 */
const fs = require('fs');
const path = require('path');

const scriptsDir = __dirname;
const webDir = path.resolve(scriptsDir, '..');

function stage(realData, fallbackData, targetName, required) {
  const target = path.resolve(webDir, 'public', targetName);
  const source = fs.existsSync(realData) ? realData : fallbackData;
  if (!source || !fs.existsSync(source)) {
    if (required) {
      console.error(`prepare-public: no data found for ${targetName}`);
      process.exit(1);
    }
    console.log(`prepare-public: no ${targetName} (optional, skipping)`);
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
  console.log(`prepare-public: staged ${path.basename(source)} -> public/${targetName}`);
}

stage(
  path.resolve(webDir, '..', 'data', 'newsletter.json'),
  path.resolve(webDir, 'src', 'sample-newsletter.json'),
  'newsletter.json',
  true,
);

stage(
  path.resolve(webDir, '..', 'data', 'charts.json'),
  null,
  'charts.json',
  false,
);
