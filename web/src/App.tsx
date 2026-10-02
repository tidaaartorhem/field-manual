import { useEffect, useState } from 'react';
import { loadNewsletter, type Newsletter } from './lib/newsletter';
import { loadCharts, type ChartSpec } from './lib/charts';
import { sampleNewsletter } from './sampleNewsletter';
import { Edition } from './components/Edition';
import { Signup } from './components/Signup';
import './styles.css';

export function App() {
  const [newsletter, setNewsletter] = useState<Newsletter | null>(null);
  const [charts, setCharts] = useState<ChartSpec[]>([]);
  const [usingSample, setUsingSample] = useState(false);

  // The pipeline stages the edition at /newsletter.json and /charts.json
  // during build. If either is missing or invalid, fall back gracefully.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('newsletter.json').then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<unknown>;
      }),
      fetch('charts.json')
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json() as Promise<unknown>;
        })
        .catch(() => null),
    ])
      .then(([data, chartsData]) => {
        if (cancelled) return;
        try {
          setNewsletter(loadNewsletter(data));
        } catch {
          setNewsletter(sampleNewsletter);
          setUsingSample(true);
        }
        if (chartsData) {
          try {
            setCharts(loadCharts(chartsData));
          } catch {
            setCharts([]);
          }
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

  return (
    <div className="page">
      <header className="masthead">
        <div className="container masthead-inner">
          <div className="brand">
            <span className="brand-mark">The Field Manual</span>
            <span className="brand-sub">A 48-hour newsletter for people building with AI agents</span>
          </div>
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
        ) : (
          <>
            <Edition newsletter={newsletter} charts={charts} />
            <Signup edition={newsletter.edition} />
          </>
        )}
      </main>

      <footer className="footer">
        <div className="container footer-inner">
          <div>The Field Manual — the last 48 hours, woven into one story.</div>
          <div>{newsletter ? `Edition ${newsletter.edition}` : ''}</div>
        </div>
      </footer>
    </div>
  );
}
