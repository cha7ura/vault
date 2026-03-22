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

interface TranscriptCompareProps {
  segments: Segment[];
  youtubeId: string;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
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

interface MatchedPair {
  ourSegment: Segment;
  ytSegment: YTSegment | null;
  ourWords: Word[];
  ytWords: Word[];
  diff: { left: DiffWord[]; right: DiffWord[] } | null;
}

function matchSegments(ours: Segment[], yt: YTSegment[]): MatchedPair[] {
  const usedYt = new Set<number>();

  return ours.map((seg) => {
    const ourWords = parseWords(seg.words);
    let bestIdx = -1;
    let bestDelta = Infinity;

    for (let i = 0; i < yt.length; i++) {
      if (usedYt.has(i)) continue;
      const delta = Math.abs(seg.start_time - yt[i].start_time);
      if (delta < bestDelta) {
        bestDelta = delta;
        bestIdx = i;
      }
    }

    if (bestIdx >= 0 && bestDelta <= 1.0) {
      usedYt.add(bestIdx);
      const ytWords = parseWords(yt[bestIdx].words);
      const ourTexts = ourWords.length > 0 ? ourWords.map((w) => w.text) : seg.text.split(/\s+/).filter(Boolean);
      const ytTexts = ytWords.length > 0 ? ytWords.map((w) => w.text) : yt[bestIdx].text.split(/\s+/).filter(Boolean);
      const diff = wordDiff(ourTexts, ytTexts);

      return {
        ourSegment: seg,
        ytSegment: yt[bestIdx],
        ourWords,
        ytWords,
        diff,
      };
    }

    return {
      ourSegment: seg,
      ytSegment: null,
      ourWords,
      ytWords: [],
      diff: null,
    };
  });
}

export function TranscriptCompare({ segments, youtubeId }: TranscriptCompareProps) {
  const [ytSegments, setYtSegments] = useState<YTSegment[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.85);

  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const isSyncing = useRef(false);

  // Fetch YT segments on mount
  useEffect(() => {
    let cancelled = false;
    async function fetchYT() {
      try {
        const res = await fetch(`/api/episodes/${youtubeId}/yt-segments`);
        if (!res.ok) {
          setYtSegments([]);
          return;
        }
        const data = await res.json();
        if (!cancelled) setYtSegments(data);
      } catch {
        if (!cancelled) setYtSegments([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchYT();
    return () => { cancelled = true; };
  }, [youtubeId]);

  // Synchronized scrolling
  const handleScroll = useCallback((source: 'left' | 'right') => {
    if (isSyncing.current) return;
    isSyncing.current = true;
    const from = source === 'left' ? leftRef.current : rightRef.current;
    const to = source === 'left' ? rightRef.current : leftRef.current;
    if (from && to) {
      to.scrollTop = from.scrollTop;
    }
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  const seekTo = useCallback((time: number) => {
    const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [time, true] }),
        '*'
      );
    }
  }, []);

  const pairs = useMemo(() => {
    if (!ytSegments) return [];
    return matchSegments(segments, ytSegments);
  }, [segments, ytSegments]);

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-card rounded-lg border">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading YouTube captions...</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (!ytSegments || ytSegments.length === 0) {
    return (
      <div className="p-8 bg-card rounded-lg border text-center">
        <p className="text-muted-foreground mb-2">No YouTube captions found for this episode.</p>
        <p className="text-xs text-muted-foreground">
          Fetch them by running:{' '}
          <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
            python scripts/fetch_yt_captions.py --youtube-id {youtubeId}
          </code>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Confidence slider */}
      <div className="flex items-center gap-3 bg-card rounded-lg border px-4 py-3">
        <label htmlFor="confidence-slider" className="text-xs font-medium text-muted-foreground whitespace-nowrap">
          Confidence threshold
        </label>
        <input
          id="confidence-slider"
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={confidenceThreshold}
          onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
          className="flex-1 h-1.5 accent-orange-500"
        />
        <span className="text-xs tabular-nums font-mono text-muted-foreground w-8 text-right">
          {confidenceThreshold.toFixed(2)}
        </span>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid grid-cols-2 gap-0 border rounded-lg overflow-hidden bg-card">
        {/* Column headers */}
        <div className="px-4 py-2.5 border-b border-r bg-muted/50 text-xs font-semibold text-muted-foreground">
          Our Transcript (Whisper + NeMo)
        </div>
        <div className="px-4 py-2.5 border-b bg-muted/50 text-xs font-semibold text-muted-foreground">
          YouTube Auto-Captions
        </div>

        {/* Left column */}
        <div
          ref={leftRef}
          onScroll={() => handleScroll('left')}
          className="max-h-[600px] overflow-y-auto border-r"
        >
          {pairs.map((pair, i) => (
            <div key={i} className="p-3 border-b border-border last:border-b-0">
              <div className="flex items-center gap-2 mb-1.5">
                {pair.ourSegment.speaker && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    {pair.ourSegment.speaker}
                  </span>
                )}
                <button
                  onClick={() => seekTo(pair.ourSegment.start_time)}
                  className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                >
                  {formatTime(pair.ourSegment.start_time)}
                </button>
              </div>
              <p className="text-sm leading-relaxed">
                {pair.diff ? (
                  pair.diff.left.map((dw, wi) => {
                    // Find corresponding original word for confidence score
                    let isLowConfidence = false;
                    if (dw.type !== 'insert') {
                      // Count non-insert words up to this index to map back to ourWords
                      let origIdx = 0;
                      for (let k = 0; k < wi; k++) {
                        if (pair.diff!.left[k].type !== 'insert') origIdx++;
                      }
                      const origWord = pair.ourWords[origIdx];
                      if (origWord?.score !== undefined && origWord.score < confidenceThreshold) {
                        isLowConfidence = true;
                      }
                    }

                    let className = '';
                    if (dw.type === 'delete') {
                      className = 'bg-red-200 dark:bg-red-500/30 rounded-sm px-0.5';
                    } else if (isLowConfidence) {
                      className = 'bg-orange-200 dark:bg-orange-500/30 rounded-sm px-0.5';
                    }

                    return (
                      <span key={wi} className={className}>
                        {dw.text}{' '}
                      </span>
                    );
                  })
                ) : (
                  // No matching YT segment — render plain text with confidence coloring
                  pair.ourWords.length > 0 ? (
                    pair.ourWords.map((w, wi) => {
                      const isLowConfidence = w.score !== undefined && w.score < confidenceThreshold;
                      return (
                        <span
                          key={wi}
                          className={isLowConfidence ? 'bg-orange-200 dark:bg-orange-500/30 rounded-sm px-0.5' : ''}
                        >
                          {w.text}{' '}
                        </span>
                      );
                    })
                  ) : (
                    pair.ourSegment.text
                  )
                )}
              </p>
            </div>
          ))}
        </div>

        {/* Right column */}
        <div
          ref={rightRef}
          onScroll={() => handleScroll('right')}
          className="max-h-[600px] overflow-y-auto"
        >
          {pairs.map((pair, i) => (
            <div key={i} className="p-3 border-b border-border last:border-b-0">
              <div className="flex items-center gap-2 mb-1.5">
                <button
                  onClick={() => seekTo(pair.ytSegment?.start_time ?? pair.ourSegment.start_time)}
                  className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                >
                  {formatTime(pair.ytSegment?.start_time ?? pair.ourSegment.start_time)}
                </button>
              </div>
              <p className="text-sm leading-relaxed">
                {pair.diff ? (
                  pair.diff.right.map((dw, wi) => {
                    let className = '';
                    if (dw.type === 'insert') {
                      className = 'bg-green-200 dark:bg-green-500/30 rounded-sm px-0.5';
                    }
                    return (
                      <span key={wi} className={className}>
                        {dw.text}{' '}
                      </span>
                    );
                  })
                ) : (
                  <span className="text-muted-foreground italic text-xs">No matching caption</span>
                )}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 px-4 py-2.5 bg-card rounded-lg border text-xs text-muted-foreground">
        <span className="font-medium">Legend:</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-red-200 dark:bg-red-500/30 border border-red-300 dark:border-red-500/50" />
          Only in our transcript
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-green-200 dark:bg-green-500/30 border border-green-300 dark:border-green-500/50" />
          Only in YouTube captions
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-orange-200 dark:bg-orange-500/30 border border-orange-300 dark:border-orange-500/50" />
          Low confidence (below {confidenceThreshold.toFixed(2)})
        </span>
      </div>
    </div>
  );
}
