"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { use } from "react";
import YouTube, { YouTubeEvent } from "react-youtube";
import { TranscriptPanel } from "@/components/transcript-panel";
import { DiffPanel } from "@/components/diff-panel";
import { formatTime } from "@/lib/utils";
import { fetchEpisode, fetchSegments } from "@/lib/api";
import type { Episode, Segment } from "@/lib/types";

const DIARIZERS = ["nemo-msdd", "pyannote-3.1"] as const;

function labelFor(d: string) {
  if (d.includes("msdd") || d.includes("nemo")) return "NeMo MSDD";
  if (d.includes("pyannote")) return "Pyannote 3.1";
  return d;
}

export default function ComparePage({
  params,
}: {
  params: Promise<{ episodeId: string }>;
}) {
  const { episodeId } = use(params);

  const [episode, setEpisode] = useState<Episode | null>(null);
  const [segmentsByDiarizer, setSegmentsByDiarizer] = useState<
    Record<string, Segment[]>
  >({});
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const playerRef = useRef<any>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch episode + segments for both diarizers
  useEffect(() => {
    async function load() {
      try {
        const ep = await fetchEpisode(episodeId);
        setEpisode(ep);

        const results = await Promise.all(
          DIARIZERS.map(async (d) => ({
            diarizer: d,
            segments: await fetchSegments(episodeId, d),
          }))
        );

        const map: Record<string, Segment[]> = {};
        for (const { diarizer, segments } of results) {
          if (segments.length > 0) map[diarizer] = segments;
        }
        setSegmentsByDiarizer(map);
      } catch (e: any) {
        setError(e.message);
      }
    }
    load();
  }, [episodeId]);

  // YouTube polling
  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      if (playerRef.current) {
        const t = playerRef.current.getCurrentTime();
        if (typeof t === "number") setCurrentTime(t);
      }
    }, 100);
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
      playerRef.current.playVideo();
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

  const diarizers = Object.keys(segmentsByDiarizer);

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3 border-b">
        <h1 className="font-semibold truncate flex-1">{episode.title}</h1>
        <span className="text-sm text-muted-foreground">
          {formatTime(currentTime)}
          {episode.duration ? ` / ${formatTime(episode.duration)}` : ""}
        </span>
        <span className="text-xs px-2 py-1 bg-muted rounded">
          {diarizers.length} diarizer{diarizers.length !== 1 ? "s" : ""}
        </span>
      </header>

      {/* YouTube Player */}
      <div className="w-full max-w-3xl mx-auto px-4 pt-4">
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

      {/* Side-by-side transcript panels + diff */}
      <div
        className="flex-1 border-t mt-4 min-h-0 grid gap-0"
        style={{
          gridTemplateColumns:
            diarizers.length >= 2 ? "1fr 1fr 1fr" : `repeat(${diarizers.length}, 1fr)`,
        }}
      >
        {diarizers.map((d, i) => (
          <div
            key={d}
            className={`min-h-0 overflow-hidden ${
              i > 0 ? "border-l border-border" : ""
            }`}
          >
            <TranscriptPanel
              title={labelFor(d)}
              segments={segmentsByDiarizer[d]}
              currentTime={currentTime}
              benchmark={null}
              onSeek={seekTo}
            />
          </div>
        ))}
        {diarizers.length >= 2 && (
          <div className="min-h-0 overflow-hidden border-l border-border">
            <DiffPanel
              leftLabel={labelFor(diarizers[0])}
              rightLabel={labelFor(diarizers[1])}
              leftSegments={segmentsByDiarizer[diarizers[0]]}
              rightSegments={segmentsByDiarizer[diarizers[1]]}
              currentTime={currentTime}
              onSeek={seekTo}
            />
          </div>
        )}
      </div>
    </div>
  );
}
