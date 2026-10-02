/**
 * Minimal SAFE markdown -> HTML for the v4 digest.
 * Escapes everything first, then allows only: **bold**, [text](http...),
 * ## subheads, and paragraphs. Anything else renders as plain text.
 * Mirrors services/emailer.py::md_to_email_html (email version adds inline
 * styles; the web version relies on CSS classes).
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inline(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
    );
}

export function renderDigestMarkdown(md: string): string {
  const escaped = escapeHtml(md || '');
  return escaped
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      if (p.startsWith('## ')) {
        return `<h3>${inline(p.slice(3).trim())}</h3>`;
      }
      return `<p>${inline(p.replace(/\n/g, '<br>'))}</p>`;
    })
    .join('\n');
}
