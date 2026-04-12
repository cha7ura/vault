"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import LocalGraph from "@/components/local-graph";
import { WikiLink, renderWikilinks } from "@/components/wikilink";
import React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EntityData {
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

export default function EntityDetailPage() {
  const params = useParams<{ type: string; slug: string }>();
  const [data, setData] = useState<EntityData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.type || !params.slug) return;
    fetch(`/api/entities/${params.type}/${params.slug}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [params.type, params.slug]);

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
  const relationships = fm.relationships as
    | Record<string, Array<Record<string, unknown>>>
    | undefined;
  const observations = fm.observations as
    | Array<{ text: string; episode?: string; timestamp?: string }>
    | undefined;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 space-y-10">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                             */}
      {/* ------------------------------------------------------------------ */}
      <section>
        <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
          {data.type}
        </p>
        <h1 className="text-3xl font-bold">{data.name}</h1>
        {fm.bio && (
          <p className="mt-2 text-muted-foreground">{String(fm.bio)}</p>
        )}
        {fm.credentials && (
          <p className="mt-1 text-sm text-muted-foreground italic">
            {String(fm.credentials)}
          </p>
        )}
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Local graph                                                        */}
      {/* ------------------------------------------------------------------ */}
      <section>
        <h2 className="text-xl font-semibold mb-3">Connections</h2>
        <LocalGraph
          entityId={`${data.type}/${data.slug}`}
          entityType={data.type}
          entityName={data.name}
          outlinks={data.outlinks}
          backrefs={data.backrefs}
        />
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Relationships                                                      */}
      {/* ------------------------------------------------------------------ */}
      {relationships &&
        Object.keys(relationships).length > 0 && (
          <section>
            <h2 className="text-xl font-semibold mb-3">Relationships</h2>
            <div className="space-y-4">
              {Object.entries(relationships).map(([relType, entries]) => (
                <div key={relType}>
                  <h3 className="text-sm font-medium uppercase tracking-wider text-muted-foreground mb-1">
                    {relType.replace(/_/g, " ")}
                  </h3>
                  <ul className="space-y-1 ml-2">
                    {Array.isArray(entries) &&
                      entries.map((entry, i) => {
                        const entityStr = String(entry.entity ?? "");
                        const parsed = parseWikilinkString(entityStr);
                        const role = entry.role ? String(entry.role) : null;
                        const timestamp = entry.timestamp
                          ? String(entry.timestamp)
                          : null;

                        return (
                          <li key={i} className="flex items-baseline gap-2">
                            {parsed ? (
                              <WikiLink type={parsed.type} slug={parsed.slug}>
                                {parsed.slug
                                  .split("-")
                                  .map(
                                    (w) =>
                                      w.charAt(0).toUpperCase() + w.slice(1),
                                  )
                                  .join(" ")}
                              </WikiLink>
                            ) : (
                              <span className="text-muted-foreground">
                                {entityStr}
                              </span>
                            )}
                            {role && (
                              <span className="text-xs text-muted-foreground">
                                ({role})
                              </span>
                            )}
                            {timestamp && (
                              <span className="text-xs text-muted-foreground">
                                {timestamp}
                              </span>
                            )}
                          </li>
                        );
                      })}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        )}

      {/* ------------------------------------------------------------------ */}
      {/* Observations                                                       */}
      {/* ------------------------------------------------------------------ */}
      {observations && observations.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold mb-3">Observations</h2>
          <ul className="space-y-3">
            {observations.map((obs, i) => (
              <li
                key={i}
                className="border-l-2 border-muted-foreground/30 pl-4"
              >
                <p>{obs.text}</p>
                <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
                  {obs.episode && <span>Episode: {obs.episode}</span>}
                  {obs.timestamp && <span>{obs.timestamp}</span>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Backrefs                                                           */}
      {/* ------------------------------------------------------------------ */}
      {data.backrefs.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold mb-3">Referenced By</h2>
          <div className="flex flex-wrap gap-2">
            {data.backrefs.map((ref) => (
              <WikiLink key={ref.id} type={ref.type} slug={ref.id.split("/").slice(1).join("/")}>
                <span className="inline-block bg-muted px-3 py-1 rounded-full text-sm">
                  {ref.name}
                </span>
              </WikiLink>
            ))}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Body                                                               */}
      {/* ------------------------------------------------------------------ */}
      {data.body.trim() && (
        <section>
          <h2 className="text-xl font-semibold mb-3">Notes</h2>
          <div className="space-y-2">
            {data.body
              .split("\n")
              .filter((line) => line.trim() !== "")
              .map((line, i) => {
                const trimmed = line.trim();
                if (trimmed.startsWith("## ")) {
                  return (
                    <h2 key={i} className="text-lg font-semibold mt-4">
                      {renderWikilinks(trimmed.slice(3))}
                    </h2>
                  );
                }
                return <p key={i}>{renderWikilinks(trimmed)}</p>;
              })}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="pt-4 border-t border-border">
        <Link
          href="/wiki"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to graph
        </Link>
      </div>
    </main>
  );
}
