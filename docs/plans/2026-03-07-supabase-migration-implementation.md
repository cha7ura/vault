# Supabase Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move vault's data layer from local SQLite to Supabase Postgres so Colab can write directly to the DB while the Next.js frontend reads from it.

**Architecture:** Colab (GPU) processes videos with whisper + NeMo MSDD, then inserts episodes and segments directly into Supabase via `supabase-py`. The Next.js frontend (already wired to Supabase) gets a new `segments` query for the episode detail page. A one-time migration script loads existing JSON exports.

**Tech Stack:** Supabase Postgres, supabase-py (Colab), @supabase/supabase-js (Next.js), pgvector (already enabled)

**Key Discovery:** The Next.js frontend is ALREADY wired to Supabase (`lib/supabase.ts`, all page components use `createServerClient()`). The episodes page, insights, books, guests all query Supabase. The only gaps are: (1) no `segments` table in Supabase, (2) no data loaded into Supabase yet, (3) Colab writes to JSON files instead of Supabase.

---

### Task 1: Create Supabase Migration for Segments Table

**Files:**
- Create: `supabase/migrations/004_add_segments.sql`

**Context:** Existing migrations 001-003 create episodes, guests, insights, books, papers with pgvector and multi-tenancy. The `segments` table is missing -- it exists in SQLite but not Supabase. This table stores word-level diarized transcript data (~1,300 rows per episode).

**Step 1: Write the migration**

```sql
-- Add segments table for word-level diarized transcripts
-- Each episode has ~1,300 segments with speaker labels and word-level timestamps

CREATE TABLE segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  text TEXT NOT NULL,
  speaker VARCHAR(100),
  tag VARCHAR(50) NOT NULL DEFAULT 'content',
  confidence FLOAT,
  diarizer VARCHAR(100) NOT NULL DEFAULT 'whisper-diarization',
  words JSONB,            -- [{text, start, end, score}] for karaoke highlighting
  youtube_text TEXT,       -- future: aligned YouTube caption text
  created_at TIMESTAMP DEFAULT NOW()
);

-- Primary query: get all segments for an episode, ordered by time
CREATE INDEX idx_segments_episode_time ON segments(episode_id, start_time);

-- Filter by speaker within an episode
CREATE INDEX idx_segments_speaker ON segments(episode_id, speaker);

-- Filter by diarizer (supports multi-diarizer comparison)
CREATE INDEX idx_segments_diarizer ON segments(episode_id, diarizer);
```

**Step 2: Run migration on Supabase**

Option A (Supabase CLI):
```bash
supabase db push
```

Option B (Supabase Dashboard):
- Go to SQL Editor in Supabase Dashboard
- Paste and run the SQL

**Step 3: Verify table exists**

In Supabase SQL Editor:
```sql
SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'segments' ORDER BY ordinal_position;
```
Expected: 11 columns (id, episode_id, start_time, end_time, text, speaker, tag, confidence, diarizer, words, youtube_text, created_at)

**Step 4: Commit**

```bash
git add supabase/migrations/004_add_segments.sql
git commit -m "feat: add segments table migration for Supabase"
```

---

### Task 2: One-Time Data Migration Script (JSON -> Supabase)

**Files:**
- Create: `scripts/migrate-to-supabase.ts`

**Context:** We have 7 completed episodes as JSON exports in `data/segments.json` (9,313 segments) and `data/episodes.json` (12 episodes). We need to load this into Supabase once. The existing `pipeline/scripts/import_colab_json.py` targets SQLite -- this new script targets Supabase.

**Important:** The Supabase schema uses UUIDs for IDs and has a different column structure than SQLite. The channels table has `youtube_channel_id` (not `youtube_id`). Episodes have `duration_seconds` (not `duration`).

**Step 1: Write the migration script**

File: `scripts/migrate-to-supabase.ts`

```typescript
/**
 * One-time migration: load JSON exports into Supabase.
 *
 * Usage:
 *   SUPABASE_SERVICE_ROLE_KEY=... npx tsx scripts/migrate-to-supabase.ts
 *
 * Reads from:
 *   data/episodes.json   -- episode metadata
 *   data/segments.json   -- all segments with words
 *   data/channels.json   -- channel metadata
 */

import { createClient } from '@supabase/supabase-js';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const dataDir = resolve(__dirname, '..', 'data');

interface JsonEpisode {
  id: number;
  channel_id: number;
  youtube_id: string;
  title: string;
  description?: string;
  duration?: number;
  published_at?: string;
  thumbnail_url?: string;
  status: string;
  created_at: string;
}

interface JsonSegment {
  id: number;
  episode_id: number;
  start_time: number;
  end_time: number;
  text: string;
  speaker?: string;
  tag: string;
  confidence?: number;
  diarizer: string;
  words?: object;
  youtube_text?: string;
  created_at: string;
}

interface JsonChannel {
  id: number;
  name: string;
  slug: string;
  youtube_id: string;
  intro_skip: number;
  created_at: string;
}

async function main() {
  // 1. Load JSON files
  const channels: JsonChannel[] = JSON.parse(readFileSync(resolve(dataDir, 'channels.json'), 'utf-8'));
  const episodes: JsonEpisode[] = JSON.parse(readFileSync(resolve(dataDir, 'episodes.json'), 'utf-8'));
  const segments: JsonSegment[] = JSON.parse(readFileSync(resolve(dataDir, 'segments.json'), 'utf-8'));

  console.log(`Loaded: ${channels.length} channels, ${episodes.length} episodes, ${segments.length} segments`);

  // 2. Upsert channel
  // Map SQLite channel to Supabase schema
  const channel = channels[0]; // DOAC
  const { data: dbChannel, error: chErr } = await supabase
    .from('channels')
    .upsert({
      youtube_channel_id: channel.youtube_id,
      name: channel.name,
      slug: channel.slug,
    }, { onConflict: 'youtube_channel_id' })
    .select('id')
    .single();

  if (chErr) {
    console.error('Channel upsert failed:', chErr.message);
    process.exit(1);
  }
  const channelId = dbChannel.id;
  console.log(`Channel: ${channel.name} -> ${channelId}`);

  // 3. Build SQLite episode_id -> Supabase UUID mapping
  const idMap = new Map<number, string>(); // sqlite_id -> supabase_uuid

  for (const ep of episodes) {
    if (ep.status !== 'complete') {
      console.log(`  Skipping ${ep.youtube_id} (status: ${ep.status})`);
      continue;
    }

    // Check if already exists
    const { data: existing } = await supabase
      .from('episodes')
      .select('id')
      .eq('youtube_id', ep.youtube_id)
      .single();

    if (existing) {
      console.log(`  ${ep.youtube_id}: already exists (${existing.id})`);
      idMap.set(ep.id, existing.id);
      continue;
    }

    const { data: inserted, error: epErr } = await supabase
      .from('episodes')
      .insert({
        channel_id: channelId,
        youtube_id: ep.youtube_id,
        title: ep.title,
        description: ep.description || null,
        duration_seconds: ep.duration ? Math.round(ep.duration) : null,
        published_at: ep.published_at || null,
        thumbnail_url: ep.thumbnail_url || null,
        processed_at: new Date().toISOString(),
      })
      .select('id')
      .single();

    if (epErr) {
      console.error(`  ${ep.youtube_id}: insert failed: ${epErr.message}`);
      continue;
    }

    idMap.set(ep.id, inserted.id);
    console.log(`  ${ep.youtube_id}: inserted -> ${inserted.id}`);
  }

  // 4. Insert segments in batches (Supabase REST has ~1MB body limit)
  const BATCH_SIZE = 200;
  let inserted = 0;
  let skipped = 0;

  // Group segments by episode
  const segsByEpisode = new Map<number, JsonSegment[]>();
  for (const seg of segments) {
    if (!segsByEpisode.has(seg.episode_id)) {
      segsByEpisode.set(seg.episode_id, []);
    }
    segsByEpisode.get(seg.episode_id)!.push(seg);
  }

  for (const [sqliteEpId, epSegments] of segsByEpisode) {
    const supabaseEpId = idMap.get(sqliteEpId);
    if (!supabaseEpId) {
      skipped += epSegments.length;
      continue;
    }

    // Check if segments already exist for this episode
    const { count } = await supabase
      .from('segments')
      .select('id', { count: 'exact', head: true })
      .eq('episode_id', supabaseEpId);

    if (count && count > 0) {
      console.log(`  Episode ${supabaseEpId}: ${count} segments already exist, skipping`);
      skipped += epSegments.length;
      continue;
    }

    // Batch insert
    for (let i = 0; i < epSegments.length; i += BATCH_SIZE) {
      const batch = epSegments.slice(i, i + BATCH_SIZE).map(seg => ({
        episode_id: supabaseEpId,
        start_time: seg.start_time,
        end_time: seg.end_time,
        text: seg.text,
        speaker: seg.speaker || null,
        tag: seg.tag || 'content',
        confidence: seg.confidence || null,
        diarizer: seg.diarizer || 'whisper-diarization',
        words: seg.words || null,
        youtube_text: seg.youtube_text || null,
      }));

      const { error: segErr } = await supabase.from('segments').insert(batch);
      if (segErr) {
        console.error(`  Batch insert failed for episode ${supabaseEpId}: ${segErr.message}`);
        break;
      }
      inserted += batch.length;
    }
    console.log(`  Episode ${supabaseEpId}: inserted ${epSegments.length} segments`);
  }

  console.log(`\nDone. Inserted: ${inserted} segments, Skipped: ${skipped}`);
}

main().catch(console.error);
```

**Step 2: Run the migration**

```bash
# Ensure .env.local has NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
npx tsx scripts/migrate-to-supabase.ts
```

Expected output:
```
Loaded: 1 channels, 12 episodes, 9313 segments
Channel: The Diary Of A CEO -> <uuid>
  jDG1m_b5Ih0: inserted -> <uuid>
  e9dljIL4rBk: inserted -> <uuid>
  ...
  ajgwabD4_HE: Skipping (status: failed)
  ...
Done. Inserted: 9313 segments, Skipped: 0
```

**Step 3: Verify in Supabase**

```sql
SELECT e.youtube_id, e.title, count(s.id) as segments
FROM episodes e
LEFT JOIN segments s ON s.episode_id = e.id
GROUP BY e.id
ORDER BY e.title;
```
Expected: 7 episodes with segment counts totaling ~9,313

**Step 4: Commit**

```bash
git add scripts/migrate-to-supabase.ts
git commit -m "feat: add one-time JSON-to-Supabase migration script"
```

---

### Task 3: Rewrite Colab Notebook — Continuous Idempotent Loop

**Files:**
- Rewrite: `vault_batch_colab.ipynb`

**Context:** The current notebook processes a hardcoded list of URLs, saves JSON files, then requires manual download + import. The new version connects directly to Supabase, checks which episodes are already processed, and loops indefinitely. On Colab timeout, user just reruns and it picks up where it left off.

**Step 1: Rewrite Cell 2 (Configuration) to connect to Supabase**

Replace the hardcoded URL list with channel-based fetching and Supabase connection:

```python
import torch, os, re, json, time

# --- Supabase Config (store as Colab secrets) ---
from google.colab import userdata
SUPABASE_URL = userdata.get('SUPABASE_URL')
SUPABASE_KEY = userdata.get('SUPABASE_SERVICE_ROLE_KEY')

from supabase import create_client
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Processing Config ---
WHISPER_MODEL = "large-v3"
BATCH_SIZE = 8
ENABLE_STEMMING = False
LANGUAGE = "en"

# --- Channel Config ---
CHANNEL_YT_ID = "UC7yZ6keOGsvERMp2HaEbbXQ"  # @StevenBartlett / DOAC
CHANNEL_NAME = "The Diary Of A CEO"
CHANNEL_SLUG = "doac"
MAX_VIDEOS = 50  # max videos to fetch from channel per loop

# --- Derived ---
AUDIO_DIR = "/content/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}")
print(f"Supabase: {SUPABASE_URL[:30]}...")
```

**Step 2: Add Cell 2b — Supabase helpers**

```python
def ensure_channel() -> str:
    """Get or create channel, return Supabase UUID."""
    result = sb.from_('channels').select('id').eq('youtube_channel_id', CHANNEL_YT_ID).execute()
    if result.data:
        return result.data[0]['id']
    result = sb.from_('channels').insert({
        'youtube_channel_id': CHANNEL_YT_ID,
        'name': CHANNEL_NAME,
        'slug': CHANNEL_SLUG,
    }).execute()
    return result.data[0]['id']


def get_processed_ids() -> set[str]:
    """Return set of youtube_ids already marked complete in Supabase."""
    result = sb.from_('episodes').select('youtube_id').eq('processed_at', None).is_('processed_at', 'not.null').execute()
    # Simpler: just get all episodes that have segments
    result = sb.from_('episodes').select('youtube_id, processed_at').execute()
    return {r['youtube_id'] for r in result.data if r.get('processed_at')}


def get_channel_video_ids(channel_id_yt: str, max_results: int = 50) -> list[str]:
    """Fetch latest video IDs from YouTube channel using yt-dlp."""
    import subprocess
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id",
         f"https://www.youtube.com/@{channel_id_yt}/videos",
         "--playlist-end", str(max_results)],
        capture_output=True, text=True, timeout=120,
    )
    return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]


def upsert_episode(channel_id: str, video_id: str, title: str, duration: float) -> str:
    """Create or update episode, return Supabase UUID."""
    result = sb.from_('episodes').select('id').eq('youtube_id', video_id).execute()
    if result.data:
        ep_id = result.data[0]['id']
        sb.from_('episodes').update({
            'title': title,
            'duration_seconds': int(duration),
            'processed_at': 'now()',
        }).eq('id', ep_id).execute()
        return ep_id
    result = sb.from_('episodes').insert({
        'channel_id': channel_id,
        'youtube_id': video_id,
        'title': title,
        'duration_seconds': int(duration),
        'processed_at': None,  # set after segments inserted
    }).execute()
    return result.data[0]['id']


def insert_segments(episode_id: str, segments: list[dict]):
    """Delete existing segments and batch-insert new ones."""
    # Clear old segments for this episode
    sb.from_('segments').delete().eq('episode_id', episode_id).execute()

    # Batch insert (supabase-py handles chunking)
    BATCH = 200
    for i in range(0, len(segments), BATCH):
        batch = [{
            'episode_id': episode_id,
            'start_time': s['start'],
            'end_time': s['end'],
            'text': s['text'],
            'speaker': s.get('speaker'),
            'tag': 'content',
            'diarizer': 'whisper-diarization',
            'words': s.get('words'),
        } for s in segments[i:i + BATCH]]
        sb.from_('segments').insert(batch).execute()


def mark_complete(episode_id: str):
    """Mark episode as processed."""
    sb.from_('episodes').update({
        'processed_at': 'now()',
    }).eq('id', episode_id).execute()


print("Supabase helpers loaded.")
```

**Step 3: Rewrite Cell 4 (Processing Loop) to be continuous and idempotent**

Replace the current single-pass loop with:

```python
channel_id = ensure_channel()
print(f"Channel UUID: {channel_id}")

SLEEP_MINUTES = 5
MAX_LOOPS = 100  # safety limit; set to None for infinite

loop_count = 0
while MAX_LOOPS is None or loop_count < MAX_LOOPS:
    loop_count += 1
    print(f"\n{'='*60}")
    print(f"LOOP {loop_count} — checking for new videos...")
    print(f"{'='*60}")

    # 1. Get video list from YouTube
    try:
        video_ids = get_channel_video_ids("StevenBartlett", MAX_VIDEOS)
        print(f"Found {len(video_ids)} videos on channel")
    except Exception as e:
        print(f"Failed to fetch video list: {e}")
        time.sleep(60)
        continue

    # 2. Check which are already processed
    processed = get_processed_ids()
    pending = [vid for vid in video_ids if vid not in processed]
    print(f"Already processed: {len(processed)}, Pending: {len(pending)}")

    if not pending:
        print(f"All caught up! Sleeping {SLEEP_MINUTES} minutes...")
        time.sleep(SLEEP_MINUTES * 60)
        continue

    # 3. Process one video at a time
    for idx, video_id in enumerate(pending, 1):
        print(f"\n[{idx}/{len(pending)}] Processing {video_id}")
        t_start = time.time()

        try:
            # Download audio
            wav_path, title = download_audio(video_id)
            print(f"  Title: {title}")

            # Transcribe with Whisper
            vocal_target = wav_path
            if ENABLE_STEMMING:
                # ... stemming code unchanged ...
                pass

            print(f"  Loading Whisper {WHISPER_MODEL}...")
            whisper_model = faster_whisper.WhisperModel(WHISPER_MODEL, device=device, compute_type="float16")
            whisper_pipeline = faster_whisper.BatchedInferencePipeline(whisper_model)
            audio_waveform = faster_whisper.decode_audio(vocal_target)

            print(f"  Transcribing ({len(audio_waveform)/16000:.0f}s audio)...")
            transcript_segments, info = whisper_pipeline.transcribe(
                audio_waveform, LANGUAGE, batch_size=BATCH_SIZE, without_timestamps=True,
            )

            word_timestamps = []
            for segment in transcript_segments:
                if segment.words:
                    for word in segment.words:
                        word_timestamps.append({
                            "text": word.word.strip(),
                            "start": word.start,
                            "end": word.end,
                            "score": word.probability,
                        })
            print(f"  Transcribed: {len(word_timestamps)} words")

            del whisper_model, whisper_pipeline
            torch.cuda.empty_cache()

            # NeMo MSDD Diarization
            print("  Running speaker diarization (NeMo MSDD)...")
            temp_path = os.path.join(AUDIO_DIR, f"temp_{video_id}")
            os.makedirs(temp_path, exist_ok=True)

            waveform_tensor = torch.from_numpy(audio_waveform).unsqueeze(0).float()
            torchaudio.save(os.path.join(temp_path, "mono_file.wav"), waveform_tensor, 16000, channels_first=True)

            msdd_model = NeuralDiarizer(cfg=create_nemo_config(temp_path)).to(device)
            msdd_model.diarize()
            del msdd_model
            torch.cuda.empty_cache()

            speaker_ts = []
            rttm_path = os.path.join(temp_path, "pred_rttms", "mono_file.rttm")
            with open(rttm_path, "r") as f:
                for line in f:
                    parts = line.split(" ")
                    s = int(float(parts[5]) * 1000)
                    e = s + int(float(parts[8]) * 1000)
                    speaker_ts.append([s, e, int(parts[11].split("_")[-1])])

            # Map speakers to words
            wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

            if info.language in punct_model_langs:
                punct_model = PunctuationModel(model="kredor/punctuate-all")
                words_list = [d["word"] for d in wsm]
                labeled_words = punct_model.predict(words_list, chunk_size=230)
                is_acronym = lambda x: re.fullmatch(r"\b(?:[a-zA-Z]\.){2,}", x)
                model_puncts = ".,;:!?"
                for word_dict, labeled_tuple in zip(wsm, labeled_words):
                    word = word_dict["word"]
                    if word and labeled_tuple[1] in sentence_ending_punctuations and (word[-1] not in model_puncts or is_acronym(word)):
                        word += labeled_tuple[1]
                        if word.endswith(".."): word = word.rstrip(".")
                        word_dict["word"] = word

            wsm = get_realigned_ws_mapping_with_punctuation(wsm)
            ssm = get_sentences_speaker_mapping(wsm, speaker_ts)
            segments = sentences_to_vault_json(ssm)

            # --- INSERT INTO SUPABASE ---
            duration = segments[-1]["end"] if segments else 0
            episode_id = upsert_episode(channel_id, video_id, title, duration)
            insert_segments(episode_id, segments)
            mark_complete(episode_id)

            elapsed = time.time() - t_start
            print(f"  Done: {len(segments)} segments -> Supabase in {elapsed:.0f}s")

        except Exception as e:
            print(f"  FAILED: {e}")
            # Create episode record with no processed_at so it can be retried
            try:
                upsert_episode(channel_id, video_id, video_id, 0)
            except:
                pass

        finally:
            # Cleanup audio
            wav_path = os.path.join(AUDIO_DIR, f"{video_id}.wav")
            if os.path.exists(wav_path):
                os.remove(wav_path)
            temp_path = os.path.join(AUDIO_DIR, f"temp_{video_id}")
            if os.path.exists(temp_path):
                import shutil
                shutil.rmtree(temp_path)

    print(f"\nBatch complete. Looping back to check for new videos...")
```

**Step 4: Remove Cell 5 (Download Results) and Cell 6 (Import Locally)**

These cells are no longer needed since data goes directly to Supabase.

**Step 5: Update Cell 1 (Install Dependencies) to add supabase**

Add to the pip install line:
```python
!pip install -q supabase
```

**Step 6: Commit**

```bash
git add vault_batch_colab.ipynb
git commit -m "feat: rewrite Colab notebook as continuous Supabase ingestion loop"
```

---

### Task 4: Add Segments Query to Episode Detail Page

**Files:**
- Modify: `app/[channel]/episodes/[id]/page.tsx:9-17` (add getSegments function)
- Modify: `app/[channel]/episodes/[id]/page.tsx:58-61` (fetch segments in parallel)
- Modify: `app/[channel]/episodes/[id]/page.tsx:119-126` (render segments instead of transcript blob)

**Context:** The episode detail page currently renders `episode.transcript` as a markdown blob via `TranscriptViewer`. We need to also fetch segments from the new table and pass them to the transcript viewer. The `TranscriptViewer` component will need updating to handle structured segment data (Task 5).

**Step 1: Add getSegments function**

In `app/[channel]/episodes/[id]/page.tsx`, add after the `getBooks` function (line 36):

```typescript
async function getSegments(episodeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('segments')
    .select('id, start_time, end_time, text, speaker, words')
    .eq('episode_id', episodeId)
    .order('start_time');
  return data || [];
}
```

**Step 2: Fetch segments in the page component**

Update the parallel fetch (line 58-61) to include segments:

```typescript
const [insights, books, segments] = await Promise.all([
  getInsights(params.id),
  getBooks(params.id),
  getSegments(params.id),
]);
```

**Step 3: Update transcript section to use segments when available**

Replace lines 118-126 with:

```typescript
{/* Transcript */}
{segments.length > 0 ? (
  <div>
    <h2 className="text-xl font-semibold mb-4">Transcript</h2>
    <TranscriptViewer
      segments={segments}
      youtubeId={episode.youtube_id}
    />
  </div>
) : episode.transcript ? (
  <div>
    <h2 className="text-xl font-semibold mb-4">Transcript</h2>
    <TranscriptViewer transcript={episode.transcript_formatted || episode.transcript} />
  </div>
) : null}
```

**Step 4: Commit**

```bash
git add app/[channel]/episodes/[id]/page.tsx
git commit -m "feat: fetch and display diarized segments on episode page"
```

---

### Task 5: Upgrade TranscriptViewer for Segment Data

**Files:**
- Modify: `components/transcript-viewer.tsx`

**Context:** The current TranscriptViewer renders a markdown string. We need it to also support an array of segments with speaker labels and timestamps. When segments are provided, it should group consecutive segments by speaker (conversational turns), show speaker labels with timestamps, and support click-to-seek on the YouTube embed.

**Step 1: Rewrite TranscriptViewer to support both modes**

```typescript
'use client'

import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  words?: { text: string; start: number; end: number; score?: number }[] | null;
}

interface TranscriptViewerProps {
  transcript?: string;
  segments?: Segment[];
  youtubeId?: string;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// Group consecutive segments by same speaker into "turns"
function groupByTurns(segments: Segment[]) {
  const turns: { speaker: string; startTime: number; segments: Segment[] }[] = [];
  for (const seg of segments) {
    const speaker = seg.speaker || 'Unknown';
    const last = turns[turns.length - 1];
    if (last && last.speaker === speaker) {
      last.segments.push(seg);
    } else {
      turns.push({ speaker, startTime: seg.start_time, segments: [seg] });
    }
  }
  return turns;
}

export function TranscriptViewer({ transcript, segments, youtubeId }: TranscriptViewerProps) {
  // Markdown mode (legacy)
  if (!segments || segments.length === 0) {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert bg-card p-6 rounded-lg border">
        <ReactMarkdown>{transcript || ''}</ReactMarkdown>
      </div>
    );
  }

  // Segments mode
  const turns = groupByTurns(segments);

  const seekTo = (time: number) => {
    if (!youtubeId) return;
    // Post message to YouTube iframe
    const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
    if (iframe) {
      iframe.contentWindow?.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [time, true] }),
        '*'
      );
    }
  };

  return (
    <div className="bg-card rounded-lg border divide-y">
      {turns.map((turn, i) => (
        <div key={i} className="p-4 hover:bg-muted/50 transition-colors">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
              {turn.speaker}
            </span>
            <button
              onClick={() => seekTo(turn.startTime)}
              className="text-xs text-muted-foreground hover:text-foreground tabular-nums"
            >
              {formatTime(turn.startTime)}
            </button>
          </div>
          <p className="text-sm leading-relaxed">
            {turn.segments.map(seg => seg.text).join(' ')}
          </p>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Verify locally**

```bash
npm run dev
```

Navigate to an episode page. If Supabase has segment data, you should see speaker-labeled turns with timestamps. Click a timestamp to seek the YouTube embed.

**Step 3: Commit**

```bash
git add components/transcript-viewer.tsx
git commit -m "feat: upgrade TranscriptViewer with speaker turns and click-to-seek"
```

---

### Task 6: Update YouTube Embed for Seek API

**Files:**
- Modify: `app/[channel]/episodes/[id]/page.tsx:109-116`

**Context:** The current YouTube embed uses a plain `<iframe>`. For the `postMessage` seek command to work, we need to add `?enablejsapi=1` to the embed URL.

**Step 1: Update iframe src**

Change line 110 from:
```tsx
src={`https://www.youtube.com/embed/${episode.youtube_id}`}
```
to:
```tsx
src={`https://www.youtube.com/embed/${episode.youtube_id}?enablejsapi=1&origin=${typeof window !== 'undefined' ? window.location.origin : ''}`}
```

Since this is a server component, we should use a fixed origin or make the iframe a client component. Simpler approach — just add the query param:

```tsx
src={`https://www.youtube.com/embed/${episode.youtube_id}?enablejsapi=1`}
```

**Step 2: Commit**

```bash
git add app/[channel]/episodes/[id]/page.tsx
git commit -m "feat: enable YouTube JS API for click-to-seek"
```

---

### Task 7: Add .env.local Template and Documentation

**Files:**
- Create: `.env.example`

**Step 1: Create env template**

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# Optional: Meilisearch (future)
# NEXT_PUBLIC_MEILISEARCH_HOST=http://localhost:7700
# NEXT_PUBLIC_MEILISEARCH_KEY=

# Optional: OpenRouter (for AI chat)
# OPENROUTER_API_KEY=
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with Supabase config"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Segments table migration | `supabase/migrations/004_add_segments.sql` |
| 2 | One-time data migration script | `scripts/migrate-to-supabase.ts` |
| 3 | Continuous Colab ingestion loop | `vault_batch_colab.ipynb` |
| 4 | Episode page segments query | `app/[channel]/episodes/[id]/page.tsx` |
| 5 | TranscriptViewer upgrade | `components/transcript-viewer.tsx` |
| 6 | YouTube embed JS API | `app/[channel]/episodes/[id]/page.tsx` |
| 7 | Env template | `.env.example` |

**Execution order:** Tasks 1 -> 2 (run migration, then load data) -> 3 (Colab notebook) can be done independently of 4 -> 5 -> 6 (frontend). Task 7 anytime.
