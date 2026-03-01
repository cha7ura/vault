# Diarization Comparison Dashboard — Design

**Date:** 2026-03-01
**Status:** Approved

## Goal

A dashboard page that plays a YouTube episode with two diarization transcripts side-by-side (PyAnnote vs whisper-diarization). Video playback auto-scrolls both transcripts to the current timestamp, highlighting the active speaker segment. Clicking a segment seeks the video. Will be reused later for manual transcript editing.

## Architecture

**Fresh Next.js 15 app** in `dashboard/` with shadcn/ui and TailwindCSS. Fetches segment data from the FastAPI pipeline API at `localhost:8001`.

**Data model change:** Add `diarizer` column to `segments` table so both diarization results can be stored for the same episode. API filters segments by diarizer name.

## Layout

```
┌─────────────────────────────────────────────────┐
│  Episode Title + Channel                    [←] │
├─────────────────────────────────────────────────┤
│                                                 │
│            YouTube Player (16:9)                │
│            (iframe embed)                       │
│                                                 │
├────────────────────┬────────────────────────────┤
│  PyAnnote          │  whisper-diarization       │
│  ⏱ 12.3s          │  ⏱ 45.1s                  │
│  2 speakers        │  3 speakers                │
├────────────────────┼────────────────────────────┤
│                    │                            │
│ ▶ Speaker 0 [0:00] │ ▶ Speaker 0 [0:00]        │
│  "Hello world..."  │  "Hello world..."          │
│                    │                            │
│  Speaker 1 [0:05]  │  Speaker 1 [0:05]          │
│  "Welcome to..."   │  "Welcome to the..."       │
│                    │                            │
│ ▶ Speaker 0 [0:12] │ ▶ Speaker 0 [0:11]        │  ← highlighted
│  "Today we..."     │  "Today we talk..."        │
│                    │                            │
└────────────────────┴────────────────────────────┘
```

## Components

### YouTubePlayer
- Embeds YouTube IFrame API via `react-youtube`
- Exposes current playback time via `onStateChange` polling (250ms interval)
- Provides `seekTo(seconds)` for transcript click-to-seek

### TranscriptPanel
- Receives: segments array, current playback time, diarizer metadata
- Renders segments as a scrollable list with speaker labels and timestamps
- Active segment (where `start <= currentTime < end`) gets highlighted background + colored left border
- Auto-scrolls to keep active segment centered using `scrollIntoView({ behavior: 'smooth', block: 'center' })`
- Speaker colors: consistent per speaker (Speaker 0 = blue, Speaker 1 = green, Speaker 2 = amber, etc.)
- Intro/ad segments shown with muted styling and tag badge
- Click handler: calls `seekTo(segment.start_time)` on the YouTube player

### ComparisonPage
- Route: `/compare/[episodeId]`
- Fetches episode metadata + segments for both diarizers from API
- Manages shared playback time state between player and both panels
- Shows diarizer stats in panel headers (processing time, speaker count, segment count)

## Data Model

### segments table change

```sql
ALTER TABLE segments ADD COLUMN diarizer TEXT NOT NULL DEFAULT 'pyannote';
```

Values: `"pyannote"` | `"whisper-diarization"`

The `store_diarization_result` function gains a `diarizer` parameter. When storing, it only deletes existing segments for that specific diarizer (not all segments).

### API changes

```
GET /api/episodes/{id}/diarization/segments?diarizer=pyannote
GET /api/episodes/{id}/diarization/segments?diarizer=whisper-diarization
GET /api/episodes/{id}/diarization/segments  (returns all)
```

### New endpoint for benchmarks

```
GET /api/episodes/{id}/benchmarks
```

Returns benchmark metadata (processing times, speaker counts) for each diarizer run.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15, React 19 |
| Styling | TailwindCSS, shadcn/ui (new-york) |
| YouTube | react-youtube (IFrame API wrapper) |
| API Client | fetch with SWR or simple useEffect |
| Backend | FastAPI (existing, extended) |

## Key Behaviors

1. **Auto-scroll sync**: Both panels scroll independently to their own active segment at the current video time
2. **Click-to-seek**: Clicking any segment seeks video to that timestamp; both panels update
3. **Speaker colors**: Consistent within each panel (Speaker 0 always blue), independent between panels (they may have different speaker assignments)
4. **Intro tagging**: Segments tagged as "intro" shown with a muted badge, helping evaluate intro detection accuracy
5. **Responsive**: On narrow screens, panels stack vertically instead of side-by-side

## Future Extension (not in scope now)

- Manual speaker name editing (click speaker label to rename)
- Segment reassignment (drag to change speaker)
- "Choose winner" button to select preferred diarizer for this episode
- Re-run diarization with different settings
