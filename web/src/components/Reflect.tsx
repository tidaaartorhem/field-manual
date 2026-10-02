import { useEffect, useMemo, useState } from 'react';
import {
  addNote,
  DEBRIEF_QUESTIONS,
  deleteNote,
  getDebrief,
  noteCount,
  notesForTarget,
  reflectedEditions,
  saveDebrief,
  type MarginaliaState,
} from '../lib/marginalia';

function useDrafts(edition: string, existing: Record<string, string>) {
  const [drafts, setDrafts] = useState<Record<string, string>>(existing);
  useEffect(() => {
    setDrafts(existing);
  }, [edition]); // eslint-disable-line react-hooks/exhaustive-deps
  return [drafts, setDrafts] as const;
}

export function Reflect({
  newsletter,
  state,
  onChange,
  initialTarget,
}: {
  newsletter: { edition: string; sections: { id: string; title: string; items: { id: string; title: string }[] }[] };
  state: MarginaliaState;
  onChange: (next: MarginaliaState) => void;
  initialTarget: string | null;
}) {
  const edition = newsletter.edition;
  const [target, setTarget] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState('');

  // Deep-linking from the Edition view: pre-select the annotated target.
  useEffect(() => {
    if (initialTarget) setTarget(initialTarget);
  }, [initialTarget, edition]);

  const saved = getDebrief(state, edition);
  const [drafts, setDrafts] = useDrafts(edition, saved?.answers ?? {});
  const [savedFlash, setSavedFlash] = useState(false);

  const targets = useMemo(() => {
    const list: string[] = [];
    for (const s of newsletter.sections) {
      list.push(`section:${s.id}`);
      for (const it of s.items) list.push(it.id);
    }
    return list;
  }, [newsletter]);

  const notes = target ? notesForTarget(state, edition, target) : [];

  const submitNote = () => {
    if (!target || !noteDraft.trim()) return;
    onChange(addNote(state, edition, target, noteDraft));
    setNoteDraft('');
  };

  const submitDebrief = () => {
    const next = saveDebrief(state, edition, drafts);
    if (next !== state) {
      onChange(next);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2500);
    }
  };

  const past = reflectedEditions(state).filter((e) => e !== edition);

  return (
    <div className="reflect">
      <header className="reflect-head">
        <div className="edition-kicker">Marginalia · {edition}</div>
        <h1 className="edition-title">Read with a pen.</h1>
        <p className="reflect-intro">
          Pin notes to any section or story while you read, then write the
          three-question debrief. {noteCount(state, edition)} note
          {noteCount(state, edition) === 1 ? '' : 's'} so far this edition.
        </p>
      </header>

      <div className="reflect-grid">
        <div className="reflect-targets">
          <h2 className="reflect-h2">Annotate</h2>
          <p className="reflect-hint">Pick a section or story, then write in the margin.</p>
          <ul className="target-list">
            {targets.map((t) => {
              const n = notesForTarget(state, edition, t).length;
              const isSection = t.startsWith('section:');
              return (
                <li key={t}>
                  <button
                    type="button"
                    className={`target-btn${target === t ? ' active' : ''}${isSection ? ' is-section' : ''}`}
                    onClick={() => setTarget(t)}
                  >
                    <span className="target-name">
                      {isSection
                        ? `§ ${newsletter.sections.find((s) => `section:${s.id}` === t)?.title}`
                        : newsletter.sections.flatMap((s) => s.items).find((i) => i.id === t)?.title}
                    </span>
                    {n > 0 && <span className="target-count">{n}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="reflect-notes">
          <h2 className="reflect-h2">Margin</h2>
          {!target ? (
            <p className="reflect-hint">Select something on the left to start annotating.</p>
          ) : (
            <>
              <div className="note-thread">
                {notes.length === 0 && (
                  <p className="reflect-hint">No notes here yet. The margin is yours.</p>
                )}
                {notes.map((n) => (
                  <div key={n.id} className="note">
                    <p className="note-text">{n.text}</p>
                    <div className="note-foot">
                      <span>{new Date(n.ts).toLocaleString()}</span>
                      <button
                        type="button"
                        className="linklike danger"
                        onClick={() => onChange(deleteNote(state, edition, target, n.id))}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="note-composer">
                <textarea
                  value={noteDraft}
                  onChange={(e) => setNoteDraft(e.target.value)}
                  placeholder="Write in the margin…"
                  rows={3}
                />
                <button type="button" className="btn" onClick={submitNote} disabled={!noteDraft.trim()}>
                  Pin note
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="debrief">
        <h2 className="reflect-h2">The debrief</h2>
        <p className="reflect-hint">Three questions, answered after you finish the edition.</p>
        {DEBRIEF_QUESTIONS.map((q) => (
          <label key={q.id} className="debrief-q">
            <span className="debrief-prompt">{q.prompt}</span>
            <textarea
              value={drafts[q.id] ?? ''}
              onChange={(e) => setDrafts({ ...drafts, [q.id]: e.target.value })}
              rows={3}
            />
          </label>
        ))}
        <div className="debrief-actions">
          <button type="button" className="btn" onClick={submitDebrief}>
            Save debrief
          </button>
          {savedFlash && <span className="flash">Saved.</span>}
          {saved && !savedFlash && (
            <span className="reflect-hint">
              Last saved {new Date(saved.ts).toLocaleString()}
            </span>
          )}
        </div>
      </div>

      {past.length > 0 && (
        <div className="past">
          <h2 className="reflect-h2">Earlier editions</h2>
          <ul className="past-list">
            {past.map((e) => (
              <li key={e} className="past-row">
                <span className="past-edition">{e}</span>
                <span className="reflect-hint">
                  {noteCount(state, e)} notes
                  {getDebrief(state, e) ? ' · debriefed' : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
