# data/manual.json — schema (contract between `services/` and `web/`)

```jsonc
{
  "edition": "2026-10-02",          // date the edition was compiled
  "generated_at": "2026-10-02T...", // ISO timestamp
  "shelves": [
    {
      "id": "papers",               // papers | courses | news | career
      "title": "Papers",
      "tagline": "One-line shelf description, storylike voice.",
      "items": [
        {
          "id": "papers-001",       // shelf + zero-padded index, unique
          "title": "Item title",
          "url": "https://...",    // REAL url from Firecrawl; never invented
          "source": "arXiv",        // publisher / outlet name
          "published": "2026-09-28",// ISO date or null when unknown
          "shelf": "papers",
          "score": 0.87,            // curator relevance score 0..1
          "briefing": {
            "lede": "1-2 sentence hook.",
            "what_happened": "2-4 sentence narrative of the thing itself.",
            "why_it_matters": "2-3 sentence opinionated take on significance.",
            "steal_this": "One concrete idea worth stealing."
          },
          "takeaways": ["short", "punchy", "takeaways"],
          "queries": ["firecrawl query that surfaced it"]  // provenance
        }
      ]
    }
  ],
  "start_here": ["papers-001", "news-003"],
  "stats": { "items": 32, "shelves": 4, "sources": 18 }
}
```

## Shelves
| id      | title                      | what belongs here                                  |
|---------|----------------------------|----------------------------------------------------|
| papers  | Papers                     | arXiv / research on agentic AI, LLM evals, RAG      |
| courses | Courses & Certifications   | agentic AI certs, AI engineering courses           |
| news    | News                       | agent frameworks, enterprise AI adoption           |
| career  | Resume-adjacent            | forward-deployed eng, solutions eng, LLM integration |

## Reflection studio (frontend-only, localStorage key `field-manual:v1`)
```jsonc
{
  "journal": { "<item-id>": [{"ts": 123, "text": "..."}] },
  "qa": { "<item-id>": [{"prompt": "...", "answer": "...", "score": 4, "ts": 123}] },
  "days": ["2026-10-02"]   // days with >=1 journal entry or answered prompt (streak)
}
```
Socratic prompt bank (rotate per item): "Explain this to a skeptic.", "Where would this break in production?", "What is the strongest counterargument?", "How would you apply this at work this week?", "What would you need to believe for this to be wrong?"
