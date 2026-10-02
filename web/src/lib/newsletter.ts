/**
 * Shape validation + helpers for the v2 newsletter data contract.
 * The pipeline writes data/newsletter.json; the web app fetches it and
 * runs it through loadNewsletter before rendering anything.
 */

export interface Briefing {
  lede: string;
  what_happened: string;
  why_it_matters: string;
  steal_this: string;
}

export interface NewsletterItem {
  id: string;
  title: string;
  url: string;
  source: string;
  published: string | null;
  date_verified: boolean;
  shelf: string;
  score: number;
  briefing: Briefing;
  takeaways: string[];
  queries: string[];
}

export interface Section {
  id: string;
  title: string;
  kicker: string;
  narrative: string;
  closing_take: string;
  items: NewsletterItem[];
}

export interface NewsletterStats {
  items: number;
  sections: number;
  sources: number;
}

export interface Newsletter {
  edition: string;
  window_hours: number;
  generated_at: string;
  lede: string;
  sections: Section[];
  stats: NewsletterStats;
}

export class NewsletterValidationError extends Error {
  declare readonly issues: string[];
  constructor(issues: string[]) {
    super(`Invalid newsletter data: ${issues.join('; ')}`);
    this.name = 'NewsletterValidationError';
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
  if (typeof it.date_verified !== 'boolean')
    issues.push(`${path}: date_verified must be a boolean`);
  if (!isNonEmptyString(it.shelf)) issues.push(`${path}: shelf must be a non-empty string`);
  if (typeof it.score !== 'number' || Number.isNaN(it.score) || it.score < 0 || it.score > 1)
    issues.push(`${path}: score must be a number between 0 and 1`);
  validateBriefing(it.briefing, path, issues);
  if (!Array.isArray(it.takeaways) || it.takeaways.length === 0 || !it.takeaways.every(isNonEmptyString))
    issues.push(`${path}: takeaways must be a non-empty array of strings`);
  if (!isStringArray(it.queries)) issues.push(`${path}: queries must be an array of strings`);
}

export function validateNewsletter(data: unknown): string[] {
  const issues: string[] = [];
  if (typeof data !== 'object' || data === null) return ['root: newsletter must be an object'];

  const d = data as Record<string, unknown>;
  if (!isNonEmptyString(d.edition)) issues.push('root: edition must be a non-empty string');
  if (typeof d.window_hours !== 'number' || d.window_hours <= 0)
    issues.push('root: window_hours must be a positive number');
  if (!isNonEmptyString(d.generated_at)) issues.push('root: generated_at must be a non-empty string');
  if (!isNonEmptyString(d.lede)) issues.push('root: lede must be a non-empty string');

  if (!Array.isArray(d.sections) || d.sections.length === 0) {
    issues.push('root: sections must be a non-empty array');
  } else {
    const sectionIds = new Set<string>();
    d.sections.forEach((section: unknown, si: number) => {
      const path = `sections[${si}]`;
      if (typeof section !== 'object' || section === null) {
        issues.push(`${path}: section must be an object`);
        return;
      }
      const s = section as Record<string, unknown>;
      if (!isNonEmptyString(s.id)) issues.push(`${path}: id must be a non-empty string`);
      else if (sectionIds.has(s.id as string)) issues.push(`${path}: duplicate section id "${s.id}"`);
      else sectionIds.add(s.id as string);
      for (const key of ['title', 'kicker', 'narrative', 'closing_take']) {
        if (!isNonEmptyString(s[key])) issues.push(`${path}: ${key} must be a non-empty string`);
      }
      if (!Array.isArray(s.items)) {
        issues.push(`${path}: items must be an array`);
      } else {
        s.items.forEach((item: unknown, ii: number) => validateItem(item, `${path}.items[${ii}]`, issues));
      }
    });
  }

  if (typeof d.stats !== 'object' || d.stats === null) {
    issues.push('root: stats must be an object');
  } else {
    const st = d.stats as Record<string, unknown>;
    for (const key of ['items', 'sections', 'sources']) {
      if (typeof st[key] !== 'number' || Number.isNaN(st[key]) || (st[key] as number) < 0)
        issues.push(`root: stats.${key} must be a non-negative number`);
    }
  }

  return issues;
}

/** Validate and return the newsletter, throwing on failure. */
export function loadNewsletter(data: unknown): Newsletter {
  const issues = validateNewsletter(data);
  if (issues.length > 0) throw new NewsletterValidationError(issues);
  return data as Newsletter;
}

/** All items across all sections, in section order. */
export function allItems(letter: Newsletter): NewsletterItem[] {
  return letter.sections.flatMap((s) => s.items);
}

/** Find a section by id. */
export function sectionById(letter: Newsletter, id: string): Section | undefined {
  return letter.sections.find((s) => s.id === id);
}

/** Find an item by id across all sections. */
export function itemById(letter: Newsletter, id: string): NewsletterItem | undefined {
  return allItems(letter).find((item) => item.id === id);
}

/** Human label for a margin-note target: "section:signal" or an item id. */
export function targetLabel(letter: Newsletter, targetId: string): string {
  if (targetId.startsWith('section:')) {
    const section = sectionById(letter, targetId.slice('section:'.length));
    return section ? `§ ${section.title}` : targetId;
  }
  const item = itemById(letter, targetId);
  return item ? item.title : targetId;
}

/** Pretty edition date, e.g. "October 2, 2026". */
export function prettyEditionDate(edition: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(edition);
  if (!m) return edition;
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}
