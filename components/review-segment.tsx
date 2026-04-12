"use client";

import { useState } from "react";

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

interface ReviewSegmentProps {
  segment: Segment;
  onAccept: (id: string, text: string) => void;
  onSkip: (id: string) => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ReviewSegment({
  segment,
  onAccept,
  onSkip,
}: ReviewSegmentProps) {
  const [editedText, setEditedText] = useState(
    segment.clean_text || segment.text
  );

  return (
    <div className="border border-gray-700 rounded-lg p-4 space-y-3">
      <div className="flex justify-between items-center text-sm text-gray-500">
        <span>
          Segment #{segment.position} [{formatTime(segment.start_time)} -{" "}
          {formatTime(segment.end_time)}]
        </span>
        <span>
          Speaker: {segment.speaker} | Confidence:{" "}
          {(segment.text_confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-medium text-gray-400 mb-1">Whisper</div>
          <div className="bg-gray-900 p-3 rounded text-sm">{segment.text}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-gray-400 mb-1">
            YT Caption
          </div>
          <div className="bg-gray-900 p-3 rounded text-sm">
            {segment.yt_text || (
              <span className="text-gray-600">No YT data</span>
            )}
          </div>
        </div>
      </div>

      <div>
        <div className="text-xs font-medium text-gray-400 mb-1">
          Merged (editable)
        </div>
        <textarea
          className="w-full bg-gray-800 border border-gray-700 rounded p-3 text-sm focus:border-blue-500 focus:outline-none"
          rows={2}
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onAccept(segment.id, editedText)}
          className="px-4 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm transition-colors"
        >
          Accept
        </button>
        <button
          onClick={() => onSkip(segment.id)}
          className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition-colors"
        >
          Skip
        </button>
      </div>
    </div>
  );
}
