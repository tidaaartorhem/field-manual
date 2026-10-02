import type { ManualData } from '../lib/manual';
import { formatDate } from '../lib/format';

interface LandingProps {
  manual: ManualData;
  onStart: () => void;
  onBrowseShelf: (shelfId: string) => void;
}

export function Landing({ manual, onStart, onBrowseShelf }: LandingProps) {
  const shelfNo = ['01', '02', '03', '04'];

  return (
    <div>
      <section className="hero">
        <div className="kicker">Field dossier · A curated curriculum for the agentic age</div>
        <h1>
          The firehose is <em>not</em> a curriculum.
        </h1>
        <div className="thesis">
          <p>
            Every week, a thousand new agent frameworks, eval papers, and breathless takes flood the
            zone. Most of it is noise — and noise, consumed daily, starts to feel like learning. It
            is not.
          </p>
          <p>
            The Field Manual is the opposite of the firehose: a small, opinionated, human-curated
            stack of the <strong>papers, courses, and dispatches that actually move the needle</strong>{' '}
            on agentic AI. Each one is read, scored, and briefed like it matters — with the
            narrative, the stakes, and the one idea worth stealing.
          </p>
          <p>
            No infinite scroll. No engagement bait. Just the good stuff, filed like intelligence.
          </p>
        </div>

        <div className="edition-line">
          <span>
            Edition <b>{formatDate(manual.edition)}</b>
          </span>
          <span>Filed from the frontier</span>
        </div>

        <div className="stats">
          <div className="stat">
            <div className="stat-num">
              {manual.stats.items}
              <em>.</em>
            </div>
            <div className="stat-label">Items briefed</div>
          </div>
          <div className="stat">
            <div className="stat-num">
              {manual.stats.shelves}
              <em>.</em>
            </div>
            <div className="stat-label">Shelves</div>
          </div>
          <div className="stat">
            <div className="stat-num">
              {manual.stats.sources}
              <em>.</em>
            </div>
            <div className="stat-label">Sources tracked</div>
          </div>
        </div>

        <div className="cta-row">
          <button className="btn btn-primary" onClick={onStart}>
            Start the manual
          </button>
          <button className="btn btn-ghost" onClick={() => onBrowseShelf(manual.shelves[0]?.id ?? '')}>
            Browse the shelves
          </button>
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2>The shelves</h2>
          <p>
            Four rooms, one for each kind of signal. Every item on every shelf earned its place —
            nothing here is filler, and nothing here is here by accident.
          </p>
        </div>
        <div className="shelf-grid">
          {manual.shelves.map((shelf, i) => {
            const top = Math.max(...shelf.items.map((item) => item.score), 0);
            return (
              <button key={shelf.id} className="shelf-card" onClick={() => onBrowseShelf(shelf.id)}>
                <div className="shelf-no">SHELF {shelfNo[i] ?? String(i + 1).padStart(2, '0')}</div>
                <h3>{shelf.title}</h3>
                <p>{shelf.tagline}</p>
                <div className="shelf-meta">
                  <span>
                    {shelf.items.length} {shelf.items.length === 1 ? 'briefing' : 'briefings'} · top
                    score {Math.round(top * 100)}
                  </span>
                  <span className="go">Open →</span>
                </div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
