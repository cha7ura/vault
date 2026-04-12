"use client";

import { useEffect, useState, useMemo } from "react";
import ForceGraph from "@/components/force-graph";
import type { GraphData, GraphNode, GraphLink } from "@/lib/wiki";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_TYPES = [
  "person",
  "concept",
  "organization",
  "work",
  "podcast",
  "place",
  "method",
  "product",
  "episode",
];

const TYPE_COLORS: Record<string, string> = {
  person: "#3b82f6",
  concept: "#22c55e",
  organization: "#f97316",
  work: "#a855f7",
  podcast: "#ef4444",
  place: "#6b7280",
  method: "#14b8a6",
  product: "#eab308",
  episode: "#ec4899",
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GraphPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    () => new Set(ALL_TYPES),
  );
  const [search, setSearch] = useState("");

  // Fetch graph data on mount
  useEffect(() => {
    fetch("/api/wiki-graph")
      .then((r) => r.json())
      .then((d: GraphData) => setData(d))
      .catch(console.error);
  }, []);

  // Compute per-type counts
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of ALL_TYPES) counts[t] = 0;
    if (data) {
      for (const node of data.nodes) {
        counts[node.type] = (counts[node.type] ?? 0) + 1;
      }
    }
    return counts;
  }, [data]);

  // Toggle a type in the active set
  function toggleType(type: string) {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  const totalNodes = data?.nodes.length ?? 0;
  const totalLinks = data?.links.length ?? 0;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside className="flex w-[280px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-border p-4">
        <h1 className="text-lg font-semibold">Knowledge Graph</h1>

        <p className="text-sm text-muted-foreground">
          {totalNodes} entities &middot; {totalLinks} edges
        </p>

        {/* Search */}
        <input
          type="text"
          placeholder="Filter nodes..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-md border border-border bg-muted px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />

        {/* Type checkboxes */}
        <div className="flex flex-col gap-1.5">
          {ALL_TYPES.map((type) => (
            <label
              key={type}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted"
            >
              <input
                type="checkbox"
                checked={activeTypes.has(type)}
                onChange={() => toggleType(type)}
                className="accent-foreground"
              />
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: TYPE_COLORS[type] ?? "#888" }}
              />
              <span className="capitalize">{type}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {typeCounts[type] ?? 0}
              </span>
            </label>
          ))}
        </div>
      </aside>

      {/* Graph area */}
      <main className="flex-1">
        {data ? (
          <ForceGraph
            nodes={data.nodes}
            links={data.links}
            typeFilter={activeTypes}
            searchQuery={search}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Loading graph...
          </div>
        )}
      </main>
    </div>
  );
}
