"use client";

import { useMemo, useRef, useEffect } from "react";
import { formatTime } from "@/lib/utils";
import type { Segment } from "@/lib/types";

interface DiffPanelProps {
  leftLabel: string;
  rightLabel: string;
  leftSegments: Segment[];
  rightSegments: Segment[];
  currentTime: number;
  onSeek: (seconds: number) => void;
}

interface DiffRow {
  startTime: number;
  endTime: number;
  text: string;
  leftSpeaker: string;
  rightSpeaker: string;
}

/**
 * Build optimal speaker label mapping between two diarizers using
 * time-overlap-based voting (greedy best match).
 */
function buildSpeakerMapping(
  left: Segment[],
  right: Segment[]
): Map<string, string> {
  // Count overlap time between each (leftSpeaker, rightSpeaker) pair
  const overlap = new Map<string, Map<string, number>>();

  for (const l of left) {
    for (const r of right) {
      const oStart = Math.max(l.start_time, r.start_time);
      const oEnd = Math.min(l.end_time, r.end_time);
      if (oEnd <= oStart) continue;
      if (!l.speaker || !r.speaker) continue;

      if (!overlap.has(r.speaker)) overlap.set(r.speaker, new Map());
      const inner = overlap.get(r.speaker)!;
      inner.set(l.speaker, (inner.get(l.speaker) ?? 0) + (oEnd - oStart));
    }
  }

  // Greedy mapping: for each right speaker, pick the left speaker with most overlap
  const mapping = new Map<string, string>();
  const usedLeft = new Set<string>();

  // Sort right speakers by total overlap (descending) for stable greedy
  const rightSpeakers = [...overlap.entries()].sort((a, b) => {
    const totalA = [...a[1].values()].reduce((s, v) => s + v, 0);
    const totalB = [...b[1].values()].reduce((s, v) => s + v, 0);
    return totalB - totalA;
  });

  for (const [rSpeaker, leftMap] of rightSpeakers) {
    let bestLeft = "";
    let bestTime = 0;
    for (const [lSpeaker, time] of leftMap) {
      if (!usedLeft.has(lSpeaker) && time > bestTime) {
        bestLeft = lSpeaker;
        bestTime = time;
      }
    }
    if (bestLeft) {
      mapping.set(rSpeaker, bestLeft);
      usedLeft.add(bestLeft);
    }
  }

  return mapping;
}

/**
 * Find segments where the two diarizers assigned different speakers
 * for the same time region.
 */
function findDifferences(
  left: Segment[],
  right: Segment[],
  speakerMap: Map<string, string>
): DiffRow[] {
  const diffs: DiffRow[] = [];

  for (const r of right) {
    // Find overlapping left segments
    for (const l of left) {
      const oStart = Math.max(l.start_time, r.start_time);
      const oEnd = Math.min(l.end_time, r.end_time);
      if (oEnd - oStart < 0.1) continue; // skip tiny overlaps

      const mappedRight = speakerMap.get(r.speaker ?? "") ?? r.speaker ?? "?";
      const leftSpeaker = l.speaker ?? "?";

      if (mappedRight !== leftSpeaker) {
        // Extract text for the overlapping time range (approximate from left)
        const text = l.text.length < 120 ? l.text : l.text.slice(0, 120) + "…";

        diffs.push({
          startTime: oStart,
          endTime: oEnd,
          text,
          leftSpeaker,
          rightSpeaker: r.speaker ?? "?",
        });
      }
    }
  }

  // Sort by time and deduplicate overlapping ranges
  diffs.sort((a, b) => a.startTime - b.startTime);

  // Merge adjacent/overlapping diffs
  const merged: DiffRow[] = [];
  for (const d of diffs) {
    const last = merged[merged.length - 1];
    if (last && d.startTime - last.endTime < 0.5 && d.leftSpeaker === last.leftSpeaker && d.rightSpeaker === last.rightSpeaker) {
      last.endTime = Math.max(last.endTime, d.endTime);
      if (last.text !== d.text) {
        last.text = last.text.length < 200 ? last.text : last.text.slice(0, 200) + "…";
      }
    } else {
      merged.push({ ...d });
    }
  }

  return merged;
}

export function DiffPanel({
  leftLabel,
  rightLabel,
  leftSegments,
  rightSegments,
  currentTime,
  onSeek,
}: DiffPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLTableRowElement>(null);
  const lastScrolled = useRef(-1);

  const speakerMap = useMemo(
    () => buildSpeakerMapping(leftSegments, rightSegments),
    [leftSegments, rightSegments]
  );

  const diffs = useMemo(
    () => findDifferences(leftSegments, rightSegments, speakerMap),
    [leftSegments, rightSegments, speakerMap]
  );

  const activeIndex = useMemo(() => {
    for (let i = diffs.length - 1; i >= 0; i--) {
      if (diffs[i].startTime <= currentTime && diffs[i].endTime >= currentTime) {
        return i;
      }
    }
    return -1;
  }, [diffs, currentTime]);

  useEffect(() => {
    if (activeIndex >= 0 && activeIndex !== lastScrolled.current && activeRef.current) {
      lastScrolled.current = activeIndex;
      activeRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeIndex]);

  // Build mapping description
  const mapDesc = [...speakerMap.entries()]
    .map(([r, l]) => `${r} → ${l}`)
    .join(", ");

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-border bg-muted/30">
        <h3 className="font-semibold text-sm">
          Differences
        </h3>
        <p className="text-xs text-muted-foreground">
          {diffs.length} disagreement{diffs.length !== 1 ? "s" : ""}
          {mapDesc && ` · Mapping: ${mapDesc}`}
        </p>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto">
        {diffs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            No speaker disagreements found
          </div>
        ) : (
          <table className="w-full border-collapse">
            <thead className="sticky top-0 bg-background z-10">
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="text-left font-medium px-4 py-2 w-[72px]">Time</th>
                <th className="text-left font-medium px-3 py-2 w-[90px]">{leftLabel}</th>
                <th className="text-left font-medium px-3 py-2 w-[90px]">{rightLabel}</th>
                <th className="text-left font-medium px-4 py-2">Text</th>
              </tr>
            </thead>
            <tbody>
              {diffs.map((d, i) => {
                const isActive = i === activeIndex;
                const isPast = d.endTime < currentTime;

                return (
                  <tr
                    key={`${d.startTime}-${i}`}
                    ref={isActive ? activeRef : undefined}
                    onClick={() => onSeek(d.startTime)}
                    className={`
                      border-b border-border align-top cursor-pointer transition-colors
                      ${isActive ? "bg-red-500/10" : ""}
                      ${isPast ? "opacity-50" : ""}
                      ${!isActive && !isPast ? "hover:bg-muted/20" : ""}
                    `}
                  >
                    <td className="px-4 py-3 text-xs text-muted-foreground font-mono whitespace-nowrap">
                      {formatTime(d.startTime)}
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs font-semibold text-blue-400">
                        {d.leftSpeaker}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs font-semibold text-emerald-400">
                        {d.rightSpeaker}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm leading-relaxed text-muted-foreground">
                      {d.text}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
