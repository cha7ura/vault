import fs from "fs";
import path from "path";
import matter from "gray-matter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Outlink {
  type: string;  // dir name like "concepts", "people"
  slug: string;
  rel?: string;  // relationship key like "appears_on", "guest", "topic"
}

export interface WikiPage {
  type: string;          // entity type: "person", "concept", "episode", etc.
  slug: string;
  name: string;
  frontmatter: Record<string, unknown>;
  body: string;
  outlinks: Outlink[];
  path: string;
}

export interface GraphNode {
  id: string;   // "type/slug"
  type: string;
  name: string;
  val: number;  // degree for node sizing
}

export interface GraphLink {
  source: string;  // "type/slug"
  target: string;
  rel: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface IndexEntry {
  name: string;
  type: string;
  file: string;
  aliases: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

/**
 * Extract wikilinks from a string.
 * Handles `[[type/slug]]` syntax only — bare `[[slug]]` links without a `/`
 * are silently ignored.
 */
export function extractWikilinks(text: string): { type: string; slug: string }[] {
  const results: { type: string; slug: string }[] = [];
  let match: RegExpExecArray | null;
  // Reset lastIndex since we reuse the regex via exec
  WIKILINK_RE.lastIndex = 0;
  while ((match = WIKILINK_RE.exec(text)) !== null) {
    const parts = match[1].split("/");
    if (parts.length >= 2) {
      results.push({ type: parts[0], slug: parts[1] });
    }
  }
  return results;
}

/** Build a dedup key from an outlink. */
function outlinkKey(o: Outlink): string {
  return `${o.type}/${o.slug}`;
}

// ---------------------------------------------------------------------------
// parsePage
// ---------------------------------------------------------------------------

/**
 * Read a wiki markdown file and return a fully-populated WikiPage.
 *
 * Gray-matter strips the YAML front-matter; the remainder is `body`.
 *
 * For episodes (type === "episode"):
 *   - slug  = youtube_id field
 *   - name  = title field
 *   - Outlinks come from guest/host/podcast (scalar wikilinks) and
 *     topics/works_referenced (array wikilinks).
 *
 * For all other types:
 *   - slug  = fm.slug
 *   - name  = fm.name
 *   - Outlinks come from frontmatter.relationships object where each key is a
 *     rel type and each entry has `entity: '[[type/slug]]'`.
 *
 * Body wikilinks are appended with rel="mentions", deduped against existing
 * relationship outlinks.
 */
export function parsePage(filePath: string): WikiPage {
  const raw = fs.readFileSync(filePath, "utf-8");

  // gray-matter can struggle with HTML comments before the front-matter fence.
  // Strip any leading HTML comment block before passing to gray-matter.
  const cleaned = raw.replace(/^<!--[\s\S]*?-->\s*/m, "");

  const { data: fm, content: body } = matter(cleaned);

  const type = (fm.type as string) ?? "unknown";
  const outlinks: Outlink[] = [];
  const seen = new Set<string>();

  function addOutlink(o: Outlink) {
    const key = outlinkKey(o);
    if (!seen.has(key)) {
      seen.add(key);
      outlinks.push(o);
    }
  }

  let slug: string;
  let name: string;

  if (type === "episode") {
    slug = String(fm.youtube_id ?? "");
    name = String(fm.title ?? "");

    // Scalar wikilink fields
    for (const [field, rel] of [
      ["guest", "guest"],
      ["host", "host"],
      ["podcast", "podcast"],
    ] as const) {
      const val = fm[field];
      if (typeof val === "string") {
        const links = extractWikilinks(val);
        for (const l of links) addOutlink({ ...l, rel });
      }
    }

    // Array wikilink fields
    for (const [field, rel] of [
      ["topics", "topic"],
      ["works_referenced", "references"],
    ] as const) {
      const arr = fm[field];
      if (Array.isArray(arr)) {
        for (const item of arr) {
          if (typeof item === "string") {
            const links = extractWikilinks(item);
            for (const l of links) addOutlink({ ...l, rel });
          }
        }
      }
    }
  } else {
    slug = String(fm.slug ?? "");
    name = String(fm.name ?? "");

    // Walk relationships object: each key is a rel type, value is an array of
    // entries that carry an `entity` field containing a wikilink string.
    const rels = fm.relationships;
    if (rels && typeof rels === "object" && !Array.isArray(rels)) {
      for (const [rel, entries] of Object.entries(
        rels as Record<string, unknown>
      )) {
        if (!Array.isArray(entries)) continue;
        for (const entry of entries) {
          if (entry && typeof entry === "object") {
            const entityVal = (entry as Record<string, unknown>).entity;
            if (typeof entityVal === "string") {
              const links = extractWikilinks(entityVal);
              for (const l of links) addOutlink({ ...l, rel });
            }
          }
        }
      }
    }
  }

  // Body wikilinks — rel="mentions", deduped against relationship outlinks
  const bodyLinks = extractWikilinks(body);
  for (const l of bodyLinks) {
    addOutlink({ ...l, rel: "mentions" });
  }

  return {
    type,
    slug,
    name,
    frontmatter: fm as Record<string, unknown>,
    body,
    outlinks,
    path: filePath,
  };
}

// ---------------------------------------------------------------------------
// DIR_TO_TYPE mapping
// ---------------------------------------------------------------------------

export const DIR_TO_TYPE: Record<string, string> = {
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

const ENTITY_DIRS = Object.keys(DIR_TO_TYPE);

// ---------------------------------------------------------------------------
// loadWiki
// ---------------------------------------------------------------------------

/**
 * Walk entity subdirectories under wikiDir and parse every .md file.
 * Returns a Map keyed by "type/slug" (e.g. "person/holly-tucker").
 */
export function loadWiki(wikiDir: string): Map<string, WikiPage> {
  const pages = new Map<string, WikiPage>();

  for (const dir of ENTITY_DIRS) {
    const dirPath = path.join(wikiDir, dir);
    if (!fs.existsSync(dirPath)) continue;

    const typeName = DIR_TO_TYPE[dir];
    const entries = fs.readdirSync(dirPath);

    for (const entry of entries) {
      if (!entry.endsWith(".md")) continue;
      const filePath = path.join(dirPath, entry);
      let page;
      try {
        page = parsePage(filePath);
      } catch {
        console.warn(`wiki: skipping ${filePath} (YAML parse error)`);
        continue;
      }
      const slug = page.slug || path.basename(entry, ".md");
      const key = `${typeName}/${slug}`;
      pages.set(key, { ...page, type: typeName, slug });
    }
  }

  return pages;
}

// ---------------------------------------------------------------------------
// buildGraph
// ---------------------------------------------------------------------------

/**
 * Build a graph of nodes and links from a loaded wiki Map.
 * Phantom nodes are created for targets that aren't in the Map.
 * Node val = total degree (in + out).
 */
export function buildGraph(pages: Map<string, WikiPage>): GraphData {
  const nodeMap = new Map<string, GraphNode>();

  // Create a node for every known page
  for (const [id, page] of pages) {
    nodeMap.set(id, { id, type: page.type, name: page.name, val: 0 });
  }

  const links: GraphLink[] = [];

  for (const [sourceId, page] of pages) {
    for (const outlink of page.outlinks) {
      const targetType = DIR_TO_TYPE[outlink.type] ?? outlink.type;
      const targetId = `${targetType}/${outlink.slug}`;

      // Create phantom node if target not in nodeMap
      if (!nodeMap.has(targetId)) {
        const phantomName = outlink.slug
          .split("-")
          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" ");
        nodeMap.set(targetId, {
          id: targetId,
          type: targetType,
          name: phantomName,
          val: 0,
        });
      }

      links.push({
        source: sourceId,
        target: targetId,
        rel: outlink.rel ?? "mentions",
      });
    }
  }

  // Compute val (degree) for each node
  for (const link of links) {
    const src = nodeMap.get(link.source);
    const tgt = nodeMap.get(link.target);
    if (src) src.val += 1;
    if (tgt) tgt.val += 1;
  }

  return { nodes: Array.from(nodeMap.values()), links };
}

// ---------------------------------------------------------------------------
// getBackrefs
// ---------------------------------------------------------------------------

/**
 * Return all pages whose outlinks reference the given targetId ("type/slug").
 * Outlinks store dir names (e.g. "people"), so we convert via DIR_TO_TYPE.
 */
export function getBackrefs(
  targetId: string,
  pages: Map<string, WikiPage>
): WikiPage[] {
  const [targetType, targetSlug] = targetId.split("/");
  const result: WikiPage[] = [];

  for (const page of pages.values()) {
    const matches = page.outlinks.some(
      (o) =>
        o.slug === targetSlug &&
        (DIR_TO_TYPE[o.type] ?? o.type) === targetType
    );
    if (matches) result.push(page);
  }

  return result;
}

// ---------------------------------------------------------------------------
// parseIndex
// ---------------------------------------------------------------------------

/**
 * Parse the markdown table in an _index.md file.
 * Skips header rows (those containing "---" or "Name").
 * Returns an array of IndexEntry objects.
 */
export function parseIndex(indexPath: string): IndexEntry[] {
  const raw = fs.readFileSync(indexPath, "utf-8");
  const entries: IndexEntry[] = [];

  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("|")) continue;
    if (trimmed.includes("---") || trimmed.includes("Name")) continue;

    const cols = trimmed
      .split("|")
      .map((c) => c.trim())
      .filter((c) => c !== "");

    if (cols.length < 3) continue;

    entries.push({
      name: cols[0],
      type: cols[1],
      file: cols[2],
      aliases: cols[3] ?? "",
    });
  }

  return entries;
}

// ---------------------------------------------------------------------------
// Singleton cache
// ---------------------------------------------------------------------------

const WIKI_DIR =
  process.env.VAULT_WIKI_DIR ?? path.join(process.cwd(), "wiki");
let _cache: Map<string, WikiPage> | null = null;

export function getWiki(): Map<string, WikiPage> {
  if (!_cache) _cache = loadWiki(WIKI_DIR);
  return _cache;
}

export function invalidateCache(): void {
  _cache = null;
}
