import { describe, expect, it } from 'vitest';
import {
  allItems,
  getStartHere,
  itemById,
  loadManual,
  ManualValidationError,
  shelfById,
  validateManual,
  type ManualData,
} from './manual';
import { sampleManual } from '../sampleManual';

function validManual(): ManualData {
  return JSON.parse(JSON.stringify(sampleManual)) as ManualData;
}

describe('validateManual', () => {
  it('accepts the bundled sample edition', () => {
    expect(validateManual(validManual())).toEqual([]);
  });

  it('rejects non-objects', () => {
    expect(validateManual(null)).toHaveLength(1);
    expect(validateManual('nope')).toHaveLength(1);
  });

  it('requires edition, generated_at, shelves, start_here, stats', () => {
    const m = validManual();
    delete (m as unknown as Record<string, unknown>).edition;
    m.shelves = [];
    const issues = validateManual(m);
    expect(issues.some((i) => i.includes('edition'))).toBe(true);
    expect(issues.some((i) => i.includes('shelves must be a non-empty array'))).toBe(true);
  });

  it('rejects duplicate shelf ids', () => {
    const m = validManual();
    m.shelves.push({ ...m.shelves[0]! });
    expect(validateManual(m).some((i) => i.includes('duplicate shelf id'))).toBe(true);
  });

  it('rejects out-of-range scores', () => {
    const m = validManual();
    m.shelves[0]!.items[0]!.score = 1.5;
    expect(validateManual(m).some((i) => i.includes('score'))).toBe(true);
  });

  it('rejects non-URL item urls', () => {
    const m = validManual();
    m.shelves[0]!.items[0]!.url = 'not-a-url';
    expect(validateManual(m).some((i) => i.includes('url'))).toBe(true);
  });

  it('rejects incomplete briefings', () => {
    const m = validManual();
    m.shelves[0]!.items[0]!.briefing.steal_this = '  ';
    expect(validateManual(m).some((i) => i.includes('briefing.steal_this'))).toBe(true);
  });

  it('rejects empty takeaways', () => {
    const m = validManual();
    m.shelves[0]!.items[0]!.takeaways = [];
    expect(validateManual(m).some((i) => i.includes('takeaways'))).toBe(true);
  });

  it('allows null published dates', () => {
    const m = validManual();
    m.shelves[1]!.items[1]!.published = null;
    expect(validateManual(m)).toEqual([]);
  });

  it('rejects bad stats', () => {
    const m = validManual();
    m.stats.items = -1;
    expect(validateManual(m).some((i) => i.includes('stats.items'))).toBe(true);
  });
});

describe('loadManual', () => {
  it('returns the data when valid', () => {
    const m = validManual();
    expect(loadManual(m)).toBe(m);
  });

  it('throws ManualValidationError with issues when invalid', () => {
    expect(() => loadManual({})).toThrowError(ManualValidationError);
    try {
      loadManual({});
    } catch (err) {
      expect(err).toBeInstanceOf(ManualValidationError);
      expect((err as ManualValidationError).issues.length).toBeGreaterThan(0);
    }
  });
});

describe('getStartHere', () => {
  it('resolves the curated path in order', () => {
    const path = getStartHere(sampleManual);
    expect(path.map((i) => i.id)).toEqual(sampleManual.start_here);
  });

  it('skips unknown ids instead of breaking', () => {
    const m = validManual();
    m.start_here = ['nope-000', ...m.start_here];
    const path = getStartHere(m);
    expect(path.map((i) => i.id)).toEqual(m.start_here.slice(1));
  });

  it('returns an empty path when start_here is empty', () => {
    const m = validManual();
    m.start_here = [];
    expect(getStartHere(m)).toEqual([]);
  });
});

describe('shelf/item helpers', () => {
  it('allItems flattens every shelf', () => {
    const items = allItems(sampleManual);
    expect(items).toHaveLength(sampleManual.stats.items);
    expect(new Set(items.map((i) => i.id)).size).toBe(items.length);
  });

  it('shelfById finds shelves and misses cleanly', () => {
    expect(shelfById(sampleManual, 'papers')?.title).toBe('Papers');
    expect(shelfById(sampleManual, 'missing')).toBeUndefined();
  });

  it('itemById finds items across shelves', () => {
    expect(itemById(sampleManual, 'news-002')?.title).toContain('Model Context Protocol');
    expect(itemById(sampleManual, 'missing')).toBeUndefined();
  });
});
