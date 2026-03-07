# Core Frontend Pages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build 3 production-quality frontend pages — episodes list (with search/sort/filter/grid-list toggle), people shell, and episode detail with youtube_id slugs and sidebar placeholders.

**Architecture:** Server components fetch all data from Supabase. Episodes list uses a client component wrapper for interactive search/sort/filter (dataset is <200 episodes, all client-side). Episode detail page queries by `youtube_id` instead of UUID. People page is a static shell with "Coming soon" state.

**Tech Stack:** Next.js 15 (App Router), Tailwind CSS, shadcn/ui, Supabase, Lucide icons, date-fns

---

### Task 1: Switch Episode URLs from UUID to YouTube ID

**Files:**
- Modify: `components/episode-card.tsx:26-28`
- Modify: `app/[channel]/episodes/[id]/page.tsx:10-16`

**Step 1: Update EpisodeCard href to use youtube_id**

In `components/episode-card.tsx`, change the href construction:

```tsx
const href = channelSlug
  ? `/${channelSlug}/episodes/${episode.youtube_id}`
  : `/episodes/${episode.youtube_id}`;
```

**Step 2: Update episode detail page to query by youtube_id**

In `app/[channel]/episodes/[id]/page.tsx`, change `getEpisode`:

```tsx
async function getEpisode(youtubeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('episodes')
    .select('*')
    .eq('youtube_id', youtubeId)
    .single();
  return data;
}
```

**Step 3: Verify in browser**

Run: `npm run dev -- -p 3001`
- Navigate to `http://localhost:3001/doac/episodes`
- Click an episode card
- URL should be `/doac/episodes/ajgwabD4_HE` (youtube ID, not UUID)
- Episode detail page should load correctly

**Step 4: Commit**

```bash
git add components/episode-card.tsx app/[channel]/episodes/[id]/page.tsx
git commit -m "feat: use youtube_id as episode URL slug instead of UUID"
```

---

### Task 2: Add YouTube Thumbnail Fallback to EpisodeCard

**Files:**
- Modify: `components/episode-card.tsx`

**Step 1: Add thumbnail fallback logic**

Replace the thumbnail section in `components/episode-card.tsx`. The card should always show a thumbnail, using the YouTube default when `thumbnail_url` is NULL:

```tsx
export function EpisodeCard({ episode, channelSlug }: EpisodeCardProps) {
  const durationMinutes = episode.duration_seconds
    ? Math.floor(episode.duration_seconds / 60)
    : null;

  const href = channelSlug
    ? `/${channelSlug}/episodes/${episode.youtube_id}`
    : `/episodes/${episode.youtube_id}`;

  const thumbnailUrl = episode.thumbnail_url
    || `https://img.youtube.com/vi/${episode.youtube_id}/hqdefault.jpg`;

  return (
    <Link href={href}>
      <Card className="overflow-hidden hover:shadow-lg transition-shadow group">
        <div className="relative w-full aspect-video">
          <Image
            src={thumbnailUrl}
            alt={episode.title}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-300"
          />
          {durationMinutes && (
            <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-2 py-1 rounded">
              {durationMinutes} min
            </span>
          )}
        </div>
        <div className="p-4">
          <h3 className="font-semibold line-clamp-2 mb-2 group-hover:text-primary transition-colors">
            {episode.title}
          </h3>
          {episode.published_at && (
            <span className="text-xs text-muted-foreground">
              {formatDistanceToNow(new Date(episode.published_at), {
                addSuffix: true,
              })}
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
}
```

**Step 2: Verify thumbnails render**

Navigate to `http://localhost:3001/doac/episodes` — all cards should show YouTube thumbnails even though `thumbnail_url` is NULL in the DB.

**Step 3: Commit**

```bash
git add components/episode-card.tsx
git commit -m "feat: fallback to YouTube thumbnail when thumbnail_url is NULL"
```

---

### Task 3: Rebuild Episodes List Page with Search, Sort, Filter, and Grid/List Toggle

**Files:**
- Modify: `app/[channel]/episodes/page.tsx` (server component — data fetching only)
- Create: `components/episodes-list.tsx` (client component — all interactivity)

**Step 1: Create the client component `components/episodes-list.tsx`**

This is the main interactive component. It receives all episodes from the server and handles search, sort, filter, and view toggle client-side.

```tsx
'use client';

import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EpisodeCard } from '@/components/episode-card';
import { Search, LayoutGrid, List, ChevronDown, Users, Calendar } from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import Image from 'next/image';
import Link from 'next/link';

interface Episode {
  id: string;
  youtube_id: string;
  title: string;
  description?: string;
  thumbnail_url?: string;
  published_at?: string;
  duration_seconds?: number;
}

type SortOption = 'newest' | 'oldest' | 'longest' | 'shortest';
type ViewMode = 'grid' | 'list';

interface EpisodesListProps {
  episodes: Episode[];
  channelSlug: string;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function EpisodesList({ episodes, channelSlug }: EpisodesListProps) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortOption>('newest');
  const [view, setView] = useState<ViewMode>('grid');
  const [sortOpen, setSortOpen] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const sortLabels: Record<SortOption, string> = {
    newest: 'Newest first',
    oldest: 'Oldest first',
    longest: 'Longest',
    shortest: 'Shortest',
  };

  const filtered = useMemo(() => {
    let result = episodes;

    // Search by title
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(ep => ep.title.toLowerCase().includes(q));
    }

    // Date range filter
    if (dateFrom) {
      const from = new Date(dateFrom);
      result = result.filter(ep => ep.published_at && new Date(ep.published_at) >= from);
    }
    if (dateTo) {
      const to = new Date(dateTo);
      to.setMonth(to.getMonth() + 1); // include the whole month
      result = result.filter(ep => ep.published_at && new Date(ep.published_at) < to);
    }

    // Sort
    result = [...result].sort((a, b) => {
      switch (sort) {
        case 'newest':
          return (b.published_at || '').localeCompare(a.published_at || '');
        case 'oldest':
          return (a.published_at || '').localeCompare(b.published_at || '');
        case 'longest':
          return (b.duration_seconds || 0) - (a.duration_seconds || 0);
        case 'shortest':
          return (a.duration_seconds || 0) - (b.duration_seconds || 0);
      }
    });

    return result;
  }, [episodes, search, sort, dateFrom, dateTo]);

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search episodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {/* Sort dropdown */}
        <div className="relative">
          <Button
            variant="outline"
            onClick={() => setSortOpen(!sortOpen)}
            className="w-full sm:w-auto justify-between gap-2"
          >
            {sortLabels[sort]}
            <ChevronDown className="h-4 w-4" />
          </Button>
          {sortOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 bg-popover border rounded-md shadow-md z-10">
              {(Object.entries(sortLabels) as [SortOption, string][]).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => { setSort(key); setSortOpen(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent ${sort === key ? 'bg-accent font-medium' : ''}`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* View toggle */}
        <div className="flex border rounded-md">
          <Button
            variant={view === 'grid' ? 'default' : 'ghost'}
            size="icon"
            onClick={() => setView('grid')}
            className="rounded-r-none"
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            variant={view === 'list' ? 'default' : 'ghost'}
            size="icon"
            onClick={() => setView('list')}
            className="rounded-l-none"
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Date range */}
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <input
            type="month"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="text-sm border rounded px-2 py-1 bg-background"
            placeholder="From"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <input
            type="month"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="text-sm border rounded px-2 py-1 bg-background"
          />
          {(dateFrom || dateTo) && (
            <Button variant="ghost" size="sm" onClick={() => { setDateFrom(''); setDateTo(''); }}>
              Clear
            </Button>
          )}
        </div>

        {/* Guest filter (disabled) */}
        <Button variant="outline" size="sm" disabled className="gap-2 opacity-50">
          <Users className="h-4 w-4" />
          Filter by guest
          <span className="text-xs bg-muted px-1.5 py-0.5 rounded">Soon</span>
        </Button>
      </div>

      {/* Results count */}
      <p className="text-sm text-muted-foreground mb-4">
        {filtered.length} episode{filtered.length !== 1 ? 's' : ''}
        {search && ` matching "${search}"`}
      </p>

      {/* Grid view */}
      {view === 'grid' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((episode) => (
            <EpisodeCard key={episode.id} episode={episode} channelSlug={channelSlug} />
          ))}
        </div>
      )}

      {/* List view */}
      {view === 'list' && (
        <div className="space-y-2">
          {filtered.map((episode) => {
            const thumbnailUrl = episode.thumbnail_url
              || `https://img.youtube.com/vi/${episode.youtube_id}/hqdefault.jpg`;
            return (
              <Link key={episode.id} href={`/${channelSlug}/episodes/${episode.youtube_id}`}>
                <div className="flex gap-4 p-3 rounded-lg hover:bg-accent transition-colors group">
                  <div className="relative w-40 aspect-video flex-shrink-0 rounded overflow-hidden">
                    <Image
                      src={thumbnailUrl}
                      alt={episode.title}
                      fill
                      className="object-cover"
                    />
                    {episode.duration_seconds && (
                      <span className="absolute bottom-1 right-1 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded">
                        {formatDuration(episode.duration_seconds)}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium line-clamp-2 group-hover:text-primary transition-colors">
                      {episode.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      {episode.published_at && (
                        <span>{format(new Date(episode.published_at), 'MMM d, yyyy')}</span>
                      )}
                      {episode.duration_seconds && (
                        <span>{formatDuration(episode.duration_seconds)}</span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">
            {search ? `No episodes matching "${search}"` : 'No episodes yet.'}
          </p>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Rewrite the episodes page server component**

Replace `app/[channel]/episodes/page.tsx` to fetch data and delegate rendering to the client component:

```tsx
import { createServerClient } from '@/lib/supabase';
import { EpisodesList } from '@/components/episodes-list';

async function getEpisodes(channelSlug: string) {
  const supabase = createServerClient();

  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();

  if (!channel) return [];

  const { data } = await supabase
    .from('episodes')
    .select('id, youtube_id, title, description, thumbnail_url, published_at, duration_seconds')
    .eq('channel_id', channel.id)
    .not('processed_at', 'is', null)
    .order('published_at', { ascending: false });

  return data || [];
}

export default async function EpisodesPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const episodes = await getEpisodes(channel);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Episodes</h1>
        </div>
        <EpisodesList episodes={episodes} channelSlug={channel} />
      </div>
    </div>
  );
}
```

**Step 3: Verify in browser**

- Navigate to `http://localhost:3001/doac/episodes`
- Test: type in search box — episodes filter by title
- Test: change sort dropdown — order changes
- Test: toggle grid/list view
- Test: set date range (may show no results if published_at is NULL — that's expected)
- Test: guest filter button is disabled with "Soon" badge

**Step 4: Commit**

```bash
git add components/episodes-list.tsx app/[channel]/episodes/page.tsx
git commit -m "feat: episodes list with search, sort, date filter, grid/list toggle"
```

---

### Task 4: Create People Shell Page

**Files:**
- Create: `app/[channel]/people/page.tsx`
- Modify: `components/channel-sidebar.tsx:59` (update Guests link to People)

**Step 1: Create the people page**

Create `app/[channel]/people/page.tsx`:

```tsx
import { Users } from 'lucide-react';

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  await params;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">People</h1>
          <p className="text-muted-foreground">
            Guests and speakers from the show
          </p>
        </div>

        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
            <Users className="h-8 w-8 text-muted-foreground" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Coming Soon</h2>
          <p className="text-muted-foreground max-w-md">
            We&apos;re working on identifying and cataloging all guests.
            This page will feature guest profiles, their episodes, and key topics they discussed.
          </p>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update sidebar navigation**

In `components/channel-sidebar.tsx`, change the Guests nav item (line 59):

```tsx
{ name: 'People', href: `${baseUrl}/people`, icon: Users },
```

**Step 3: Verify in browser**

- Navigate to `http://localhost:3001/doac/people`
- Should show "Coming Soon" centered message
- Sidebar should show "People" instead of "Guests" and highlight when active

**Step 4: Commit**

```bash
git add app/[channel]/people/page.tsx components/channel-sidebar.tsx
git commit -m "feat: add people shell page with coming soon state"
```

---

### Task 5: Update Episode Detail Page with Sidebar Placeholders

**Files:**
- Modify: `app/[channel]/episodes/[id]/page.tsx`

**Step 1: Rewrite the episode detail page**

Replace `app/[channel]/episodes/[id]/page.tsx` with youtube_id routing and sidebar placeholders:

```tsx
import { notFound } from 'next/navigation';
import { createServerClient } from '@/lib/supabase';
import { TranscriptViewer } from '@/components/transcript-viewer';
import { format } from 'date-fns';
import { Clock, Calendar, ExternalLink, FileText, Lightbulb, BookOpen } from 'lucide-react';

async function getEpisode(youtubeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('episodes')
    .select('*')
    .eq('youtube_id', youtubeId)
    .single();
  return data;
}

async function getSegments(episodeId: string) {
  const supabase = createServerClient();
  const { data } = await supabase
    .from('segments')
    .select('id, start_time, end_time, text, speaker, words')
    .eq('episode_id', episodeId)
    .order('start_time');
  return data || [];
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function ComingSoonSection({ icon: Icon, title }: { icon: React.ComponentType<{ className?: string }>; title: string }) {
  return (
    <div className="border rounded-lg p-4 opacity-60">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <p className="text-xs text-muted-foreground">Coming soon</p>
    </div>
  );
}

export default async function EpisodePage({
  params,
}: {
  params: Promise<{ channel: string; id: string }>;
}) {
  const { channel, id } = await params;
  const episode = await getEpisode(id);

  if (!episode) {
    notFound();
  }

  const segments = await getSegments(episode.id);

  const thumbnailUrl = episode.thumbnail_url
    || `https://img.youtube.com/vi/${episode.youtube_id}/hqdefault.jpg`;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="max-w-4xl mb-8">
          <h1 className="text-3xl font-bold mb-4">{episode.title}</h1>

          <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-4">
            {episode.published_at && (
              <div className="flex items-center gap-1">
                <Calendar className="h-4 w-4" />
                {format(new Date(episode.published_at), 'MMM d, yyyy')}
              </div>
            )}
            {episode.duration_seconds && (
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                {formatDuration(episode.duration_seconds)}
              </div>
            )}
            <a
              href={`https://youtube.com/watch?v=${episode.youtube_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-foreground"
            >
              <ExternalLink className="h-4 w-4" />
              Watch on YouTube
            </a>
          </div>

          {episode.description && (
            <p className="text-muted-foreground text-sm whitespace-pre-line line-clamp-4">
              {episode.description}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-8">
            {/* Video Embed */}
            <div className="aspect-video bg-muted rounded-lg overflow-hidden">
              <iframe
                src={`https://www.youtube.com/embed/${episode.youtube_id}?enablejsapi=1`}
                title={episode.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full h-full"
              />
            </div>

            {/* Transcript */}
            {segments.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold mb-4">Transcript</h2>
                <TranscriptViewer
                  segments={segments}
                  youtubeId={episode.youtube_id}
                />
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            <ComingSoonSection icon={FileText} title="Summary" />
            <ComingSoonSection icon={Lightbulb} title="Key Insights" />
            <ComingSoonSection icon={BookOpen} title="Books Mentioned" />
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify in browser**

- Navigate to `http://localhost:3001/doac/episodes/ajgwabD4_HE`
- Should show: title, metadata, YouTube embed, transcript, sidebar with 3 "Coming soon" sections
- Click-to-seek should work in transcript

**Step 3: Commit**

```bash
git add app/[channel]/episodes/[id]/page.tsx
git commit -m "feat: episode detail with youtube_id slug, sidebar placeholders"
```

---

### Task 6: Clean Up Old Guests Route

**Files:**
- Delete: `app/[channel]/guests/page.tsx`

**Step 1: Remove the old guests page**

The `/[channel]/guests` route is replaced by `/[channel]/people`. Delete the old file:

```bash
rm app/[channel]/guests/page.tsx
```

**Step 2: Verify no broken links**

- Navigate to `http://localhost:3001/doac/people` — works
- Navigate to `http://localhost:3001/doac/guests` — should 404 (expected)
- Sidebar "People" link works

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove old guests page, replaced by people"
```

---

### Task 7: Final Verification and Commit

**Step 1: Run type check**

```bash
npx tsc --noEmit
```

Expected: No errors

**Step 2: Test all 3 pages end-to-end**

1. `http://localhost:3001/doac/episodes` — grid of episodes with thumbnails, search works, sort works, view toggle works
2. `http://localhost:3001/doac/people` — "Coming Soon" shell
3. `http://localhost:3001/doac/episodes/{any_youtube_id}` — detail page with video, transcript, sidebar placeholders
4. Click episode card from list — navigates to detail with youtube_id in URL

**Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address any issues from final verification"
```
