import {
  emptyReflectionState,
  STORAGE_KEY,
  type JournalEntry,
  type QaAnswer,
  type ReflectionState,
} from './reflection';

function isJournalEntry(v: unknown): v is JournalEntry {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as JournalEntry).ts === 'number' &&
    typeof (v as JournalEntry).text === 'string'
  );
}

function isQaAnswer(v: unknown): v is QaAnswer {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as QaAnswer).prompt === 'string' &&
    typeof (v as QaAnswer).answer === 'string' &&
    typeof (v as QaAnswer).score === 'number' &&
    typeof (v as QaAnswer).ts === 'number'
  );
}

/** Load persisted reflection state; falls back to empty on any failure. */
export function loadReflectionState(): ReflectionState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyReflectionState();
    const parsed = JSON.parse(raw) as Partial<ReflectionState>;
    const journal: ReflectionState['journal'] = {};
    if (parsed.journal && typeof parsed.journal === 'object') {
      for (const [id, entries] of Object.entries(parsed.journal)) {
        if (Array.isArray(entries) && entries.every(isJournalEntry)) journal[id] = entries;
      }
    }
    const qa: ReflectionState['qa'] = {};
    if (parsed.qa && typeof parsed.qa === 'object') {
      for (const [id, answers] of Object.entries(parsed.qa)) {
        if (Array.isArray(answers) && answers.every(isQaAnswer)) qa[id] = answers;
      }
    }
    const days = Array.isArray(parsed.days) ? parsed.days.filter((d) => typeof d === 'string') : [];
    return { journal, qa, days };
  } catch {
    return emptyReflectionState();
  }
}

/** Persist reflection state. Never throws (quota or privacy modes). */
export function saveReflectionState(state: ReflectionState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Silently ignore: reflections live in memory for this session.
  }
}
