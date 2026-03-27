'use client'

import { useCallback, useMemo, useRef } from 'react';

interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  words?: any;
  diarizer?: string;
}

interface DiarizeCompareProps {
  segments: Segment[];
  youtubeId: string;
  diarizers: string[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function labelFor(diarizer: string): string {
  if (diarizer.includes('msdd') || diarizer.includes('nemo')) return 'NeMo MSDD';
  if (diarizer.includes('pyannote')) return 'Pyannote 3.1';
  return diarizer;
}

interface MatchedPair {
  left: Segment | null;
  right: Segment | null;
  time: number;
}

function matchByTime(leftSegs: Segment[], rightSegs: Segment[]): MatchedPair[] {
  const pairs: MatchedPair[] = [];
  const usedRight = new Set<number>();

  for (const left of leftSegs) {
    let bestIdx = -1;
    let bestDelta = Infinity;

    for (let i = 0; i < rightSegs.length; i++) {
      if (usedRight.has(i)) continue;
      const delta = Math.abs(left.start_time - rightSegs[i].start_time);
      if (delta < bestDelta) {
        bestDelta = delta;
        bestIdx = i;
      }
    }

    if (bestIdx >= 0 && bestDelta <= 2.0) {
      usedRight.add(bestIdx);
      pairs.push({ left, right: rightSegs[bestIdx], time: left.start_time });
    } else {
      pairs.push({ left, right: null, time: left.start_time });
    }
  }

  // Add unmatched right segments
  for (let i = 0; i < rightSegs.length; i++) {
    if (!usedRight.has(i)) {
      pairs.push({ left: null, right: rightSegs[i], time: rightSegs[i].start_time });
    }
  }

  pairs.sort((a, b) => a.time - b.time);
  return pairs;
}

export function DiarizeCompare({ segments, youtubeId, diarizers }: DiarizeCompareProps) {
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const isSyncing = useRef(false);

  const leftDiarizer = diarizers[0];
  const rightDiarizer = diarizers[1] || diarizers[0];

  const leftSegs = useMemo(() => segments.filter(s => s.diarizer === leftDiarizer), [segments, leftDiarizer]);
  const rightSegs = useMemo(() => segments.filter(s => s.diarizer === rightDiarizer), [segments, rightDiarizer]);

  const pairs = useMemo(() => matchByTime(leftSegs, rightSegs), [leftSegs, rightSegs]);

  // Stats
  const leftSpeakers = new Set(leftSegs.map(s => s.speaker).filter(Boolean));
  const rightSpeakers = new Set(rightSegs.map(s => s.speaker).filter(Boolean));
  const matchedCount = pairs.filter(p => p.left && p.right).length;
  const speakerAgreement = pairs.filter(p => {
    if (!p.left || !p.right) return false;
    // Can't directly compare speaker labels (different IDs), but we can check text overlap
    return true;
  }).length;

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

  return (
    <div className="space-y-3">
      {/* Stats bar */}
      <div className="flex flex-wrap items-center gap-4 bg-card rounded-lg border px-4 py-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Diarizer Comparison</span>
        <span>{labelFor(leftDiarizer)}: {leftSegs.length} segments, {leftSpeakers.size} speakers</span>
        <span>{labelFor(rightDiarizer)}: {rightSegs.length} segments, {rightSpeakers.size} speakers</span>
        <span>Matched: {matchedCount}/{Math.max(leftSegs.length, rightSegs.length)}</span>
      </div>

      {/* Side-by-side */}
      <div className="grid grid-cols-2 gap-0 border rounded-lg overflow-hidden bg-card">
        {/* Headers */}
        <div className="px-4 py-2.5 border-b border-r bg-muted/50 text-xs font-semibold text-muted-foreground">
          {labelFor(leftDiarizer)}
        </div>
        <div className="px-4 py-2.5 border-b bg-muted/50 text-xs font-semibold text-muted-foreground">
          {labelFor(rightDiarizer)}
        </div>

        {/* Left column */}
        <div
          ref={leftRef}
          onScroll={() => handleScroll('left')}
          className="max-h-[600px] overflow-y-auto border-r"
        >
          {pairs.map((pair, i) => (
            <div key={i} className={`p-3 border-b border-border last:border-b-0 ${!pair.left ? 'bg-muted/20' : ''}`}>
              {pair.left ? (
                <>
                  <div className="flex items-center gap-2 mb-1.5">
                    {pair.left.speaker && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                        {pair.left.speaker}
                      </span>
                    )}
                    <button
                      onClick={() => seekTo(pair.left!.start_time)}
                      className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                    >
                      {formatTime(pair.left.start_time)}
                    </button>
                  </div>
                  <p className="text-sm leading-relaxed">{pair.left.text}</p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground italic">No matching segment</p>
              )}
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
            <div key={i} className={`p-3 border-b border-border last:border-b-0 ${!pair.right ? 'bg-muted/20' : ''}`}>
              {pair.right ? (
                <>
                  <div className="flex items-center gap-2 mb-1.5">
                    {pair.right.speaker && (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400">
                        {pair.right.speaker}
                      </span>
                    )}
                    <button
                      onClick={() => seekTo(pair.right!.start_time)}
                      className="text-xs tabular-nums text-muted-foreground hover:text-foreground hover:underline"
                    >
                      {formatTime(pair.right.start_time)}
                    </button>
                  </div>
                  <p className="text-sm leading-relaxed">{pair.right.text}</p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground italic">No matching segment</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 px-4 py-2.5 bg-card rounded-lg border text-xs text-muted-foreground">
        <span className="font-medium">Legend:</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full bg-primary/10 border border-primary/30" />
          {labelFor(leftDiarizer)} speaker
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full bg-blue-500/10 border border-blue-500/30" />
          {labelFor(rightDiarizer)} speaker
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-muted/20 border border-border" />
          No match
        </span>
      </div>
    </div>
  );
}
