# Field Manual — the last 48 hours, in one story

Keeping up with AI is a firehose: launches, raises, papers, and five podcasts all talking at once. A firehose doesn't teach you anything. A story does — and a story with numbers is harder to fool.

Field Manual is a newsletter that writes itself every other morning. A Python pipeline ingests the last 48 hours — RSS first (reliable dates, canonical links), Firecrawl for what RSS can't reach — computes honest aggregates from what it gathered (funding rounds, topic momentum, source mix), and weaves everything into one 500-700 word story-like digest in the voice of Acquired meets All In, with inline links for everything it references. The charts are computed from the same items you're reading about: every number traces to a gathered story. The React frontend is the edition itself — the digest, the "By the numbers" strip, the full link list — plus a signup form and a personal source adder.

Every edition covers exactly the last 48 hours. Nothing older.

## The pipeline

```bash
.venv/bin/python -m services.user_sources scrape   # scrape pending user-added URLs
.venv/bin/python -m services.manual edition --hours 48
# scan (RSS + Firecrawl discovery) -> 48h filter -> curate -> enrich
#   -> digest (500-700 words, word-count guarded) -> charts -> email HTMLs
# writes data/newsletter.json + data/newsletter.md
#        data/charts.json + web/public/charts/<edition>/*.png
#        data/newsletter-email.html            (global)
#        data/emails/<subscriber-slug>.html    (per-user, with their sources)
```

- `services/rss.py` — the RSS backbone (primary ingestion): Hacker News, TechCrunch AI, The Verge, arXiv cs.AI + cs.CL, and the real podcast feeds (All In, Acquired, Invest Like the Best, Hard Fork, This Week in Startups). In-window filtering at the source; arXiv/HN pass relevance gates.
- `services/scanner.py` — Firecrawl for the two things RSS can't do: startup-news discovery (time-bounded search) and full-article text extraction for the top curated items, so digest gists come from the real article.
- `services/curator.py` — source reliability tiers (1: official/papers, 2: newsrooms, 3: blogs/wires) weight the relevance score; dedupe by normalized URL *and* title similarity; `filter_recent` prefers RSS pub dates; `extract_funding` pulls company + USD amount + round from raise announcements (both required — never invented).
- `services/writer.py` — the model is a stylist, never a researcher. One constrained OpenAI call writes the 500-700 word digest from deterministic gists (inline `[title](url)` links, every URL validated against the gathered set — invented links are rejected). Hard word-count guard in code: over 700 → one compression pass → still over → hard-truncate at a sentence boundary and mark it. Template fallback + circuit breaker when the API is unavailable.
- `services/compiler.py` — assembles the v4 edition: the digest, word count, and slim link shelves (no per-item briefings).
- `services/charts.py` — honest aggregates only (startup funding, topic momentum, source mix). Hard rules: no chart with fewer than 3 data points, no filler. Specs go to `data/charts.json`; matplotlib renders email-ready PNGs into `web/public/charts/<edition>/`.
- `services/chart_editor.py` — one constrained OpenAI call per edition: KEEP/REDESIGN/DROP per chart, insight-stating titles, right chart type. Never touches data; any failure keeps the computed charts.
- `services/user_sources.py` — the personal source adder, server-side. Scrapes `pending` docs in the Firestore `user_sources` collection with Firecrawl (`/v2/scrape` + json format: title, summary, bullets), flips each to `scraped` (or `failed` — never faked). Pending docs are never re-scraped. Also renders the per-user email HTML files.
- `services/emailer.py` — renders `data/newsletter-email.html` (global: digest + charts + link list) and, per subscriber, `data/emails/<slug>.html` (global digest + a "From your sources" section with ONLY that subscriber's scraped URLs). Table-based, inline CSS, light theme, absolute URLs, hosted chart images. Footer: reply to unsubscribe (manual handling).
- `services/subscribers.py` — fetches the Firestore `subscribers` collection for the scheduled send.
- `VOICE.md` — the editorial voice, researched from Acquired and All In.

## The app

`web/` is a Vite + React + TypeScript reader in light, minimal editorial style: the digest (safe markdown rendering), the "By the numbers" chart strip (inline SVG), the full link list, the email signup form (name + email → Firestore `subscribers`), and the source adder ("Add a source": URL + email → Firestore `user_sources`; the visitor sees their own URLs with scrape status; the email is pre-filled from localStorage and becomes their identity — no auth yet).

## Privacy notes

- A user-added URL is scraped and used **only for that user**. It never enters the global edition, the charts, or anyone else's email. Per-user scoping is enforced in `services/user_sources.py` and `services/emailer.py` (there is a test asserting user A's URL never appears in user B's email).
- Tradeoff (documented, accepted): the `user_sources` Firestore collection allows **public reads** so visitors can see the status of their own submissions without auth. That means submitted URLs — and the submitter emails on those docs — are listable by anyone. If this ever matters, the fix is Firebase Auth + per-user read rules; the pipeline already keys everything by email so the migration is small.
- `subscribers` remains create-only from clients (no reads/updates/deletes).

## Email: how the scheduled send works

Every other morning at 08:00 ET a scheduled job runs:

1. **Scrape user URLs** — `.venv/bin/python -m services.user_sources scrape` in the repo root. Scrapes every `pending` doc in `user_sources` (title + summary + bullets via Firecrawl), flips to `scraped`/`failed`.
2. **Build** — `.venv/bin/python -m services.manual edition --hours 48`. Scans, curates, enriches, writes the 500-700 word digest, computes charts, renders `data/newsletter-email.html`, drops chart PNGs into `web/public/charts/<edition>/`, and renders per-user emails into `data/emails/<slug>.html`. It also prints `email<TAB>path` lines for the next step.
3. **Deploy** — `cd web && npm run build && firebase deploy --only hosting --project portfolio-3da31` (firebase CLI). The PNGs must be live at `https://aadit-field-manual.web.app/charts/<edition>/*.png` *before* sending, since the emails reference them by URL.
4. **Send** — for each subscriber: the HTML at `data/emails/<slug>.html` goes out via Gmail (one email per subscriber, since content is personalized), subject `The Field Manual — <edition date>`. The subscriber list comes from `.venv/bin/python -m services.subscribers --emails`. Unsubscribes are handled by reply ("Reply to this email to unsubscribe" is in the footer).

Firestore rules (`firestore.rules`, deployed) allow public `create` on `subscribers` (name/email validation) and on `user_sources` (email/URL validation, status must be `pending`), public `read` on `user_sources` only, and deny everything else.

## Deploy

Static hosting. `npm run build` in `web/` stages `data/newsletter.json` (+ `charts.json` when present) into the bundle, then `vite build`; deploy `web/dist` to Firebase Hosting (site `aadit-field-manual`, project `portfolio-3da31`).

## Tests

- `.venv/bin/python -m pytest tests/ -q` — pipeline (RSS parsing, 48h filter, tiers, title dedupe, funding extraction, chart aggregates, digest word-count guard, link validation, user-source scoping, email HTML, CLI)
- `cd web && npm test` — frontend (digest schema, safe markdown renderer, charts contract, signup + source-adder validation)
