import type { Episode, Segment, BenchmarkData } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchEpisode(id: number): Promise<Episode> {
  const res = await fetch(`${API}/api/episodes/${id}`);
  if (!res.ok) throw new Error(`Episode ${id} not found`);
  return res.json();
}

export async function fetchSegments(
  episodeId: number,
  diarizer: string
): Promise<Segment[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/segments?diarizer=${diarizer}`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function fetchBenchmarks(
  episodeId: number
): Promise<BenchmarkData[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/benchmarks`
  );
  if (!res.ok) return [];
  return res.json();
}
