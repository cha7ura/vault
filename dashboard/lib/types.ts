export interface WordData {
  text: string;
  start: number;
  end: number;
  score: number | null;
}

export interface Segment {
  id: string;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  tag: string;
  words?: WordData[] | null;
  youtube_text?: string | null;
  diarizer: string;
}

export interface BenchmarkData {
  id: string;
  diarizer: string;
  duration_s: number | null;
  wer: number | null;
  der: number | null;
  notes: string | null;
}

export interface Episode {
  id: string;
  youtube_id: string;
  title: string;
  status: string;
  duration: number | null;
  intro_end_at: number | null;
}

/** Consecutive segments from the same speaker, grouped as a single turn. */
export interface SpeakerTurn {
  speaker: string | null;
  segments: Segment[];
  startTime: number;
  endTime: number;
}

/** Word timing — real from API or interpolated from segment timestamps. */
export interface WordTiming {
  word: string;
  start: number;
  end: number;
  score?: number | null;
}

const SPEAKER_COLORS = [
  {
    bg: "bg-blue-500/10",
    border: "border-l-blue-500",
    text: "text-blue-400",
    label: "bg-blue-500/20 text-blue-300",
  },
  {
    bg: "bg-emerald-500/10",
    border: "border-l-emerald-500",
    text: "text-emerald-400",
    label: "bg-emerald-500/20 text-emerald-300",
  },
  {
    bg: "bg-amber-500/10",
    border: "border-l-amber-500",
    text: "text-amber-400",
    label: "bg-amber-500/20 text-amber-300",
  },
  {
    bg: "bg-purple-500/10",
    border: "border-l-purple-500",
    text: "text-purple-400",
    label: "bg-purple-500/20 text-purple-300",
  },
  {
    bg: "bg-rose-500/10",
    border: "border-l-rose-500",
    text: "text-rose-400",
    label: "bg-rose-500/20 text-rose-300",
  },
];

export function getSpeakerColor(speaker: string | null, speakers: string[]) {
  if (!speaker) return SPEAKER_COLORS[0];
  const idx = speakers.indexOf(speaker);
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
}

/** Group consecutive segments by speaker into turns. */
export function groupBySpeaker(segments: Segment[]): SpeakerTurn[] {
  if (segments.length === 0) return [];

  const turns: SpeakerTurn[] = [];
  let current: SpeakerTurn = {
    speaker: segments[0].speaker,
    segments: [segments[0]],
    startTime: segments[0].start_time,
    endTime: segments[0].end_time,
  };

  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i];
    if (seg.speaker === current.speaker) {
      current.segments.push(seg);
      current.endTime = seg.end_time;
    } else {
      turns.push(current);
      current = {
        speaker: seg.speaker,
        segments: [seg],
        startTime: seg.start_time,
        endTime: seg.end_time,
      };
    }
  }
  turns.push(current);
  return turns;
}

/** Use real word timestamps when available, fall back to interpolation. */
export function getWordTimings(segment: Segment): WordTiming[] {
  // Use real word-level data from the API if available
  if (segment.words && segment.words.length > 0) {
    return segment.words.map((w) => ({
      word: w.text,
      start: w.start,
      end: w.end,
      score: w.score,
    }));
  }

  // Fallback: interpolate word positions from segment timestamps
  const words = segment.text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];

  const duration = segment.end_time - segment.start_time;
  const wordDuration = duration / words.length;

  return words.map((word, i) => ({
    word,
    start: segment.start_time + i * wordDuration,
    end: segment.start_time + (i + 1) * wordDuration,
  }));
}
