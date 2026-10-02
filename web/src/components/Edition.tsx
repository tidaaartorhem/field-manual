import { prettyEditionDate, type Newsletter } from '../lib/newsletter';
import { renderDigestMarkdown } from '../lib/markdown';
import type { ChartSpec } from '../lib/charts';
import { ChartsStrip } from './Charts';

export function Edition({
  newsletter,
  charts,
}: {
  newsletter: Newsletter;
  charts: ChartSpec[];
}) {
  return (
    <div>
      <header className="edition-head">
        <div className="edition-kicker">The Field Manual · {prettyEditionDate(newsletter.edition)}</div>
        <h1 className="edition-title">The last {newsletter.window_hours} hours, in one story.</h1>
        <div className="edition-stats">
          {newsletter.word_count} words · {newsletter.stats.items} stories ·{' '}
          {newsletter.stats.sources} sources · filed{' '}
          {new Date(newsletter.generated_at).toLocaleString()}
        </div>
      </header>

      <div
        className="digest"
        // Safe: renderDigestMarkdown escapes everything, then allows only
        // **bold**, [text](http...), ## subheads, and paragraphs.
        dangerouslySetInnerHTML={{ __html: renderDigestMarkdown(newsletter.digest) }}
      />

      <ChartsStrip charts={charts} />

      <section className="links-section">
        <div className="section-kicker">All the links</div>
        <h2 className="section-title">Go deeper</h2>
        {newsletter.sections.map((section) => (
          <div key={section.id} className="links-group">
            <div className="links-group-title">{section.title}</div>
            <ul className="links-list">
              {section.items.map((item) => (
                <li key={item.id}>
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                  <span className="links-source">
                    {' '}
                    — {item.source}
                    {item.published ? ` · ${item.published}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  );
}
