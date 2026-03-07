'use client'

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
  if (!segments || segments.length === 0) {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert bg-card p-6 rounded-lg border">
        <ReactMarkdown>{transcript || ''}</ReactMarkdown>
      </div>
    );
  }

  const turns = groupByTurns(segments);

  const seekTo = (time: number) => {
    if (!youtubeId) return;
    const iframe = document.querySelector('iframe[src*="youtube"]') as HTMLIFrameElement;
    if (iframe) {
      iframe.contentWindow?.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [time, true] }),
        '*'
      );
    }
  };

  return (
    <div className="bg-card rounded-lg border divide-y max-h-[600px] overflow-y-auto">
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
