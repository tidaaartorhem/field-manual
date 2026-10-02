/**
 * Marginalia — the reflection experience, as pure functions.
 *
 * One idea, done well: while you read, pin margin notes to any section or
 * item; when you finish, write the three-question debrief. Everything is
 * keyed by edition date and persisted to localStorage (see storage.ts).
 *
 * Targets are addressed as `section:<section-id>` or an item id.
 */

export const STORAGE_KEY = 'field-manual:v2';

export interface MarginNote {
  id: string;
  ts: number;
  text: string;
}

export interface Debrief {
  answers: Record<string, string>; // questionId -> answer
  ts: number;
}

export interface MarginaliaState {
  notes: Record<string, Record<string, MarginNote[]>>; // edition -> target -> notes
  debriefs: Record<string, Debrief>; // edition -> debrief
}

export const DEBRIEF_QUESTIONS: readonly { id: string; prompt: string }[] = [
  { id: 'changed-mind', prompt: 'What changed your mind?' },
  { id: 'will-try', prompt: 'What is one thing you will try this week?' },
  { id: 'still-skeptical', prompt: 'What are you still skeptical about?' },
];

/** Deterministic-ish note id (unique per call). */
export function makeNoteId(ts: number = Date.now()): string {
  return `n${ts.toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

export function emptyState(): MarginaliaState {
  return { notes: {}, debriefs: {} };
}

/** Pin a margin note to a target. Ignores blank text. */
export function addNote(
  state: MarginaliaState,
  edition: string,
  target: string,
  text: string,
  ts: number = Date.now(),
): MarginaliaState {
  const trimmed = text.trim();
  if (!trimmed) return state;
  const note: MarginNote = { id: makeNoteId(ts), ts, text: trimmed };
  const byEdition = state.notes[edition] ?? {};
  return {
    ...state,
    notes: {
      ...state.notes,
      [edition]: {
        ...byEdition,
        [target]: [...(byEdition[target] ?? []), note],
      },
    },
  };
}

/** Remove one margin note. Unknown ids are ignored. */
export function deleteNote(
  state: MarginaliaState,
  edition: string,
  target: string,
  noteId: string,
): MarginaliaState {
  const byEdition = state.notes[edition];
  if (!byEdition || !byEdition[target]) return state;
  if (!byEdition[target].some((n) => n.id === noteId)) return state;
  const kept = byEdition[target].filter((n) => n.id !== noteId);
  const nextTargets = { ...byEdition };
  if (kept.length === 0) delete nextTargets[target];
  else nextTargets[target] = kept;
  const nextEditions = { ...state.notes };
  if (Object.keys(nextTargets).length === 0) delete nextEditions[edition];
  else nextEditions[edition] = nextTargets;
  return { ...state, notes: nextEditions };
}

/** Notes for one target, oldest first. */
export function notesForTarget(
  state: MarginaliaState,
  edition: string,
  target: string,
): MarginNote[] {
  return state.notes[edition]?.[target] ?? [];
}

/** Every target with notes in an edition, in first-note order. */
export function annotatedTargets(
  state: MarginaliaState,
  edition: string,
): string[] {
  const byEdition = state.notes[edition];
  if (!byEdition) return [];
  return Object.keys(byEdition).filter((t) => byEdition[t].length > 0);
}

/** Total margin notes in an edition. */
export function noteCount(state: MarginaliaState, edition: string): number {
  const byEdition = state.notes[edition];
  if (!byEdition) return 0;
  return Object.values(byEdition).reduce((n, notes) => n + notes.length, 0);
}

/**
 * Save the debrief for an edition. Blank answers are dropped; if every
 * answer is blank the existing debrief is left untouched (returns state).
 */
export function saveDebrief(
  state: MarginaliaState,
  edition: string,
  answers: Record<string, string>,
  ts: number = Date.now(),
): MarginaliaState {
  const kept: Record<string, string> = {};
  for (const q of DEBRIEF_QUESTIONS) {
    const a = (answers[q.id] ?? '').trim();
    if (a) kept[q.id] = a;
  }
  if (Object.keys(kept).length === 0) return state;
  return {
    ...state,
    debriefs: { ...state.debriefs, [edition]: { answers: kept, ts } },
  };
}

/** The saved debrief for an edition, if any. */
export function getDebrief(
  state: MarginaliaState,
  edition: string,
): Debrief | undefined {
  return state.debriefs[edition];
}

/** Editions with any reflection (notes or a debrief), newest first. */
export function reflectedEditions(state: MarginaliaState): string[] {
  const editions = new Set<string>([
    ...Object.keys(state.notes),
    ...Object.keys(state.debriefs),
  ]);
  return [...editions].sort().reverse();
}

/** True when the edition has at least one note or a debrief. */
export function editionHasReflection(
  state: MarginaliaState,
  edition: string,
): boolean {
  return noteCount(state, edition) > 0 || getDebrief(state, edition) !== undefined;
}
