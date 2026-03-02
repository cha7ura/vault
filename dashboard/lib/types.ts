export interface Segment {
  id: number;
  start_time: number;
  end_time: number;
  text: string;
  speaker: string | null;
  tag: string;
  diarizer: string;
}

export interface BenchmarkData {
  id: number;
  diarizer: string;
  duration_s: number | null;
  wer: number | null;
  der: number | null;
  notes: string | null;
}

export interface Episode {
  id: number;
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

/** Approximate word timing derived from segment-level timestamps. */
export interface WordTiming {
  word: string;
  start: number;
  end: number;
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

/** Interpolate word positions within a segment's time range. */
export function getWordTimings(segment: Segment): WordTiming[] {
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
