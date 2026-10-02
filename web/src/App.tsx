import { useEffect, useState } from 'react';
import { loadNewsletter, type Newsletter } from './lib/newsletter';
import { loadMarginalia, saveMarginalia } from './lib/storage';
import { type MarginaliaState } from './lib/marginalia';
import { sampleNewsletter } from './sampleNewsletter';
import { Edition } from './components/Edition';
import { Reflect } from './components/Reflect';
import './styles.css';

type Tab = 'edition' | 'reflect';

const TABS: { id: Tab; label: string }[] = [
  { id: 'edition', label: 'The Edition' },
  { id: 'reflect', label: 'Reflect' },
];

export function App() {
  const [tab, setTab] = useState<Tab>('edition');
  const [newsletter, setNewsletter] = useState<Newsletter | null>(null);
  const [usingSample, setUsingSample] = useState(false);
  const [marginalia, setMarginalia] = useState<MarginaliaState>(() => loadMarginalia());
  const [annotateTarget, setAnnotateTarget] = useState<string | null>(null);

  // The pipeline stages the edition at /newsletter.json during build.
  // If it is missing or invalid, fall back to the bundled sample edition.
  useEffect(() => {
    let cancelled = false;
    fetch('newsletter.json')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<unknown>;
      })
      .then((data) => {
        if (cancelled) return;
        try {
          setNewsletter(loadNewsletter(data));
        } catch {
          setNewsletter(sampleNewsletter);
          setUsingSample(true);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setNewsletter(sampleNewsletter);
        setUsingSample(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    saveMarginalia(marginalia);
  }, [marginalia]);

  const goAnnotate = (target: string) => {
    setAnnotateTarget(target);
    setTab('reflect');
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="page">
      <header className="masthead">
        <div className="container masthead-inner">
          <div className="brand">
            <span className="brand-mark">The Field Manual</span>
            <span className="brand-sub">A 48-hour newsletter for people building with AI agents</span>
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

      {usingSample && (
        <div className="container">
          <div className="sample-note">
            Showing the sample edition — this week's filed data hasn't landed yet.
          </div>
        </div>
      )}

      <main className="container">
        {!newsletter ? (
          <div className="loading">Filing the edition…</div>
        ) : tab === 'edition' ? (
          <Edition
            newsletter={newsletter}
            onAnnotate={goAnnotate}
            notesFor={(target) =>
              (marginalia.notes[newsletter.edition]?.[target] ?? []).length
            }
          />
        ) : (
          <Reflect
            newsletter={newsletter}
            state={marginalia}
            onChange={setMarginalia}
            initialTarget={annotateTarget}
          />
        )}
      </main>

      <footer className="footer">
        <div className="container footer-inner">
          <div>The Field Manual — the last 48 hours, woven into one story.</div>
          <div>{newsletter ? `Edition ${newsletter.edition}` : ''} · Notes stay in your browser</div>
        </div>
      </footer>
    </div>
  );
}
