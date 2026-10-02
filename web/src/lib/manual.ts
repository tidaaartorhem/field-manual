/**
 * Shape validation + helpers for the field-manual data contract
 * (see ../SCHEMA.md). The pipeline writes data/manual.json; the web app
 * fetches it and runs it through loadManual before rendering anything.
 */

export interface Briefing {
  lede: string;
  what_happened: string;
  why_it_matters: string;
  steal_this: string;
}

export interface ManualItem {
  id: string;
  title: string;
  url: string;
  source: string;
  published: string | null;
  shelf: string;
  score: number;
  briefing: Briefing;
  takeaways: string[];
  queries: string[];
}

export interface Shelf {
  id: string;
  title: string;
  tagline: string;
  items: ManualItem[];
}

export interface ManualStats {
  items: number;
  shelves: number;
  sources: number;
}

export interface ManualData {
  edition: string;
  generated_at: string;
  shelves: Shelf[];
  start_here: string[];
  stats: ManualStats;
}

export class ManualValidationError extends Error {
  readonly issues: string[];
  constructor(issues: string[]) {
    super(`Invalid manual data: ${issues.join('; ')}`);
    this.name = 'ManualValidationError';
    this.issues = issues;
  }
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.trim().length > 0;
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === 'string');
}

function validateBriefing(b: unknown, path: string, issues: string[]): void {
  if (typeof b !== 'object' || b === null) {
    issues.push(`${path}: briefing must be an object`);
    return;
  }
  const rec = b as Record<string, unknown>;
  for (const key of ['lede', 'what_happened', 'why_it_matters', 'steal_this']) {
    if (!isNonEmptyString(rec[key])) issues.push(`${path}: briefing.${key} must be a non-empty string`);
  }
}

function validateItem(item: unknown, path: string, issues: string[]): void {
  if (typeof item !== 'object' || item === null) {
    issues.push(`${path}: item must be an object`);
    return;
  }
  const it = item as Record<string, unknown>;
  if (!isNonEmptyString(it.id)) issues.push(`${path}: id must be a non-empty string`);
  if (!isNonEmptyString(it.title)) issues.push(`${path}: title must be a non-empty string`);
  if (!isNonEmptyString(it.url) || !/^https?:\/\//.test(it.url as string))
    issues.push(`${path}: url must be a non-empty http(s) URL`);
  if (!isNonEmptyString(it.source)) issues.push(`${path}: source must be a non-empty string`);
  if (it.published !== null && !isNonEmptyString(it.published))
    issues.push(`${path}: published must be an ISO date string or null`);
  if (!isNonEmptyString(it.shelf)) issues.push(`${path}: shelf must be a non-empty string`);
  if (typeof it.score !== 'number' || Number.isNaN(it.score) || it.score < 0 || it.score > 1)
    issues.push(`${path}: score must be a number between 0 and 1`);
  validateBriefing(it.briefing, path, issues);
  if (!Array.isArray(it.takeaways) || it.takeaways.length === 0 || !it.takeaways.every(isNonEmptyString))
    issues.push(`${path}: takeaways must be a non-empty array of strings`);
  if (!isStringArray(it.queries)) issues.push(`${path}: queries must be an array of strings`);
}

/**
 * Validate unknown data against the schema. Returns a list of issues;
 * an empty list means the data is a valid ManualData.
 */
export function validateManual(data: unknown): string[] {
  const issues: string[] = [];
  if (typeof data !== 'object' || data === null) return ['root: manual must be an object'];

  const d = data as Record<string, unknown>;
  if (!isNonEmptyString(d.edition)) issues.push('root: edition must be a non-empty string');
  if (!isNonEmptyString(d.generated_at)) issues.push('root: generated_at must be a non-empty string');

  if (!Array.isArray(d.shelves) || d.shelves.length === 0) {
    issues.push('root: shelves must be a non-empty array');
  } else {
    const shelfIds = new Set<string>();
    d.shelves.forEach((shelf: unknown, si: number) => {
      const path = `shelves[${si}]`;
      if (typeof shelf !== 'object' || shelf === null) {
        issues.push(`${path}: shelf must be an object`);
        return;
      }
      const s = shelf as Record<string, unknown>;
      if (!isNonEmptyString(s.id)) issues.push(`${path}: id must be a non-empty string`);
      else if (shelfIds.has(s.id as string)) issues.push(`${path}: duplicate shelf id "${s.id}"`);
      else shelfIds.add(s.id as string);
      if (!isNonEmptyString(s.title)) issues.push(`${path}: title must be a non-empty string`);
      if (!isNonEmptyString(s.tagline)) issues.push(`${path}: tagline must be a non-empty string`);
      if (!Array.isArray(s.items)) {
        issues.push(`${path}: items must be an array`);
      } else {
        s.items.forEach((item: unknown, ii: number) => validateItem(item, `${path}.items[${ii}]`, issues));
      }
    });
  }

  if (!isStringArray(d.start_here)) issues.push('root: start_here must be an array of item-id strings');

  if (typeof d.stats !== 'object' || d.stats === null) {
    issues.push('root: stats must be an object');
  } else {
    const st = d.stats as Record<string, unknown>;
    for (const key of ['items', 'shelves', 'sources']) {
      if (typeof st[key] !== 'number' || Number.isNaN(st[key]) || (st[key] as number) < 0)
        issues.push(`root: stats.${key} must be a non-negative number`);
    }
  }

  return issues;
}

/** Validate and return the manual, throwing ManualValidationError on failure. */
export function loadManual(data: unknown): ManualData {
  const issues = validateManual(data);
  if (issues.length > 0) throw new ManualValidationError(issues);
  return data as ManualData;
}

/** All items across all shelves, in shelf order. */
export function allItems(manual: ManualData): ManualItem[] {
  return manual.shelves.flatMap((shelf) => shelf.items);
}

/** Find a shelf by id. */
export function shelfById(manual: ManualData, id: string): Shelf | undefined {
  return manual.shelves.find((shelf) => shelf.id === id);
}

/** Find an item by id across all shelves. */
export function itemById(manual: ManualData, id: string): ManualItem | undefined {
  return allItems(manual).find((item) => item.id === id);
}

/**
 * Resolve the curated "start here" reading path, in order.
 * Unknown ids are skipped so one stale id can never break the path.
 */
export function getStartHere(manual: ManualData): ManualItem[] {
  const byId = new Map(allItems(manual).map((item) => [item.id, item]));
  const path: ManualItem[] = [];
  for (const id of manual.start_here) {
    const item = byId.get(id);
    if (item) path.push(item);
  }
  return path;
}
