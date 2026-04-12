"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { WikiLink, renderWikilinks } from "@/components/wikilink";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EpisodeData {
  type: string;
  slug: string;
  name: string;
  frontmatter: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  body: string;
  outlinks: Array<{ type: string; slug: string; rel?: string }>;
  backrefs: Array<{ id: string; type: string; name: string }>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract wikilink type and slug from a `[[type/slug]]` string. */
function parseWikilinkString(raw: string): { type: string; slug: string } | null {
  const m = raw.match(/\[\[([^/\]]+)\/([^\]]+)\]\]/);
  if (!m) return null;
  return { type: m[1], slug: m[2] };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EpisodeWikiPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<EpisodeData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;
    fetch(`/api/episodes/${params.id}/wiki`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [params.id]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-destructive text-lg">Error: {error}</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-lg">Loading...</p>
      </main>
    );
  }

  const fm = data.frontmatter;
  const topics = Array.isArray(fm.topics) ? (fm.topics as string[]) : [];

  return (
    <main className="mx-auto max-w-4xl px-6 py-10 space-y-8">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                             */}
      {/* ------------------------------------------------------------------ */}
      <section>
        <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
          Episode
        </p>
        <h1 className="text-3xl font-bold">{data.name}</h1>
        {fm.date && (
          <p className="mt-2 text-sm text-muted-foreground">
            {String(fm.date)}
          </p>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Metadata row                                                       */}
      {/* ------------------------------------------------------------------ */}
      {(fm.guest || fm.host || fm.podcast) && (
        <section className="flex flex-wrap gap-4 text-sm">
          {fm.guest && (
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Guest:</span>
              <span>{renderWikilinks(String(fm.guest))}</span>
            </div>
          )}
          {fm.host && (
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Host:</span>
              <span>{renderWikilinks(String(fm.host))}</span>
            </div>
          )}
          {fm.podcast && (
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Podcast:</span>
              <span>{renderWikilinks(String(fm.podcast))}</span>
            </div>
          )}
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Topic chips                                                        */}
      {/* ------------------------------------------------------------------ */}
      {topics.length > 0 && (
        <section className="flex flex-wrap gap-2">
          {topics.map((topic, i) => {
            const parsed = parseWikilinkString(topic);
            if (parsed) {
              return (
                <WikiLink key={i} type={parsed.type} slug={parsed.slug}>
                  <span className="bg-muted rounded px-2 py-1 text-xs">
                    {parsed.slug
                      .split("-")
                      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                      .join(" ")}
                  </span>
                </WikiLink>
              );
            }
            return (
              <span key={i} className="bg-muted rounded px-2 py-1 text-xs">
                {topic}
              </span>
            );
          })}
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* YouTube embed                                                      */}
      {/* ------------------------------------------------------------------ */}
      {fm.youtube_id && (
        <div className="aspect-video mb-8 rounded-lg overflow-hidden">
          <iframe
            src={`https://www.youtube.com/embed/${String(fm.youtube_id)}`}
            className="w-full h-full"
            allowFullScreen
          />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Body                                                               */}
      {/* ------------------------------------------------------------------ */}
      {data.body.trim() && (
        <section className="space-y-2">
          {data.body.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return (
                <h2 key={i} className="text-xl font-semibold mt-6">
                  {renderWikilinks(line.slice(3))}
                </h2>
              );
            }
            if (line.startsWith("- ")) {
              return (
                <li key={i} className="ml-4 list-disc">
                  {renderWikilinks(line.slice(2))}
                </li>
              );
            }
            if (line.trim() === "") {
              return <br key={i} />;
            }
            return <p key={i}>{renderWikilinks(line)}</p>;
          })}
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="pt-4 border-t border-border">
        <Link
          href="/graph"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to graph
        </Link>
      </div>
    </main>
  );
}
