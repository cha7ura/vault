import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-[calc(100vh-52px)] flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Vault Dashboard</h1>
      <p className="text-muted-foreground mb-8">
        Knowledge graph and diarization tools
      </p>
      <div className="flex gap-4">
        <Link
          href="/graph"
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90"
        >
          Knowledge Graph
        </Link>
      </div>
    </main>
  );
}
