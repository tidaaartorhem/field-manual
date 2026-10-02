import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  addJournalEntry,
  answerPrompt,
  currentStreak,
  emptyReflectionState,
  progressStats,
  recordDay,
  todayLocal,
  type ReflectionState,
} from '../lib/reflection';
import { loadReflectionState, saveReflectionState } from '../lib/storage';

/**
 * Reflection studio state: journal entries + socratic answers persisted to
 * localStorage (key `field-manual:v1`), with derived streak and progress.
 */
export function useReflection(totalItems: number) {
  const [state, setState] = useState<ReflectionState>(() => {
    try {
      return loadReflectionState();
    } catch {
      return emptyReflectionState();
    }
  });

  useEffect(() => {
    saveReflectionState(state);
  }, [state]);

  const addEntry = useCallback((itemId: string, text: string) => {
    setState((s) => recordDay(addJournalEntry(s, itemId, text), todayLocal()));
  }, []);

  const addAnswer = useCallback((itemId: string, prompt: string, answer: string, score: number) => {
    setState((s) => recordDay(answerPrompt(s, itemId, prompt, answer, score), todayLocal()));
  }, []);

  const streak = useMemo(() => currentStreak(state), [state]);
  const progress = useMemo(() => progressStats(state, totalItems), [state, totalItems]);

  return { state, addEntry, addAnswer, streak, progress };
}
