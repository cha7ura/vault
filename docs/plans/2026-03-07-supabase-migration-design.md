# Supabase Migration Design

**Date:** 2026-03-07
**Status:** Approved

---

## Context

Vault currently uses a local SQLite database with 1 episode imported (942 segments). 7 episodes have been fully processed via Colab but exist only as JSON exports. The project is transitioning from local-first to cloud-hosted, with the goal of going public.

### Current State
- SQLite DB: 1 episode, 942 segments
- JSON exports: 12 episodes (7 complete with 9,313 segments, 5 failed)
- Colab notebook: processes videos, saves JSON files, requires manual import
- Existing Supabase migrations (001-003): episodes, guests, insights, books, papers, pgvector, multi-tenancy

### Problem
- Colab produces JSON files that must be manually downloaded and imported
- SQLite is not accessible from Colab or a deployed frontend
- No way to avoid re-processing already-completed episodes

---

## Decision: Supabase Postgres

**Why Supabase over alternatives:**
- Already have 3 migrations written (pgvector, multi-tenancy, semantic search)
- 500MB free tier sufficient for ~200 episodes
- supabase-py SDK for Colab integration
- pgvector for future RAG, built-in full-text search
- REST API for Next.js frontend (deployable to Vercel)

**Free tier limits:**
- 500MB database storage (read-only mode when exceeded)
- 1GB file storage
- 2 projects, projects pause after 1 week of inactivity
- Pro plan ($25/mo) gives 8GB if needed

**Alternatives considered:**
- Cloudflare D1: 500MB per DB (not 5GB). HTTP-only access, no standard DB driver from Colab
- Neon Postgres: 512MB free. No extras (auth, storage, realtime)

---

## Schema Changes

### New Migration: 004_add_segments.sql

The existing Supabase schema stores transcripts as TEXT on episodes. The pipeline produces word-level segments with speaker labels, timestamps, and confidence scores. These power the dashboard's karaoke highlighting and click-to-seek features.

```sql
CREATE TABLE segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  text TEXT NOT NULL,
  speaker VARCHAR(100),
  tag VARCHAR(50) DEFAULT 'content',
  confidence FLOAT,
  diarizer VARCHAR(100) NOT NULL DEFAULT 'whisper-diarization',
  words JSONB,
  youtube_text TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_segments_episode ON segments(episode_id);
CREATE INDEX idx_segments_speaker ON segments(speaker);
CREATE INDEX idx_segments_time ON segments(episode_id, start_time);
```

### Storage Estimate
- ~1,300 segments per episode, ~2KB each (with words JSONB)
- ~2.6MB per episode
- ~200 episodes before hitting 500MB free tier

---

## Colab Ingestion: Continuous Loop

The Colab notebook becomes a self-driving ingestion loop:

```
while True:
    videos = fetch_video_list()           # from YouTube channel API or hardcoded list
    processed = get_processed_ids()       # query Supabase for status='complete'
    pending = [v for v in videos if v not in processed]

    if not pending:
        print("All caught up. Sleeping...")
        sleep(300)
        continue

    for video in pending:
        process(video)                    # whisper + NeMo MSDD
        upsert_episode(video)             # supabase-py
        batch_insert_segments(video)      # supabase-py
        mark_complete(video)              # update status

    # Loop back to recheck — new videos may have appeared
```

Key behaviors:
- Checks Supabase for already-processed episodes (avoids re-work)
- Processes one video at a time, inserts directly into Supabase
- Marks episodes complete after successful insert
- Loops indefinitely, sleeping when caught up
- Can be left running on Colab with GPU runtime
- Resilient to interrupts (skips completed episodes on restart)

Connection: `supabase-py` SDK with URL + service_role key stored as Colab secrets.

---

## Migration Path

1. Run migration 004 on Supabase (add segments table)
2. One-time data migration: load existing JSON exports into Supabase
3. Update Colab notebook to continuous loop with direct Supabase inserts
4. Update Next.js frontend to read from Supabase instead of local SQLite API
5. Keep local SQLite as development backup (no longer source of truth)

---

## Future (Deferred)

These are noted for architectural awareness but not part of this plan:

- **Meilisearch**: No free cloud tier ($30/mo). Start with Postgres full-text search (tsvector). Add Meilisearch later for typo-tolerant instant search if needed. Self-hosting is free.
- **Graphiti + FalkorDB**: Knowledge graph for guest relationships, topic extraction. Does NOT require Neo4j — FalkorDB is the default backend and is open-source. Phase 5+.
- **pgvector RAG**: Already enabled in migration 001. Semantic search functions already written. Ready to use when embedding generation is implemented.
- **OpenSearch**: Alternative to pgvector for RAG. Evaluate when the time comes — pgvector may be sufficient.

---

## Sources

- [Cloudflare D1 Pricing](https://developers.cloudflare.com/d1/platform/pricing/)
- [Supabase Pricing](https://supabase.com/pricing)
- [Meilisearch Pricing](https://www.meilisearch.com/pricing)
- [Graphiti + FalkorDB](https://github.com/getzep/graphiti/blob/main/mcp_server/README.md)
