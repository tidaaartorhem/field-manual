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
