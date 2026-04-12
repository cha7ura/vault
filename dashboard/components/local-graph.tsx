"use client";

import { useMemo, useRef, useState, useEffect } from "react";
import ForceGraphView from "@/components/force-graph";
import type { GraphNode, GraphLink } from "@/lib/wiki";

// ---------------------------------------------------------------------------
// DIR_TO_TYPE — resolve directory names used in outlinks to entity type names
// ---------------------------------------------------------------------------

const DIR_TO_TYPE: Record<string, string> = {
  people: "person",
  concepts: "concept",
  organizations: "organization",
  works: "work",
  methods: "method",
  products: "product",
  podcasts: "podcast",
  _places: "place",
  _episodes: "episode",
};

// All entity types that can appear in the local graph
const ALL_TYPES = new Set(Object.values(DIR_TO_TYPE));

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  entityId: string; // "type/slug"
  entityType: string;
  entityName: string;
  outlinks: Array<{ type: string; slug: string; rel?: string }>;
  backrefs: Array<{ id: string; type: string; name: string }>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function titleCase(slug: string): string {
  return slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function LocalGraph({
  entityId,
  entityType,
  entityName,
  outlinks,
  backrefs,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const { nodes, links } = useMemo(() => {
    const nodeMap = new Map<string, GraphNode>();
    const graphLinks: GraphLink[] = [];

    // Center node
    nodeMap.set(entityId, {
      id: entityId,
      type: entityType,
      name: entityName,
      val: 0,
    });

    // Outlink target nodes
    for (const ol of outlinks) {
      const targetType = DIR_TO_TYPE[ol.type] ?? ol.type;
      const targetId = `${targetType}/${ol.slug}`;
      if (!nodeMap.has(targetId)) {
        nodeMap.set(targetId, {
          id: targetId,
          type: targetType,
          name: titleCase(ol.slug),
          val: 0,
        });
      }
      graphLinks.push({
        source: entityId,
        target: targetId,
        rel: ol.rel ?? "mentions",
      });
    }

    // Backref source nodes
    for (const br of backrefs) {
      if (!nodeMap.has(br.id)) {
        nodeMap.set(br.id, {
          id: br.id,
          type: br.type,
          name: br.name,
          val: 0,
        });
      }
      graphLinks.push({
        source: br.id,
        target: entityId,
        rel: "references",
      });
    }

    // Compute degrees
    for (const link of graphLinks) {
      const src = nodeMap.get(link.source);
      const tgt = nodeMap.get(link.target);
      if (src) src.val += 1;
      if (tgt) tgt.val += 1;
    }

    return { nodes: Array.from(nodeMap.values()), links: graphLinks };
  }, [entityId, entityType, entityName, outlinks, backrefs]);

  return (
    <div
      ref={containerRef}
      className="w-full border border-border rounded-lg overflow-hidden"
      style={{ height: 400 }}
    >
      <ForceGraphView
        nodes={nodes}
        links={links}
        typeFilter={ALL_TYPES}
        searchQuery=""
        width={containerWidth}
        height={400}
      />
    </div>
  );
}
