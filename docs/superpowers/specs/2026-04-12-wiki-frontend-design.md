# Wiki Front End + Data Refresh Design

**Date:** 2026-04-12
**Status:** approved (pending spec review)
**Author:** Claude (session with d821)

## Goal

Build an Obsidian-like front end over the existing Karpathy-style wiki
(`vault/wiki/`) so the user can browse the knowledge graph produced by the
24-episode pipeline run: global force graph, per-entity local graph, detail
pages for people/concepts/orgs/etc., and clickable episode summaries.

Before the front end is usable, refresh wiki data for the 24 episodes so the
pages reflect the four quality fixes landed this session (stage0 search
context, stage3 episode-meta block, canonical timestamps, slug drift
collapse).

Non-goals: concept co-occurrence analytics, timeline scrubber, per-episode
filter, person affiliation network. These are deferred post-MVP.

## Part 1 — Data refresh

### Scope

Only the 24 episodes touched by the current batch. Entity pages not
referenced by any of those episodes stay put.

### Steps

1. **Collect touched slugs.** For each of the 24 `youtube_id`s in the batch,
   read the existing `_episodes/<yid>.md` and walk every wikilink
   (`[[<type>/<slug>]]`) in the body. Build a set
   `{(type, slug)}` of pages those episodes currently reference.
2. **Wipe.** Delete `wiki/_episodes/<yid>.md` for all 24 episodes, plus every
   `wiki/<type>/<slug>.md` in the touched set — except the seeds:
   `wiki/people/steven-bartlett.md`, `wiki/podcasts/diary-of-a-ceo.md`. Delete
   `wiki/podcasts/unnamed-podcast.md` unconditionally (it is the orphan the
   fixes target).
3. **Rebuild index.** Remove any lines in `wiki/_index.md` pointing at
   deleted pages. The extract step will append new lines as it writes.
4. **Reset DB checkpoints.** For the 24 episodes:
   ```sql
   UPDATE episodes
      SET wiki_processed_at = NULL,
          persona_enriched_at = NULL
    WHERE youtube_id IN (...);
   ```
5. **Re-run pipeline.**
   ```
   python -m scripts.agents.run_pipeline --stage extract --start 6 --limit 24
   python -m scripts.agents.run_pipeline --stage enrich  --start 6 --limit 24
   ```
6. **Sanity check.** Grep for `unnamed-podcast`, bare `\d+s` timestamps, and
   `not-in-the-high-street` drift. All must be zero.

### Why wipe touched pages, not merge

The quality fixes apply at write time. Merging onto stale pages leaves the
old wrong edges in place (fix #4's fuzzy slug lookup only collapses drift on
fresh write, not after the fact). Wiping ensures the final state matches the
fixed code.

### Risk

- Re-spend: ~$1.34 groq + openrouter (validated envelope from last run).
- Reversible via `git restore wiki/` if result regresses.

## Part 2 — MVP feature set

Five features. Anything else is post-MVP.

1. **Global force graph** (`/graph`) — every wiki entity as a node, every
   edge in its body as a link, colored by entity type. Click node to
   navigate. This is the Obsidian parity feature.
2. **Local graph** on each entity detail page — the 1-hop neighborhood of
   the current entity.
3. **Entity detail pages** (`/entity/[type]/[slug]`) — parsed front-matter,
   body, back-refs (who links here), sources, appearances, local graph.
4. **Episode detail pages** (`/episodes/[id]`) — the episode summary page
   with wikilinks rendered as clickable internal links.
5. **Cmd+K search** — fuzzy over `_index.md` titles + slugs, with type
   filter, navigates to detail page on enter.

## Part 3 — Architecture (Path A: files-as-truth)

### Why Path A

- Wiki files are already the canonical artifact of the pipeline.
- Zero DB schema work.
- Rebuild = rerun pipeline + restart Next. Matches Obsidian's mental model.
- Parser is the only new serialization boundary.

### Data flow

```
wiki/*.md   (files, written by pipeline)
    │
    ▼
lib/wiki.ts (parse yaml front-matter + body, extract wikilinks, cache in-memory)
    │
    ├─► /api/graph             → {nodes, links}
    ├─► /api/entities          → _index.md as JSON
    ├─► /api/entities/[t]/[s]  → one page as structured JSON
    └─► /api/episodes/[yid]    → one episode page as structured JSON
    │
    ▼
Next.js pages render
```

### New files

```
dashboard/
  lib/
    wiki.ts
  app/
    api/
      entities/route.ts
      entities/[type]/[slug]/route.ts
      graph/route.ts
      episodes/[youtubeId]/route.ts
    graph/
      page.tsx
    entity/[type]/[slug]/
      page.tsx
    episodes/[id]/
      page.tsx
```

### `lib/wiki.ts` responsibilities

- `parsePage(path: string) → WikiPage` — yaml front-matter + body, extracts
  all `[[type/slug]]` wikilinks from body, returns `{frontmatter, body,
  outlinks, type, slug, path}`.
- `loadAll() → Map<string, WikiPage>` — walks `wiki/`, parses every `.md`
  (skip `_index.md`), keyed by `"<type>/<slug>"`.
- `buildGraph(pages) → {nodes, links}` — projects pages into force-graph
  shape. Node: `{id, type, title, degree}`. Link: `{source, target, rel}`.
- `findBackrefs(target, pages) → WikiPage[]` — every page whose outlinks
  contain `target`.
- `parseIndex() → IndexEntry[]` — one entry per line of `_index.md`.

Cache: parsed pages held in a module-level `Map`, rebuilt on dev file
change (chokidar), frozen in prod. Exposed through a `getWiki()` accessor
so route handlers don't re-parse per request.

### `/graph` page

- `react-force-graph-2d` — lighter than 3d, better for labels, same API.
- Node color: person=blue, concept=green, org=orange, work=purple,
  podcast=red, place=gray, method=teal, product=yellow.
- Sidebar: type filter checkboxes + text search.
- Click node → `router.push("/entity/[type]/[slug]")`.

### Existing code to touch

- `app/[channel]/people/page.tsx` — currently reads `agent_memories` (0
  rows). Rewrite to use `lib/wiki.ts` + `wiki/people/`. Kills the
  pipeline→front-end disconnect.

### Config

- `lib/wiki.ts` reads `process.env.VAULT_WIKI_DIR` (default
  `../wiki` relative to `dashboard/`).
- `react-force-graph-2d` added to `dashboard/package.json`.

## Part 4 — Build order

Each step is a stop-and-review checkpoint:

1. `lib/wiki.ts` + unit tests against 2-3 sample pages.
2. `/api/graph` + `/api/entities` routes.
3. `/graph/page.tsx` MVP (the hero view — demo here).
4. `/entity/[type]/[slug]/page.tsx` (detail + local graph).
5. `/episodes/[id]/page.tsx`.
6. Cmd+K search overlay.
7. Rewrite `app/[channel]/people/page.tsx`.

Run the data refresh (Part 1) either before step 1 or in parallel with it —
the parser can be developed against the existing (dirty) pages, then the
graph demo hits the fresh ones.

## Testing

- `lib/wiki.ts`: vitest unit tests with fixture `.md` files checked into
  `dashboard/lib/__fixtures__/`.
- API routes: smoke test via `curl` against `next dev`.
- Pages: manual browser walkthrough — load `/graph`, click 5 random nodes,
  confirm navigation + back-refs + local graph.

## Open questions

None blocking. Deferred capabilities (timeline, co-occurrence, per-episode
filter) tracked separately if/when the MVP lands.
