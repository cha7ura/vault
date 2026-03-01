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

const SPEAKER_COLORS = [
  { bg: "bg-blue-50", border: "border-l-blue-500", text: "text-blue-700" },
  { bg: "bg-green-50", border: "border-l-green-500", text: "text-green-700" },
  { bg: "bg-amber-50", border: "border-l-amber-500", text: "text-amber-700" },
  { bg: "bg-purple-50", border: "border-l-purple-500", text: "text-purple-700" },
  { bg: "bg-rose-50", border: "border-l-rose-500", text: "text-rose-700" },
];

export function getSpeakerColor(speaker: string | null, speakers: string[]) {
  if (!speaker) return SPEAKER_COLORS[0];
  const idx = speakers.indexOf(speaker);
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
}
