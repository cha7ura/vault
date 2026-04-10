/**
 * Aiven Postgres helper for the dashboard Next.js app.
 *
 * This is a sibling of `vault/lib/db.ts` — kept in sync manually because the
 * dashboard is a standalone Next.js project with its own `node_modules`.
 * When you change one, change both.
 *
 *     import { fetchOne, fetchAll, execute } from "@/lib/db";
 *
 *     const rows = await fetchAll<Segment>(
 *       "SELECT * FROM segments WHERE episode_id=$1 ORDER BY position",
 *       [episodeId],
 *     );
 *
 * See `vault/lib/db.ts` for full design notes.
 */
import { Pool, types, type PoolClient } from "pg";

// int8 → number (default is string)
types.setTypeParser(20, (val) => (val === null ? null : parseInt(val, 10)));

const RAW_URL = process.env.AIVEN_DATABASE_URL;
if (!RAW_URL) {
  throw new Error("AIVEN_DATABASE_URL is not set");
}

// See note in vault/lib/db.ts: strip sslmode from URL so our explicit
// ssl object is respected (node-postgres v8+ treats sslmode=require as
// strict verify-full, which fails against Aiven's non-system CA).
function stripSslmode(url: string): string {
  const u = new URL(url);
  u.searchParams.delete("sslmode");
  return u.toString();
}

const DATABASE_URL = stripSslmode(RAW_URL);

const globalForPg = globalThis as unknown as { __aivenPool?: Pool };

export const pool: Pool =
  globalForPg.__aivenPool ??
  new Pool({
    connectionString: DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 15_000,
  });

if (process.env.NODE_ENV !== "production") {
  globalForPg.__aivenPool = pool;
}

pool.on("error", (err) => {
  console.error("[db] idle client error:", err.message);
});

// ---------------------------------------------------------------------------
// Query helpers
// ---------------------------------------------------------------------------

type Params = readonly unknown[];

export async function fetchAll<T = Record<string, unknown>>(
  query: string,
  params?: Params,
): Promise<T[]> {
  const result = await pool.query(query, params as unknown[] | undefined);
  return result.rows as T[];
}

export async function fetchOne<T = Record<string, unknown>>(
  query: string,
  params?: Params,
): Promise<T | null> {
  const result = await pool.query(query, params as unknown[] | undefined);
  return (result.rows[0] as T) ?? null;
}

export async function fetchValue<T = unknown>(
  query: string,
  params?: Params,
): Promise<T | null> {
  const result = await pool.query(query, params as unknown[] | undefined);
  if (result.rows.length === 0) return null;
  const row = result.rows[0] as Record<string, unknown>;
  const firstKey = Object.keys(row)[0];
  return (row[firstKey] as T) ?? null;
}

export async function execute(
  query: string,
  params?: Params,
): Promise<number> {
  const result = await pool.query(query, params as unknown[] | undefined);
  return result.rowCount ?? 0;
}

export async function executeReturning<T = Record<string, unknown>>(
  query: string,
  params?: Params,
): Promise<T | null> {
  const result = await pool.query(query, params as unknown[] | undefined);
  return (result.rows[0] as T) ?? null;
}

export async function withTransaction<T>(
  fn: (client: PoolClient) => Promise<T>,
): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (err) {
    try {
      await client.query("ROLLBACK");
    } catch {
      // Ignore rollback failure.
    }
    throw err;
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
// pgvector helpers
// ---------------------------------------------------------------------------

export function vecStr(vec: readonly number[]): string {
  return "[" + vec.map((x) => Number(x).toString()).join(",") + "]";
}

export function parseVector(raw: unknown): number[] | null {
  if (raw == null) return null;
  if (Array.isArray(raw)) return raw.map((x) => Number(x));
  const s = String(raw).trim();
  const stripped = s.startsWith("[") && s.endsWith("]") ? s.slice(1, -1) : s;
  if (!stripped) return [];
  return stripped.split(",").map((x) => Number(x));
}

// ---------------------------------------------------------------------------
// JSONB helper
// ---------------------------------------------------------------------------

/**
 * Legacy-data guard: see note in `vault/lib/db.ts`. Use this for columns
 * where pre-migration rows were double-encoded (e.g. `yt_segments.words`).
 */
export function parseJsonb<T = unknown>(raw: unknown): T | null {
  if (raw == null) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }
  return raw as T;
}
