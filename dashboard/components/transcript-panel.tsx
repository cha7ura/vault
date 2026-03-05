"use client";

import { useEffect, useRef, useMemo, useCallback, useState } from "react";
import { formatTime } from "@/lib/utils";
import type { Segment, BenchmarkData, SpeakerTurn, WordTiming } from "@/lib/types";
import { groupBySpeaker, getWordTimings } from "@/lib/types";

interface TranscriptPanelProps {
  title: string;
  segments: Segment[];
  currentTime: number;
  benchmark: BenchmarkData | null;
  onSeek: (seconds: number) => void;
}

/** Renders a segment's text with word-by-word yellow highlight during playback. */
function HighlightedSegment({
  segment,
  currentTime,
  isActiveTurn,
  onSeek,
}: {
  segment: Segment;
  currentTime: number;
  isActiveTurn: boolean;
  onSeek: (seconds: number) => void;
}) {
  const words = useMemo(() => getWordTimings(segment), [segment]);

  // Build per-word YouTube text lookup from segment.youtube_text
  const ytWords = useMemo(() => {
    if (!segment.youtube_text) return null;
    return segment.youtube_text.split(/\s+/).filter(Boolean);
  }, [segment.youtube_text]);

  const isActiveSegment =
    isActiveTurn &&
    currentTime >= segment.start_time &&
    currentTime < segment.end_time;

  if (!isActiveSegment) {
    // Past segments in the active turn get subtle highlight to show they've been spoken
    const isPastInTurn = isActiveTurn && currentTime >= segment.end_time;
    return (
      <span
        className={`cursor-pointer hover:bg-muted/50 rounded-sm ${isPastInTurn ? "text-foreground/50" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          onSeek(segment.start_time);
        }}
      >
        {segment.text}{" "}
      </span>
    );
  }

  return (
    <>
      {words.map((w, i) => {
        const isPast = currentTime >= w.end;
        const isCurrent = currentTime >= w.start && currentTime < w.end;
        const isLowConfidence = w.score != null && w.score < 0.7;

        return (
          <span
            key={i}
            onClick={(e) => {
              e.stopPropagation();
              onSeek(w.start);
            }}
            title={
              w.score != null
                ? (() => {
                    let tip = `Confidence: ${Math.round(w.score * 100)}%`;
                    const ytWord = ytWords?.[i];
                    if (
                      ytWord &&
                      ytWord.toLowerCase() !== w.word.replace(/[.,!?;:]+$/, "").toLowerCase()
                    ) {
                      tip += ` | YouTube: '${ytWord}'`;
                    }
                    return tip;
                  })()
                : undefined
            }
            className={`cursor-pointer ${
              isCurrent
                ? isLowConfidence
                  ? "bg-red-400 text-black rounded-sm px-[1px] transition-colors duration-75"
                  : "bg-yellow-400 text-black rounded-sm px-[1px] transition-colors duration-75"
                : isPast
                  ? "bg-yellow-400/25 rounded-sm px-[1px]"
                  : "hover:bg-muted/50 rounded-sm"
            }`}
            style={
              isLowConfidence && !isCurrent
                ? {
                    textDecoration: "underline wavy",
                    textDecorationColor: "rgb(248 113 113)",
                    textUnderlineOffset: "3px",
                  }
                : undefined
            }
          >
            {w.word}{" "}
          </span>
        );
      })}
    </>
  );
}

export function TranscriptPanel({
  title,
  segments,
  currentTime,
  benchmark,
  onSeek,
}: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLTableRowElement>(null);
  const lastScrolledTurn = useRef<number>(-1);

  const speakers = useMemo(() => {
    const seen = new Set<string>();
    for (const seg of segments) {
      if (seg.speaker) seen.add(seg.speaker);
    }
    return Array.from(seen);
  }, [segments]);

  const turns = useMemo(() => groupBySpeaker(segments), [segments]);

  const activeTurnIndex = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].startTime <= currentTime) {
        return i;
      }
    }
    return -1;
  }, [turns, currentTime]);

  // Only scroll when the active turn CHANGES (i.e. when speaker finishes)
  useEffect(() => {
    if (
      activeTurnIndex >= 0 &&
      activeTurnIndex !== lastScrolledTurn.current &&
      activeRef.current
    ) {
      lastScrolledTurn.current = activeTurnIndex;
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeTurnIndex]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
        <div>
          <h3 className="font-semibold text-sm">{title}</h3>
          <p className="text-xs text-muted-foreground">
            {speakers.length} speaker{speakers.length !== 1 ? "s" : ""}
            {" · "}
            {turns.length} turns
          </p>
        </div>
        {benchmark && benchmark.duration_s && (
          <span className="text-xs text-muted-foreground">
            {benchmark.duration_s.toFixed(1)}s
          </span>
        )}
      </div>

      {/* Table */}
      <div ref={containerRef} className="flex-1 overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-background z-10">
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="text-left font-medium px-4 py-2 w-[72px]">Time</th>
              <th className="text-left font-medium px-3 py-2 w-[80px]">Speaker</th>
              <th className="text-left font-medium px-4 py-2">Text</th>
            </tr>
          </thead>
          <tbody>
            {turns.map((turn, ti) => {
              const isActive = ti === activeTurnIndex;
              const isPast = ti < activeTurnIndex;

              return (
                <tr
                  key={`${turn.speaker}-${turn.startTime}`}
                  ref={isActive ? activeRef : undefined}
                  onClick={() => onSeek(turn.startTime)}
                  className={`
                    border-b border-border align-top cursor-pointer transition-colors
                    ${isActive ? "bg-muted/50" : ""}
                    ${isPast ? "opacity-50" : ""}
                    ${!isActive && !isPast ? "hover:bg-muted/20" : ""}
                  `}
                >
                  {/* Start Time */}
                  <td className="px-4 py-3 text-xs text-muted-foreground font-mono whitespace-nowrap">
                    {formatTime(turn.startTime)}
                  </td>

                  {/* Speaker */}
                  <td className="px-3 py-3">
                    <span
                      className={`text-xs font-semibold ${
                        isActive ? "text-foreground" : "text-muted-foreground"
                      }`}
                    >
                      {turn.speaker ?? "Unknown"}
                    </span>
                  </td>

                  {/* Text — all segments merged with word highlight */}
                  <td className="px-4 py-3 text-sm leading-relaxed">
                    {turn.segments.map((seg) => (
                      <HighlightedSegment
                        key={seg.id}
                        segment={seg}
                        currentTime={currentTime}
                        isActiveTurn={isActive}
                        onSeek={onSeek}
                      />
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
