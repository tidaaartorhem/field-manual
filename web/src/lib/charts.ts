/**
 * Shape validation for the charts data contract.
 * The pipeline writes data/charts.json; the web app fetches it alongside
 * the newsletter and renders each spec as inline SVG.
 */

export interface ChartDatum {
  label: string;
  value: number;
  detail?: string;
  tier?: number;
}

export interface ChartSpec {
  id: string;
  title: string;
  subtitle: string;
  kind: 'bar' | 'hbar';
  unit: string;
  data: ChartDatum[];
  note: string;
}

export class ChartsValidationError extends Error {
  declare readonly issues: string[];
  constructor(issues: string[]) {
    super(`Invalid charts data: ${issues.join('; ')}`);
    this.name = 'ChartsValidationError';
    this.issues = issues;
  }
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.trim().length > 0;
}

function validateSpec(spec: unknown, path: string, issues: string[]): void {
  if (typeof spec !== 'object' || spec === null) {
    issues.push(`${path}: chart must be an object`);
    return;
  }
  const s = spec as Record<string, unknown>;
  if (!isNonEmptyString(s.id)) issues.push(`${path}: id must be a non-empty string`);
  for (const key of ['title', 'subtitle', 'unit', 'note']) {
    if (!isNonEmptyString(s[key])) issues.push(`${path}: ${key} must be a non-empty string`);
  }
  if (s.kind !== 'bar' && s.kind !== 'hbar')
    issues.push(`${path}: kind must be "bar" or "hbar"`);
  if (!Array.isArray(s.data) || s.data.length === 0) {
    issues.push(`${path}: data must be a non-empty array`);
    return;
  }
  s.data.forEach((d: unknown, i: number) => {
    const rec = d as Record<string, unknown>;
    if (typeof d !== 'object' || d === null || !isNonEmptyString(rec.label))
      issues.push(`${path}.data[${i}]: label must be a non-empty string`);
    if (typeof rec.value !== 'number' || Number.isNaN(rec.value) || rec.value < 0)
      issues.push(`${path}.data[${i}]: value must be a non-negative number`);
    if (rec.detail !== undefined && typeof rec.detail !== 'string')
      issues.push(`${path}.data[${i}]: detail must be a string`);
    if (rec.tier !== undefined && rec.tier !== 1 && rec.tier !== 2 && rec.tier !== 3)
      issues.push(`${path}.data[${i}]: tier must be 1, 2 or 3`);
  });
}

export function validateCharts(data: unknown): string[] {
  const issues: string[] = [];
  if (typeof data !== 'object' || data === null) return ['root: charts must be an object'];
  const d = data as Record<string, unknown>;
  if (!isNonEmptyString(d.edition)) issues.push('root: edition must be a non-empty string');
  if (!Array.isArray(d.charts)) {
    issues.push('root: charts must be an array');
    return issues;
  }
  const ids = new Set<string>();
  d.charts.forEach((spec: unknown, i: number) => {
    validateSpec(spec, `charts[${i}]`, issues);
    const id = (spec as Record<string, unknown>).id;
    if (typeof id === 'string') {
      if (ids.has(id)) issues.push(`charts[${i}]: duplicate chart id "${id}"`);
      ids.add(id);
    }
  });
  return issues;
}

/** Validate and return the chart specs, throwing on failure. */
export function loadCharts(data: unknown): ChartSpec[] {
  const issues = validateCharts(data);
  if (issues.length > 0) throw new ChartsValidationError(issues);
  return (data as { charts: ChartSpec[] }).charts;
}
