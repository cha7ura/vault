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

      {tab === 'transcript' ? (
        <TranscriptViewer segments={segments} youtubeId={youtubeId} />
      ) : (
        <TranscriptCompare segments={segments} youtubeId={youtubeId} />
      )}
    </div>
  );
}
