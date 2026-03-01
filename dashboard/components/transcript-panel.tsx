"use client";

import { useEffect, useRef, useMemo } from "react";
import { formatTime } from "@/lib/utils";
import type { Segment, BenchmarkData } from "@/lib/types";
import { getSpeakerColor } from "@/lib/types";

interface TranscriptPanelProps {
  title: string;
  segments: Segment[];
  currentTime: number;
  benchmark: BenchmarkData | null;
  onSeek: (seconds: number) => void;
}

export function TranscriptPanel({
  title,
  segments,
  currentTime,
  benchmark,
  onSeek,
}: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  const speakers = useMemo(() => {
    const seen = new Set<string>();
    for (const seg of segments) {
      if (seg.speaker) seen.add(seg.speaker);
    }
    return Array.from(seen);
  }, [segments]);

  const activeIndex = useMemo(() => {
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i].start_time <= currentTime) {
        return i;
      }
    }
    return -1;
  }, [segments, currentTime]);

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeIndex]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
        <div>
          <h3 className="font-semibold text-sm">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {speakers.length} speaker{speakers.length !== 1 ? "s" : ""}
            {" · "}
            {segments.length} segments
          </p>
        </div>
        {benchmark && benchmark.duration_s && (
          <span className="text-xs text-muted-foreground">
            ⏱ {benchmark.duration_s.toFixed(1)}s
          </span>
        )}
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto">
        {segments.map((seg, i) => {
          const isActive = i === activeIndex;
          const color = getSpeakerColor(seg.speaker, speakers);
          const isMuted = seg.tag === "intro" || seg.tag === "ad" || seg.tag === "subscribe";

          return (
            <div
              key={seg.id}
              ref={isActive ? activeRef : undefined}
              onClick={() => onSeek(seg.start_time)}
              className={`
                px-4 py-2 border-l-4 cursor-pointer transition-colors
                ${isActive ? `${color.bg} ${color.border}` : `border-l-transparent hover:bg-muted/30`}
                ${isMuted ? "opacity-50" : ""}
              `}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`text-xs font-medium ${isActive ? color.text : "text-muted-foreground"}`}>
                  {seg.speaker ?? "Unknown"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatTime(seg.start_time)}
                </span>
                {isMuted && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground uppercase">
                    {seg.tag}
                  </span>
                )}
              </div>
              <p className={`text-sm leading-relaxed ${isActive ? "text-foreground" : "text-foreground/80"}`}>
                {seg.text}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
