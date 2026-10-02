import { loadNewsletter, type Newsletter } from './lib/newsletter';
import sampleData from './sample-newsletter.json';

/** Bundled sample edition, used when the pipeline hasn't filed data yet. */
export const sampleNewsletter: Newsletter = loadNewsletter(sampleData);
