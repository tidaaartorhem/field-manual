import { useEffect, useMemo, useState } from 'react';
import {
  allItems,
  getStartHere,
  shelfById,
  type ManualData,
  type ManualItem,
} from '../lib/manual';
import { formatDate } from '../lib/format';

interface ReaderProps {
  manual: ManualData;
  shelf: string | null;
  onReflect: (itemId: string) => void;
}

type ActiveTab = 'start' | string;

function ScoreBadge({ score }: { score: number }) {
  return (
    <span className="score-badge" title={`Curator score ${(score * 100).toFixed(0)} of 100`}>
      <span className="n">{Math.round(score * 100)}</span>
      <span className="l">score</span>
    </span>
  );
}

function Dossier({ item, onReflect }: { item: ManualItem; onReflect: (itemId: string) => void }) {
  return (
    <article className="dossier">
      <div className="file-no">File nº {item.id}</div>
      <h2>{item.title}</h2>
      <div className="byline">
        <span>{item.source}</span>
        <span>{formatDate(item.published)}</span>
        <span>Score {Math.round(item.score * 100)}</span>
      </div>

      <div className="brief-block lede">
        <div className="brief-label">The lede</div>
        <p>{item.briefing.lede}</p>
      </div>

      <div className="brief-block">
        <div className="brief-label">What happened</div>
        <p>{item.briefing.what_happened}</p>
      </div>

      <div className="brief-block">
        <div className="brief-label">Why it matters</div>
        <p>{item.briefing.why_it_matters}</p>
      </div>

      <div className="brief-block steal">
        <div className="brief-label">Steal this</div>
        <p>{item.briefing.steal_this}</p>
      </div>

      <div className="brief-block">
        <div className="brief-label">Field notes</div>
        <ul className="takeaways">
          {item.takeaways.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </div>

      <div className="dossier-actions">
        <a href={item.url} target="_blank" rel="noopener noreferrer">
          <button className="btn btn-primary btn-sm" type="button">
            Read the source
          </button>
        </a>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => onReflect(item.id)}>
          Reflect on this
        </button>
      </div>
    </article>
  );
}

export function Reader({ manual, shelf, onReflect }: ReaderProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('start');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Landing shelf cards deep-link into the reader.
  useEffect(() => {
    if (shelf) {
      setActiveTab(shelf);
      const first = shelfById(manual, shelf)?.items[0];
      setSelectedId(first ? first.id : null);
    }
  }, [shelf, manual]);

  const startHere = useMemo(() => getStartHere(manual), [manual]);
  const items = useMemo(() => allItems(manual), [manual]);

  const activeShelf = activeTab === 'start' ? undefined : shelfById(manual, activeTab);
  const listItems = activeTab === 'start' ? [] : (activeShelf?.items ?? []);
  const selected = selectedId ? items.find((i) => i.id === selectedId) ?? null : null;

  const openShelf = (shelfId: string) => {
    setActiveTab(shelfId);
    const first = shelfById(manual, shelfId)?.items[0];
    setSelectedId(first ? first.id : null);
  };

  const openStartHereItem = (item: ManualItem) => {
    setActiveTab(item.shelf);
    setSelectedId(item.id);
  };

  return (
    <div className="reader">
      <div className="section-head">
        <h2>The manual</h2>
        <p>
          Read it like a briefing, not a feed. Start with the shortest path through the noise —
          or pull a shelf and work it cover to cover.
        </p>
      </div>

      <div className="shelf-tabs" role="tablist" aria-label="Shelves">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'start'}
          className={activeTab === 'start' ? 'active' : ''}
          onClick={() => {
            setActiveTab('start');
            setSelectedId(null);
          }}
        >
          Start here
        </button>
        {manual.shelves.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={activeTab === s.id}
            className={activeTab === s.id ? 'active' : ''}
            onClick={() => openShelf(s.id)}
          >
            {s.title}
          </button>
        ))}
      </div>

      {activeTab === 'start' ? (
        <div>
          <div className="section-head">
            <h2 style={{ fontSize: '1.6rem' }}>The shortest path through the noise</h2>
            <p>
              If you read nothing else this week, read these — in this order. Each one earns the
              next.
            </p>
          </div>
          <div className="path">
            {startHere.map((item, i) => {
              const s = shelfById(manual, item.shelf);
              return (
                <button key={item.id} type="button" className="path-row" onClick={() => openStartHereItem(item)}>
                  <span className="path-num">{String(i + 1).padStart(2, '0')}</span>
                  <span>
                    <h4>{item.title}</h4>
                    <p className="path-why">{item.briefing.lede}</p>
                  </span>
                  <span className="path-shelf">{s?.title ?? item.shelf}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="reader-grid">
          <div className="item-list" role="listbox" aria-label={`${activeShelf?.title ?? ''} items`}>
            {listItems.map((item) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={item.id === selectedId}
                className={`item-row${item.id === selectedId ? ' selected' : ''}`}
                onClick={() => setSelectedId(item.id)}
              >
                <span>
                  <h4>{item.title}</h4>
                  <span className="item-meta">
                    {item.source} · {formatDate(item.published)}
                  </span>
                </span>
                <ScoreBadge score={item.score} />
              </button>
            ))}
          </div>
          {selected ? (
            <Dossier item={selected} onReflect={onReflect} />
          ) : (
            <div className="dossier-empty">
              <div className="big">Select a dispatch to open its briefing.</div>
              <div>Every file on this shelf has been read so you don&apos;t have to skim it.</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
