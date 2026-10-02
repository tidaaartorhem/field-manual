import { describe, expect, it } from 'vitest';
import { loadCharts, validateCharts, ChartsValidationError } from './charts';

const good = {
  edition: '2026-10-02',
  charts: [
    {
      id: 'funding',
      title: 'Startup money in the window',
      subtitle: '$170M raised across 2 rounds',
      kind: 'hbar',
      unit: '$M',
      data: [
        { label: 'Acme', value: 50, detail: '$50M · Series A' },
        { label: 'BetaCo', value: 120, detail: '$120M' },
      ],
      note: 'Parsed from 2 raise announcements.',
    },
  ],
};

describe('charts data contract', () => {
  it('loads a valid charts payload', () => {
    const specs = loadCharts(good);
    expect(specs).toHaveLength(1);
    expect(specs[0].id).toBe('funding');
    expect(specs[0].data[1].value).toBe(120);
  });

  it('rejects a bad kind', () => {
    const bad = {
      ...good,
      charts: [{ ...good.charts[0], kind: 'pie' }],
    };
    expect(validateCharts(bad).some((i) => i.includes('kind'))).toBe(true);
    expect(() => loadCharts(bad)).toThrow(ChartsValidationError);
  });

  it('rejects negative values and empty data', () => {
    const bad = {
      ...good,
      charts: [
        { ...good.charts[0], id: 'a', data: [{ label: 'X', value: -1 }] },
        { ...good.charts[0], id: 'b', data: [] },
      ],
    };
    const issues = validateCharts(bad);
    expect(issues.some((i) => i.includes('non-negative'))).toBe(true);
    expect(issues.some((i) => i.includes('non-empty array'))).toBe(true);
  });

  it('rejects duplicate chart ids', () => {
    const bad = { ...good, charts: [good.charts[0], { ...good.charts[0] }] };
    expect(validateCharts(bad).some((i) => i.includes('duplicate'))).toBe(true);
  });

  it('accepts an empty charts array (charts are optional)', () => {
    expect(loadCharts({ edition: '2026-10-02', charts: [] })).toEqual([]);
  });

  it('rejects non-object roots', () => {
    expect(validateCharts(null)).toHaveLength(1);
    expect(() => loadCharts('nope')).toThrow(ChartsValidationError);
  });
});
