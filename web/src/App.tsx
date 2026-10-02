import { useEffect, useState } from 'react';
import { loadManual, type ManualData } from './lib/manual';
import { sampleManual } from './sampleManual';
import { Landing } from './components/Landing';
import { Reader } from './components/Reader';
import { Studio } from './components/Studio';
import './styles.css';

type Tab = 'landing' | 'manual' | 'studio';

const TABS: { id: Tab; label: string }[] = [
  { id: 'landing', label: 'Cover' },
  { id: 'manual', label: 'The Manual' },
  { id: 'studio', label: 'Studio' },
];

export function App() {
  const [tab, setTab] = useState<Tab>('landing');
  const [manual, setManual] = useState<ManualData | null>(null);
  const [usingSample, setUsingSample] = useState(false);
  const [readerShelf, setReaderShelf] = useState<string | null>(null);
  const [studioItem, setStudioItem] = useState<string | null>(null);

  // The pipeline stages the edition at /manual.json during build.
  // If it is missing or invalid, fall back to the bundled sample edition.
  useEffect(() => {
    let cancelled = false;
    fetch('manual.json')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<unknown>;
      })
      .then((data) => {
        if (cancelled) return;
        try {
          setManual(loadManual(data));
        } catch {
          setManual(sampleManual);
          setUsingSample(true);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setManual(sampleManual);
        setUsingSample(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const goToShelf = (shelfId: string) => {
    setReaderShelf(shelfId);
    setTab('manual');
    window.scrollTo({ top: 0 });
  };

  const reflectOn = (itemId: string) => {
    setStudioItem(itemId);
    setTab('studio');
    window.scrollTo({ top: 0 });
  };

  return (
    <div>
      <header className="masthead">
        <div className="container masthead-inner">
          <div className="brand">
            <span className="brand-mark">
              The Field <em>Manual</em>
            </span>
            <span className="brand-sub">Agentic AI · Curated Intelligence</span>
          </div>
          <nav className="nav" aria-label="Views">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={tab === t.id ? 'active' : ''}
                onClick={() => {
                  setTab(t.id);
                  window.scrollTo({ top: 0 });
                }}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {usingSample && manual && (
        <div
          className="container"
          style={{
            marginTop: 18,
            padding: '12px 20px',
            border: '1px solid var(--accent-deep)',
            background: 'var(--accent-wash)',
            borderRadius: 2,
            fontSize: '0.85rem',
            color: 'var(--dim)',
          }}
        >
          Reading the bundled sample edition — this week&apos;s filed data hasn&apos;t landed yet.
          The shelves below are representative of what the pipeline files.
        </div>
      )}

      <main className="container">
        {!manual ? (
          <div className="loading-wrap">
            <div className="loading">Compiling the dossier</div>
          </div>
        ) : tab === 'landing' ? (
          <Landing manual={manual} onStart={() => goToShelf('start')} onBrowseShelf={goToShelf} />
        ) : tab === 'manual' ? (
          <Reader manual={manual} shelf={readerShelf} onReflect={reflectOn} />
        ) : (
          <Studio manual={manual} focusItemId={studioItem} />
        )}
      </main>

      <footer className="footer">
        <div className="container footer-inner">
          <div className="colophon">
            The Field Manual — filed from the frontier, read like intelligence. Small, opinionated,
            and allergic to filler.
          </div>
          <div>
            {manual ? `Edition ${manual.edition}` : ''} · Reflections stay in your browser
          </div>
        </div>
      </footer>
    </div>
  );
}
