# data/newsletter.json — schema v4 (contract between `services/` and `web/`)

```jsonc
{
  "edition": "2026-10-02",          // date the edition was compiled
  "window_hours": 48,              // recency window; nothing older
  "generated_at": "2026-10-02T...",// ISO timestamp
  "digest": "500-700 word story-like markdown digest with inline [title](url) links.",
  "word_count": 642,               // len(digest.split()); hard-guarded <= 700
  "digest_truncated": false,       // true when the guard hard-truncated it
  "sections": [                    // slim link shelves (no per-item briefings)
    {
      "id": "signal",              // signal | tech | startups | podcasts
      "title": "The Signal",
      "kicker": "One-line section description.",
      "items": [
        {
          "id": "signal-001",      // section + zero-padded index, unique
          "title": "Item title",
          "url": "https://...",    // REAL url from the pipeline; never invented
          "source": "Wired",       // publisher / outlet name
          "published": "2026-10-02" // ISO date or null when unknown
        }
      ]
    }
  ],
  "stats": { "items": 21, "sections": 4, "sources": 14 }
}
```

Rules: the digest is the newsletter. Every markdown link in it must use an
exact URL from the edition's items (validated pipeline-side; invented links
are rejected). `word_count` is guarded to <= 700 in code (compression pass,
then sentence-boundary truncation marked in the text).

## Sections
| id       | title              | what belongs here                                              |
|----------|--------------------|----------------------------------------------------------------|
| signal   | The Signal         | agentic AI trends, last 48h                                    |
| tech     | The Wider Current  | broader tech news, through an AI builder's lens                 |
| startups | Startups           | launches, raises, pivots, hot takes                            |
| podcasts | The Podcast Circuit| latest episodes (real titles from RSS feeds)                   |

## data/charts.json — schema (contract between `services/charts.py` and `web/`)

Unchanged from v3:

```jsonc
{
  "edition": "2026-10-02",
  "charts": [
    {
      "id": "momentum",              // momentum | sources (+ funding when >= 3 raises)
      "title": "AI agents dominate the conversation",  // insight, not metric
      "subtitle": "Topic mentions across every story in this edition",
      "kind": "hbar",                // hbar | bar
      "unit": "mentions",            // unit of `value`
      "data": [
        {"label": "AI agents", "value": 12, "detail": "12 stories"}
      ],
      "note": "how this was computed (honesty footnote)"
    }
  ]
}
```

Rules: every `value` must trace to a gathered item. No chart with fewer
than 3 data points is emitted; a chart that can't be honestly computed is
omitted — never zero-filled or invented. The frontend renders each spec as
inline SVG; the pipeline also renders PNG twins into
`web/public/charts/<edition>/<id>.png` for the email edition, referenced at
`https://aadit-field-manual.web.app/charts/<edition>/<id>.png`.

## data/newsletter-email.html (global)

Email-safe single file: table-based layout, inline CSS only, no webfonts,
no flexbox/grid, no scripts, light theme, absolute URLs. Carries the digest
(safe markdown -> HTML), the "By the numbers" chart strip, and the full link
list. Footer carries the reply-to-unsubscribe line. Regenerated every
edition by `services/emailer.py`.

## data/emails/<subscriber-slug>.html (per-user)

Same as the global email, plus a "From your sources" section inserted after
the digest containing ONLY that subscriber's scraped `user_sources` URLs
(title + summary + bullets + link). Per-user scoping is enforced in
`services/user_sources.py` / `services/emailer.py`: a user's URL never
appears in another user's email or the global edition.

## Firestore: user_sources (personal source adder)

```jsonc
{
  "email": "ada@example.com",   // submitter; the identity key (no auth yet)
  "url": "https://...",         // submitted URL
  "title": "",                  // filled by the pipeline after scraping
  "summary": "",                // 2-3 sentences, Firecrawl-extracted
  "bullets": ["..."],           // up to 3 key bullets
  "status": "pending",          // pending -> scraped | failed (pipeline only)
  "addedAt": "<timestamp>",
  "scrapedAt": "<timestamp>",   // set on success
  "error": ""                   // set on failure
}
```

Rules (`firestore.rules`): public `create` (email/URL validation, status
must be `pending`); public `read` (so visitors see their own submission
status without auth — tradeoff documented in README "Privacy notes"); no
client update/delete. The pipeline reads/writes server-side via the
Firestore REST API.
