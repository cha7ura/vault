"use client";

import { useRef, useCallback, useMemo, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import type { GraphNode, GraphLink } from "@/lib/wiki";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SIDEBAR_WIDTH = 280;

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

const BG_COLOR = "hsl(0, 0%, 3.9%)";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  nodes: GraphNode[];
  links: GraphLink[];
  typeFilter: Set<string>;
  searchQuery: string;
  onNodeClick?: (node: GraphNode) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ForceGraph({
  nodes,
  links,
  typeFilter,
  searchQuery,
  onNodeClick,
}: Props) {
  const router = useRouter();
  const fgRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any

  // Track available size
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    function updateSize() {
      setDimensions({
        width: window.innerWidth - SIDEBAR_WIDTH,
        height: window.innerHeight,
      });
    }
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  // ---- Filtered data -------------------------------------------------------

  const visibleNodeIds = useMemo(() => {
    const query = searchQuery.toLowerCase();
    const ids = new Set<string>();
    for (const node of nodes) {
      if (!typeFilter.has(node.type)) continue;
      if (query && !node.name.toLowerCase().includes(query)) continue;
      ids.add(node.id);
    }
    return ids;
  }, [nodes, typeFilter, searchQuery]);

  const graphData = useMemo(() => {
    const filteredNodes = nodes.filter((n) => visibleNodeIds.has(n.id));
    const filteredLinks = links.filter((l) => {
      // After force-graph processes data, source/target become objects
      const sourceId =
        typeof l.source === "object"
          ? (l.source as unknown as GraphNode).id
          : l.source;
      const targetId =
        typeof l.target === "object"
          ? (l.target as unknown as GraphNode).id
          : l.target;
      return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId);
    });
    return { nodes: filteredNodes, links: filteredLinks };
  }, [nodes, links, visibleNodeIds]);

  // ---- Handlers ------------------------------------------------------------

  const handleClick = useCallback(
    (node: any) => {  // eslint-disable-line @typescript-eslint/no-explicit-any
      if (onNodeClick) onNodeClick(node as GraphNode);
      const { type, id } = node as GraphNode;
      const slug = id.split("/").slice(1).join("/");
      if (type === "episode") {
        router.push(`/episodes/${slug}/wiki`);
      } else {
        router.push(`/entity/${type}/${slug}`);
      }
    },
    [router, onNodeClick],
  );

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const { name, type, val, x, y } = node as GraphNode & {
        x: number;
        y: number;
      };
      const radius = Math.sqrt(Math.max(val ?? 1, 1)) * 3;
      const color = TYPE_COLORS[type] ?? "#888";

      // Circle
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      ctx.fill();

      // Label — only when zoomed in enough
      if (globalScale > 1.5) {
        const fontSize = 12 / globalScale;
        ctx.font = `${fontSize}px Sans-Serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.fillText(name, x, y + radius + 2 / globalScale);
      }
    },
    [],
  );

  const nodePointerAreaPaint = useCallback(
    (node: any, color: string, ctx: CanvasRenderingContext2D) => {
      const { val, x, y } = node as GraphNode & { x: number; y: number };
      const radius = Math.sqrt(Math.max(val ?? 1, 1)) * 3 + 4;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = color;
      ctx.fill();
    },
    [],
  );

  // ---- Render --------------------------------------------------------------

  return (
    <ForceGraph2D
      ref={fgRef}
      width={dimensions.width}
      height={dimensions.height}
      graphData={graphData}
      backgroundColor={BG_COLOR}
      nodeCanvasObject={nodeCanvasObject}
      nodePointerAreaPaint={nodePointerAreaPaint}
      onNodeClick={handleClick}
      linkColor={() => "rgba(255,255,255,0.08)"}
      linkWidth={0.5}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
    />
  );
}
