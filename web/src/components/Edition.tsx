import { useState } from 'react';
import {
  prettyEditionDate,
  type Newsletter,
  type NewsletterItem,
} from '../lib/newsletter';

function ItemCard({
  item,
  onAnnotate,
  noteCount,
}: {
  item: NewsletterItem;
  onAnnotate: (target: string) => void;
  noteCount: number;
}) {
  const [open, setOpen] = useState(false);
  const b = item.briefing;
  return (
    <article className="item">
      <div className="item-head">
        <a className="item-title" href={item.url} target="_blank" rel="noreferrer">
          {item.title}
        </a>
        <div className="item-meta">
          {item.source}
          {item.published ? ` · ${item.published}` : ''}
        </div>
      </div>
      <p className="item-lede">{b.lede}</p>
      {open && (
        <div className="item-body">
          <p>{b.what_happened}</p>
          <p>
            <strong>Why it matters.</strong> {b.why_it_matters}
          </p>
          <p>
            <strong>Steal this.</strong> {b.steal_this}
          </p>
          <p className="item-takeaways">{item.takeaways.join(' · ')}</p>
        </div>
      )}
      <div className="item-actions">
        <button type="button" className="linklike" onClick={() => setOpen((v) => !v)}>
          {open ? 'Show less' : 'Read the briefing'}
        </button>
        <button type="button" className="linklike" onClick={() => onAnnotate(item.id)}>
          Annotate{noteCount > 0 ? ` (${noteCount})` : ''}
        </button>
      </div>
    </article>
  );
}

export function Edition({
  newsletter,
  onAnnotate,
  notesFor,
}: {
  newsletter: Newsletter;
  onAnnotate: (target: string) => void;
  notesFor: (target: string) => number;
}) {
  return (
    <div>
      <header className="edition-head">
        <div className="edition-kicker">The Field Manual · {prettyEditionDate(newsletter.edition)}</div>
        <h1 className="edition-title">The last {newsletter.window_hours} hours, in one story.</h1>
        <p className="edition-lede">{newsletter.lede}</p>
        <div className="edition-stats">
          {newsletter.stats.items} items · {newsletter.stats.sources} sources · filed{' '}
          {new Date(newsletter.generated_at).toLocaleString()}
        </div>
      </header>

      {newsletter.sections.map((section) => (
        <section key={section.id} className="section">
          <div className="section-kicker">{section.kicker}</div>
          <h2 className="section-title">{section.title}</h2>
          <div className="section-annotate">
            <button
              type="button"
              className="linklike"
              onClick={() => onAnnotate(`section:${section.id}`)}
            >
              Annotate this section
              {notesFor(`section:${section.id}`) > 0
                ? ` (${notesFor(`section:${section.id}`)})`
                : ''}
            </button>
          </div>
          <p className="section-narrative">{section.narrative}</p>
          <div className="items">
            {section.items.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                onAnnotate={onAnnotate}
                noteCount={notesFor(item.id)}
              />
            ))}
          </div>
          <blockquote className="closing-take">
            <span className="closing-label">So what?</span> {section.closing_take}
          </blockquote>
        </section>
      ))}
    </div>
  );
}
