"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { ReviewSegment } from "@/components/review-segment";

interface Segment {
  id: string;
  position: number;
  speaker: string;
  text: string;
  clean_text: string | null;
  yt_text: string;
  text_confidence: number;
  start_time: number;
  end_time: number;
}

interface EpisodeData {
  episode: {
    id: string;
    youtube_id: string;
    title: string;
    quality_issues: { type: string; detail: string }[] | null;
  };
  segments: Segment[];
}

export default function ReviewPage() {
  const params = useParams();
  const episodeId = params.episodeId as string;
  const [data, setData] = useState<EpisodeData | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [reviewed, setReviewed] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch(`/api/review/${episodeId}`)
      .then((r) => r.json())
      .then(setData);
  }, [episodeId]);

  const handleAccept = useCallback(
    async (segmentId: string, text: string) => {
      if (!data) return;
      const seg = data.segments.find((s) => s.id === segmentId);
      if (!seg) return;

      await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_id: segmentId,
          episode_id: data.episode.id,
          source: "auto_merge_review",
          original_text: seg.text,
          suggested_text: text,
        }),
      });

      setReviewed((prev) => new Set(prev).add(segmentId));
      setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
    },
    [data]
  );

  const handleSkip = useCallback(
    (segmentId: string) => {
      if (!data) return;
      setReviewed((prev) => new Set(prev).add(segmentId));
      setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
    },
    [data]
  );

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (!data) return;
      if (e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight") {
        setCurrentIdx((prev) => Math.min(prev + 1, data.segments.length - 1));
      } else if (e.key === "ArrowLeft") {
        setCurrentIdx((prev) => Math.max(prev - 1, 0));
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [data]);

  if (!data) return <div className="p-8 text-gray-400">Loading...</div>;

  if (data.segments.length === 0) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <h1 className="text-xl font-bold">{data.episode.title}</h1>
        <p className="text-green-500 mt-4">
          No segments need review — all above confidence threshold.
        </p>
      </div>
    );
  }

  const remaining = data.segments.filter((s) => !reviewed.has(s.id));
  const current = data.segments[currentIdx];

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-xl font-bold">{data.episode.title}</h1>
        <p className="text-sm text-gray-400">
          {data.segments.length} segments to review | {reviewed.size} reviewed |{" "}
          {remaining.length} remaining
        </p>
        {data.episode.quality_issues && data.episode.quality_issues.length > 0 && (
          <div className="mt-2 text-yellow-500 text-sm">
            Quality issues:{" "}
            {data.episode.quality_issues.map((i) => i.detail).join(", ")}
          </div>
        )}
      </div>

      {current && (
        <ReviewSegment
          key={current.id}
          segment={current}
          onAccept={handleAccept}
          onSkip={handleSkip}
        />
      )}

      <div className="flex justify-between text-sm text-gray-500">
        <span>
          ← → to navigate | {currentIdx + 1} / {data.segments.length}
        </span>
      </div>
    </div>
  );
}
