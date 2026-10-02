# Field Manual — the last 48 hours, in one story

Keeping up with AI is a firehose: launches, raises, papers, and four podcasts all talking at once. A firehose doesn't teach you anything. A story does.

Field Manual is a newsletter that writes itself every other morning. A Python pipeline scans the web (via Firecrawl, time-bounded to the last 48 hours) for agentic AI trends, broader tech currents, what startups are saying and doing, and the latest episodes from the podcast circuit — then weaves it all into one story-like narrative in the voice of Acquired meets All In. The React frontend is the edition itself, plus Marginalia: pin notes to any section or story while you read, then write the three-question debrief.

Every edition covers exactly the last 48 hours. Nothing older.

## The pipeline

```bash
python -m services.manual edition --hours 48
# scan -> 48h filter -> curate -> write -> compile
# writes data/newsletter.json + data/newsletter.md
```

- `services/scanner.py` — news query sets (signal / tech / startups) via Firecrawl search with `tbs` recency bounds, plus the podcast circuit (latest episodes scraped for real show notes: All In, Acquired, Invest Like the Best, Hard Fork, This Week in Startups)
- `services/curator.py` — URL dedupe, relevance scoring, ranking, and `filter_recent`: drops anything provably older than the window
- `services/writer.py` — the model is a stylist, never a researcher: the pipeline supplies every fact deterministically; one constrained OpenAI call per item writes the briefing, one per section weaves the narrative, one writes the edition lede. Template fallback + circuit breaker when the API is unavailable
- `services/compiler.py` — assembles the edition: lede, sections with narratives and closing takes, Worth Your Time picks
- `VOICE.md` — the editorial voice, researched from Acquired and All In

## The app

`web/` is a Vite + React + TypeScript reader in light, minimal editorial style: the edition (lede, section narratives, story cards with expandable briefings) and Reflect (margin notes pinned to sections/stories + the three-question debrief), persisted to localStorage.

## Deploy

Static hosting. `npm run build` in `web/` stages `data/newsletter.json` into the bundle, then `vite build`; deploy `web/dist` to Firebase Hosting (site `aadit-field-manual`).

## Tests

- `python -m pytest tests/ -q` — pipeline (dedupe, 48h filter, writer fallback paths, newsletter compiler, CLI)
- `cd web && npm test` — frontend (newsletter schema, marginalia logic)
