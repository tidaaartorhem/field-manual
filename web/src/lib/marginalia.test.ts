import { describe, expect, it } from 'vitest';
import {
  addNote,
  deleteNote,
  DEBRIEF_QUESTIONS,
  editionHasReflection,
  emptyState,
  getDebrief,
  noteCount,
  notesForTarget,
  reflectedEditions,
  saveDebrief,
  type MarginaliaState,
} from './marginalia';

describe('margin notes', () => {
  it('adds a note to a target and lists it oldest-first', () => {
    let s = emptyState();
    s = addNote(s, '2026-10-02', 'signal-001', 'second', 2000);
    s = addNote(s, '2026-10-02', 'signal-001', 'first', 1000);
    const notes = notesForTarget(s, '2026-10-02', 'signal-001');
    expect(notes.map((n) => n.text)).toEqual(['second', 'first']);
    expect(notes[0].id).not.toBe(notes[1].id);
  });

  it('ignores blank notes', () => {
    const s = addNote(emptyState(), '2026-10-02', 'signal-001', '   ');
    expect(noteCount(s, '2026-10-02')).toBe(0);
  });

  it('supports section targets', () => {
    const s = addNote(emptyState(), '2026-10-02', 'section:signal', 'on the section');
    expect(notesForTarget(s, '2026-10-02', 'section:signal')).toHaveLength(1);
  });

  it('deletes a note and prunes empty targets', () => {
    let s = addNote(emptyState(), '2026-10-02', 'signal-001', 'bye', 1000);
    const id = notesForTarget(s, '2026-10-02', 'signal-001')[0].id;
    s = deleteNote(s, '2026-10-02', 'signal-001', id);
    expect(notesForTarget(s, '2026-10-02', 'signal-001')).toEqual([]);
    expect('2026-10-02' in s.notes).toBe(false);
  });

  it('ignores unknown note ids', () => {
    const s = addNote(emptyState(), '2026-10-02', 'signal-001', 'keep me');
    const s2 = deleteNote(s, '2026-10-02', 'signal-001', 'nope');
    expect(s2).toBe(s);
  });

  it('counts notes across targets', () => {
    let s = emptyState();
    s = addNote(s, '2026-10-02', 'signal-001', 'a');
    s = addNote(s, '2026-10-02', 'section:tech', 'b');
    expect(noteCount(s, '2026-10-02')).toBe(2);
    expect(noteCount(s, '2026-10-01')).toBe(0);
  });
});

describe('debrief', () => {
  const answers = {
    'changed-mind': 'Agents are infrastructure now.',
    'will-try': 'Ship one eval this week.',
    'still-skeptical': 'The pricing of all these tools.',
  };

  it('saves and retrieves a debrief', () => {
    const s = saveDebrief(emptyState(), '2026-10-02', answers, 1234);
    const d = getDebrief(s, '2026-10-02');
    expect(d?.answers).toEqual(answers);
    expect(d?.ts).toBe(1234);
  });

  it('drops blank answers and ignores all-blank saves', () => {
    const s = saveDebrief(emptyState(), '2026-10-02', {
      'changed-mind': '  ',
      'will-try': 'Something real.',
      'still-skeptical': '',
    });
    expect(getDebrief(s, '2026-10-02')?.answers).toEqual({
      'will-try': 'Something real.',
    });
    const s2 = saveDebrief(s, '2026-10-03', {
      'changed-mind': ' ',
      'will-try': ' ',
      'still-skeptical': ' ',
    });
    expect(getDebrief(s2, '2026-10-03')).toBeUndefined();
  });

  it('has exactly three questions', () => {
    expect(DEBRIEF_QUESTIONS).toHaveLength(3);
    expect(DEBRIEF_QUESTIONS.map((q) => q.id)).toEqual([
      'changed-mind',
      'will-try',
      'still-skeptical',
    ]);
  });
});

describe('edition rollup', () => {
  it('lists reflected editions newest-first', () => {
    let s: MarginaliaState = emptyState();
    s = addNote(s, '2026-10-01', 'signal-001', 'old');
    s = saveDebrief(s, '2026-10-02', { 'will-try': 'x' });
    expect(reflectedEditions(s)).toEqual(['2026-10-02', '2026-10-01']);
  });

  it('detects reflection presence', () => {
    const s = addNote(emptyState(), '2026-10-02', 'signal-001', 'x');
    expect(editionHasReflection(s, '2026-10-02')).toBe(true);
    expect(editionHasReflection(s, '2026-10-01')).toBe(false);
  });
});
