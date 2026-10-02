import { describe, expect, it } from 'vitest';
import { normalizeSignup, validateSignup, normalizeSource, validateSource } from './validate';

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

describe('source adder validation', () => {
  it('accepts a good url and email', () => {
    expect(validateSource('https://example.com/paper', 'a@b.com')).toEqual({});
    expect(normalizeSource('  https://example.com/x ', '  A@B.COM ')).toEqual({
      url: 'https://example.com/x',
      email: 'a@b.com',
    });
  });

  it('rejects bad urls', () => {
    for (const bad of ['', '   ', 'notaurl', 'ftp://example.com/x', 'http://']) {
      expect(validateSource(bad, 'a@b.com').url, bad).toBeTruthy();
    }
  });

  it('rejects bad emails', () => {
    for (const bad of ['', 'nope', 'a@b']) {
      expect(validateSource('https://example.com/x', bad).email, bad).toBeTruthy();
    }
  });
});
