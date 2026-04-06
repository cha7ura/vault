import neo4j, { Driver } from 'neo4j-driver';

let driver: Driver | null = null;

function getDriver(): Driver {
  if (!driver) {
    const uri = process.env.NEO4J_URI!;
    const user = process.env.NEO4J_USERNAME!;
    const password = process.env.NEO4J_PASSWORD!;
    driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  }
  return driver;
}

const DB = process.env.NEO4J_DATABASE || 'neo4j';

export interface GraphNode {
  id: string;
  name: string;
  labels: string[];
  edges: number;
  summary?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  fact: string;
  valid_at?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function getGraphOverview(): Promise<GraphData> {
  const d = getDriver();
  const session = d.session({ database: DB });
  try {
    // Get all entities with edge counts
    const nodesResult = await session.run(`
      MATCH (n:Entity)
      WITH n, size([(n)-[:RELATES_TO]-() | 1]) AS edgeCount
      WHERE edgeCount > 0
      RETURN n.uuid AS id, n.name AS name, labels(n) AS labels,
             edgeCount, n.summary AS summary
      ORDER BY edgeCount DESC
    `);

    const nodes: GraphNode[] = nodesResult.records.map(r => ({
      id: r.get('id'),
      name: r.get('name'),
      labels: r.get('labels'),
      edges: r.get('edgeCount').toNumber ? r.get('edgeCount').toNumber() : r.get('edgeCount'),
      summary: r.get('summary'),
    }));

    // Get all entity-to-entity edges
    const edgesResult = await session.run(`
      MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
      RETURN a.uuid AS source, b.uuid AS target, r.name AS type, r.fact AS fact, r.valid_at AS valid_at
    `);

    const edges: GraphEdge[] = edgesResult.records.map(r => {
      const va = r.get('valid_at');
      return {
        source: r.get('source'),
        target: r.get('target'),
        type: r.get('type'),
        fact: r.get('fact'),
        valid_at: va ? va.toString() : undefined,
      };
    });

    return { nodes, edges };
  } finally {
    await session.close();
  }
}

export async function getEntityDetails(uuid: string) {
  const d = getDriver();
  const session = d.session({ database: DB });
  try {
    const result = await session.run(`
      MATCH (n:Entity {uuid: $uuid})
      OPTIONAL MATCH (n)-[r:RELATES_TO]-(m:Entity)
      RETURN n.name AS name, n.summary AS summary, labels(n) AS labels,
             collect(DISTINCT {
               target: m.name, targetId: m.uuid,
               type: r.name, fact: r.fact,
               direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END
             }) AS connections
    `, { uuid });

    const record = result.records[0];
    if (!record) return null;

    return {
      name: record.get('name'),
      summary: record.get('summary'),
      labels: record.get('labels'),
      connections: record.get('connections'),
    };
  } finally {
    await session.close();
  }
}
