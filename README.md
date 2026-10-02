# Field Manual — the last 48 hours, in one story

Keeping up with AI is a firehose: launches, raises, papers, and five podcasts all talking at once. A firehose doesn't teach you anything. A story does — and a story with numbers is harder to fool.

Field Manual is a newsletter that writes itself every other morning. A Python pipeline ingests the last 48 hours — RSS first (reliable dates, canonical links), Firecrawl for what RSS can't reach — computes honest aggregates from what it gathered (funding rounds, topic momentum, source mix), and weaves everything into one story-like narrative in the voice of Acquired meets All In. The charts are computed from the same items you're reading about: every number traces to a gathered story. The React frontend is the edition itself — narrative, visualizations, stories — plus a signup form for the email edition.

Every edition covers exactly the last 48 hours. Nothing older.

## The pipeline

```bash
.venv/bin/python -m services.manual edition --hours 48
# scan (RSS + Firecrawl discovery) -> 48h filter -> curate -> enrich
#   -> compile -> charts -> email HTML
# writes data/newsletter.json + data/newsletter.md
#        data/charts.json + web/public/charts/<edition>/*.png
#        data/newsletter-email.html
```

- `services/rss.py` — the RSS backbone (primary ingestion): Hacker News, TechCrunch AI, The Verge, arXiv cs.AI + cs.CL, and the real podcast feeds (All In, Acquired, Invest Like the Best, Hard Fork, This Week in Startups). In-window filtering at the source; arXiv/HN pass relevance gates.
- `services/scanner.py` — Firecrawl for the two things RSS can't do: startup-news discovery (time-bounded search) and full-article text extraction for the top curated items, so briefings are written from the real article.
- `services/curator.py` — source reliability tiers (1: official/papers, 2: newsrooms, 3: blogs/wires) weight the relevance score; dedupe by normalized URL *and* title similarity; `filter_recent` prefers RSS pub dates; `extract_funding` pulls company + USD amount + round from raise announcements (both required — never invented).
- `services/writer.py` — the model is a stylist, never a researcher: the pipeline supplies every fact deterministically; one constrained OpenAI call per item writes the briefing, one per section weaves the narrative, one writes the edition lede. Template fallback + circuit breaker when the API is unavailable.
- `services/compiler.py` — assembles the edition: lede, sections with narratives and closing takes, Worth Your Time picks.
- `services/charts.py` — honest aggregates only (startup funding, topic momentum, source mix, section volume). A chart that can't be computed from the gathered items is omitted, not faked. Specs go to `data/charts.json`; matplotlib renders email-ready PNGs into `web/public/charts/<edition>/`.
- `services/emailer.py` — renders `data/newsletter-email.html`: table-based, inline CSS, light theme, absolute URLs, hosted chart images. Footer: reply to unsubscribe (manual handling).
- `services/subscribers.py` — fetches the Firestore `subscribers` collection for the scheduled send.
- `VOICE.md` — the editorial voice, researched from Acquired and All In.

## The app

`web/` is a Vite + React + TypeScript reader in light, minimal editorial style: the edition (lede, "By the numbers" chart strip rendered as inline SVG, section narratives, story cards with expandable briefings) and the email signup form (name + email → Firestore `subscribers`, client + server validation).

## Email: how the scheduled send works

Every other morning at 08:00 ET a scheduled job runs:

1. **Build** — `.venv/bin/python -m services.manual edition --hours 48` in the repo root. This scans, curates, writes briefings, computes charts, renders `data/newsletter-email.html`, and drops chart PNGs into `web/public/charts/<edition>/`.
2. **Deploy** — `cd web && npm run build && firebase deploy --only hosting --project portfolio-3da31` (firebase CLI). The PNGs must be live at `https://aadit-field-manual.web.app/charts/<edition>/*.png` *before* sending, since the email references them by URL.
3. **Subscribers** — `.venv/bin/python -m services.subscribers --emails` prints one email per line from the Firestore `subscribers` collection (project `portfolio-3da31`).
4. **Send** — the HTML at `data/newsletter-email.html` goes out via Gmail to the subscriber list (BCC), subject `The Field Manual — <edition date>`. Unsubscribes are handled by reply ("Reply to this email to unsubscribe" is in the footer).

Firestore rules (`firestore.rules`, deployed) allow public `create` on `subscribers` with name/email validation and deny all reads/updates/deletes.

## Deploy

Static hosting. `npm run build` in `web/` stages `data/newsletter.json` (+ `charts.json` when present) into the bundle, then `vite build`; deploy `web/dist` to Firebase Hosting (site `aadit-field-manual`, project `portfolio-3da31`).

## Tests

- `.venv/bin/python -m pytest tests/ -q` — pipeline (RSS parsing, 48h filter, tiers, title dedupe, funding extraction, chart aggregates, email HTML, CLI)
- `cd web && npm test` — frontend (newsletter schema, charts contract, signup validation)
