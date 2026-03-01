# Vault — Local-First YouTube Podcast Knowledge Extraction

**Date:** 2026-03-01
**Status:** Approved

## Overview

A local-first platform for extracting structured knowledge (frameworks, quotes, stories, insights) from YouTube podcast episodes. Supports multiple channels (DOAC, MFM, etc.). All processing runs locally — no cloud APIs for transcription, diarization, or LLM inference.

Inspired by [MFM Vault](https://www.mfmvault.com/). Primary target: Diary of a CEO (DOAC) YouTube channel.

## Architecture

**Two services:**
- **Python FastAPI backend** — handles the ML pipeline (download, preprocess, diarize, extract) + REST API
- **Next.js dashboard** — monitoring, diarization review, and the public vault UI

**Database:** SQLite (single file, zero setup)
**LLM:** LM Studio (local, OpenAI-compatible API at localhost:1234)

### System Flow

```
YouTube URL/Channel
       |
       v
[1. Download]    yt-dlp → audio WAV + metadata → SQLite
       |
       v
[2. Preprocess]  ffmpeg → 16kHz mono + intro boundary detection
       |
       v
[3. Diarize]     Whisper STT + speaker diarization → word-level segments
       |
       v
[4. Review]      Dashboard: edit speakers, adjust tags, compare diarizers
       |
       v
[5. Extract]     LM Studio → frameworks, quotes, stories, books, etc.
       |
       v
[6. Publish]     FastAPI endpoints → Next.js vault UI
```

Every stage writes output to SQLite + filesystem. Any stage can be re-run independently.

## Key Design Decisions

### Full Audio Preserved
The preprocessor detects intro boundaries but does NOT cut the audio. The full transcript (including intro) is stored with word-level timestamps. Intro/ad/content segments are tagged, not removed.

### Dual Diarizer Benchmarking
Both approaches run during the benchmarking phase:
1. **whisper-diarization** — Whisper + NeMo VAD + TitaNet + CTC forced alignment + Demucs vocal separation (BSD-2)
2. **Whisper + PyAnnote** — Whisper STT + PyAnnote speaker-diarization-3.1 (MIT lib, gated model weights)

Dashboard shows side-by-side comparison. After benchmarking, the better performer becomes the default.

### DOAC-Specific Handling
DOAC episodes have: intro montage with guest clips + music → subscribe prompt → ad reads → interview. The preprocessor auto-detects the intro end via energy analysis. User can adjust in dashboard before diarization.

### Clickable Transcript
Word-level timestamps from CTC forced alignment enable clickable transcript where each word/sentence links to `youtube.com/watch?v={id}&t={seconds}`.

### Configurable LLM
Different model sizes for different tasks via LM Studio:
- Smaller models (8B) for title generation, guest extraction
- Larger models (14B+) for insight extraction, framework content

## Database Schema

```sql
channels (
  id, name, slug, youtube_id, intro_skip, config, created_at
)

episodes (
  id, channel_id, youtube_id, title, description, duration,
  published_at, thumbnail_url, audio_path, intro_end_at,
  status, created_at
)
-- status: pending → downloading → preprocessing → diarizing →
--         reviewing → extracting → done | error

segments (
  id, episode_id, start_time, end_time, text, speaker,
  tag, confidence, created_at
)
-- tag: intro | ad | subscribe | content

insights (
  id, episode_id, type, title, content, start_time, end_time,
  speaker, metadata, created_at
)
-- type: framework | quote | story | business_idea | opinion |
--       product | book

guests (id, name, slug, bio, role, company, links, created_at)

episode_guests (episode_id, guest_id)

jobs (
  id, episode_id, stage, status, progress, error, config,
  started_at, completed_at, created_at
)

benchmarks (
  id, episode_id, diarizer, config, wer, der, duration_s,
  output_path, notes, created_at
)
```

## Project Structure

```
vault/
├── pipeline/                        # Python backend (FastAPI)
│   ├── pyproject.toml
│   ├── main.py                     # FastAPI app entry point
│   ├── config.py                   # Settings
│   ├── db.py                       # SQLite + SQLAlchemy
│   ├── models/                     # ORM models
│   │   ├── channel.py
│   │   ├── episode.py
│   │   ├── segment.py
│   │   ├── insight.py
│   │   ├── guest.py
│   │   ├── job.py
│   │   └── benchmark.py
│   ├── core/                       # Pipeline stages
│   │   ├── downloader.py           # yt-dlp
│   │   ├── preprocessor.py         # ffmpeg + intro detection
│   │   ├── diarizer_whisper.py     # whisper-diarization
│   │   ├── diarizer_pyannote.py    # PyAnnote
│   │   ├── extractor.py            # LLM insight extraction
│   │   ├── llm_client.py           # LM Studio client
│   │   └── prompts/                # Prompt templates
│   ├── api/                        # FastAPI routes
│   │   ├── channels.py
│   │   ├── episodes.py
│   │   ├── jobs.py
│   │   ├── search.py
│   │   └── diarization.py
│   ├── workers/
│   │   └── pipeline_worker.py      # Async orchestration
│   └── tests/
├── dashboard/                       # Next.js frontend
│   ├── app/
│   │   ├── page.tsx                # Dashboard home
│   │   ├── channels/               # Channel management
│   │   ├── episodes/[id]/          # Episode detail (MFM Vault-style)
│   │   │   ├── page.tsx
│   │   │   ├── review/page.tsx     # Diarization review
│   │   │   └── benchmark/page.tsx  # Diarizer comparison
│   │   ├── pipeline/page.tsx       # Job queue + progress
│   │   └── settings/page.tsx       # LM Studio config
│   ├── components/
│   │   ├── transcript-viewer.tsx   # Clickable word-level transcript
│   │   ├── waveform-viewer.tsx     # Speaker-colored waveform
│   │   ├── job-status.tsx
│   │   ├── insight-card.tsx
│   │   └── speaker-editor.tsx
│   └── lib/
│       └── api.ts                  # FastAPI client
├── data/                           # Local storage (gitignored)
│   ├── audio/{channel_slug}/{youtube_id}.wav
│   ├── transcripts/
│   └── vault.db
├── Makefile
└── README.md
```

## Tech Stack

| Component | Technology | License |
|-----------|-----------|---------|
| Pipeline | Python 3.11+, FastAPI, SQLAlchemy | MIT |
| STT | OpenAI Whisper / faster-whisper | MIT |
| Diarization A | whisper-diarization (NeMo + Demucs) | BSD-2 |
| Diarization B | PyAnnote speaker-diarization-3.1 | MIT (lib), gated (model) |
| Audio | ffmpeg, yt-dlp, librosa | LGPL, Unlicense, ISC |
| LLM | LM Studio (OpenAI-compatible) | Proprietary (free) |
| Database | SQLite | Public domain |
| Dashboard | Next.js 15, TailwindCSS, shadcn/ui | MIT |

## API Endpoints

```
GET  /api/channels                  # List channels
GET  /api/channels/{slug}           # Channel details
GET  /api/channels/{slug}/episodes  # Channel episodes
GET  /api/episodes/{id}             # Episode + transcript + insights
GET  /api/episodes/{id}/transcript  # Segments with timestamps
GET  /api/episodes/{id}/insights    # Insights by type
GET  /api/guests                    # All guests
GET  /api/guests/{slug}             # Guest with episodes
GET  /api/search?q=...              # Full-text search
GET  /api/jobs                      # Pipeline job status
POST /api/channels                  # Add channel
POST /api/episodes/ingest           # Trigger ingestion
POST /api/episodes/{id}/diarize     # Re-run diarization
POST /api/episodes/{id}/extract     # Re-run extraction
```

## Extraction Prompts

Adapted from MFM Vault (leverage.to) for DOAC:

1. **Insight Extraction** — Extract frameworks, quotes, stories, opinions, business ideas, products, books from transcript chunks
2. **Title Generation** — Short, specific, active-voice titles for each insight
3. **Timestamp Extraction** — Map insights to start/end timestamps in transcript
4. **Framework Content** — Expand frameworks into structured markdown with bullet points

DOAC-specific additions to prompts:
- "The host is Steven Bartlett"
- "Ignore intro montage clips, sponsor reads, and subscribe prompts (tagged as intro/ad/subscribe)"
- "Focus on actionable advice, mental models, and personal stories"

## Implementation Priority

1. **Phase 1: Pipeline Core** — Download + preprocess + diarize (both approaches) + SQLite storage
2. **Phase 2: Dashboard MVP** — Job monitoring + diarization review/editor + diarizer benchmarking
3. **Phase 3: Extraction** — LLM insight extraction via LM Studio + prompt engineering
4. **Phase 4: Vault UI** — Episode page (MFM Vault-style), clickable transcript, insight browsing
5. **Phase 5: Polish** — Search, guest profiles, multi-channel support, batch processing
