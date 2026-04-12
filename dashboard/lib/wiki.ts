import fs from "fs";
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
