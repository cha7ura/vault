# Core Frontend Pages Design

**Date:** 2026-03-07
**Status:** Approved

---

## Context

Vault has 53 episodes in Supabase with transcripts and segments, but the frontend is minimal — no search, sort, filtering, or proper episode detail pages. The goal is to build 3 production-quality pages modeled after mfmvault.com, while leaving placeholders for future LLM-generated content.

### Current State
- 53 episodes processed, segments with word-level timestamps and speaker diarization
- Guests table exists but is empty
- Episode metadata (description, thumbnail_url, published_at) is NULL — only title and duration populated
- Existing pages are basic server-rendered grids with no interactivity
- Episode URLs use UUID (`/doac/episodes/94bc3b0d-...`)

---

## Decision: YouTube Video ID as URL Slug

**Why YouTube ID over UUID:**
- Shorter, shareable URLs: `/doac/episodes/ajgwabD4_HE`
- Cross-referenceable with YouTube
- Already unique-indexed in the database
- No schema changes needed — UUID stays as primary key, routing queries by `youtube_id`

**Implementation:** Change `getEpisode(id)` from `.eq('id', id)` to `.eq('youtube_id', id)`. Update `EpisodeCard` href to use `youtube_id` instead of `id`.

---

## Page 1: Episodes List (`/[channel]/episodes`)

### Layout
- **Grid/List toggle** — grid (3-column cards) is default, list (compact rows) is alternative
- Toggle state persisted in URL search params or localStorage

### Search
- Client-side title search with debounced input
- Simple `includes()` filter — sufficient for <200 episodes

### Sort
- Dropdown with options: "Newest first" (default), "Oldest first", "Longest", "Shortest"

### Filters
- **Date range** — month/year selector for filtering by air date range
- **Guest filter** — disabled dropdown with "Coming soon" label (guests table empty)

### Episode Cards
- YouTube thumbnail (use `https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg` as fallback when `thumbnail_url` is NULL)
- Title (2-line clamp)
- Air date (relative time or formatted date)
- Duration badge overlay on thumbnail

### Data Strategy
- Server-side fetch all episodes, pass to client component
- All search/sort/filter happens client-side (dataset is small)

---

## Page 2: People (`/[channel]/people`)

### Current Implementation
- Shell page with "Coming soon" state
- Placeholder card grid showing the future layout
- Route: `/[channel]/people` (new, replaces `/[channel]/guests`)

### Future Layout (when guest data exists)
- Card grid with: name, photo, tagline, episode count
- Click through to person detail page showing episodes they appeared in

---

## Page 3: Episode Detail (`/[channel]/episodes/[youtube_id]`)

### Header
- Title
- Date, duration, guest name (when available)
- YouTube external link

### Main Content (left, 2/3 width)
- YouTube iframe embed with JS API enabled for click-to-seek
- YouTube description (when populated)
- Transcript viewer with speaker labels and click-to-seek (already built)

### Sidebar (right, 1/3 width)
- Greyed-out placeholder sections with "Coming soon" labels:
  - Summary
  - Key Insights
  - Books Mentioned
- These activate when LLM extraction populates the data

---

## Future Tasks (not part of this implementation)

### Near-term
1. **Colab metadata extraction** — update `upsert_episode` to pull `description`, `thumbnail_url`, `published_at` from yt-dlp
2. **Backfill metadata** — one-time script to fetch metadata for existing 53 episodes
3. **Guest hydration** — extract guest names from episode titles via LLM, populate guests table

### Medium-term
4. **LLM insight extraction** — generate summary, key insights, books, frameworks per episode
5. **Meilisearch integration** — full-text search across transcripts (self-hosted, no free cloud tier)
6. **pgvector RAG** — semantic search via embeddings (already enabled in migration 001)

### Long-term
7. **Graphiti + FalkorDB** — knowledge graph for guest relationships, topic extraction
8. **OpenSearch** — evaluate vs pgvector for RAG at scale

---

## Tech Stack

- **Framework:** Next.js 15 (App Router, async params)
- **Styling:** Tailwind CSS + shadcn/ui components
- **Data:** Supabase Postgres via `@supabase/supabase-js`
- **Icons:** Lucide React
- **Date formatting:** date-fns

---

## Sources

- [MFM Vault — Episodes](https://www.mfmvault.com/episode)
- [MFM Vault — People](https://www.mfmvault.com/people)
- [MFM Vault — Episode Detail](https://www.mfmvault.com/episode/XwVUuE9qc2U)
