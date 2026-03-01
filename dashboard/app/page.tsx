import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Vault Dashboard</h1>
      <p className="text-muted-foreground mb-8">Diarization comparison and pipeline monitoring</p>
      <p className="text-sm text-muted-foreground">
        Navigate to <code className="bg-muted px-2 py-1 rounded">/compare/[episodeId]</code> to compare diarizers
      </p>
    </main>
  );
}
