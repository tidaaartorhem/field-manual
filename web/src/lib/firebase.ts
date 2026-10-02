import { initializeApp, type FirebaseApp } from 'firebase/app';
import {
  addDoc,
  collection,
  getDocs,
  getFirestore,
  query,
  serverTimestamp,
  where,
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

/** Submit a URL for scraping. Rules validate email/url server-side. */
export async function addUserSource(email: string, url: string): Promise<void> {
  await addDoc(collection(getDb(), 'user_sources'), {
    email: email.trim().toLowerCase(),
    url: url.trim(),
    title: '',
    addedAt: serverTimestamp(),
    status: 'pending',
  });
}

/** The visitor's own submitted URLs (and their scrape status). */
export async function listUserSources(email: string): Promise<UserSource[]> {
  const q = query(
    collection(getDb(), 'user_sources'),
    where('email', '==', email.trim().toLowerCase()),
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => {
    const data = d.data() as Record<string, unknown>;
    const status = data.status as string;
    return {
      id: d.id,
      email: String(data.email ?? ''),
      url: String(data.url ?? ''),
      title: String(data.title ?? ''),
      summary: String(data.summary ?? ''),
      status: (status === 'scraped' || status === 'failed' ? status : 'pending') as UserSourceStatus,
    };
  });
}
