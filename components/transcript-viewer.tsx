'use client'

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';

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

interface Turn {
  speaker: string;
  startTime: number;
  endTime: number;
  text: string;
  words: Word[];
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

function groupByTurns(segments: Segment[]): Turn[] {
  const turns: Turn[] = [];
  for (const seg of segments) {
    const speaker = seg.speaker || 'Unknown';
    const last = turns[turns.length - 1];
    const segWords = parseWords(seg.words);
    if (last && last.speaker === speaker) {
      last.text += ' ' + seg.text;
      last.endTime = seg.end_time;
      last.words.push(...segWords);
    } else {
      turns.push({
        speaker,
        startTime: seg.start_time,
        endTime: seg.end_time,
        text: seg.text,
        words: [...segWords],
      });
    }
  }
  return turns;
}

// Inactive turns are memoized so they never re-render on currentTime changes
const InactiveTurn = memo(function InactiveTurn({
  turn,
  onSeek,
}: {
  turn: Turn;
  onSeek: (time: number) => void;
}) {
  return (
    <div
      className="p-4 border-b border-border last:border-b-0 border-l-[3px] border-l-transparent hover:bg-muted/30 cursor-pointer"
      onClick={() => onSeek(turn.startTime)}
    >
      <div className="flex items-center gap-3 mb-2">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
          {turn.speaker}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatTime(turn.startTime)}
        </span>
      </div>
      <p className="text-sm leading-relaxed">{turn.text}</p>
    </div>
  );
});

export function TranscriptViewer({ transcript, segments, youtubeId }: TranscriptViewerProps) {
  const [currentTime, setCurrentTime] = useState(-1);
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const activeTurnRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimeout = useRef<ReturnType<typeof setTimeout>>();
  const programmaticScroll = useRef(false);

  useEffect(() => {
    if (!youtubeId) return;

    const onMessage = (e: MessageEvent) => {
      try {
        const data = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
        if (data.event === 'infoDelivery' && data.info?.currentTime !== undefined) {
          setCurrentTime(data.info.currentTime);
        }
      } catch {}
    };

    window.addEventListener('message', onMessage);

    const startListening = () => {
      const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
      if (iframe?.contentWindow) {
        iframe.contentWindow.postMessage(JSON.stringify({ event: 'listening' }), '*');
      }
    };

    const timers = [
      setTimeout(startListening, 500),
      setTimeout(startListening, 1000),
      setTimeout(startListening, 2000),
      setTimeout(startListening, 4000),
    ];

    return () => {
      window.removeEventListener('message', onMessage);
      timers.forEach(clearTimeout);
    };
  }, [youtubeId]);

  const turns = useMemo(
    () => (segments?.length ? groupByTurns(segments) : []),
    [segments]
  );

  const activeTurnIndex = useMemo(() => {
    if (currentTime < 0 || turns.length === 0) return -1;
    for (let i = turns.length - 1; i >= 0; i--) {
      if (currentTime >= turns[i].startTime) return i;
    }
    return -1;
  }, [currentTime, turns]);

  // Auto-scroll within container only — never moves the page
  useEffect(() => {
    if (!autoScroll || activeTurnIndex < 0 || userScrolling.current) return;
    const el = activeTurnRef.current;
    const container = containerRef.current;
    if (el && container) {
      const targetTop = el.offsetTop;
      if (Math.abs(container.scrollTop - targetTop) > 20) {
        programmaticScroll.current = true;
        container.scrollTo({ top: targetTop, behavior: 'smooth' });
        setTimeout(() => { programmaticScroll.current = false; }, 500);
      }
    }
  }, [activeTurnIndex, autoScroll]);

  const handleScroll = useCallback(() => {
    if (programmaticScroll.current) return;
    userScrolling.current = true;
    if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
    scrollTimeout.current = setTimeout(() => {
      userScrolling.current = false;
    }, 4000);
  }, []);

  const seekTo = useCallback((time: number) => {
    if (!youtubeId) return;
    const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [time, true] }),
        '*'
      );
    }
  }, [youtubeId]);

  if (!segments || segments.length === 0) {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert bg-card p-6 rounded-lg border">
        <ReactMarkdown>{transcript || ''}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="flex items-center justify-end gap-2 mb-2">
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`text-xs px-2 py-1 rounded transition-colors ${
            autoScroll
              ? 'bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 font-medium'
              : 'bg-muted text-muted-foreground hover:text-foreground'
          }`}
        >
          {autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
        </button>
      </div>

      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="bg-card rounded-lg border max-h-[600px] overflow-y-auto"
      >
        {turns.map((turn, i) => {
          if (i !== activeTurnIndex) {
            return <InactiveTurn key={i} turn={turn} onSeek={seekTo} />;
          }

          // Only the active turn renders individual word spans
          return (
            <div
              key={i}
              ref={activeTurnRef}
              className="p-4 border-b border-border last:border-b-0 border-l-[3px] bg-yellow-50 dark:bg-yellow-500/[0.07] border-l-yellow-500"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-400/30 text-yellow-800 dark:text-yellow-300">
                  {turn.speaker}
                </span>
                <button
                  onClick={() => seekTo(turn.startTime)}
                  className="text-xs tabular-nums text-yellow-700 dark:text-yellow-400 font-medium hover:underline"
                >
                  {formatTime(turn.startTime)}
                </button>
              </div>

              <p className="text-sm leading-relaxed">
                {turn.words.length > 0 ? (
                  turn.words.map((word, wi) => {
                    const isCurrentWord =
                      currentTime >= word.start && currentTime < word.end;
                    return (
                      <span
                        key={wi}
                        onClick={(e) => { e.stopPropagation(); seekTo(word.start); }}
                        className={`cursor-pointer rounded-sm ${
                          isCurrentWord
                            ? 'bg-yellow-300 dark:bg-yellow-500/40 text-yellow-900 dark:text-yellow-100 font-medium px-0.5'
                            : 'hover:bg-yellow-200/50 dark:hover:bg-yellow-500/20'
                        }`}
                      >
                        {word.text}{' '}
                      </span>
                    );
                  })
                ) : (
                  turn.text
                )}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
