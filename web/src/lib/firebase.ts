import { initializeApp, type FirebaseApp } from 'firebase/app';
import {
  addDoc,
  collection,
  doc,
  getDoc,
  getFirestore,
  serverTimestamp,
  type Firestore,
} from 'firebase/firestore';

// Public client config for the portfolio-3da31 project (safe to ship in
// the bundle — Firestore rules, not the key, guard the data).
const firebaseConfig = {
  "apiKey": "AIzaSyBtvsuk3yM7IkNO0ODOJZxK7JD1wQq5XZ8",
  "authDomain": "portfolio-3da31.firebaseapp.com",
  "projectId": "portfolio-3da31",
  "storageBucket": "portfolio-3da31.firebasestorage.app",
  "messagingSenderId": "1028354535112",
  "appId": "1:1028354535112:web:15cb15d709f378c6dcfffd"
};

let app: FirebaseApp | null = null;
let db: Firestore | null = null;

export function getDb(): Firestore {
  if (!db) {
    app = app ?? initializeApp(firebaseConfig);
    db = getFirestore(app);
  }
  return db;
}

/** Write a subscriber document. Rules validate name/email server-side. */
export async function addSubscriber(name: string, email: string): Promise<void> {
  await addDoc(collection(getDb(), 'subscribers'), {
    name: name.trim(),
    email: email.trim().toLowerCase(),
    source: 'web',
    createdAt: serverTimestamp(),
  });
}

/* ---- remembered identity (no auth yet — the email is the key) ---- */

const EMAIL_KEY = 'fm_email';

export function getStoredEmail(): string {
  try {
    return localStorage.getItem(EMAIL_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setStoredEmail(email: string): void {
  try {
    localStorage.setItem(EMAIL_KEY, email.trim().toLowerCase());
  } catch {
    /* private mode etc. — non-fatal */
  }
}

/* ---- personal source adder ---- */

export type UserSourceStatus = 'pending' | 'scraped' | 'failed';

export interface UserSource {
  id: string;
  email: string;
  url: string;
  title: string;
  summary: string;
  status: UserSourceStatus;
}

/* ---- submitted-source IDs (this browser only) ---- */

// Firestore rules allow get-by-ID on user_sources but deny list, so the
// client can only re-read a submission whose doc ID it already knows. The
// IDs are kept in localStorage; a doc ID is a random 20-char string, so
// knowing it is the capability. Sources added from another browser still
// get scraped and emailed (the pipeline keys by email) — they just don't
// show in this browser's list.
const SOURCE_IDS_KEY = 'fm_source_ids';
const MAX_STORED_SOURCE_IDS = 50;

export function getStoredSourceIds(): string[] {
  try {
    const raw = localStorage.getItem(SOURCE_IDS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v): v is string => typeof v === 'string').slice(0, MAX_STORED_SOURCE_IDS);
  } catch {
    return [];
  }
}

export function addStoredSourceId(id: string): void {
  try {
    const ids = [id, ...getStoredSourceIds().filter((v) => v !== id)].slice(
      0,
      MAX_STORED_SOURCE_IDS,
    );
    localStorage.setItem(SOURCE_IDS_KEY, JSON.stringify(ids));
  } catch {
    /* private mode etc. — non-fatal */
  }
}

/** Submit a URL for scraping. Rules validate email/url server-side.
 *  Returns the new doc's ID so the caller can remember it for status. */
export async function addUserSource(email: string, url: string): Promise<string> {
  const ref = await addDoc(collection(getDb(), 'user_sources'), {
    email: email.trim().toLowerCase(),
    url: url.trim(),
    title: '',
    addedAt: serverTimestamp(),
    status: 'pending',
  });
  return ref.id;
}

/** The visitor's own submitted URLs (and their scrape status), fetched one
 *  doc at a time by the IDs stored in this browser. Docs that no longer
 *  exist are skipped. */
export async function getUserSources(ids: string[]): Promise<UserSource[]> {
  const out: UserSource[] = [];
  for (const id of ids) {
    const snap = await getDoc(doc(getDb(), 'user_sources', id));
    if (!snap.exists()) continue;
    const data = snap.data() as Record<string, unknown>;
    const status = data.status as string;
    out.push({
      id: snap.id,
      email: String(data.email ?? ''),
      url: String(data.url ?? ''),
      title: String(data.title ?? ''),
      summary: String(data.summary ?? ''),
      status: (status === 'scraped' || status === 'failed' ? status : 'pending') as UserSourceStatus,
    });
  }
  return out;
}
