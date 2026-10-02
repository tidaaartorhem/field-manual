import sampleData from './sample-manual.json';
import { loadManual, type ManualData } from './lib/manual';

/**
 * Bundled sample edition. The app fetches /manual.json first (staged at
 * build time from ../data/manual.json when the pipeline has run); this is
 * the fallback so the app and the test suite always have a real,
 * schema-valid edition to work with before real data lands.
 */
export const sampleManual: ManualData = loadManual(sampleData);
