'use client';

import { useEffect, useState, useCallback, useRef } from 'react';

interface GraphNode {
  id: string;
  name: string;
  labels: string[];
  edges: number;
  summary?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  fact: string;
  valid_at?: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const TYPE_COLORS: Record<string, string> = {
  HOSTS: '#60a5fa',
  APPEARS_ON: '#818cf8',
  WORKS_WITH: '#eab308',
  AFFILIATED_WITH: '#14b8a6',
  CLAIMS: '#ef4444',
  RECOMMENDS: '#f97316',
  DESCRIBES: '#10b981',
  REFERENCES: '#06b6d4',
  SPONSORS: '#f59e0b',
  RELATES_TO: '#6b7280',
};

function getEdgeColor(type: string): string {
  return TYPE_COLORS[type] || '#6b7280';
}

function getNodeSize(edges: number): number {
  return Math.max(6, Math.min(30, 4 + edges * 1.5));
}

export default function GraphPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [selectedEdges, setSelectedEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [ForceGraph, setForceGraph] = useState<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    import('react-force-graph-2d').then(mod => setForceGraph(() => mod.default));
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const fg = graphRef.current;
    if (fg) {
      fg.d3Force('charge')?.strength(-400).distanceMax(500);
      fg.d3Force('link')?.distance(120);
    }
  }, [ForceGraph, data]);

  useEffect(() => {
    fetch('/api/graph')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    if (!data) return;
    setSelected(node);
    const edges = data.edges.filter(
      e => e.source === node.id || e.target === node.id ||
           (e.source as any)?.id === node.id || (e.target as any)?.id === node.id
    );
    setSelectedEdges(edges);
  }, [data]);

  if (loading) return <div className="flex items-center justify-center min-h-screen"><p className="text-lg">Loading graph...</p></div>;
  if (error) return <div className="flex items-center justify-center min-h-screen"><p className="text-red-500">Error: {error}</p></div>;
  if (!data || !ForceGraph) return null;

  const graphData = {
    nodes: data.nodes.map(n => ({ ...n, val: getNodeSize(n.edges) })),
    links: data.edges.map(e => ({ ...e })),
  };

  // Edge type stats
  const edgeStats: Record<string, number> = {};
  data.edges.forEach(e => { edgeStats[e.type] = (edgeStats[e.type] || 0) + 1; });
  const sortedTypes = Object.entries(edgeStats).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Graph */}
      <div className="flex-1 relative overflow-hidden" ref={containerRef}>
        <ForceGraph
          ref={graphRef}
          graphData={graphData}
          nodeLabel={(node: any) => `${node.name} (${node.edges} connections)`}
          nodeColor={() => '#3b82f6'}
          nodeVal={(node: any) => node.val}
          linkColor={(link: any) => getEdgeColor(link.type)}
          linkLabel={(link: any) => `${link.type}: ${link.fact?.slice(0, 80) || ''}`}
          linkWidth={1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          cooldownTime={3000}
          onNodeClick={handleNodeClick}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const size = node.val || 6;
            const isSelected = selected?.id === node.id;

            // Node circle
            ctx.beginPath();
            ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
            ctx.fillStyle = isSelected ? '#ef4444' : '#3b82f6';
            ctx.fill();
            if (isSelected) {
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 2;
              ctx.stroke();
            }

            // Label
            const fontSize = Math.max(10, 12 / globalScale);
            ctx.font = `${fontSize}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillStyle = '#e5e7eb';
            ctx.fillText(node.name, node.x, node.y + size + 2);
          }}
          backgroundColor="#09090b"
          width={dimensions.width}
          height={dimensions.height}
        />

        {/* Stats overlay */}
        <div className="absolute top-4 left-4 bg-zinc-900/90 rounded-lg p-3 text-sm">
          <p className="font-semibold">{data.nodes.length} entities, {data.edges.length} relationships</p>
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-[520px] border-l border-zinc-800 overflow-y-auto bg-zinc-950 p-4">
        {selected ? (
          <>
            <h2 className="text-xl font-bold mb-1">{selected.name}</h2>
            <p className="text-xs text-zinc-500 mb-2">{selected.labels.filter(l => l !== 'Entity').join(', ')}</p>
            {selected.summary && (
              <p className="text-sm text-zinc-400 mb-4">{selected.summary}</p>
            )}
            <h3 className="text-sm font-semibold text-zinc-300 mb-2">
              Connections ({selectedEdges.length})
            </h3>
            <div className="space-y-2">
              {selectedEdges.map((e, i) => {
                const sourceName = typeof e.source === 'string'
                  ? data.nodes.find(n => n.id === e.source)?.name || e.source
                  : (e.source as any).name;
                const targetName = typeof e.target === 'string'
                  ? data.nodes.find(n => n.id === e.target)?.name || e.target
                  : (e.target as any).name;
                const isOutgoing = (typeof e.source === 'string' ? e.source : (e.source as any).id) === selected.id;

                return (
                  <div key={i} className="rounded bg-zinc-900 p-2 text-sm">
                    <div className="flex items-center gap-1 mb-1">
                      <span
                        className="inline-block w-2 h-2 rounded-full"
                        style={{ backgroundColor: getEdgeColor(e.type) }}
                      />
                      <span className="font-medium text-zinc-300">{e.type}</span>
                      <span className="text-zinc-600 text-xs">
                        {isOutgoing ? '→' : '←'} {isOutgoing ? targetName : sourceName}
                      </span>
                    </div>
                    {e.fact && <p className="text-xs text-zinc-500">{e.fact}</p>}
                    {e.valid_at && (
                      <p className="text-xs text-zinc-600 mt-1">
                        {new Date(e.valid_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <>
            <h2 className="text-lg font-bold mb-4">Knowledge Graph</h2>
            <p className="text-sm text-zinc-400 mb-4">Click a node to see its connections</p>

            <h3 className="text-sm font-semibold text-zinc-300 mb-2">Edge Types</h3>
            <div className="space-y-1 mb-6">
              {sortedTypes.map(([type, count]) => (
                <div key={type} className="flex items-center gap-2 text-sm">
                  <span
                    className="inline-block w-3 h-3 rounded-full"
                    style={{ backgroundColor: getEdgeColor(type) }}
                  />
                  <span className="text-zinc-400">{type}</span>
                  <span className="text-zinc-600 ml-auto">{count}</span>
                </div>
              ))}
            </div>

            <h3 className="text-sm font-semibold text-zinc-300 mb-2">Top Entities</h3>
            <div className="space-y-1">
              {data.nodes.slice(0, 15).map(n => (
                <button
                  key={n.id}
                  onClick={() => handleNodeClick(n)}
                  className="w-full text-left text-sm hover:bg-zinc-800 rounded px-2 py-1 flex justify-between"
                >
                  <span className="text-zinc-300">{n.name}</span>
                  <span className="text-zinc-600">{n.edges}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
