import {
  DEBRIEF_QUESTIONS,
  emptyState,
  STORAGE_KEY,
  type Debrief,
  type MarginaliaState,
  type MarginNote,
} from './marginalia';

function isMarginNote(v: unknown): v is MarginNote {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as MarginNote).id === 'string' &&
    typeof (v as MarginNote).ts === 'number' &&
    typeof (v as MarginNote).text === 'string'
  );
}

function isDebrief(v: unknown): v is Debrief {
  if (typeof v !== 'object' || v === null) return false;
  const d = v as Debrief;
  if (typeof d.ts !== 'number' || typeof d.answers !== 'object' || d.answers === null)
    return false;
  return Object.values(d.answers).every((a) => typeof a === 'string');
}

/** Load persisted marginalia; falls back to empty on any failure. */
export function loadMarginalia(): MarginaliaState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw) as Partial<MarginaliaState>;
    const notes: MarginaliaState['notes'] = {};
    if (parsed.notes && typeof parsed.notes === 'object') {
      for (const [edition, targets] of Object.entries(parsed.notes)) {
        if (typeof targets !== 'object' || targets === null) continue;
        const clean: Record<string, MarginNote[]> = {};
        for (const [target, list] of Object.entries(targets)) {
          if (Array.isArray(list) && list.every(isMarginNote)) clean[target] = list;
        }
        if (Object.keys(clean).length > 0) notes[edition] = clean;
      }
    }
    const debriefs: MarginaliaState['debriefs'] = {};
    if (parsed.debriefs && typeof parsed.debriefs === 'object') {
      for (const [edition, d] of Object.entries(parsed.debriefs)) {
        if (isDebrief(d)) debriefs[edition] = d;
      }
    }
    return { notes, debriefs };
  } catch {
    return emptyState();
  }
}

/** Persist marginalia. Never throws (quota or privacy modes). */
export function saveMarginalia(state: MarginaliaState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Silently ignore: reflections live in memory for this session.
  }
}

export { DEBRIEF_QUESTIONS };
