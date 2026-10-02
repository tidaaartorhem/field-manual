# Field Manual — a living curriculum for Agentic AI

Keeping up with agentic AI is a firehose: papers drop daily, frameworks launch weekly, every vendor claims the future. A firehose doesn't teach you anything. A field manual does.

Field Manual is a self-updating reading manual. A Python pipeline scans the web (via Firecrawl) for the latest on agentic AI — papers, certifications and courses, framework news, and resume-adjacent topics like forward-deployed engineering — then curates, scores, and rewrites everything into narrative briefings with a point of view. The React frontend is the manual itself, plus a reflection studio: journal per item, argue with socratic prompts, keep a reading streak.

Every edition is regenerated from fresh scans. The manual you read today is not the manual from last week.

## The pipeline

```
python -m services.manual scan   # Firecrawl scans -> data/raw.json
python -m services.manual build  # curate -> write -> compile -> data/manual.json + data/manual.md
```

- `services/scanner.py` — curated Firecrawl query sets across four shelves
- `services/curator.py` — URL dedupe, relevance scoring, ranking
- `services/writer.py` — narrative briefings (lede / what happened / why it matters / steal this)
- `services/compiler.py` — assembles the edition: TOC, start-here path, stats

## The app

`web/` is a Vite + React + TypeScript reader: the manual, item briefings with source links, and a reflection studio (journaling, socratic Q&A with self-scoring, reading streak) persisted to localStorage.

## Deploy

Static hosting. `npm run build` in `web/`, deploy `web/dist` to Firebase Hosting.

## Tests

- `python -m pytest tests/ -q` — pipeline
- `cd web && npm test` — frontend
