import type { Episode, Segment, BenchmarkData } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchEpisode(id: string): Promise<Episode> {
  const res = await fetch(`${API}/api/episodes/${id}`);
  if (!res.ok) throw new Error(`Episode ${id} not found`);
  return res.json();
}

export async function fetchSegments(
  episodeId: string,
  diarizer: string
): Promise<Segment[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/segments?diarizer=${diarizer}`
  );
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDiarizers(episodeId: string): Promise<string[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/segments`
  );
  if (!res.ok) return [];
  const segments: Segment[] = await res.json();
  return [...new Set(segments.map((s) => s.diarizer))];
}

export async function fetchBenchmarks(
  episodeId: string
): Promise<BenchmarkData[]> {
  const res = await fetch(
    `${API}/api/episodes/${episodeId}/diarization/benchmarks`
  );
  if (!res.ok) return [];
  return res.json();
}
