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
    digest:
      'Two days in AI. Read [Agentic coding](https://example.com/agents) for the big story.',
    word_count: 15,
    digest_truncated: false,
    sections: [
      {
        id: 'signal',
        title: 'The Signal',
        kicker: 'Agentic AI, last 48 hours.',
        items: [
          {
            id: 'signal-001',
            title: 'Agentic coding goes mainstream',
            url: 'https://example.com/agents',
            source: 'Example',
            published: '2026-10-02',
          },
        ],
      },
    ],
    stats: { items: 1, sections: 1, sources: 1 },
  };
}

describe('newsletter validation (v4 digest)', () => {
  it('accepts a valid digest newsletter', () => {
    expect(validateNewsletter(validNewsletter())).toEqual([]);
    expect(loadNewsletter(validNewsletter()).edition).toBe('2026-10-02');
  });

  it('rejects missing digest and bad urls', () => {
    const bad = validNewsletter() as unknown as Record<string, unknown>;
    bad.digest = '';
    const sections = bad.sections as Record<string, unknown>[];
    sections[0] = {
      ...(sections[0] as Record<string, unknown>),
      items: [
        {
          ...(((sections[0] as Record<string, unknown>).items as unknown[])[0] as Record<string, unknown>),
          url: 'notaurl',
        },
      ],
    };
    const issues = validateNewsletter(bad);
    expect(issues.some((i) => i.includes('digest'))).toBe(true);
    expect(issues.some((i) => i.includes('url'))).toBe(true);
  });

  it('rejects duplicate item ids', () => {
    const dup = validNewsletter();
    dup.sections = [dup.sections[0], dup.sections[0]];
    expect(validateNewsletter(dup).some((i) => i.includes('duplicate'))).toBe(true);
  });

  it('rejects inconsistent stats', () => {
    const bad = validNewsletter();
    (bad.stats as unknown as Record<string, unknown>).items = 99;
    expect(validateNewsletter(bad).some((i) => i.includes('stats'))).toBe(true);
  });
});

describe('helpers', () => {
  it('formats edition dates', () => {
    expect(prettyEditionDate('2026-10-02')).toBe('October 2, 2026');
    expect(prettyEditionDate('garbage')).toBe('garbage');
  });
});
