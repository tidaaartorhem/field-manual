/** Client-side signup validation (mirrors the Firestore rules). */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface SignupIssues {
  name?: string;
  email?: string;
}

/** Returns field-level issues; empty object means valid. */
export function validateSignup(name: string, email: string): SignupIssues {
  const issues: SignupIssues = {};
  const n = name.trim();
  if (!n) issues.name = 'Please tell us your name.';
  else if (n.length > 80) issues.name = 'Keep it under 80 characters.';
  const e = email.trim().toLowerCase();
  if (!e) issues.email = 'We need an email to send the newsletter to.';
  else if (!EMAIL_RE.test(e)) issues.email = "That doesn't look like an email address.";
  return issues;
}

/** Normalize before writing: trim + lowercase email. */
export function normalizeSignup(name: string, email: string): { name: string; email: string } {
  return { name: name.trim(), email: email.trim().toLowerCase() };
}

/* ---- personal source adder (mirrors the Firestore rules) ---- */

const URL_RE = /^https?:\/\/\S+$/;

export interface SourceIssues {
  url?: string;
  email?: string;
}

/** Returns field-level issues; empty object means valid. */
export function validateSource(url: string, email: string): SourceIssues {
  const issues: SourceIssues = {};
  const u = url.trim();
  if (!u) issues.url = 'Paste a link to add it.';
  else if (u.length > 2000) issues.url = 'That URL is too long.';
  else if (!URL_RE.test(u)) issues.url = 'That doesn\u2019t look like a valid http(s) URL.';
  const e = email.trim().toLowerCase();
  if (!e) issues.email = 'We need your email so the scrape is only used for you.';
  else if (!EMAIL_RE.test(e)) issues.email = "That doesn't look like an email address.";
  return issues;
}

/** Normalize before writing: trim + lowercase email. */
export function normalizeSource(url: string, email: string): { url: string; email: string } {
  return { url: url.trim(), email: email.trim().toLowerCase() };
}
