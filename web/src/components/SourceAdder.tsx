import { useEffect, useState } from 'react';
import {
  addUserSource,
  getStoredEmail,
  listUserSources,
  setStoredEmail,
  type UserSource,
} from '../lib/firebase';
import { normalizeSource, validateSource } from '../lib/validate';

type Status = 'idle' | 'sending' | 'done' | 'error';

const STATUS_LABEL: Record<UserSource['status'], string> = {
  pending: 'Queued for scraping',
  scraped: 'In your next email',
  failed: "Couldn't scrape this one",
};

export function SourceAdder() {
  const [url, setUrl] = useState('');
  const [email, setEmail] = useState('');
  const [issues, setIssues] = useState<{ url?: string; email?: string }>({});
  const [status, setStatus] = useState<Status>('idle');
  const [errorDetail, setErrorDetail] = useState('');
  const [sources, setSources] = useState<UserSource[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  // Pre-fill the email if they signed up (or added a source before).
  useEffect(() => {
    const stored = getStoredEmail();
    if (stored) {
      setEmail(stored);
      void refresh(stored);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh(forEmail: string) {
    setLoadingList(true);
    try {
      setSources(await listUserSources(forEmail));
    } catch {
      /* list is best-effort; the form still works */
    } finally {
      setLoadingList(false);
    }
  }

  const submit = async () => {
    const found = validateSource(url, email);
    setIssues(found);
    if (Object.keys(found).length > 0) return;
    setStatus('sending');
    setErrorDetail('');
    try {
      const clean = normalizeSource(url, email);
      await addUserSource(clean.email, clean.url);
      setStoredEmail(clean.email);
      setUrl('');
      setStatus('done');
      void refresh(clean.email);
    } catch (err) {
      setStatus('error');
      setErrorDetail(err instanceof Error ? err.message : 'Something went wrong.');
    }
  };

  return (
    <section className="source-adder" aria-label="Add your own source">
      <div className="signup-inner">
        <div className="signup-kicker">Your sources</div>
        <h2 className="signup-title">Add a link. We read it for you.</h2>
        <p className="signup-sub">
          Paste any article, paper, or post. We scrape it and fold it into{' '}
          <em>your</em> email edition — nobody else ever sees it.
        </p>
        {status === 'done' ? (
          <p className="signup-done">
            Added. It will be scraped before the next run and appear only in your email.
          </p>
        ) : (
          <form
            className="signup-form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label className="signup-field">
              <span>Link</span>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://…"
                autoComplete="off"
                maxLength={2000}
              />
              {issues.url && <em className="field-error">{issues.url}</em>}
            </label>
            <label className="signup-field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                maxLength={254}
              />
              {issues.email && <em className="field-error">{issues.email}</em>}
            </label>
            <button type="submit" className="btn" disabled={status === 'sending'}>
              {status === 'sending' ? 'Adding…' : 'Add source'}
            </button>
            {status === 'error' && (
              <p className="field-error">{errorDetail || 'Something went wrong.'}</p>
            )}
          </form>
        )}

        {email.trim() && (
          <div className="source-list">
            <div className="source-list-title">Your added sources</div>
            {loadingList ? (
              <p className="source-list-empty">Loading…</p>
            ) : sources.length === 0 ? (
              <p className="source-list-empty">Nothing added yet with this email.</p>
            ) : (
              <ul>
                {sources.map((s) => (
                  <li key={s.id} className="source-item">
                    <a href={s.url} target="_blank" rel="noreferrer" className="source-url">
                      {s.title || s.url}
                    </a>
                    <span className={`source-status source-status-${s.status}`}>
                      {STATUS_LABEL[s.status]}
                    </span>
                    {s.status === 'scraped' && s.summary && (
                      <p className="source-summary">{s.summary}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
