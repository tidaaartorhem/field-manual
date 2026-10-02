import { useState } from 'react';
import { addSubscriber, setStoredEmail } from '../lib/firebase';
import { normalizeSignup, validateSignup } from '../lib/validate';

type Status = 'idle' | 'sending' | 'done' | 'error';

export function Signup({ edition }: { edition: string }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [issues, setIssues] = useState<{ name?: string; email?: string }>({});
  const [status, setStatus] = useState<Status>('idle');
  const [errorDetail, setErrorDetail] = useState('');

  const submit = async () => {
    const found = validateSignup(name, email);
    setIssues(found);
    if (Object.keys(found).length > 0) return;
    setStatus('sending');
    setErrorDetail('');
    try {
      const clean = normalizeSignup(name, email);
      await addSubscriber(clean.name, clean.email);
      setStoredEmail(clean.email);
      setStatus('done');
    } catch (err) {
      setStatus('error');
      setErrorDetail(err instanceof Error ? err.message : 'Something went wrong.');
    }
  };

  return (
    <section className="signup" aria-label="Get the newsletter by email">
      <div className="signup-inner">
        <div className="signup-kicker">The email edition</div>
        <h2 className="signup-title">Get this in your inbox.</h2>
        <p className="signup-sub">
          Every other morning, the latest edition — charts included — lands in
          your inbox. No spam, ever. Reply to any email to unsubscribe.
        </p>
        {status === 'done' ? (
          <p className="signup-done">
            You're on the list. The next edition ({edition}) ships on the next run.
          </p>
        ) : (
          <form
            className="signup-form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label className="signup-field">
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ada Lovelace"
                autoComplete="name"
                maxLength={80}
              />
              {issues.name && <em className="field-error">{issues.name}</em>}
            </label>
            <label className="signup-field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ada@example.com"
                autoComplete="email"
              />
              {issues.email && <em className="field-error">{issues.email}</em>}
            </label>
            <button type="submit" className="btn" disabled={status === 'sending'}>
              {status === 'sending' ? 'Signing up…' : 'Sign me up'}
            </button>
            {status === 'error' && (
              <p className="field-error">Couldn't sign you up: {errorDetail}</p>
            )}
          </form>
        )}
      </div>
    </section>
  );
}
