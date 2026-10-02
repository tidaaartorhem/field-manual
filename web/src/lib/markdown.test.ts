import { describe, expect, it } from 'vitest';
import { renderDigestMarkdown } from './markdown';

describe('renderDigestMarkdown', () => {
  it('renders paragraphs, bold, links, and subheads', () => {
    const html = renderDigestMarkdown(
      '## Agents\n\nBig story: [Launch](https://example.com/x) happened. **So what?** Ship.',
    );
    expect(html).toContain('<h3>Agents</h3>');
    expect(html).toContain('<strong>So what?</strong>');
    expect(html).toContain(
      '<a href="https://example.com/x" target="_blank" rel="noreferrer">Launch</a>',
    );
  });

  it('escapes HTML before allowing formatting', () => {
    const html = renderDigestMarkdown('<script>alert(1)</script>\n\n**bold**');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('<strong>bold</strong>');
  });

  it('ignores non-http link targets', () => {
    const html = renderDigestMarkdown('[x](javascript:alert(1))');
    expect(html).not.toContain('<a ');
    expect(html).toContain('[x](javascript:alert(1))');
  });

  it('handles empty input', () => {
    expect(renderDigestMarkdown('')).toBe('');
  });
});
