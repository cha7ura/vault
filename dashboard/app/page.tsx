import Link from "next/link";
import { supabase } from "@/lib/supabase";

export default async function Home() {
  const { data: episodes } = await supabase
    .from("segments")
    .select("episode_id, episodes!inner(youtube_id, title)")
    .not("diarizer", "is", null)
    .limit(100);

  // Deduplicate by episode
  const seen = new Set<string>();
  const unique: { id: string; youtube_id: string; title: string }[] = [];
  for (const row of episodes ?? []) {
    const ep = row.episodes as any;
    if (!seen.has(row.episode_id)) {
      seen.add(row.episode_id);
      unique.push({
        id: row.episode_id,
        youtube_id: ep.youtube_id,
        title: ep.title,
      });
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Vault Dashboard</h1>
      <p className="text-muted-foreground mb-8">
        Diarization comparison and pipeline monitoring
      </p>

      {unique.length > 0 ? (
        <div className="space-y-3 w-full max-w-lg">
          <h2 className="text-sm font-medium text-muted-foreground">
            Episodes with diarization data
          </h2>
          {unique.map((ep) => (
            <Link
              key={ep.id}
              href={`/compare/${ep.youtube_id}`}
              className="block p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
            >
              <p className="font-medium">{ep.title}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {ep.youtube_id}
              </p>
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          No diarization data yet. Run the comparison notebook to upload
          segments.
        </p>
      )}
    </main>
  );
}
