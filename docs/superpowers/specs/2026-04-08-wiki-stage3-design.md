# Wiki-Based Stage 3 Design

**Date:** 2026-04-08
**Status:** Approved
**Replaces:** Graphiti-based Stage 3 extraction (2026-04-03-pipeline-design.md §Stage 3)
**Scope:** Stage 3 extraction only. Stages 1, 2, and the enrichment/persona steps are unchanged.

## Problem

The Graphiti-based Stage 3 is blocked by structured output compatibility issues between Graphiti's JSON schema injection and the local/OpenRouter LLM stack. Neo4j AuraDB adds cloud infrastructure dependency. Both are unblocked by switching to a flat markdown wiki approach inspired by Karpathy's LLM Knowledge Base pattern.

## Goal

Replace `graphiti.add_episode()` with a two-step extract-then-write pipeline that:
- Produces the same knowledge graph content (same ontology, same entity/edge types)
- Stores it as YAML-fronted markdown files instead of Neo4j nodes/edges
- Is viewable in Obsidian (graph view replaces Neo4j Bloom)
- Is parseable by a future frontend (YAML front matter → structured data)
- Uses Groq/OpenRouter for reliable structured JSON output

---

## Stack Changes

| Component | Before | After |
|---|---|---|
| LLM (extraction) | Local Ollama / OpenRouter | Groq `openai/gpt-oss-20b` (strict JSON) |
| LLM (summaries) | Local Ollama | OpenRouter `deepseek/deepseek-chat` |
| LLM (lint) | — | Groq `llama-3.1-8b-instant` |
| Knowledge store | Neo4j AuraDB + Graphiti | `wiki/` directory (markdown files) |
| Graph viewer | Neo4j Bloom | Obsidian graph view |
| Graph framework | `vendor/graphiti/` submodule | removed from stage 3 |

`vendor/graphiti/` stays in the repo but stage 3 stops importing it.

---

## Wiki Directory Structure

The `wiki/` directory at the project root is the Obsidian vault.

```
wiki/
  _index.md                    # LLM-maintained entity registry (dedup key)
  _episodes/
    {youtube_id}.md            # One summary page per episode
  people/
    {slug}.md
  concepts/
    {slug}.md
  works/
    {slug}.md                  # Books, papers, articles
  methods/
    {slug}.md                  # Protocols, frameworks, routines
  organizations/
    {slug}.md
  products/
    {slug}.md
  podcasts/
    {slug}.md                  # Podcast series (e.g. diary-of-a-ceo)
```

Entity types map directly from the approved ontology (2026-04-06-knowledge-graph-ontology-design.md). Events and Places rarely need standalone pages — they appear inline in entity pages.

---

## Entity Page Format

Every entity page uses the same structure: YAML front matter (machine-readable, the "graph"), then markdown body (human/LLM-readable, the "detail panel").

```markdown
---
type: person
name: Andrew Huberman
slug: andrew-huberman
aliases: [Dr. Huberman, Huberman]
expertise: Neuroscience
credentials: PhD, Stanford professor
role_context: Neuroscientist and podcast host
appearances:
  - youtube_id: abc123
    title: "The Science of Sleep"
    date: 2023-01-15
    timestamp: "14:23"
relationships:
  affiliated_with:
    - entity: "[[Stanford University]]"
      role: professor
  claims:
    - concept: "[[Dopamine]]"
      insight_type: claim
      episode: abc123
      timestamp: "14:23"
      youtube_url: "https://youtube.com/watch?v=abc123&t=863"
  recommends:
    - entity: "[[AG1]]"
      type: product
      strength: strong
      episode: abc123
      timestamp: "22:10"
observations:
  - episode: abc123
    timestamp: "31:12"
    text: "mentions investing in a company called 'Flow State Labs' — unclear if active or past"
  - episode: abc123
    timestamp: "44:05"
    text: "references a framework he calls 'the 3 pillars' — possible Method entity"
enriched: false
created_at: 2026-04-08
updated_at: 2026-04-08
---

## Summary
Andrew Huberman is a neuroscientist and tenured professor at Stanford School of Medicine...

## Appearances
- [[_episodes/abc123|The Science of Sleep]] (2023-01-15) — discussed dopamine, sleep protocols

## Notes
- Recommends [[products/ag1]] daily
- Describes [[methods/cold-exposure-protocol]] for mental resilience
```

**Front matter = graph.** YAML `relationships` = Neo4j edges. `[[wikilinks]]` = Obsidian graph view edges. Markdown body = Bloom node detail panel.

**`observations` field** captures anything the LLM noticed that doesn't fit the current ontology (unknown entities, unclear relationships, partial names). A lint pass promotes observations into proper typed fields or creates new entity pages. Data is never discarded.

---

## Episode Summary Page Format

```markdown
---
type: episode
youtube_id: abc123
title: "Andrew Huberman: The Science of Sleep and Dopamine"
date: 2023-01-15
guest: "[[people/andrew-huberman]]"
host: "[[people/steven-bartlett]]"
podcast: "[[podcasts/diary-of-a-ceo]]"
topics:
  - "[[concepts/dopamine]]"
  - "[[concepts/sleep]]"
  - "[[methods/cold-exposure-protocol]]"
works_referenced:
  - "[[works/why-we-sleep]]"
---

## Summary
Steven Bartlett interviews Andrew Huberman about the neurochemistry of sleep...

## Key Claims
- [[people/andrew-huberman]] explains that [[concepts/dopamine]] peaks in anticipation rather than reward ([14:23](https://youtube.com/watch?v=abc123&t=863))

## References
- [[works/why-we-sleep]] by Matthew Walker — cited in support of sleep debt claims
```

---

## Index File Format

`wiki/_index.md` is maintained by the pipeline after every write pass. The LLM reads this file with every chunk extraction call to check for existing entities before creating new ones.

```markdown
# Entity Index

| Name | Type | File | Aliases |
|---|---|---|---|
| Steven Bartlett | person | people/steven-bartlett | Steve Bartlett |
| Andrew Huberman | person | people/andrew-huberman | Dr. Huberman, Huberman |
| Diary of a CEO | podcast | podcasts/diary-of-a-ceo | DOAC |
| Dopamine | concept | concepts/dopamine | dopamine system |
| Stanford University | organization | organizations/stanford-university | Stanford |
```

---

## Updated Stage 3 Pipeline

Stages 1, 2, and enrichment (3f–3h) are unchanged. Only step 3c is replaced.

```
segments (Supabase, stage 1+2 output)
  → 3a. Triage          (unchanged — heuristic filler filter)
  → 3b. Chunk           (unchanged — 15-20min windows, 2min overlap)
  → 3c. Extract JSON    ← replaces graphiti.add_episode()
  → 3d. Write to wiki   ← new
  → 3e. Episode summary ← new
  → 3f. Show notes      (unchanged)
  → 3g. Checkpoint      (unchanged + new wiki_processed_at field)
```

### 3c — Extract JSON

One LLM call per chunk. Input: chunk transcript text + full `_index.md` content. Output: structured JSON using the approved ontology.

**Model:** Groq `openai/gpt-oss-20b` with strict JSON schema mode. Schema is derived from the Pydantic entity/edge models in the approved ontology spec. Strict mode guarantees zero parsing failures.

```json
{
  "entities": [
    {
      "type": "Person",
      "name": "Andrew Huberman",
      "slug": "andrew-huberman",
      "attributes": {
        "expertise": "Neuroscience",
        "credentials": "PhD, Stanford professor",
        "role_context": "Neuroscientist"
      }
    }
  ],
  "edges": [
    {
      "type": "Claims",
      "from_name": "Andrew Huberman",
      "from_type": "Person",
      "to_name": "Dopamine",
      "to_type": "Concept",
      "attributes": {
        "insight_type": "claim",
        "timestamp": "14:23",
        "youtube_url": "https://youtube.com/watch?v=abc123&t=863"
      },
      "episode": "abc123"
    }
  ],
  "observations": [
    {
      "entity_name": "Andrew Huberman",
      "episode": "abc123",
      "timestamp": "31:12",
      "text": "mentions investing in a company called Flow State Labs — unclear if active or past"
    }
  ]
}
```

Extraction prompt instructs: *"Check the index before naming an entity. Use the canonical name if the entity exists. If you see something interesting that doesn't fit the entity or edge types, add it to observations with episode and timestamp. Do not discard it."*

### 3d — Write to Wiki

Deterministic Python — no LLM calls. Operates on the JSON from 3c.

```
for each entity in JSON:
  1. look up name (and aliases) in _index.md
  2a. found → read existing .md file
              → merge new attributes into YAML front matter (skip if already present)
              → append new relationships (deduplicate by type+target+episode)
              → append new observations
              → update updated_at
  2b. not found → create wiki/{type_dir}/{slug}.md with front matter template
                 → append to _index.md

for each edge in JSON:
  → already handled as part of the source entity's relationships section
```

Merging is dict-based — read YAML, update keys, write back. No LLM involved.

### 3e — Episode Summary

One LLM call per episode, after all chunks have been written. Reads: episode title, guest name, date, and all entity pages that were touched during this episode's extraction.

**Model:** OpenRouter `deepseek/deepseek-chat` — best reasoning quality for synthesis, 164K context fits all touched entity pages.

Writes: `wiki/_episodes/{youtube_id}.md`

### Processing Order

Episodes are processed **oldest to newest** (`ORDER BY published_at ASC`). This ensures entity pages accumulate data chronologically — by the time a frequently-referenced guest appears in episode 200, their page is already rich from earlier appearances.

**Seed pass (before episode 1):**
Create `wiki/people/steven-bartlett.md` and `wiki/podcasts/diary-of-a-ceo.md` with known information. Add both to `_index.md`. This prevents Steven Bartlett from ever being created as a new entity.

**Checkpoint:** `episodes.wiki_processed_at` — set after 3e completes. Pipeline skips episodes where this is not null. The existing `knowledge_processed_at` (Graphiti) is left untouched for now.

---

## Deduplication

**Level 1 — Index lookup (every chunk, fast)**

The LLM receives `_index.md` with every extraction call and is instructed to match existing canonical names. The writer resolves entities by slug — never creates `people/huberman.md` if `people/andrew-huberman.md` exists.

**Level 2 — Lint pass (periodic, catches misses)**

`stage3_lint.py` runs after every ~50 episodes:

- Fuzzy-match page titles to find near-duplicates (e.g. "Steve Bartlett" vs "Steven Bartlett")
- Find entities referenced in edges but with no page → create stub pages
- Find observations that match existing entity names → promote to typed relationships
- Find episodes not referenced by any entity page → flag as unlinked
- Report gaps (entities with no relationships, concepts mentioned once)

Merging: transfer all relationships from duplicate page to canonical page → delete duplicate → update `_index.md` → update all wikilinks.

**Model for lint:** Groq `llama-3.1-8b-instant` — simple comparison and classification tasks.

---

## Obsidian Setup

Open Obsidian → File → Open Vault → select `wiki/`.

**What you get immediately:**
- **Graph view** — wikilinks render as edges. Clusters by entity type. Person nodes connect to their concepts, works, methods.
- **Backlinks panel** — open `concepts/dopamine.md`, see every person who claimed something about dopamine and every episode it appeared in.
- **Search** — full-text across all entity pages and episode summaries.

**Recommended plugin: Dataview.** Enables live queries over front matter fields:

````markdown
```dataview
TABLE appearances, expertise
FROM "people"
WHERE enriched = false
SORT updated_at DESC
```
````

This gives a live enrichment queue directly in Obsidian.

---

## Cost Estimate (484 Episodes)

| Step | Calls | Model | Est. Cost |
|---|---|---|---|
| Extract JSON (~7 chunks/ep) | ~3,400 | Groq `gpt-oss-20b` | ~$1.00 |
| Episode summaries | 484 | OpenRouter `deepseek/deepseek-chat` | ~$2.00 |
| Lint passes (~10 runs) | ~100 | Groq `llama-3.1-8b-instant` | <$0.10 |
| **Total** | | | **~$3–4** |

---

## Frontend Path

The wiki is the intermediate layer. Two options for frontend serving (decided later):

1. **Parse-on-build** — Next.js reads `wiki/**/*.md` files at build time, extracts YAML front matter, renders entity pages statically.
2. **Sync-to-Supabase** — A `wiki_sync.py` script reads front matter from all wiki pages and upserts into Supabase tables. Existing frontend API routes continue to work unchanged.

Option 2 is lower friction given the existing Supabase-backed frontend.

---

## Files Changed

```
scripts/agents/
  config.py              # Add GROQ_API_KEY, GROQ_BASE_URL, OPENROUTER_API_KEY,
                         # WIKI_DIR, WIKI_EXTRACT_MODEL, WIKI_SUMMARY_MODEL, WIKI_LINT_MODEL
  stage3_extract.py      # Replace ingest_episode() with extract_chunk_json() + merge_to_wiki()
                         # Add write_episode_summary()
  stage3_lint.py         # New: lint pass (fuzzy dedup, stub creation, observation promotion)
  run_pipeline.py        # Add seed pass before episode loop; use wiki_processed_at checkpoint

wiki/                    # New directory (Obsidian vault)
  _index.md
  _episodes/
  people/
  concepts/
  works/
  methods/
  organizations/
  products/
```

---

## What Is Removed

- All `graphiti_core` imports from `stage3_extract.py`
- Neo4j driver, connection config, AuraDB dependency
- `OpenAIEmbedder` (no embeddings needed)
- OpenRouter structured output workarounds

`vendor/graphiti/` submodule stays for now. The Pydantic entity/edge models in `podcast_vault/` continue to serve as the extraction schema reference.

---

## Sources

- [Karpathy LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595)
- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)
- [Groq Models & Pricing](https://groq.com/pricing)
- [OpenRouter Models](https://openrouter.ai/models)
- Approved ontology: `docs/superpowers/specs/2026-04-06-knowledge-graph-ontology-design.md`
