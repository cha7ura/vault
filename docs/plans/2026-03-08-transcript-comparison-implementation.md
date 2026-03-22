# Transcript Comparison Debug Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dev-only debug tab on the episode page that shows our Whisper+NeMo transcript side-by-side with YouTube's auto-captions, with word-level diff highlighting and a confidence threshold slider.

**Architecture:** Python script fetches YT captions via `yt-dlp`, slices them to match our segment boundaries, stores in a `yt_segments` table. A Next.js API route serves this data. A React client component renders the side-by-side comparison with word-level LCS diff and confidence heat coloring.

**Tech Stack:** Python (yt-dlp, supabase-py, dotenv), Next.js 15 API routes, React client components, Tailwind CSS, Supabase/PostgreSQL

---

### Task 1: Database Migration — `yt_segments` Table

**Files:**
- Create: `supabase/migrations/005_add_yt_segments.sql`

**Step 1: Write the migration**

```sql
CREATE TABLE yt_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  position INT NOT NULL,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  text TEXT NOT NULL,
  words JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_yt_segments_episode ON yt_segments(episode_id);
CREATE INDEX idx_yt_segments_position ON yt_segments(episode_id, position);
```

**Step 2: Apply migration to Supabase**

Run the SQL in Supabase dashboard or via CLI.

**Step 3: Commit**

```bash
git add supabase/migrations/005_add_yt_segments.sql
git commit -m "feat: add yt_segments table for YouTube caption comparison"
```

---

### Task 2: YT Captions Fetch Script

**Files:**
- Create: `scripts/fetch_yt_captions.py`

**Context:** Follow the same patterns as `scripts/hydrate_episodes.py` — uses `dotenv`, `supabase-py`, `yt-dlp` subprocess calls, and `.env.local` for credentials.

**Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Fetch YouTube auto-generated captions and store in yt_segments table,
aligned to our existing segment time boundaries.

Usage:
    python scripts/fetch_yt_captions.py                    # all episodes missing YT captions
    python scripts/fetch_yt_captions.py --youtube-id ABC   # single episode
    python scripts/fetch_yt_captions.py --force             # re-fetch all
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env.local")

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_yt_captions(video_id: str) -> list[dict] | None:
    """Fetch YouTube auto-captions in JSON3 format, return word events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "json3",
                "--skip-download",
                "--no-warnings",
                "-o", f"{tmpdir}/%(id)s.%(ext)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"    yt-dlp error: {result.stderr[:200]}")
            return None

        # Find the .json3 file
        json3_files = list(Path(tmpdir).glob("*.json3"))
        if not json3_files:
            print(f"    No auto-captions available")
            return None

        with open(json3_files[0]) as f:
            data = json.load(f)

        # Extract word events from json3 format
        words = []
        for event in data.get("events", []):
            t_start_ms = event.get("tStartMs", 0)
            for seg in event.get("segs", []):
                utf8 = seg.get("utf8", "").strip()
                if not utf8 or utf8 == "\n":
                    continue
                offset_ms = seg.get("tOffsetMs", 0)
                start_s = (t_start_ms + offset_ms) / 1000.0
                # Duration not always available; estimate from next word
                words.append({
                    "text": utf8,
                    "start": round(start_s, 3),
                })

        # Estimate end times from next word's start
        for i in range(len(words) - 1):
            words[i]["end"] = words[i + 1]["start"]
        if words:
            words[-1]["end"] = words[-1]["start"] + 0.5

        return words


def slice_words_to_segments(yt_words: list[dict], segments: list[dict]) -> list[dict]:
    """Slice YT caption words into our segment time boundaries."""
    yt_segments = []
    wi = 0  # word index

    for seg in segments:
        seg_start = seg["start_time"]
        seg_end = seg["end_time"]
        seg_words = []

        # Advance past words before this segment
        while wi < len(yt_words) and yt_words[wi]["start"] < seg_start:
            # Include words that are close to segment start (within 0.5s)
            if yt_words[wi]["start"] >= seg_start - 0.5:
                seg_words.append(yt_words[wi])
            wi += 1

        # Collect words within this segment
        while wi < len(yt_words) and yt_words[wi]["start"] < seg_end:
            seg_words.append(yt_words[wi])
            wi += 1

        text = " ".join(w["text"] for w in seg_words)
        yt_segments.append({
            "position": seg["position"],
            "start_time": seg_start,
            "end_time": seg_end,
            "text": text,
            "words": seg_words,
        })

    return yt_segments


def process_episode(episode: dict, force: bool = False):
    """Fetch and store YT captions for a single episode."""
    vid = episode["youtube_id"]
    ep_id = episode["id"]

    # Check if already fetched
    if not force:
        existing = sb.table("yt_segments").select("id").eq("episode_id", ep_id).limit(1).execute()
        if existing.data:
            print(f"    Already fetched (use --force to re-fetch)")
            return

    # Get our segments for time boundaries
    our_segments = (
        sb.table("segments")
        .select("position, start_time, end_time")
        .eq("episode_id", ep_id)
        .order("start_time")
        .execute()
    ).data

    if not our_segments:
        print(f"    No segments found — skipping")
        return

    # Fetch YT captions
    yt_words = fetch_yt_captions(vid)
    if not yt_words:
        return

    print(f"    Got {len(yt_words)} YT caption words")

    # Slice into our segment boundaries
    yt_segs = slice_words_to_segments(yt_words, our_segments)

    # Delete existing if force
    if force:
        sb.table("yt_segments").delete().eq("episode_id", ep_id).execute()

    # Insert
    rows = [
        {
            "episode_id": ep_id,
            "position": s["position"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "text": s["text"],
            "words": json.dumps(s["words"]),
        }
        for s in yt_segs
    ]

    # Batch insert (Supabase limit ~1000 rows)
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        sb.table("yt_segments").insert(rows[i : i + batch_size]).execute()

    print(f"    Inserted {len(rows)} yt_segments")


def main():
    force = "--force" in sys.argv
    single_id = None

    for i, arg in enumerate(sys.argv):
        if arg == "--youtube-id" and i + 1 < len(sys.argv):
            single_id = sys.argv[i + 1]

    if single_id:
        ep = sb.table("episodes").select("id, youtube_id").eq("youtube_id", single_id).single().execute()
        if not ep.data:
            print(f"Episode not found: {single_id}")
            sys.exit(1)
        print(f"Processing: {single_id}")
        process_episode(ep.data, force)
    else:
        # Batch: all episodes with segments but no yt_segments
        episodes = sb.table("episodes").select("id, youtube_id, title").execute().data
        print(f"Found {len(episodes)} episodes")

        for i, ep in enumerate(episodes, 1):
            print(f"[{i}/{len(episodes)}] {ep['youtube_id']} — {ep.get('title', '')[:50]}")
            process_episode(ep, force)

    print("\nDone!")


if __name__ == "__main__":
    main()
```

**Step 2: Test with a single episode**

```bash
python scripts/fetch_yt_captions.py --youtube-id <any_youtube_id_from_db>
```

Expected: Script fetches captions, prints word count, inserts yt_segments rows.

**Step 3: Verify data in Supabase**

Check that `yt_segments` rows exist for the test episode, with populated `text` and `words` fields.

**Step 4: Commit**

```bash
git add scripts/fetch_yt_captions.py
git commit -m "feat: add YT captions fetch script with segment alignment"
```

---

### Task 3: Word-Level Diff Utility

**Files:**
- Create: `lib/diff.ts`

**Step 1: Write the LCS-based word diff**

```typescript
export interface DiffWord {
  text: string;
  type: 'match' | 'insert' | 'delete';
}

/**
 * Word-level diff using Longest Common Subsequence.
 * Returns two arrays (one per side) with diff annotations.
 */
export function wordDiff(
  wordsA: string[],
  wordsB: string[]
): { left: DiffWord[]; right: DiffWord[] } {
  const m = wordsA.length;
  const n = wordsB.length;

  // Build LCS table
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to build diff
  const left: DiffWord[] = [];
  const right: DiffWord[] = [];
  let i = m, j = n;

  const leftStack: DiffWord[] = [];
  const rightStack: DiffWord[] = [];

  while (i > 0 || j > 0) {
    if (
      i > 0 &&
      j > 0 &&
      wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()
    ) {
      leftStack.push({ text: wordsA[i - 1], type: 'match' });
      rightStack.push({ text: wordsB[j - 1], type: 'match' });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      rightStack.push({ text: wordsB[j - 1], type: 'insert' });
      j--;
    } else {
      leftStack.push({ text: wordsA[i - 1], type: 'delete' });
      i--;
    }
  }

  // Reverse stacks (we built them backwards)
  leftStack.reverse();
  rightStack.reverse();

  return { left: leftStack, right: rightStack };
}
```

**Step 2: Commit**

```bash
git add lib/diff.ts
git commit -m "feat: add word-level LCS diff utility"
```

---

### Task 4: API Route for YT Segments

**Files:**
- Create: `app/api/episodes/[id]/yt-segments/route.ts`

**Context:** Follow the pattern from `app/api/search/route.ts`. Use the `supabase` client from `@/lib/supabase` (anon key, not service role — this is a read-only GET).

**Step 1: Write the API route**

```typescript
import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: episodeId } = await params;

  // Look up episode by youtube_id to get the UUID
  const { data: episode } = await supabase
    .from('episodes')
    .select('id')
    .eq('youtube_id', episodeId)
    .single();

  if (!episode) {
    return NextResponse.json({ error: 'Episode not found' }, { status: 404 });
  }

  const { data, error } = await supabase
    .from('yt_segments')
    .select('id, position, start_time, end_time, text, words')
    .eq('episode_id', episode.id)
    .order('start_time');

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data || []);
}
```

**Step 2: Test the route**

Start dev server and hit: `curl http://localhost:3001/api/episodes/<youtube_id>/yt-segments`

Expected: JSON array of yt_segments (or empty array if none fetched yet).

**Step 3: Commit**

```bash
git add app/api/episodes/\[id\]/yt-segments/route.ts
git commit -m "feat: add API route for YT caption segments"
```

---

### Task 5: Transcript Compare Component

**Files:**
- Create: `components/transcript-compare.tsx`

**Context:** This is a `'use client'` component. It receives our segments as props (already loaded server-side) and fetches YT segments from the API route on mount. Uses `wordDiff` from `lib/diff.ts`. Includes a confidence threshold slider.

**Step 1: Write the comparison component**

```typescript
'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wordDiff, type DiffWord } from '@/lib/diff';

interface Word {
  text: string;
  start: number;
  end: number;
  score?: number;
}

interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  words?: Word[] | string | null;
}

interface YTSegment {
  id: string;
  position: number;
  start_time: number;
  end_time: number;
  text: string;
  words?: Word[] | string | null;
}

function parseWords(raw: Word[] | string | null | undefined): Word[] {
  if (!raw) return [];
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return Array.isArray(raw) ? raw : [];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

interface TranscriptCompareProps {
  segments: Segment[];
  youtubeId: string;
}

export function TranscriptCompare({ segments, youtubeId }: TranscriptCompareProps) {
  const [ytSegments, setYtSegments] = useState<YTSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [threshold, setThreshold] = useState(0.85);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);

  // Fetch YT segments
  useEffect(() => {
    fetch(`/api/episodes/${youtubeId}/yt-segments`)
      .then(r => r.json())
      .then(data => {
        setYtSegments(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [youtubeId]);

  // Sync scroll between columns
  const handleScroll = useCallback((source: 'left' | 'right') => {
    if (syncing.current) return;
    syncing.current = true;
    const from = source === 'left' ? leftRef.current : rightRef.current;
    const to = source === 'left' ? rightRef.current : leftRef.current;
    if (from && to) {
      const ratio = from.scrollTop / (from.scrollHeight - from.clientHeight || 1);
      to.scrollTop = ratio * (to.scrollHeight - to.clientHeight);
    }
    requestAnimationFrame(() => { syncing.current = false; });
  }, []);

  // Seek YouTube video
  const seekTo = useCallback((time: number) => {
    const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [time, true] }),
        '*'
      );
    }
  }, []);

  // Build aligned pairs: match our segments to YT segments by position/time
  const pairs = useMemo(() => {
    return segments.map((seg) => {
      // Find matching YT segment by closest start_time
      const ytSeg = ytSegments.find(
        yt => Math.abs(yt.start_time - seg.start_time) < 1.0
      ) || null;

      const ourWords = parseWords(seg.words);
      const ourTexts = ourWords.length > 0
        ? ourWords.map(w => w.text)
        : seg.text.split(/\s+/).filter(Boolean);
      const ytTexts = ytSeg
        ? (ytSeg.text || '').split(/\s+/).filter(Boolean)
        : [];

      const diff = ytTexts.length > 0
        ? wordDiff(ourTexts, ytTexts)
        : { left: ourTexts.map(t => ({ text: t, type: 'match' as const })), right: [] };

      return { segment: seg, ytSegment: ytSeg, ourWords, diff };
    });
  }, [segments, ytSegments]);

  if (loading) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        Loading YouTube captions...
      </div>
    );
  }

  if (ytSegments.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground text-sm mb-2">No YouTube captions available for this episode.</p>
        <p className="text-xs text-muted-foreground">
          Run: <code className="bg-muted px-1.5 py-0.5 rounded">python scripts/fetch_yt_captions.py --youtube-id {youtubeId}</code>
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Confidence threshold slider */}
      <div className="flex items-center gap-3 mb-3 bg-muted/50 rounded-lg px-4 py-2">
        <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">
          Confidence threshold:
        </label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={threshold}
          onChange={e => setThreshold(parseFloat(e.target.value))}
          className="flex-1 h-1.5 accent-orange-500"
        />
        <span className="text-xs font-mono tabular-nums w-10 text-right">
          {threshold.toFixed(2)}
        </span>
      </div>

      {/* Side-by-side columns */}
      <div className="grid grid-cols-2 gap-0 border rounded-lg overflow-hidden">
        {/* Column headers */}
        <div className="bg-muted/70 px-3 py-2 border-b border-r text-xs font-semibold">
          Our Transcript (Whisper + NeMo)
        </div>
        <div className="bg-muted/70 px-3 py-2 border-b text-xs font-semibold">
          YouTube Auto-Captions
        </div>

        {/* Scrollable columns */}
        <div
          ref={leftRef}
          onScroll={() => handleScroll('left')}
          className="max-h-[600px] overflow-y-auto border-r"
        >
          {pairs.map((pair, i) => (
            <div
              key={i}
              className="p-3 border-b border-border last:border-b-0 text-sm"
            >
              {/* Speaker + time + confidence */}
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                  {pair.segment.speaker || 'Unknown'}
                </span>
                <button
                  onClick={() => seekTo(pair.segment.start_time)}
                  className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                >
                  {formatTime(pair.segment.start_time)}
                </button>
              </div>
              {/* Words with diff + confidence coloring */}
              <p className="leading-relaxed">
                {pair.diff.left.map((dw, wi) => {
                  const word = pair.ourWords[wi];
                  const isLowConfidence = word?.score != null && word.score < threshold;
                  const bgColor = dw.type === 'delete'
                    ? 'bg-red-200 dark:bg-red-500/30'
                    : isLowConfidence
                      ? 'bg-orange-200 dark:bg-orange-500/30'
                      : '';
                  return (
                    <span
                      key={wi}
                      className={`rounded-sm ${bgColor}`}
                      title={word?.score != null ? `confidence: ${(word.score * 100).toFixed(1)}%` : undefined}
                    >
                      {dw.text}{' '}
                    </span>
                  );
                })}
              </p>
            </div>
          ))}
        </div>

        <div
          ref={rightRef}
          onScroll={() => handleScroll('right')}
          className="max-h-[600px] overflow-y-auto"
        >
          {pairs.map((pair, i) => (
            <div
              key={i}
              className="p-3 border-b border-border last:border-b-0 text-sm"
            >
              {/* Time only (no speaker for YT) */}
              <div className="flex items-center gap-2 mb-1.5">
                <button
                  onClick={() => seekTo(pair.segment.start_time)}
                  className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                >
                  {formatTime(pair.segment.start_time)}
                </button>
              </div>
              {/* Words with diff coloring */}
              <p className="leading-relaxed">
                {pair.diff.right.length > 0 ? (
                  pair.diff.right.map((dw, wi) => (
                    <span
                      key={wi}
                      className={`rounded-sm ${
                        dw.type === 'insert' ? 'bg-green-200 dark:bg-green-500/30' : ''
                      }`}
                    >
                      {dw.text}{' '}
                    </span>
                  ))
                ) : (
                  <span className="text-muted-foreground italic">No caption data</span>
                )}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-red-200 dark:bg-red-500/30" /> Only in ours
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-green-200 dark:bg-green-500/30" /> Only in YouTube
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-orange-200 dark:bg-orange-500/30" /> Low confidence
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add components/transcript-compare.tsx
git commit -m "feat: add transcript comparison component with diff and confidence"
```

---

### Task 6: Episode Page — Tab Bar & Debug Tab Integration

**Files:**
- Modify: `app/[channel]/episodes/[id]/page.tsx`

**Context:** The transcript section currently renders `<TranscriptViewer>` directly. We need to wrap it in a client component that provides tab switching. Since the page is a server component, we create a small client wrapper.

**Step 1: Create the tab wrapper component**

Create `components/episode-transcript-tabs.tsx`:

```typescript
'use client'

import { useState } from 'react';
import { TranscriptViewer } from './transcript-viewer';
import { TranscriptCompare } from './transcript-compare';

interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  words?: any;
}

interface EpisodeTranscriptTabsProps {
  segments: Segment[];
  youtubeId: string;
}

export function EpisodeTranscriptTabs({ segments, youtubeId }: EpisodeTranscriptTabsProps) {
  const [tab, setTab] = useState<'transcript' | 'compare'>('transcript');
  const isDev = process.env.NODE_ENV === 'development';

  return (
    <div>
      {/* Tab bar */}
      <div className="flex items-center gap-1 mb-3 sm:mb-4">
        <h2 className="text-lg sm:text-xl font-semibold mr-4">Transcript</h2>
        <button
          onClick={() => setTab('transcript')}
          className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
            tab === 'transcript'
              ? 'bg-primary text-primary-foreground font-medium'
              : 'bg-muted text-muted-foreground hover:text-foreground'
          }`}
        >
          Viewer
        </button>
        {isDev && (
          <button
            onClick={() => setTab('compare')}
            className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
              tab === 'compare'
                ? 'bg-orange-500 text-white font-medium'
                : 'bg-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            Compare (Dev)
          </button>
        )}
      </div>

      {/* Tab content */}
      {tab === 'transcript' ? (
        <TranscriptViewer segments={segments} youtubeId={youtubeId} />
      ) : (
        <TranscriptCompare segments={segments} youtubeId={youtubeId} />
      )}
    </div>
  );
}
```

**Step 2: Update the episode page to use tabs**

In `app/[channel]/episodes/[id]/page.tsx`, replace the transcript section:

**Before (lines 112-123):**
```tsx
<div className="lg:col-span-2">
  {segments.length > 0 && (
    <div>
      <h2 className="text-lg sm:text-xl font-semibold mb-3 sm:mb-4">Transcript</h2>
      <TranscriptViewer
        segments={segments}
        youtubeId={episode.youtube_id}
      />
    </div>
  )}
</div>
```

**After:**
```tsx
<div className="lg:col-span-2">
  {segments.length > 0 && (
    <EpisodeTranscriptTabs
      segments={segments}
      youtubeId={episode.youtube_id}
    />
  )}
</div>
```

Update imports — remove direct `TranscriptViewer` import, add `EpisodeTranscriptTabs`:

```typescript
import { EpisodeTranscriptTabs } from '@/components/episode-transcript-tabs';
```

Remove the unused `TranscriptViewer` import.

**Step 3: Verify in browser**

Navigate to an episode page. Confirm:
- "Transcript" and "Compare (Dev)" tabs appear
- Default tab shows the transcript viewer as before
- Compare tab shows loading → either comparison data or "no captions" message

**Step 4: Commit**

```bash
git add components/episode-transcript-tabs.tsx app/\[channel\]/episodes/\[id\]/page.tsx
git commit -m "feat: add tab bar with dev-only compare tab on episode page"
```

---

### Task 7: Run YT Captions Fetch & End-to-End Test

**Step 1: Run the fetch script for a test episode**

```bash
python scripts/fetch_yt_captions.py --youtube-id <pick_one_with_segments>
```

**Step 2: Verify in browser**

Open that episode's page → click "Compare (Dev)" tab. Confirm:
- Side-by-side layout renders
- Left shows our transcript with speaker tags
- Right shows YT captions
- Red highlights show words only in our transcript
- Green highlights show words only in YT captions
- Orange highlights show low-confidence words (adjust slider to verify)
- Synchronized scrolling works between columns
- Click-to-seek works on timestamps

**Step 3: Run batch fetch (optional)**

```bash
python scripts/fetch_yt_captions.py
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: transcript comparison tool — complete implementation"
```
