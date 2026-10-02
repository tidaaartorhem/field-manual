import { useEffect, useMemo, useState } from 'react';
import { allItems, type ManualData } from '../lib/manual';
import { formatTs } from '../lib/format';
import { SOCRATIC_PROMPTS } from '../lib/reflection';
import { useReflection } from '../hooks/useReflection';

interface StudioProps {
  manual: ManualData;
  focusItemId: string | null;
}

function Star() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z" />
    </svg>
  );
}

function ItemSelect({
  id,
  label,
  value,
  onChange,
  manual,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  manual: ManualData;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {manual.shelves.map((shelf) => (
          <optgroup key={shelf.id} label={shelf.title}>
            {shelf.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

export function Studio({ manual, focusItemId }: StudioProps) {
  const items = useMemo(() => allItems(manual), [manual]);
  const { state, addEntry, addAnswer, streak, progress } = useReflection(items.length);

  const [journalItem, setJournalItem] = useState(focusItemId ?? items[0]?.id ?? '');
  const [journalText, setJournalText] = useState('');
  const [qaItem, setQaItem] = useState(focusItemId ?? items[0]?.id ?? '');
  const [promptIndex, setPromptIndex] = useState(0);
  const [answerText, setAnswerText] = useState('');
  const [score, setScore] = useState(0);

  // "Reflect on this" from the reader deep-links into the studio.
  useEffect(() => {
    if (focusItemId) {
      setJournalItem(focusItemId);
      setQaItem(focusItemId);
    }
  }, [focusItemId]);

  const drawPrompt = () => setPromptIndex((i) => (i + 1) % SOCRATIC_PROMPTS.length);
  const prompt = SOCRATIC_PROMPTS[promptIndex] ?? '';

  const saveEntry = () => {
    if (!journalItem || !journalText.trim()) return;
    addEntry(journalItem, journalText);
    setJournalText('');
  };

  const saveAnswer = () => {
    if (!qaItem || !answerText.trim() || score === 0) return;
    addAnswer(qaItem, prompt, answerText, score);
    setAnswerText('');
    setScore(0);
    drawPrompt();
  };

  const journalEntries = useMemo(
    () => [...(state.journal[journalItem] ?? [])].sort((a, b) => b.ts - a.ts),
    [state.journal, journalItem],
  );
  const qaAnswers = useMemo(
    () => [...(state.qa[qaItem] ?? [])].sort((a, b) => b.ts - a.ts),
    [state.qa, qaItem],
  );

  const streakCopy =
    streak === 0
      ? 'No streak yet. Write one note and the count begins.'
      : streak === 1
        ? 'One day on the board. Come back tomorrow and make it a habit.'
        : 'Days of showing up. The manual remembers; so will you.';

  return (
    <div className="studio">
      <div className="section-head">
        <h2>Reflection studio</h2>
        <p>
          Reading without writing is just sightseeing. This is where the manual becomes yours —
          argue with it in the notebook, spar with the socratic prompts, and watch the streak
          compound. Everything stays in your browser; nothing leaves the dossier.
        </p>
      </div>

      <div className="studio-hero">
        <div className="streak-card">
          <div className="studio-label">Reading streak</div>
          <div className="num">
            {streak} <small>{streak === 1 ? 'day' : 'days'}</small>
          </div>
          <p>{streakCopy}</p>
        </div>
        <div className="progress-card">
          <div className="studio-label">Coverage</div>
          <div className="progress-line">
            <span className="pct">{progress.percent}%</span>
            <span style={{ color: 'var(--faint)', fontSize: '0.8rem', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
              {progress.reflected} of {progress.total} reflected
            </span>
          </div>
          <div className="progress-bar">
            <i style={{ width: `${progress.percent}%` }} />
          </div>
          <p>
            An item counts once you&apos;ve written about it or answered a prompt on it. The goal
            isn&apos;t 100% — it&apos;s never zero.
          </p>
        </div>
      </div>

      <div className="studio-grid">
        <section className="panel" aria-label="Notebook">
          <h3>The notebook</h3>
          <p className="panel-sub">
            Argue with the briefing. What&apos;s wrong, what&apos;s overhyped, what you&apos;d
            steal — get it out of your head and onto the page.
          </p>
          <ItemSelect id="journal-item" label="Briefing" value={journalItem} onChange={setJournalItem} manual={manual} />
          <div className="field">
            <label htmlFor="journal-text">Entry</label>
            <textarea
              id="journal-text"
              value={journalText}
              onChange={(e) => setJournalText(e.target.value)}
              placeholder="What did this one get right that nobody talks about?"
            />
          </div>
          <button className="btn btn-primary btn-sm" type="button" onClick={saveEntry} disabled={!journalText.trim()}>
            File the entry
          </button>
          <div className="entries">
            {journalEntries.length === 0 ? (
              <p className="empty-note">An empty notebook is a decision. Start writing.</p>
            ) : (
              journalEntries.map((e, i) => (
                <div className="entry" key={`${e.ts}-${i}`}>
                  <div className="entry-meta">
                    <span>{formatTs(e.ts)}</span>
                  </div>
                  <p>{e.text}</p>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel" aria-label="Socratic sparring">
          <h3>Socratic sparring</h3>
          <p className="panel-sub">
            Pick a briefing, take a prompt, answer honestly — then score yourself. The score
            isn&apos;t a grade; it&apos;s a mirror.
          </p>
          <ItemSelect id="qa-item" label="Briefing" value={qaItem} onChange={setQaItem} manual={manual} />
          <div className="prompt-card">
            <p className="prompt-text">{prompt}</p>
            <div className="prompt-actions">
              <button className="link-btn" type="button" onClick={drawPrompt}>
                Draw another
              </button>
              <span className="prompt-count">
                {promptIndex + 1} / {SOCRATIC_PROMPTS.length}
              </span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="qa-answer">Your answer</label>
            <textarea
              id="qa-answer"
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              placeholder="Steel-man it first. Then land the punch."
            />
          </div>
          <div className="stars-label">Self-score</div>
          <div className="stars" role="radiogroup" aria-label="Self-score from 1 to 5">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={score === n}
                aria-label={`${n} of 5`}
                className={n <= score ? 'lit' : ''}
                onClick={() => setScore(n)}
              >
                <Star />
              </button>
            ))}
          </div>
          <button
            className="btn btn-primary btn-sm"
            type="button"
            onClick={saveAnswer}
            disabled={!answerText.trim() || score === 0}
          >
            File the answer
          </button>
          <div className="entries">
            {qaAnswers.length === 0 ? (
              <p className="empty-note">No sparring rounds yet. The prompts don&apos;t bite.</p>
            ) : (
              qaAnswers.map((a, i) => (
                <div className="entry" key={`${a.ts}-${i}`}>
                  <div className="entry-meta">
                    <span>{formatTs(a.ts)}</span>
                    <span className="entry-stars">{'★'.repeat(a.score)}{'☆'.repeat(5 - a.score)}</span>
                  </div>
                  <div className="entry-prompt">{a.prompt}</div>
                  <p>{a.answer}</p>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
