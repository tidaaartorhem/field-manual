/**
 * Shape validation + helpers for the v4 newsletter data contract.
 * The pipeline writes data/newsletter.json; the web app fetches it and
 * runs it through loadNewsletter before rendering anything.
 *
 * v4: the newsletter is a 500-700 word digest with inline markdown links.
 * Sections are slim link shelves (no per-item briefings).
 */

export interface DigestItem {
  id: string;
  title: string;
  url: string;
  source: string;
  published: string | null;
}

export interface Section {
  id: string;
  title: string;
  kicker: string;
  items: DigestItem[];
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
  digest: string;
  word_count: number;
  digest_truncated: boolean;
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

function isHttpUrl(v: unknown): v is string {
  return typeof v === 'string' && /^https?:\/\/\S+$/.test(v);
}

function validateItem(item: unknown, path: string, issues: string[]): void {
  if (typeof item !== 'object' || item === null) {
    issues.push(`${path}: item must be an object`);
    return;
  }
  const rec = item as Record<string, unknown>;
  if (!isNonEmptyString(rec.id)) issues.push(`${path}: id must be a non-empty string`);
  if (!isNonEmptyString(rec.title)) issues.push(`${path}: title must be a non-empty string`);
  if (!isHttpUrl(rec.url)) issues.push(`${path}: url must be an http(s) URL`);
  if (!isNonEmptyString(rec.source)) issues.push(`${path}: source must be a non-empty string`);
  if (rec.published !== null && typeof rec.published !== 'string')
    issues.push(`${path}: published must be a string or null`);
}

export function loadNewsletter(data: unknown): Newsletter {
  const issues = validateNewsletter(data);
  if (issues.length > 0) throw new NewsletterValidationError(issues);
  return data as Newsletter;
}

/** Non-throwing validation: returns the list of issues (empty = valid). */
export function validateNewsletter(data: unknown): string[] {
  const issues: string[] = [];
  if (typeof data !== 'object' || data === null) {
    return ['newsletter must be an object'];
  }
  const rec = data as Record<string, unknown>;
  if (!isNonEmptyString(rec.edition)) issues.push('edition must be a non-empty string');
  if (typeof rec.window_hours !== 'number') issues.push('window_hours must be a number');
  if (!isNonEmptyString(rec.generated_at)) issues.push('generated_at must be a non-empty string');
  if (!isNonEmptyString(rec.digest)) issues.push('digest must be a non-empty string');
  if (typeof rec.word_count !== 'number' || rec.word_count < 0)
    issues.push('word_count must be a non-negative number');
  if (typeof rec.digest_truncated !== 'boolean')
    issues.push('digest_truncated must be a boolean');
  if (!Array.isArray(rec.sections) || rec.sections.length === 0) {
    issues.push('sections must be a non-empty array');
  } else {
    const seenIds = new Set<string>();
    rec.sections.forEach((s, i) => {
      const path = `sections[${i}]`;
      if (typeof s !== 'object' || s === null) {
        issues.push(`${path}: section must be an object`);
        return;
      }
      const sec = s as Record<string, unknown>;
      if (!isNonEmptyString(sec.id)) issues.push(`${path}: id must be a non-empty string`);
      if (!isNonEmptyString(sec.title)) issues.push(`${path}: title must be a non-empty string`);
      if (!Array.isArray(sec.items)) {
        issues.push(`${path}: items must be an array`);
      } else {
        sec.items.forEach((it, j) => {
          validateItem(it, `${path}.items[${j}]`, issues);
          const id = (it as Record<string, unknown>)?.id;
          if (typeof id === 'string') {
            if (seenIds.has(id)) issues.push(`duplicate item id: ${id}`);
            seenIds.add(id);
          }
        });
      }
    });
  }
  const stats = rec.stats as Record<string, unknown> | undefined;
  if (typeof stats !== 'object' || stats === null) {
    issues.push('stats must be an object');
  } else if (Array.isArray(rec.sections)) {
    const n = (rec.sections as unknown[]).reduce<number>(
      (acc, s) =>
        acc + (((s as Record<string, unknown>).items as unknown[])?.length ?? 0),
      0,
    );
    if (stats.items !== n) issues.push('stats.items inconsistent with sections');
    if (stats.sections !== (rec.sections as unknown[]).length)
      issues.push('stats.sections inconsistent with sections');
  }
  return issues;
}

export function prettyEditionDate(edition: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(edition);
  if (!m) return edition;
  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

/** Word count of the digest (mirrors the pipeline's guard). */
export function digestWordCount(digest: string): number {
  return digest.split(/\s+/).filter(Boolean).length;
}
