/**
 * Aiven Postgres helper for the Next.js runtime.
 *
 * Mirrors `scripts/agents/db.py` so Python and TypeScript code can be
 * reviewed side by side:
 *
 *     import { fetchOne, fetchAll, execute, vecStr, parseVector } from "@/lib/db";
 *
 *     const ep = await fetchOne<Episode>(
 *       "SELECT * FROM episodes WHERE id=$1",
 *       [episodeId],
 *     );
 *     const rows = await fetchAll<Segment>(
 *       "SELECT * FROM segments WHERE episode_id=$1 ORDER BY position",
 *       [episodeId],
 *     );
 *
 * Design notes
 * ------------
 * - Uses `pg.Pool` — API routes run concurrently, so a single client would
 *   serialise requests. The pool also transparently replaces dead clients,
 *   which makes a manual reconnect harness (cf. the Python side) unnecessary.
 * - The pool is cached on `globalThis` so Next.js hot reload does not leak
 *   a fresh pool per module reload.
 * - `int8` (BIGINT) is parsed to `number` instead of node-postgres's default
 *   `string`, which is safe for our row counts and makes `COUNT(*)` ergonomic.
 * - pgvector is handled as text: callers use `vecStr()` for writes
 *   (with an explicit `::vector` cast in the SQL) and `parseVector()` for
 *   reads.
 */
import { Pool, types, type PoolClient } from "pg";

// int8 → number (default is string to preserve bigint precision we don't need)
types.setTypeParser(20, (val) => (val === null ? null : parseInt(val, 10)));

const RAW_URL = process.env.AIVEN_DATABASE_URL;
if (!RAW_URL) {
  throw new Error("AIVEN_DATABASE_URL is not set");
}

// Aiven's connection string ships with `?sslmode=require`, but node-postgres
// v8+ now treats `require`/`prefer`/`verify-ca` as strict `verify-full`, which
// fails against Aiven's non-system CA. Strip `sslmode` from the URL and let
// our explicit `ssl` object win. (Python side works because psycopg2 still
// honours the loose libpq semantics of `sslmode=require`.)
function stripSslmode(url: string): string {
  const u = new URL(url);
  u.searchParams.delete("sslmode");
  return u.toString();
}

const DATABASE_URL = stripSslmode(RAW_URL);

// Cache the pool across Next.js hot reloads.
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

// A pool-level error handler prevents an unhandled-error crash when an
// *idle* client errors (e.g. Aiven reaps the connection). The pool will
// still replace the client on the next checkout; this just silences the
// process-level warning.
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

/**
 * Run a function inside a transaction. The client is released automatically
 * on both success and failure.
 *
 *     await withTransaction(async (client) => {
 *       await client.query("UPDATE episodes SET status='pending' WHERE id=$1", [id]);
 *       await client.query("INSERT INTO job_queue (episode_id) VALUES ($1)", [id]);
 *     });
 */
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
      // Ignore rollback failure — original error is more useful.
    }
    throw err;
  } finally {
    client.release();
  }
}

// ---------------------------------------------------------------------------
// pgvector helpers (text-adapter strategy, no `pgvector` npm dep)
// ---------------------------------------------------------------------------

/**
 * Format a JS number[] as a pgvector literal. Usage:
 *
 *     await execute(
 *       "INSERT INTO speaker_embeddings (embedding) VALUES ($1::vector)",
 *       [vecStr(centroid)],
 *     );
 */
export function vecStr(vec: readonly number[]): string {
  return "[" + vec.map((x) => Number(x).toString()).join(",") + "]";
}

/**
 * Convert a pgvector value (returned as `'[1.0,2.0,...]'` text by pg) into
 * a `number[]`. Safe to call on already-parsed arrays too.
 */
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
 * node-postgres auto-decodes jsonb columns. However, legacy rows inserted by
 * the pre-migration supabase-py code used `json.dumps()` before insert, so
 * the JSONB value is a *string* rather than an array/object. Use this
 * helper anywhere a JSONB column might still hold legacy-encoded data (e.g.
 * `yt_segments.words`):
 *
 *     const words = parseJsonb<Word[]>(row.words) ?? [];
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
