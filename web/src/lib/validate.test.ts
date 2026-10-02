import { describe, expect, it } from 'vitest';
import { normalizeSignup, validateSignup } from './validate';

describe('signup validation', () => {
  it('accepts a good name and email', () => {
    expect(validateSignup('Aadit', 'aadit@example.com')).toEqual({});
  });

  it('requires a name', () => {
    expect(validateSignup('   ', 'a@b.com').name).toBeTruthy();
  });

  it('caps the name at 80 chars', () => {
    expect(validateSignup('x'.repeat(81), 'a@b.com').name).toBeTruthy();
    expect(validateSignup('x'.repeat(80), 'a@b.com')).toEqual({});
  });

  it('rejects bad emails', () => {
    for (const bad of ['', '   ', 'nope', 'a@b', 'a b@c.com', '@c.com']) {
      expect(validateSignup('Aadit', bad).email, bad).toBeTruthy();
    }
  });

  it('accepts dotted and plus emails', () => {
    expect(validateSignup('A', 'first.last+fm@example.co')).toEqual({});
  });

  it('normalizes before writing', () => {
    expect(normalizeSignup('  Aadit  ', '  Aadit@Example.COM ')).toEqual({
      name: 'Aadit',
      email: 'aadit@example.com',
    });
  });
});
