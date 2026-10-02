import { describe, expect, it } from 'vitest';
import {
  addJournalEntry,
  answerPrompt,
  currentStreak,
  emptyReflectionState,
  prevDay,
  progressStats,
  recordDay,
  reflectedItemIds,
  todayLocal,
  type ReflectionState,
} from './reflection';

describe('emptyReflectionState', () => {
  it('starts with no journal, qa, or days', () => {
    expect(emptyReflectionState()).toEqual({ journal: {}, qa: {}, days: [] });
  });
});

describe('addJournalEntry', () => {
  it('appends an entry for the item with a timestamp', () => {
    const s0 = emptyReflectionState();
    const s1 = addJournalEntry(s0, 'papers-001', '  Big idea: evals are the product.  ', 1700000000000);
    expect(s1.journal['papers-001']).toEqual([{ ts: 1700000000000, text: 'Big idea: evals are the product.' }]);
    // original state untouched (immutability)
    expect(s0.journal['papers-001']).toBeUndefined();
  });

  it('keeps entries in insertion order', () => {
    let s = emptyReflectionState();
    s = addJournalEntry(s, 'papers-001', 'first', 1);
    s = addJournalEntry(s, 'papers-001', 'second', 2);
    expect(s.journal['papers-001']?.map((e) => e.text)).toEqual(['first', 'second']);
  });

  it('ignores blank text and returns the same state', () => {
    const s0 = emptyReflectionState();
    expect(addJournalEntry(s0, 'papers-001', '   ')).toBe(s0);
  });
});

describe('answerPrompt', () => {
  it('records prompt, answer, score, and timestamp', () => {
    const s1 = answerPrompt(emptyReflectionState(), 'news-001', 'Explain this to a skeptic.', 'Because the primitives are free now.', 4, 1700000000000);
    expect(s1.qa['news-001']).toEqual([
      { prompt: 'Explain this to a skeptic.', answer: 'Because the primitives are free now.', score: 4, ts: 1700000000000 },
    ]);
  });

  it('clamps scores to 1..5', () => {
    const low = answerPrompt(emptyReflectionState(), 'a', 'p', 'ans', 0, 1);
    const high = answerPrompt(emptyReflectionState(), 'a', 'p', 'ans', 99, 1);
    expect(low.qa['a']?.[0]?.score).toBe(1);
    expect(high.qa['a']?.[0]?.score).toBe(5);
  });

  it('ignores blank answers', () => {
    const s0 = emptyReflectionState();
    expect(answerPrompt(s0, 'a', 'p', '  ', 3)).toBe(s0);
  });
});

describe('recordDay', () => {
  it('adds a day, dedupes, and keeps days sorted', () => {
    let s = emptyReflectionState();
    s = recordDay(s, '2026-10-02');
    s = recordDay(s, '2026-09-30');
    s = recordDay(s, '2026-10-02'); // duplicate
    expect(s.days).toEqual(['2026-09-30', '2026-10-02']);
  });
});

describe('todayLocal / prevDay', () => {
  it('formats a known date as YYYY-MM-DD', () => {
    expect(todayLocal(new Date(2026, 9, 2, 12, 0, 0))).toBe('2026-10-02');
  });

  it('prevDay crosses month boundaries', () => {
    expect(prevDay('2026-10-01')).toBe('2026-09-30');
    expect(prevDay('2026-03-01')).toBe('2026-02-28');
  });
});

describe('currentStreak', () => {
  const withDays = (days: string[]): ReflectionState => ({ ...emptyReflectionState(), days });

  it('counts consecutive days ending today', () => {
    const s = withDays(['2026-09-30', '2026-10-01', '2026-10-02']);
    expect(currentStreak(s, '2026-10-02')).toBe(3);
  });

  it('keeps the streak alive when today has no activity yet', () => {
    const s = withDays(['2026-09-30', '2026-10-01']);
    expect(currentStreak(s, '2026-10-02')).toBe(2);
  });

  it('breaks the streak on a gap', () => {
    const s = withDays(['2026-09-28', '2026-10-01', '2026-10-02']);
    expect(currentStreak(s, '2026-10-02')).toBe(2);
  });

  it('is zero with no activity', () => {
    expect(currentStreak(emptyReflectionState(), '2026-10-02')).toBe(0);
  });

  it('is zero when the last activity is older than yesterday', () => {
    const s = withDays(['2026-09-29']);
    expect(currentStreak(s, '2026-10-02')).toBe(0);
  });
});

describe('progressStats', () => {
  it('counts items with any journal entry or answered prompt, once each', () => {
    let s = emptyReflectionState();
    s = addJournalEntry(s, 'papers-001', 'note', 1);
    s = addJournalEntry(s, 'papers-001', 'another', 2);
    s = answerPrompt(s, 'news-001', 'p', 'a', 5, 3);
    const stats = progressStats(s, 8);
    expect(stats).toEqual({ reflected: 2, total: 8, percent: 25 });
  });

  it('handles zero items', () => {
    expect(progressStats(emptyReflectionState(), 0)).toEqual({ reflected: 0, total: 0, percent: 0 });
  });

  it('rounds percent', () => {
    let s = emptyReflectionState();
    s = addJournalEntry(s, 'papers-001', 'note', 1);
    expect(progressStats(s, 3).percent).toBe(33);
  });
});

describe('reflectedItemIds', () => {
  it('unions journal and qa item ids', () => {
    let s = emptyReflectionState();
    s = addJournalEntry(s, 'papers-001', 'x', 1);
    s = answerPrompt(s, 'news-002', 'p', 'y', 3, 2);
    expect(reflectedItemIds(s).sort()).toEqual(['news-002', 'papers-001']);
  });
});
