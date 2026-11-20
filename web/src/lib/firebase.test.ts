import { beforeEach, describe, expect, it, vi } from 'vitest';

// --- Firestore mocks -------------------------------------------------------

const mocks = vi.hoisted(() => ({
  addDoc: vi.fn(),
  collection: vi.fn(),
  doc: vi.fn(),
  getDoc: vi.fn(),
  getFirestore: vi.fn(),
  initializeApp: vi.fn(),
  serverTimestamp: vi.fn(),
}));

vi.mock('firebase/app', () => ({
  initializeApp: mocks.initializeApp,
}));

vi.mock('firebase/firestore', () => ({
  addDoc: mocks.addDoc,
  collection: mocks.collection,
  doc: mocks.doc,
  getDoc: mocks.getDoc,
  getFirestore: mocks.getFirestore,
  serverTimestamp: mocks.serverTimestamp,
}));

import {
  addStoredSourceId,
  addUserSource,
  getStoredSourceIds,
  getUserSources,
} from './firebase';

// --- in-memory localStorage (vitest runs in node) --------------------------

function installLocalStorage(): void {
  const store = new Map<string, string>();
  const shim = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: shim,
    configurable: true,
  });
}

function docSnap(id: string, data: Record<string, unknown> | null) {
  return {
    id,
    exists: () => data !== null,
    data: () => data,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  installLocalStorage();
  mocks.initializeApp.mockReturnValue({ __app: true });
  mocks.getFirestore.mockReturnValue({ __db: true });
  mocks.collection.mockImplementation((_db: unknown, name: string) => ({ __coll: name }));
  mocks.doc.mockImplementation((_db: unknown, coll: string, id: string) => ({
    __coll: coll,
    __id: id,
  }));
  mocks.serverTimestamp.mockReturnValue('TS');
});

describe('addUserSource', () => {
  it('returns the new doc id and writes a pending doc', async () => {
    mocks.addDoc.mockResolvedValue({ id: 'AbC123xYz' });
    const id = await addUserSource('  Aadit@Example.com ', 'https://example.com/a');
    expect(id).toBe('AbC123xYz');
    expect(mocks.addDoc).toHaveBeenCalledTimes(1);
    const [, payload] = mocks.addDoc.mock.calls[0] as [unknown, Record<string, unknown>];
    expect(payload.email).toBe('aadit@example.com');
    expect(payload.url).toBe('https://example.com/a');
    expect(payload.status).toBe('pending');
    expect(payload.title).toBe('');
  });
});

describe('stored source ids (localStorage)', () => {
  it('round-trips ids newest-first, deduped, capped at 50', () => {
    expect(getStoredSourceIds()).toEqual([]);
    addStoredSourceId('id-1');
    addStoredSourceId('id-2');
    addStoredSourceId('id-1');
    expect(getStoredSourceIds()).toEqual(['id-1', 'id-2']);
    for (let i = 0; i < 60; i++) addStoredSourceId(`id-${i}`);
    const ids = getStoredSourceIds();
    expect(ids).toHaveLength(50);
    expect(ids[0]).toBe('id-59');
    expect(ids).not.toContain('id-0');
  });

  it('ignores corrupt stored data', () => {
    localStorage.setItem('fm_source_ids', 'not-json{');
    expect(getStoredSourceIds()).toEqual([]);
    localStorage.setItem('fm_source_ids', JSON.stringify({ not: 'a list' }));
    expect(getStoredSourceIds()).toEqual([]);
  });
});

describe('getUserSources', () => {
  it('fetches each id with getDoc and skips missing docs', async () => {
    mocks.getDoc.mockImplementation(async (ref: { __id: string }) => {
      if (ref.__id === 'gone') return docSnap('gone', null);
      return docSnap(ref.__id, {
        email: 'a@example.com',
        url: 'https://example.com/a',
        title: 'T',
        summary: 'S',
        status: 'scraped',
      });
    });
    const out = await getUserSources(['one', 'gone', 'two']);
    expect(mocks.getDoc).toHaveBeenCalledTimes(3);
    expect(out.map((s) => s.id)).toEqual(['one', 'two']);
    expect(out[0].status).toBe('scraped');
    expect(out[0].summary).toBe('S');
    // Per-doc get only: the client must never run a collection list/query,
    // which the rules now deny.
    expect(mocks.doc).toHaveBeenCalledTimes(3);
  });

  it('normalizes unknown statuses to pending', async () => {
    mocks.getDoc.mockResolvedValue(
      docSnap('x', { email: 'a@b.c', url: 'https://x.y', status: 'weird' }),
    );
    const out = await getUserSources(['x']);
    expect(out[0].status).toBe('pending');
  });
});
