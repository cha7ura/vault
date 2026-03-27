'use client'

import { useState } from 'react';
import { TranscriptViewer } from './transcript-viewer';
import { TranscriptCompare } from './transcript-compare';
import { DiarizeCompare } from './diarize-compare';

interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  words?: any;
  diarizer?: string;
}

interface EpisodeTranscriptTabsProps {
  segments: Segment[];
  youtubeId: string;
}

export function EpisodeTranscriptTabs({ segments, youtubeId }: EpisodeTranscriptTabsProps) {
  const [tab, setTab] = useState<'transcript' | 'compare' | 'diarize'>('transcript');
  const isDev = process.env.NODE_ENV === 'development';

  // Check if we have segments from multiple diarizers
  const diarizers = [...new Set(segments.map(s => s.diarizer).filter(Boolean))];
  const hasMultipleDiarizers = diarizers.length > 1;

  return (
    <div>
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
            vs YouTube
          </button>
        )}
        {hasMultipleDiarizers && (
          <button
            onClick={() => setTab('diarize')}
            className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
              tab === 'diarize'
                ? 'bg-blue-500 text-white font-medium'
                : 'bg-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            MSDD vs Pyannote
          </button>
        )}
      </div>

      {tab === 'transcript' ? (
        <TranscriptViewer segments={segments} youtubeId={youtubeId} />
      ) : tab === 'compare' ? (
        <TranscriptCompare segments={segments} youtubeId={youtubeId} />
      ) : (
        <DiarizeCompare segments={segments} youtubeId={youtubeId} diarizers={diarizers} />
      )}
    </div>
  );
}
