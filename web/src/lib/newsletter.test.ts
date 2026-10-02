import { describe, expect, it } from 'vitest';
import {
  loadNewsletter,
  prettyEditionDate,
  validateNewsletter,
} from './newsletter';

function validNewsletter() {
  return {
    edition: '2026-10-02',
    window_hours: 48,
    generated_at: '2026-10-02T12:00:00+00:00',
    lede: 'The last 48 hours, distilled.',
    sections: [
      {
        id: 'signal',
        title: 'The Signal',
        kicker: 'Agentic AI, last 48 hours.',
        narrative: 'A story in four sentences.',
        closing_take: 'So what: ship.',
        items: [
          {
            id: 'signal-001',
            title: 'An agent launched',
            url: 'https://example.com/launch',
            source: 'Example',
            published: '2026-10-02',
            date_verified: true,
            shelf: 'signal',
            score: 0.9,
            briefing: {
              lede: 'Lede.',
              what_happened: 'What happened.',
              why_it_matters: 'Why it matters.',
              steal_this: 'Steal this.',
            },
            takeaways: ['One', 'Two'],
            queries: ['q'],
          },
        ],
      },
    ],
    stats: { items: 1, sections: 1, sources: 1 },
  };
}

describe('newsletter validation', () => {
  it('accepts a valid newsletter', () => {
    expect(validateNewsletter(validNewsletter())).toEqual([]);
    expect(loadNewsletter(validNewsletter()).edition).toBe('2026-10-02');
  });

  it('rejects missing lede and bad urls', () => {
    const bad = validNewsletter() as Record<string, unknown>;
    bad.lede = '';
    (bad.sections as unknown[])[0] = {
      ...(bad.sections as Record<string, unknown>[])[0],
      items: [{ ...((((bad.sections as Record<string, unknown>[])[0] as Record<string, unknown>).items as unknown[])[0] as Record<string, unknown>), url: 'notaurl' }],
    };
    const issues = validateNewsletter(bad);
    expect(issues.some((i) => i.includes('lede'))).toBe(true);
    expect(issues.some((i) => i.includes('url'))).toBe(true);
  });

  it('rejects duplicate section ids', () => {
    const dup = validNewsletter();
    dup.sections = [dup.sections[0], dup.sections[0]];
    expect(validateNewsletter(dup).some((i) => i.includes('duplicate'))).toBe(true);
  });
});

describe('helpers', () => {
  it('formats edition dates', () => {
    expect(prettyEditionDate('2026-10-02')).toBe('October 2, 2026');
    expect(prettyEditionDate('garbage')).toBe('garbage');
  });
});
