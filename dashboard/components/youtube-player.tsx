"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import YouTube, { YouTubeEvent, YouTubePlayer as YTPlayer } from "react-youtube";

interface YouTubePlayerProps {
  videoId: string;
  onTimeUpdate: (time: number) => void;
}

export function YouTubePlayer({ videoId, onTimeUpdate }: YouTubePlayerProps) {
  const playerRef = useRef<YTPlayer | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      if (playerRef.current) {
        const time = playerRef.current.getCurrentTime();
        if (typeof time === "number") {
          onTimeUpdate(time);
        }
      }
    }, 250);
  }, [onTimeUpdate]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const onReady = (event: YouTubeEvent) => {
    playerRef.current = event.target;
  };

  const onStateChange = (event: YouTubeEvent) => {
    if (event.data === 1) {
      setIsPlaying(true);
      startPolling();
    } else {
      setIsPlaying(false);
      stopPolling();
      if (playerRef.current) {
        onTimeUpdate(playerRef.current.getCurrentTime());
      }
    }
  };

  return (
    <div className="w-full aspect-video bg-black rounded-lg overflow-hidden">
      <YouTube
        videoId={videoId}
        opts={{
          width: "100%",
          height: "100%",
          playerVars: {
            autoplay: 0,
            modestbranding: 1,
            rel: 0,
          },
        }}
        onReady={onReady}
        onStateChange={onStateChange}
        className="w-full h-full"
        iframeClassName="w-full h-full"
      />
    </div>
  );
}
