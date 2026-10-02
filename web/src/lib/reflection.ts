/**
 * Pure reflection-studio logic. State shape mirrors SCHEMA.md's
 * localStorage contract (key `field-manual:v1`); everything here is a pure
 * function so it can be unit-tested without a DOM or localStorage.
 */

export const STORAGE_KEY = 'field-manual:v1';

export interface JournalEntry {
  ts: number;
  text: string;
}

export interface QaAnswer {
  prompt: string;
  answer: string;
  score: number; // 1..5 self-score
  ts: number;
}

export interface ReflectionState {
  journal: Record<string, JournalEntry[]>;
  qa: Record<string, QaAnswer[]>;
  days: string[]; // YYYY-MM-DD, days with >=1 journal entry or answered prompt
}

export const SOCRATIC_PROMPTS: readonly string[] = [
  'Explain this to a skeptic.',
  'Where would this break in production?',
  'What is the strongest counterargument?',
  'How would you apply this at work this week?',
  'What would you need to believe for this to be wrong?',
];

/** Today's date as YYYY-MM-DD in local time. */
export function todayLocal(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** The day before a YYYY-MM-DD date. */
export function prevDay(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() - 1);
  return todayLocal(dt);
}

export function emptyReflectionState(): ReflectionState {
  return { journal: {}, qa: {}, days: [] };
}

/** Append a journal entry for an item. Ignores blank text. */
export function addJournalEntry(
  state: ReflectionState,
  itemId: string,
  text: string,
  ts: number = Date.now(),
): ReflectionState {
  const trimmed = text.trim();
  if (!trimmed) return state;
  const entry: JournalEntry = { ts, text: trimmed };
  return {
    ...state,
    journal: { ...state.journal, [itemId]: [...(state.journal[itemId] ?? []), entry] },
  };
}

/**
 * Record an answered socratic prompt. Score is clamped to 1..5.
 * Ignores blank answers.
 */
export function answerPrompt(
  state: ReflectionState,
  itemId: string,
  prompt: string,
  answer: string,
  score: number,
  ts: number = Date.now(),
): ReflectionState {
  const trimmed = answer.trim();
  if (!trimmed) return state;
  const clamped = Math.min(5, Math.max(1, Math.round(score)));
  const qa: QaAnswer = { prompt, answer: trimmed, score: clamped, ts };
  return {
    ...state,
    qa: { ...state.qa, [itemId]: [...(state.qa[itemId] ?? []), qa] },
  };
}

/** Mark a day as active (has >=1 journal entry or answered prompt). Dedupes and sorts. */
export function recordDay(state: ReflectionState, day: string = todayLocal()): ReflectionState {
  if (state.days.includes(day)) return state;
  return { ...state, days: [...state.days, day].sort() };
}

/**
 * Current reading streak: consecutive active days ending today (or
 * yesterday, if today has no activity yet — the streak is still alive).
 */
export function currentStreak(state: ReflectionState, today: string = todayLocal()): number {
  const active = new Set(state.days);
  let cursor = today;
  if (!active.has(cursor)) cursor = prevDay(cursor);
  let streak = 0;
  while (active.has(cursor)) {
    streak += 1;
    cursor = prevDay(cursor);
  }
  return streak;
}

/** Item ids with at least one journal entry or answered prompt. */
export function reflectedItemIds(state: ReflectionState): string[] {
  const ids = new Set<string>();
  for (const [id, entries] of Object.entries(state.journal)) if (entries.length > 0) ids.add(id);
  for (const [id, answers] of Object.entries(state.qa)) if (answers.length > 0) ids.add(id);
  return [...ids];
}

export interface ProgressStats {
  reflected: number;
  total: number;
  percent: number; // 0..100
}

/** Coverage: how many of the manual's items have any reflection. */
export function progressStats(state: ReflectionState, totalItems: number): ProgressStats {
  if (totalItems <= 0) return { reflected: 0, total: 0, percent: 0 };
  const reflected = Math.min(reflectedItemIds(state).length, totalItems);
  return { reflected, total: totalItems, percent: Math.round((reflected / totalItems) * 100) };
}
