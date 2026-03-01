# Diarization Comparison Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dashboard that plays a YouTube episode with two diarizer transcripts side-by-side, auto-scrolling both to the current playback position so the user can compare PyAnnote vs whisper-diarization output.

**Architecture:** Backend: add `diarizer` column to segments model, update API to filter by diarizer, add benchmarks endpoint. Frontend: fresh Next.js 15 app in `dashboard/` with a `/compare/[episodeId]` page containing a YouTube player and two synchronized transcript panels.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (backend changes); Next.js 15, React 19, TailwindCSS, shadcn/ui, react-youtube (frontend)

---

## Task 1: Add `diarizer` Column to Segments Model

**Files:**
- Modify: `pipeline/models/segment.py`
- Modify: `pipeline/api/diarization.py`
- Modify: `pipeline/tests/test_diarization_api.py`

**Step 1: Write failing test for diarizer-scoped storage**

Add this test to `pipeline/tests/test_diarization_api.py` after the existing test:

```python
def test_store_segments_per_diarizer(db):
    """Storing for one diarizer must not delete the other's segments."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="xyz789", title="Test", status="diarizing")
    db.add(episode)
    db.commit()

    from pipeline.core.diarizer_pyannote import TranscriptSegment, DiarizedTranscript
    from pipeline.api.diarization import store_diarization_result

    pyannote_transcript = DiarizedTranscript(
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Hello", speaker="Speaker 0")],
        speakers=["Speaker 0"],
        full_text="Hello",
    )
    store_diarization_result(db, episode.id, pyannote_transcript, diarizer="pyannote")

    whisper_transcript = DiarizedTranscript(
        segments=[TranscriptSegment(start=0.0, end=4.8, text="Hello there", speaker="Speaker 0")],
        speakers=["Speaker 0"],
        full_text="Hello there",
    )
    store_diarization_result(db, episode.id, whisper_transcript, diarizer="whisper-diarization")

    all_segments = db.query(Segment).filter(Segment.episode_id == episode.id).all()
    assert len(all_segments) == 2

    pyannote_segs = [s for s in all_segments if s.diarizer == "pyannote"]
    whisper_segs = [s for s in all_segments if s.diarizer == "whisper-diarization"]
    assert len(pyannote_segs) == 1
    assert len(whisper_segs) == 1
    assert pyannote_segs[0].text == "Hello"
    assert whisper_segs[0].text == "Hello there"
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py -v`
Expected: FAIL — `TypeError` (unexpected keyword argument `diarizer`)

**Step 3: Add diarizer column to Segment model**

Modify `pipeline/models/segment.py` — add this line after the `confidence` field:

```python
    diarizer: Mapped[str] = mapped_column(String(100), default="pyannote")
```

**Step 4: Update store_diarization_result to accept diarizer param**

Modify `pipeline/api/diarization.py` — change the function signature and delete logic:

```python
def store_diarization_result(
    db: Session,
    episode_id: int,
    transcript: DiarizedTranscript,
    intro_end_at: float = 0.0,
    diarizer: str = "pyannote",
) -> list[Segment]:
    """Store diarization segments in the database."""
    # Only delete segments for this specific diarizer
    db.query(Segment).filter(
        Segment.episode_id == episode_id,
        Segment.diarizer == diarizer,
    ).delete()

    segments = []
    for seg in transcript.segments:
        tag = "intro" if seg.start < intro_end_at else "content"
        db_seg = Segment(
            episode_id=episode_id,
            start_time=seg.start,
            end_time=seg.end,
            text=seg.text,
            speaker=seg.speaker,
            tag=tag,
            diarizer=diarizer,
        )
        db.add(db_seg)
        segments.append(db_seg)

    db.commit()
    return segments
```

**Step 5: Add diarizer to SegmentResponse and filter endpoint**

In `pipeline/api/diarization.py`, update `SegmentResponse`:

```python
class SegmentResponse(BaseModel):
    id: int
    start_time: float
    end_time: float
    text: str
    speaker: str | None
    tag: str
    diarizer: str

    model_config = {"from_attributes": True}
```

Update the `get_segments` endpoint to accept an optional `diarizer` query param:

```python
@router.get("/segments", response_model=list[SegmentResponse])
def get_segments(
    episode_id: int,
    diarizer: str | None = None,
    db: Session = Depends(get_db),
):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    query = db.query(Segment).filter(Segment.episode_id == episode_id)
    if diarizer:
        query = query.filter(Segment.diarizer == diarizer)
    return query.order_by(Segment.start_time).all()
```

**Step 6: Run tests to verify they pass**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py -v`
Expected: 2 tests PASS

**Step 7: Run all tests**

Run: `cd pipeline && uv run pytest -v -m "not integration"`
Expected: 25 passed (24 existing + 1 new)

**Step 8: Commit**

```bash
git add pipeline/models/segment.py pipeline/api/diarization.py pipeline/tests/test_diarization_api.py
git commit -m "feat(pipeline): add diarizer column to segments — scoped storage and filtered retrieval"
```

---

## Task 2: Add Benchmarks API Endpoint

**Files:**
- Modify: `pipeline/api/diarization.py`
- Modify: `pipeline/tests/test_diarization_api.py`

**Step 1: Write failing test**

Add to `pipeline/tests/test_diarization_api.py`:

```python
from pipeline.models import Benchmark


def test_get_benchmarks(db):
    """Verify benchmarks endpoint returns diarizer run metadata."""
    channel = Channel(name="DOAC", slug="doac", youtube_id="@DOAC")
    db.add(channel)
    db.commit()
    episode = Episode(channel_id=channel.id, youtube_id="bench1", title="Test", status="done")
    db.add(episode)
    db.commit()

    db.add(Benchmark(episode_id=episode.id, diarizer="pyannote", duration_s=12.3))
    db.add(Benchmark(episode_id=episode.id, diarizer="whisper-diarization", duration_s=45.1))
    db.commit()

    from pipeline.api.diarization import get_benchmarks_for_episode
    results = get_benchmarks_for_episode(db, episode.id)
    assert len(results) == 2
    assert results[0].diarizer == "pyannote"
    assert results[1].diarizer == "whisper-diarization"
```

**Step 2: Run test to verify it fails**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py::test_get_benchmarks -v`
Expected: FAIL — `ImportError`

**Step 3: Implement benchmarks endpoint**

Add to `pipeline/api/diarization.py`:

```python
from pipeline.models import Episode, Segment, Benchmark


class BenchmarkResponse(BaseModel):
    id: int
    diarizer: str
    duration_s: float | None
    wer: float | None
    der: float | None
    notes: str | None
    created_at: str | None

    model_config = {"from_attributes": True}


def get_benchmarks_for_episode(db: Session, episode_id: int) -> list[Benchmark]:
    return db.query(Benchmark).filter(
        Benchmark.episode_id == episode_id
    ).order_by(Benchmark.created_at).all()


@router.get("/benchmarks", response_model=list[BenchmarkResponse])
def get_benchmarks(episode_id: int, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(404, "Episode not found")
    return get_benchmarks_for_episode(db, episode_id)
```

Note: The `created_at` field in `BenchmarkResponse` is `str | None` to avoid datetime serialization issues. FastAPI auto-converts datetime to ISO string.

**Step 4: Run tests**

Run: `cd pipeline && uv run pytest tests/test_diarization_api.py -v`
Expected: 3 tests PASS

**Step 5: Run all tests**

Run: `cd pipeline && uv run pytest -v -m "not integration"`
Expected: 26 passed

**Step 6: Commit**

```bash
git add pipeline/api/diarization.py pipeline/tests/test_diarization_api.py
git commit -m "feat(pipeline): add benchmarks API endpoint for diarizer comparison metadata"
```

---

## Task 3: Scaffold Next.js Dashboard App

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/next.config.ts`
- Create: `dashboard/tailwind.config.ts`
- Create: `dashboard/postcss.config.mjs`
- Create: `dashboard/app/layout.tsx`
- Create: `dashboard/app/globals.css`
- Create: `dashboard/app/page.tsx`
- Create: `dashboard/lib/utils.ts`
- Create: `dashboard/components/ui/card.tsx`
- Modify: `Makefile`

**Step 1: Create package.json**

```json
{
  "name": "vault-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --turbopack --port 3000",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "^15.3.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-youtube": "^10.1.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.0.0",
    "lucide-react": "^0.511.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "typescript": "^5.7.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0"
  }
}
```

**Step 2: Create next.config.ts**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8001/api/:path*",
      },
    ];
  },
};

export default nextConfig;
```

This proxies `/api/*` requests to the FastAPI backend so we avoid CORS issues.

**Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

**Step 4: Create postcss.config.mjs**

```javascript
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

**Step 5: Create app/globals.css**

```css
@import "tailwindcss";

:root {
  --background: 0 0% 100%;
  --foreground: 0 0% 3.9%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 3.9%;
  --primary: 0 0% 9%;
  --primary-foreground: 0 0% 98%;
  --secondary: 0 0% 96.1%;
  --secondary-foreground: 0 0% 9%;
  --muted: 0 0% 96.1%;
  --muted-foreground: 0 0% 45.1%;
  --accent: 0 0% 96.1%;
  --accent-foreground: 0 0% 9%;
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 0 0% 98%;
  --border: 0 0% 89.8%;
  --ring: 0 0% 3.9%;
  --radius: 0.5rem;
}

.dark {
  --background: 0 0% 3.9%;
  --foreground: 0 0% 98%;
  --card: 0 0% 3.9%;
  --card-foreground: 0 0% 98%;
  --primary: 0 0% 98%;
  --primary-foreground: 0 0% 9%;
  --secondary: 0 0% 14.9%;
  --secondary-foreground: 0 0% 98%;
  --muted: 0 0% 14.9%;
  --muted-foreground: 0 0% 63.9%;
  --accent: 0 0% 14.9%;
  --accent-foreground: 0 0% 98%;
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 0 0% 98%;
  --border: 0 0% 14.9%;
  --ring: 0 0% 83.1%;
}

@theme inline {
  --color-background: hsl(var(--background));
  --color-foreground: hsl(var(--foreground));
  --color-card: hsl(var(--card));
  --color-card-foreground: hsl(var(--card-foreground));
  --color-primary: hsl(var(--primary));
  --color-primary-foreground: hsl(var(--primary-foreground));
  --color-secondary: hsl(var(--secondary));
  --color-secondary-foreground: hsl(var(--secondary-foreground));
  --color-muted: hsl(var(--muted));
  --color-muted-foreground: hsl(var(--muted-foreground));
  --color-accent: hsl(var(--accent));
  --color-accent-foreground: hsl(var(--accent-foreground));
  --color-destructive: hsl(var(--destructive));
  --color-destructive-foreground: hsl(var(--destructive-foreground));
  --color-border: hsl(var(--border));
  --color-ring: hsl(var(--ring));
  --radius: 0.5rem;
}

body {
  background: hsl(var(--background));
  color: hsl(var(--foreground));
  font-family: system-ui, sans-serif;
}
```

**Step 6: Create lib/utils.ts**

```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
```

**Step 7: Create app/layout.tsx**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vault Dashboard",
  description: "Diarization comparison and pipeline monitoring",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">{children}</body>
    </html>
  );
}
```

**Step 8: Create app/page.tsx (landing page)**

```tsx
import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Vault Dashboard</h1>
      <p className="text-muted-foreground mb-8">Diarization comparison and pipeline monitoring</p>
      <p className="text-sm text-muted-foreground">
        Navigate to <code className="bg-muted px-2 py-1 rounded">/compare/[episodeId]</code> to compare diarizers
      </p>
    </main>
  );
}
```

**Step 9: Update Makefile**

Add dashboard targets to the existing `Makefile` at the project root:

```makefile
.PHONY: setup dev test dashboard-setup dashboard

setup:
	cd pipeline && uv venv && uv pip install -e ".[dev]"

dev:
	cd pipeline && uv run uvicorn pipeline.main:app --reload --port 8001

test:
	cd pipeline && uv run pytest -v

dashboard-setup:
	cd dashboard && npm install

dashboard:
	cd dashboard && npm run dev
```

**Step 10: Install dependencies and verify**

Run: `cd dashboard && npm install`
Run: `cd dashboard && npm run dev`
Open: `http://localhost:3000` — should see "Vault Dashboard" landing page.

**Step 11: Commit**

```bash
git add dashboard/ Makefile
git commit -m "feat(dashboard): scaffold Next.js 15 app with TailwindCSS and shadcn/ui config"
```

---

## Task 4: YouTube Player Component

**Files:**
- Create: `dashboard/components/youtube-player.tsx`

**Step 1: Create the component**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import YouTube, { YouTubeEvent, YouTubePlayer as YTPlayer } from "react-youtube";

interface YouTubePlayerProps {
  videoId: string;
  onTimeUpdate: (time: number) => void;
}

export function YouTubePlayer({ videoId, onTimeUpdate }: YouTubePlayerProps) {
  const playerRef = useRef<YTPlayer | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      if (playerRef.current) {
        const time = playerRef.current.getCurrentTime();
        if (typeof time === "number") {
          onTimeUpdate(time);
        }
      }
    }, 250);
  }, [onTimeUpdate]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const onReady = (event: YouTubeEvent) => {
    playerRef.current = event.target;
  };

  const onStateChange = (event: YouTubeEvent) => {
    // YT.PlayerState: PLAYING=1, PAUSED=2, ENDED=0
    if (event.data === 1) {
      setIsPlaying(true);
      startPolling();
    } else {
      setIsPlaying(false);
      stopPolling();
      // Send one last time update on pause
      if (playerRef.current) {
        onTimeUpdate(playerRef.current.getCurrentTime());
      }
    }
  };

  return (
    <div className="w-full aspect-video bg-black rounded-lg overflow-hidden">
      <YouTube
        videoId={videoId}
        opts={{
          width: "100%",
          height: "100%",
          playerVars: {
            autoplay: 0,
            modestbranding: 1,
            rel: 0,
          },
        }}
        onReady={onReady}
        onStateChange={onStateChange}
        className="w-full h-full"
        iframeClassName="w-full h-full"
      />
    </div>
  );
}

// Export a seekTo helper — parent stores this ref
export function useYouTubeSeek() {
  const playerRef = useRef<YTPlayer | null>(null);

  const seekTo = useCallback((seconds: number) => {
    if (playerRef.current) {
      playerRef.current.seekTo(seconds, true);
    }
  }, []);

  const setPlayer = useCallback((player: YTPlayer) => {
    playerRef.current = player;
  }, []);

  return { seekTo, setPlayer };
}
```

**Step 2: Verify it compiles**

Run: `cd dashboard && npx next build`
Expected: Build succeeds (the component isn't used on a page yet, but TypeScript should compile)

**Step 3: Commit**

```bash
git add dashboard/components/youtube-player.tsx
git commit -m "feat(dashboard): add YouTube player component with 250ms time polling"
```

---

## Task 5: Transcript Panel Component

**Files:**
- Create: `dashboard/components/transcript-panel.tsx`
- Create: `dashboard/lib/types.ts`

**Step 1: Create shared types**

```typescript
// dashboard/lib/types.ts
export interface Segment {
  id: number;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  tag: string;
  diarizer: string;
}

export interface BenchmarkData {
  id: number;
  diarizer: string;
  duration_s: number | null;
  wer: number | null;
  der: number | null;
  notes: string | null;
}

export interface Episode {
  id: number;
  youtube_id: string;
  title: string;
  status: string;
  duration: number | null;
  intro_end_at: number | null;
}

const SPEAKER_COLORS = [
  { bg: "bg-blue-50", border: "border-l-blue-500", text: "text-blue-700" },
  { bg: "bg-green-50", border: "border-l-green-500", text: "text-green-700" },
  { bg: "bg-amber-50", border: "border-l-amber-500", text: "text-amber-700" },
  { bg: "bg-purple-50", border: "border-l-purple-500", text: "text-purple-700" },
  { bg: "bg-rose-50", border: "border-l-rose-500", text: "text-rose-700" },
];

export function getSpeakerColor(speaker: string | null, speakers: string[]) {
  if (!speaker) return SPEAKER_COLORS[0];
  const idx = speakers.indexOf(speaker);
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
}
```

**Step 2: Create transcript panel**

```tsx
// dashboard/components/transcript-panel.tsx
"use client";

import { useEffect, useRef, useMemo } from "react";
import { formatTime } from "@/lib/utils";
import type { Segment, BenchmarkData } from "@/lib/types";
import { getSpeakerColor } from "@/lib/types";

interface TranscriptPanelProps {
  title: string;
  segments: Segment[];
  currentTime: number;
  benchmark: BenchmarkData | null;
  onSeek: (seconds: number) => void;
}

export function TranscriptPanel({
  title,
  segments,
  currentTime,
  benchmark,
  onSeek,
}: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  const speakers = useMemo(() => {
    const seen = new Set<string>();
    for (const seg of segments) {
      if (seg.speaker) seen.add(seg.speaker);
    }
    return Array.from(seen);
  }, [segments]);

  const activeIndex = useMemo(() => {
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i].start_time <= currentTime) {
        return i;
      }
    }
    return -1;
  }, [segments, currentTime]);

  // Auto-scroll to active segment
  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeIndex]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
        <div>
          <h3 className="font-semibold text-sm">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {speakers.length} speaker{speakers.length !== 1 ? "s" : ""}
            {" · "}
            {segments.length} segments
          </p>
        </div>
        {benchmark && benchmark.duration_s && (
          <span className="text-xs text-muted-foreground">
            ⏱ {benchmark.duration_s.toFixed(1)}s
          </span>
        )}
      </div>

      {/* Segments */}
      <div ref={containerRef} className="flex-1 overflow-y-auto">
        {segments.map((seg, i) => {
          const isActive = i === activeIndex;
          const color = getSpeakerColor(seg.speaker, speakers);
          const isMuted = seg.tag === "intro" || seg.tag === "ad" || seg.tag === "subscribe";

          return (
            <div
              key={seg.id}
              ref={isActive ? activeRef : undefined}
              onClick={() => onSeek(seg.start_time)}
              className={`
                px-4 py-2 border-l-4 cursor-pointer transition-colors
                ${isActive ? `${color.bg} ${color.border}` : `border-l-transparent hover:bg-muted/30`}
                ${isMuted ? "opacity-50" : ""}
              `}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`text-xs font-medium ${isActive ? color.text : "text-muted-foreground"}`}>
                  {seg.speaker ?? "Unknown"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatTime(seg.start_time)}
                </span>
                {isMuted && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground uppercase">
                    {seg.tag}
                  </span>
                )}
              </div>
              <p className={`text-sm leading-relaxed ${isActive ? "text-foreground" : "text-foreground/80"}`}>
                {seg.text}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 3: Verify it compiles**

Run: `cd dashboard && npx next build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add dashboard/lib/types.ts dashboard/components/transcript-panel.tsx
git commit -m "feat(dashboard): add transcript panel with speaker colors and auto-scroll"
```

---

## Task 6: Comparison Page

**Files:**
- Create: `dashboard/app/compare/[episodeId]/page.tsx`
- Create: `dashboard/lib/api.ts`

**Step 1: Create API client**

```typescript
// dashboard/lib/api.ts
import type { Episode, Segment, BenchmarkData } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchEpisode(id: number): Promise<Episode> {
  const res = await fetch(`${API}/api/episodes/${id}`);
  if (!res.ok) throw new Error(`Episode ${id} not found`);
  return res.json();
}

export async function fetchSegments(
  episodeId: number,
  diarizer: string
): Promise<Segment[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/segments?diarizer=${diarizer}`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function fetchBenchmarks(
  episodeId: number
): Promise<BenchmarkData[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/benchmarks`
  );
  if (!res.ok) return [];
  return res.json();
}
```

**Step 2: Create comparison page**

```tsx
// dashboard/app/compare/[episodeId]/page.tsx
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { use } from "react";
import YouTube, { YouTubeEvent } from "react-youtube";
import { TranscriptPanel } from "@/components/transcript-panel";
import { formatTime } from "@/lib/utils";
import { fetchEpisode, fetchSegments, fetchBenchmarks } from "@/lib/api";
import type { Episode, Segment, BenchmarkData } from "@/lib/types";

export default function ComparePage({
  params,
}: {
  params: Promise<{ episodeId: string }>;
}) {
  const { episodeId } = use(params);
  const id = parseInt(episodeId, 10);

  const [episode, setEpisode] = useState<Episode | null>(null);
  const [pyannoteSegments, setPyannoteSegments] = useState<Segment[]>([]);
  const [whisperSegments, setWhisperSegments] = useState<Segment[]>([]);
  const [benchmarks, setBenchmarks] = useState<BenchmarkData[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const playerRef = useRef<any>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch data
  useEffect(() => {
    async function load() {
      try {
        const [ep, pySegs, wdSegs, bm] = await Promise.all([
          fetchEpisode(id),
          fetchSegments(id, "pyannote"),
          fetchSegments(id, "whisper-diarization"),
          fetchBenchmarks(id),
        ]);
        setEpisode(ep);
        setPyannoteSegments(pySegs);
        setWhisperSegments(wdSegs);
        setBenchmarks(bm);
      } catch (e: any) {
        setError(e.message);
      }
    }
    load();
  }, [id]);

  // YouTube polling
  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      if (playerRef.current) {
        const t = playerRef.current.getCurrentTime();
        if (typeof t === "number") setCurrentTime(t);
      }
    }, 250);
  }, []);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const onReady = (e: YouTubeEvent) => {
    playerRef.current = e.target;
  };

  const onStateChange = (e: YouTubeEvent) => {
    if (e.data === 1) startPolling();
    else {
      stopPolling();
      if (playerRef.current) setCurrentTime(playerRef.current.getCurrentTime());
    }
  };

  const seekTo = useCallback((seconds: number) => {
    if (playerRef.current) {
      playerRef.current.seekTo(seconds, true);
      setCurrentTime(seconds);
    }
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const pyBenchmark = benchmarks.find((b) => b.diarizer === "pyannote") ?? null;
  const wdBenchmark = benchmarks.find((b) => b.diarizer === "whisper-diarization") ?? null;

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3 border-b">
        <h1 className="font-semibold truncate flex-1">{episode.title}</h1>
        <span className="text-sm text-muted-foreground">
          {formatTime(currentTime)}
          {episode.duration ? ` / ${formatTime(episode.duration)}` : ""}
        </span>
      </header>

      {/* YouTube Player */}
      <div className="w-full max-w-4xl mx-auto px-4 pt-4">
        <div className="aspect-video bg-black rounded-lg overflow-hidden">
          <YouTube
            videoId={episode.youtube_id}
            opts={{
              width: "100%",
              height: "100%",
              playerVars: { autoplay: 0, modestbranding: 1, rel: 0 },
            }}
            onReady={onReady}
            onStateChange={onStateChange}
            className="w-full h-full"
            iframeClassName="w-full h-full"
          />
        </div>
      </div>

      {/* Transcript Panels */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-0 border-t mt-4 min-h-0">
        <div className="border-r min-h-0 flex flex-col">
          <TranscriptPanel
            title="PyAnnote"
            segments={pyannoteSegments}
            currentTime={currentTime}
            benchmark={pyBenchmark}
            onSeek={seekTo}
          />
        </div>
        <div className="min-h-0 flex flex-col">
          <TranscriptPanel
            title="whisper-diarization"
            segments={whisperSegments}
            currentTime={currentTime}
            benchmark={wdBenchmark}
            onSeek={seekTo}
          />
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Verify it compiles and renders**

Run: `cd dashboard && npm run dev`
Open: `http://localhost:3000/compare/1` (will show loading state or error since no data yet)
Verify: No build errors, page renders.

**Step 4: Commit**

```bash
git add dashboard/lib/api.ts dashboard/app/compare/
git commit -m "feat(dashboard): add comparison page — YouTube player + dual transcript panels with sync"
```

---

## Task 7: Update CORS and End-to-End Test

**Files:**
- Modify: `pipeline/main.py` (update CORS to allow dashboard port)

**Step 1: Verify CORS allows dashboard**

The existing CORS in `pipeline/main.py` allows `http://localhost:3000`. The Next.js `rewrites` in `next.config.ts` proxies API calls through Next.js, so CORS isn't strictly needed. But to support direct browser API calls (React DevTools, etc.), confirm the origin is correct.

Current code already has:
```python
allow_origins=["http://localhost:3000"],
```

This is correct. No change needed.

**Step 2: Manual end-to-end test**

Start both servers:
- Terminal 1: `make dev` (FastAPI on 8001)
- Terminal 2: `make dashboard` (Next.js on 3000)

If you have an episode with ID 1 in the database with segments:
- Open `http://localhost:3000/compare/1`
- Verify: YouTube player loads, transcript panels show segments
- Play video: transcripts auto-scroll
- Click a segment: video seeks to that time

If no data exists yet, seed test data using the API:
```bash
# Create channel
curl -X POST http://localhost:8001/api/channels \
  -H "Content-Type: application/json" \
  -d '{"name":"DOAC","slug":"doac","youtube_id":"@StevenBartlett"}'

# Ingest episode
curl -X POST http://localhost:8001/api/episodes/ingest \
  -H "Content-Type: application/json" \
  -d '{"channel_slug":"doac","youtube_url":"https://www.youtube.com/watch?v=jDG1m_b5Ih0"}'
```

Then run the benchmark script (when complete) to store segments.

**Step 3: Commit if any changes were made**

```bash
git add -A
git commit -m "chore(dashboard): verify end-to-end connectivity between dashboard and pipeline API"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | `diarizer` column on segments, scoped storage | 1 new test |
| 2 | Benchmarks API endpoint | 1 new test |
| 3 | Next.js dashboard scaffold | Manual (npm run dev) |
| 4 | YouTube player component with time polling | Manual (build check) |
| 5 | Transcript panel with speaker colors + auto-scroll | Manual (build check) |
| 6 | Comparison page at /compare/[episodeId] | Manual (end-to-end) |
| 7 | CORS check + end-to-end verification | Manual |

**Total: 7 tasks, 2 new backend tests, ~10 new files**

After completing all tasks you'll have:
- Backend supports storing segments per diarizer and serving them filtered
- A working dashboard with YouTube player + dual transcript panels
- Auto-scrolling transcripts synced to video playback
- Click-to-seek on any segment
- Speaker-colored segments with intro/ad tag badges
