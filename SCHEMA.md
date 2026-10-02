# data/newsletter.json — schema (contract between `services/` and `web/`)

```jsonc
{
  "edition": "2026-10-02",          // date the edition was compiled
  "window_hours": 48,              // recency window; nothing older
  "generated_at": "2026-10-02T...",// ISO timestamp
  "lede": "3-5 sentence story-like opening.",
  "sections": [
    {
      "id": "signal",              // signal | tech | startups | podcasts | worth
      "title": "The Signal",
      "kicker": "One-line section description.",
      "narrative": "4-7 sentence story weaving the items together.",
      "closing_take": "One sharp 'so what?' line.",
      "items": [
        {
          "id": "signal-001",      // section + zero-padded index, unique
          "title": "Item title",
          "url": "https://...",    // REAL url from Firecrawl; never invented
          "source": "Wired",       // publisher / outlet name
          "published": "2026-10-02", // ISO date or null when unknown
          "date_verified": true,   // false when no date was detectable
          "shelf": "signal",
          "score": 0.87,           // curator relevance score 0..1
          "briefing": {
            "lede": "1-2 sentence hook.",
            "what_happened": "2-4 sentence narrative of the thing itself.",
            "why_it_matters": "2-3 sentence opinionated take with the mechanism.",
            "steal_this": "One concrete idea worth stealing."
          },
          "takeaways": ["short", "punchy", "takeaways"],
          "queries": ["firecrawl query that surfaced it"]  // provenance
        }
      ]
    }
  ],
  "stats": { "items": 21, "sections": 5, "sources": 14 }
}
```

## Sections
| id       | title              | what belongs here                                              |
|----------|--------------------|----------------------------------------------------------------|
| signal   | The Signal         | agentic AI trends, last 48h                                    |
| tech     | The Wider Current  | broader tech news, through an AI builder's lens                 |
| startups | Startups           | launches, raises, pivots, hot takes                            |
| podcasts | The Podcast Circuit| latest episodes (real titles from scraped show notes)          |
| worth    | Worth Your Time    | the 3 highest-scored items across the edition                  |

## Marginalia (frontend-only, localStorage key `field-manual:v2`)
```jsonc
{
  "notes": {
    "2026-10-02": {
      "section:signal": [{"id": "n...", "ts": 123, "text": "..."}],
      "signal-001": [{"id": "n...", "ts": 123, "text": "..."}]
    }
  },
  "debriefs": {
    "2026-10-02": {
      "answers": {
        "changed-mind": "...",
        "will-try": "...",
        "still-skeptical": "..."
      },
      "ts": 123
    }
  }
}
```
