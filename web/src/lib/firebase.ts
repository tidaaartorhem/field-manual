import { initializeApp, type FirebaseApp } from 'firebase/app';
import { addDoc, collection, getFirestore, serverTimestamp, type Firestore } from 'firebase/firestore';

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
