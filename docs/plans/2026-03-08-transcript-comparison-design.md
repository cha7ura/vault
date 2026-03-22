# Transcript Comparison Debug Tool — Design

**Date**: 2026-03-08
**Status**: Approved

## Purpose

Compare our Whisper+NeMo generated transcript against YouTube's auto-generated captions to identify gaps, missed words, and low-confidence regions. Provides a dev-only debug tab on the episode page with side-by-side comparison and word-level confidence visualization.

## Decisions

| Decision | Choice |
|----------|--------|
| YT captions source | Pre-stored via batch script |
| Storage | New `yt_segments` table |
| Visualization | Side-by-side (left: ours, right: YT) |
| Confidence display | Word-level heat coloring with threshold |
| Threshold control | Per-session slider in debug tab (default 0.85) |
| Diff algorithm | Word-level LCS, no external library |
| Debug tab visibility | Dev-only (`NODE_ENV === 'development'`) |
| Tab UI | Simple button toggle, no dependency |

## Data Layer

### New table: `yt_segments`

```sql
CREATE TABLE yt_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  position INT NOT NULL,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  text TEXT NOT NULL,
  words JSONB,  -- [{text, start, end}] from YT captions
  created_at TIMESTAMP DEFAULT NOW()
);
```

No `speaker` column — YouTube captions lack speaker diarization. This is itself a comparison point (our pipeline adds speaker labels).

Segmentation strategy: Use our existing segments' `start_time`/`end_time` boundaries to slice YT caption words into matching time windows, giving 1:1 segment alignment.

### API Route

`app/api/episodes/[id]/yt-segments/route.ts` — GET endpoint returning `yt_segments` for an episode.

## Ingestion Script

`scripts/fetch_yt_captions.py`:

- Uses `yt-dlp --write-auto-sub --sub-lang en --sub-format json3 --skip-download`
- JSON3 format provides word-level timestamps: `{utf8, tStartMs, dDurMs}`
- Reads our `segments` table for episode time boundaries
- Slices YT caption words into matching time windows by word start time
- Inserts into `yt_segments` with matching `position` values
- Supports `--youtube-id <id>` (single) or `--all` (batch for episodes missing YT captions)
- Uses `.env.local` for Supabase keys
- Skips episodes already fetched unless `--force` flag
- Logs warning and skips videos with no auto-captions

## Frontend

### Tab Bar

Below the video player: **"Transcript"** (default) | **"Compare (Dev)"**

Compare tab only renders when `process.env.NODE_ENV === 'development'`. Simple button toggle, no Radix dependency.

### Compare Tab Layout

```
┌─────────────────────────┬─────────────────────────┐
│  Our Transcript         │  YouTube Captions       │
│  Speaker 0 | 0:00      │  0:00                   │
│  "The ███ key thing..." │  "The key thing..."     │
└─────────────────────────┴─────────────────────────┘
         ┌──────────────────────┐
         │ Confidence: ──●───── │  0.85
         └──────────────────────┘
```

- Left: Whisper+NeMo transcript with speaker labels
- Right: YT captions aligned to same time windows (no speakers)
- Diff: Words only in one side get red/orange tint; matches stay neutral
- Confidence slider: 0.0–1.0 (default 0.85), words below threshold get orange/red heat coloring
- Synchronized scrolling between columns
- Click-to-seek on both columns

### Diff Algorithm

Word-level longest-common-subsequence (~30 lines). No external library needed — segments are typically 10–50 words.

## Files to Create/Modify

| File | Action |
|------|--------|
| `supabase/migrations/005_add_yt_segments.sql` | Create — new table |
| `scripts/fetch_yt_captions.py` | Create — ingestion script |
| `app/api/episodes/[id]/yt-segments/route.ts` | Create — API route |
| `lib/diff.ts` | Create — word-level LCS utility |
| `components/transcript-compare.tsx` | Create — side-by-side comparison |
| `components/transcript-viewer.tsx` | Modify — add confidence heat coloring |
| `app/[channel]/episodes/[id]/page.tsx` | Modify — add tab bar, debug tab |

## Not Building

- No external diff libraries
- No Radix tabs dependency
- No production-facing comparison UI
