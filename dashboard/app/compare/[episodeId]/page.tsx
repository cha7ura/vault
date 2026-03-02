"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { use } from "react";
import YouTube, { YouTubeEvent } from "react-youtube";
import { TranscriptPanel } from "@/components/transcript-panel";
import { formatTime } from "@/lib/utils";
import { fetchEpisode, fetchSegments, fetchBenchmarks } from "@/lib/api";
import type { Episode, Segment, BenchmarkData } from "@/lib/types";

export default function ComparePage({
  params,
}: {
  params: Promise<{ episodeId: string }>;
}) {
  const { episodeId } = use(params);
  const id = parseInt(episodeId, 10);

  const [episode, setEpisode] = useState<Episode | null>(null);
  const [pyannoteSegments, setPyannoteSegments] = useState<Segment[]>([]);
  const [whisperSegments, setWhisperSegments] = useState<Segment[]>([]);
  const [benchmarks, setBenchmarks] = useState<BenchmarkData[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const playerRef = useRef<any>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch data
  useEffect(() => {
    async function load() {
      try {
        const [ep, pySegs, wdSegs, bm] = await Promise.all([
          fetchEpisode(id),
          fetchSegments(id, "pyannote"),
          fetchSegments(id, "whisper-diarization"),
          fetchBenchmarks(id),
        ]);
        setEpisode(ep);
        setPyannoteSegments(pySegs);
        setWhisperSegments(wdSegs);
        setBenchmarks(bm);
      } catch (e: any) {
        setError(e.message);
      }
    }
    load();
  }, [id]);

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

  const pyBenchmark = benchmarks.find((b) => b.diarizer === "pyannote") ?? null;
  const wdBenchmark = benchmarks.find((b) => b.diarizer === "whisper-diarization") ?? null;

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3 border-b">
        <h1 className="font-semibold truncate flex-1">{episode.title}</h1>
        <span className="text-sm text-muted-foreground">
          {formatTime(currentTime)}
          {episode.duration ? ` / ${formatTime(episode.duration)}` : ""}
        </span>
      </header>

      {/* YouTube Player */}
      <div className="w-full max-w-4xl mx-auto px-4 pt-4">
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

      {/* Transcript Panels */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-0 border-t mt-4 min-h-0">
        <div className="border-r min-h-0 flex flex-col">
          <TranscriptPanel
            title="PyAnnote"
            segments={pyannoteSegments}
            currentTime={currentTime}
            benchmark={pyBenchmark}
            onSeek={seekTo}
          />
        </div>
        <div className="min-h-0 flex flex-col">
          <TranscriptPanel
            title="whisper-diarization"
            segments={whisperSegments}
            currentTime={currentTime}
            benchmark={wdBenchmark}
            onSeek={seekTo}
          />
        </div>
      </div>
    </div>
  );
}
