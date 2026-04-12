# Wiki Front End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Obsidian-like knowledge graph front end over `vault/wiki/` — global force graph, entity detail pages, episode pages, and Cmd+K search.

**Architecture:** Path A (files-as-truth). A `lib/wiki.ts` parser reads wiki `.md` files at startup, caches in-memory, exposes through Next.js API routes. `react-force-graph-2d` renders the graph. All pages in the existing dashboard app at `vault/dashboard/`.

**Tech Stack:** Next.js 15 (App Router), React 19, Tailwind v4, gray-matter (YAML), react-force-graph-2d, vitest, TypeScript strict mode.

**Spec:** `docs/superpowers/specs/2026-04-12-wiki-frontend-design.md`

---

## File Map

```
dashboard/
  lib/
    wiki.ts                                  ← CREATE: parser, cache, graph builder
    wiki.test.ts                             ← CREATE: vitest unit tests
    __fixtures__/
      sample-person.md                       ← CREATE: test fixture
      sample-concept.md                      ← CREATE: test fixture
      sample-episode.md                      ← CREATE: test fixture
      sample-index.md                        ← CREATE: test fixture
  components/
    force-graph.tsx                           ← CREATE: client wrapper for ForceGraph2D
    local-graph.tsx                           ← CREATE: 1-hop neighborhood graph
    wikilink.tsx                              ← CREATE: [[type/slug]] → <Link>
    search-command.tsx                        ← CREATE: Cmd+K overlay
  app/
    layout.tsx                               ← MODIFY: add nav bar + search trigger
    page.tsx                                  ← MODIFY: add links to /graph
    api/
      graph/route.ts                         ← CREATE: GET {nodes, links}
      entities/route.ts                      ← CREATE: GET index as JSON
      entities/[type]/[slug]/route.ts        ← CREATE: GET one entity
      episodes/[youtubeId]/wiki/route.ts     ← CREATE: GET episode wiki page
    graph/
      page.tsx                               ← CREATE: Obsidian-style force graph
    entity/[type]/[slug]/
      page.tsx                               ← CREATE: entity detail + local graph
    episodes/[id]/
      wiki/page.tsx                          ← CREATE: episode wiki page
  vitest.config.ts                           ← CREATE: test config
  package.json                               ← MODIFY: add deps
```

---

### Task 1: Install dependencies and configure vitest

**Files:**
- Modify: `dashboard/package.json`
- Create: `dashboard/vitest.config.ts`

- [ ] **Step 1: Install packages**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npm install gray-matter react-force-graph-2d
npm install -D vitest @vitejs/plugin-react
```

- [ ] **Step 2: Create vitest config**

Create `dashboard/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
```

- [ ] **Step 3: Add test script to package.json**

In `dashboard/package.json`, add to `"scripts"`:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 4: Verify vitest runs**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx vitest run
```

Expected: "No test files found" (clean exit).

- [ ] **Step 5: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/vitest.config.ts
git commit -m "chore: add gray-matter, react-force-graph-2d, vitest"
```

---

### Task 2: Create test fixtures

**Files:**
- Create: `dashboard/lib/__fixtures__/sample-person.md`
- Create: `dashboard/lib/__fixtures__/sample-concept.md`
- Create: `dashboard/lib/__fixtures__/sample-episode.md`
- Create: `dashboard/lib/__fixtures__/sample-index.md`

These are trimmed copies of real wiki files for deterministic testing.

- [ ] **Step 1: Create sample person fixture**

Create `dashboard/lib/__fixtures__/sample-person.md`:

```markdown
---
type: person
name: Holly Tucker
slug: holly-tucker
aliases: []
appearances: []
relationships:
  appears_on:
  - entity: '[[podcasts/diary-of-a-ceo]]'
    episode: 2PeHDoThIp8
  affiliated_with:
  - role: founder
    entity: '[[organizations/not-on-the-high-street]]'
    episode: 2PeHDoThIp8
  claims:
  - insight_type: claim
    timestamp: '00:03:49'
    entity: '[[concepts/work-ethic]]'
    episode: 2PeHDoThIp8
observations:
- episode: 2PeHDoThIp8
  timestamp: 418-426
  text: Her father was a CFO at General Electric.
enriched: false
created_at: '2026-04-12'
updated_at: '2026-04-12'
---

## Sources
- [Holly Tucker MBE](https://hollyandco.com) — Founder of NotOnTheHighStreet
```

- [ ] **Step 2: Create sample concept fixture**

Create `dashboard/lib/__fixtures__/sample-concept.md`:

```markdown
---
type: concept
name: Work Ethic
slug: work-ethic
aliases: []
appearances: []
relationships: {}
observations:
- episode: 2PeHDoThIp8
  timestamp: 474-486
  text: Holly's father instilled a strong work ethic from early childhood.
enriched: false
created_at: '2026-04-12'
updated_at: '2026-04-12'
---
```

- [ ] **Step 3: Create sample episode fixture**

Create `dashboard/lib/__fixtures__/sample-episode.md`:

```markdown
<!-- youtube_id: 2PeHDoThIp8 -->
---
type: episode
youtube_id: 2PeHDoThIp8
title: "NotOnTheHighStreet.com Founder: Rapid Success Lead To My Darkest Days - Holly Tucker | E92"
date: 2021-08-09
guest: "[[people/holly-tucker]]"
host: "[[people/steven-bartlett]]"
podcast: "[[podcasts/diary-of-a-ceo]]"
topics:
  - "[[concepts/mental-health]]"
  - "[[concepts/work-ethic]]"
works_referenced: []
---

## Summary
Holly Tucker, founder of [[organizations/not-on-the-high-street]], shares her journey.

## Key Claims
- [[concepts/work-ethic]] was instilled early (3:49)
```

- [ ] **Step 4: Create sample index fixture**

Create `dashboard/lib/__fixtures__/sample-index.md`:

```markdown
# Entity Index

| Name | Type | File | Aliases |
|---|---|---|---|
| Holly Tucker | person | people/holly-tucker |  |
| Steven Bartlett | person | people/steven-bartlett |  |
| Work Ethic | concept | concepts/work-ethic |  |
| Diary of a CEO | podcast | podcasts/diary-of-a-ceo |  |
| Not On The High Street | organization | organizations/not-on-the-high-street |  |
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/lib/__fixtures__/
git commit -m "test: add wiki parser fixtures"
```

---

### Task 3: Build `lib/wiki.ts` — types and `parsePage`

**Files:**
- Create: `dashboard/lib/wiki.ts`
- Create: `dashboard/lib/wiki.test.ts`

- [ ] **Step 1: Write failing test for parsePage**

Create `dashboard/lib/wiki.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import path from "path";
import { parsePage, extractWikilinks } from "./wiki";

const FIXTURES = path.join(__dirname, "__fixtures__");

describe("extractWikilinks", () => {
  it("extracts type/slug pairs from wikilink syntax", () => {
    const text = "Talked about [[concepts/work-ethic]] with [[people/holly-tucker]].";
    const links = extractWikilinks(text);
    expect(links).toEqual([
      { type: "concepts", slug: "work-ethic" },
      { type: "people", slug: "holly-tucker" },
    ]);
  });

  it("returns empty array for text with no wikilinks", () => {
    expect(extractWikilinks("plain text")).toEqual([]);
  });
});

describe("parsePage", () => {
  it("parses a person page", () => {
    const page = parsePage(path.join(FIXTURES, "sample-person.md"));
    expect(page.type).toBe("person");
    expect(page.slug).toBe("holly-tucker");
    expect(page.name).toBe("Holly Tucker");
    expect(page.outlinks.length).toBeGreaterThan(0);
    expect(page.outlinks).toContainEqual({
      type: "podcasts",
      slug: "diary-of-a-ceo",
      rel: "appears_on",
    });
    expect(page.outlinks).toContainEqual({
      type: "organizations",
      slug: "not-on-the-high-street",
      rel: "affiliated_with",
    });
  });

  it("parses a concept page with empty relationships", () => {
    const page = parsePage(path.join(FIXTURES, "sample-concept.md"));
    expect(page.type).toBe("concept");
    expect(page.slug).toBe("work-ethic");
    expect(page.name).toBe("Work Ethic");
  });

  it("parses an episode page", () => {
    const page = parsePage(path.join(FIXTURES, "sample-episode.md"));
    expect(page.type).toBe("episode");
    expect(page.slug).toBe("2PeHDoThIp8");
    expect(page.name).toContain("NotOnTheHighStreet");
    expect(page.outlinks).toContainEqual({
      type: "people",
      slug: "holly-tucker",
      rel: "guest",
    });
    expect(page.outlinks).toContainEqual({
      type: "concepts",
      slug: "mental-health",
      rel: "topic",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx vitest run lib/wiki.test.ts
```

Expected: FAIL — `Cannot find module './wiki'`

- [ ] **Step 3: Implement wiki.ts types and parsePage**

Create `dashboard/lib/wiki.ts`:

```ts
import fs from "fs";
import path from "path";
import matter from "gray-matter";

// ── Types ──────────────────────────────────────────────

export interface Outlink {
  type: string;
  slug: string;
  rel?: string;
}

export interface WikiPage {
  type: string;
  slug: string;
  name: string;
  frontmatter: Record<string, unknown>;
  body: string;
  outlinks: Outlink[];
  path: string;
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  val: number;
}

export interface GraphLink {
  source: string;
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

// ── Helpers ────────────────────────────────────────────

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

export function extractWikilinks(text: string): Array<{ type: string; slug: string }> {
  const results: Array<{ type: string; slug: string }> = [];
  let m: RegExpExecArray | null;
  while ((m = WIKILINK_RE.exec(text)) !== null) {
    const parts = m[1].split("/");
    if (parts.length === 2) {
      results.push({ type: parts[0], slug: parts[1] });
    }
  }
  return results;
}

function extractRelationshipOutlinks(relationships: Record<string, unknown>): Outlink[] {
  const outlinks: Outlink[] = [];
  if (!relationships || typeof relationships !== "object") return outlinks;
  for (const [rel, entries] of Object.entries(relationships)) {
    if (!Array.isArray(entries)) continue;
    for (const entry of entries) {
      if (!entry || typeof entry !== "object") continue;
      const entityStr = (entry as Record<string, unknown>).entity;
      if (typeof entityStr !== "string") continue;
      const links = extractWikilinks(entityStr);
      for (const link of links) {
        outlinks.push({ ...link, rel });
      }
    }
  }
  return outlinks;
}

function extractEpisodeOutlinks(fm: Record<string, unknown>): Outlink[] {
  const outlinks: Outlink[] = [];
  const fieldToRel: Record<string, string> = {
    guest: "guest",
    host: "host",
    podcast: "podcast",
  };
  for (const [field, rel] of Object.entries(fieldToRel)) {
    const val = fm[field];
    if (typeof val === "string") {
      for (const link of extractWikilinks(val)) {
        outlinks.push({ ...link, rel });
      }
    }
  }
  const topics = fm.topics;
  if (Array.isArray(topics)) {
    for (const t of topics) {
      if (typeof t === "string") {
        for (const link of extractWikilinks(t)) {
          outlinks.push({ ...link, rel: "topic" });
        }
      }
    }
  }
  const works = fm.works_referenced;
  if (Array.isArray(works)) {
    for (const w of works) {
      if (typeof w === "string") {
        for (const link of extractWikilinks(w)) {
          outlinks.push({ ...link, rel: "references" });
        }
      }
    }
  }
  return outlinks;
}

// ── Core ───────────────────────────────────────────────

export function parsePage(filePath: string): WikiPage {
  const raw = fs.readFileSync(filePath, "utf-8");
  const { data: fm, content: body } = matter(raw);

  const type = (fm.type as string) || "unknown";
  const isEpisode = type === "episode";
  const slug = isEpisode
    ? (fm.youtube_id as string) || path.basename(filePath, ".md")
    : (fm.slug as string) || path.basename(filePath, ".md");
  const name = (fm.title as string) || (fm.name as string) || slug;

  let outlinks: Outlink[] = [];
  if (isEpisode) {
    outlinks = extractEpisodeOutlinks(fm);
  } else {
    outlinks = extractRelationshipOutlinks(
      fm.relationships as Record<string, unknown>,
    );
  }

  // Also extract wikilinks from body text (deduped against relationship outlinks)
  const bodyLinks = extractWikilinks(body);
  const seen = new Set(outlinks.map((o) => `${o.type}/${o.slug}`));
  for (const bl of bodyLinks) {
    const key = `${bl.type}/${bl.slug}`;
    if (!seen.has(key)) {
      outlinks.push({ ...bl, rel: "mentions" });
      seen.add(key);
    }
  }

  return { type, slug, name, frontmatter: fm, body, outlinks, path: filePath };
}
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx vitest run lib/wiki.test.ts
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/lib/wiki.ts dashboard/lib/wiki.test.ts
git commit -m "feat: add wiki parser with parsePage and extractWikilinks"
```

---

### Task 4: Add `loadWiki`, `buildGraph`, `getBackrefs` to `lib/wiki.ts`

**Files:**
- Modify: `dashboard/lib/wiki.ts`
- Modify: `dashboard/lib/wiki.test.ts`

- [ ] **Step 1: Write failing tests for loadWiki and buildGraph**

Append to `dashboard/lib/wiki.test.ts`:

```ts
import { loadWiki, buildGraph, getBackrefs, parseIndex } from "./wiki";

describe("loadWiki", () => {
  it("loads all fixture pages into a Map", () => {
    const pages = loadWiki(FIXTURES);
    expect(pages.size).toBeGreaterThanOrEqual(3);
    expect(pages.has("person/holly-tucker")).toBe(true);
    expect(pages.has("concept/work-ethic")).toBe(true);
    expect(pages.has("episode/2PeHDoThIp8")).toBe(true);
  });
});

describe("buildGraph", () => {
  it("produces nodes and links", () => {
    const pages = loadWiki(FIXTURES);
    const graph = buildGraph(pages);
    expect(graph.nodes.length).toBeGreaterThanOrEqual(3);
    expect(graph.links.length).toBeGreaterThan(0);
    const hollyNode = graph.nodes.find((n) => n.id === "person/holly-tucker");
    expect(hollyNode).toBeDefined();
    expect(hollyNode!.type).toBe("person");
    const guestLink = graph.links.find(
      (l) => l.source === "episode/2PeHDoThIp8" && l.target === "person/holly-tucker",
    );
    expect(guestLink).toBeDefined();
    expect(guestLink!.rel).toBe("guest");
  });
});

describe("getBackrefs", () => {
  it("finds pages that link to a target", () => {
    const pages = loadWiki(FIXTURES);
    const refs = getBackrefs("concept/work-ethic", pages);
    const ids = refs.map((p) => `${p.type}/${p.slug}`);
    expect(ids).toContain("person/holly-tucker");
    expect(ids).toContain("episode/2PeHDoThIp8");
  });
});

describe("parseIndex", () => {
  it("parses the markdown table into entries", () => {
    const entries = parseIndex(path.join(FIXTURES, "sample-index.md"));
    expect(entries.length).toBe(5);
    expect(entries[0]).toEqual({
      name: "Holly Tucker",
      type: "person",
      file: "people/holly-tucker",
      aliases: "",
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx vitest run lib/wiki.test.ts
```

Expected: FAIL — `loadWiki is not exported`

- [ ] **Step 3: Implement loadWiki, buildGraph, getBackrefs, parseIndex**

Append to `dashboard/lib/wiki.ts`:

```ts
// ── Directory walker ───────────────────────────────────

const ENTITY_DIRS = [
  "people",
  "concepts",
  "organizations",
  "works",
  "methods",
  "products",
  "podcasts",
  "_places",
  "_episodes",
];

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

export function loadWiki(wikiDir: string): Map<string, WikiPage> {
  const pages = new Map<string, WikiPage>();
  for (const dir of ENTITY_DIRS) {
    const dirPath = path.join(wikiDir, dir);
    if (!fs.existsSync(dirPath)) continue;
    for (const file of fs.readdirSync(dirPath)) {
      if (!file.endsWith(".md")) continue;
      const filePath = path.join(dirPath, file);
      try {
        const page = parsePage(filePath);
        const typeKey = DIR_TO_TYPE[dir] || dir;
        const key = `${typeKey}/${page.slug}`;
        pages.set(key, page);
      } catch {
        // skip unparseable files
      }
    }
  }
  return pages;
}

// ── Graph builder ──────────────────────────────────────

export function buildGraph(pages: Map<string, WikiPage>): GraphData {
  const nodeMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  // Create nodes for every page
  for (const [id, page] of pages) {
    nodeMap.set(id, { id, type: page.type, name: page.name, val: 0 });
  }

  // Create links from outlinks; also create phantom nodes for targets not in pages
  for (const [sourceId, page] of pages) {
    for (const outlink of page.outlinks) {
      const targetId = `${DIR_TO_TYPE[outlink.type] || outlink.type}/${outlink.slug}`;
      // Normalize: outlink.type might be a dir name (e.g. "concepts")
      // or already a type name (e.g. "concept"). Check both.
      let resolvedTarget = targetId;
      if (!nodeMap.has(resolvedTarget)) {
        // Try dir name as type directly
        const altId = `${outlink.type}/${outlink.slug}`;
        if (nodeMap.has(altId)) {
          resolvedTarget = altId;
        } else {
          // Create phantom node
          nodeMap.set(resolvedTarget, {
            id: resolvedTarget,
            type: DIR_TO_TYPE[outlink.type] || outlink.type,
            name: outlink.slug.replace(/-/g, " "),
            val: 0,
          });
        }
      }

      links.push({
        source: sourceId,
        target: resolvedTarget,
        rel: outlink.rel || "mentions",
      });
    }
  }

  // Compute degree (val) for node sizing
  for (const link of links) {
    const s = nodeMap.get(link.source);
    if (s) s.val++;
    const t = nodeMap.get(link.target);
    if (t) t.val++;
  }

  return { nodes: Array.from(nodeMap.values()), links };
}

// ── Backrefs ───────────────────────────────────────────

export function getBackrefs(targetId: string, pages: Map<string, WikiPage>): WikiPage[] {
  const results: WikiPage[] = [];
  const [targetType, targetSlug] = targetId.split("/");
  for (const [id, page] of pages) {
    if (id === targetId) continue;
    const links = page.outlinks.some(
      (o) => o.slug === targetSlug && (DIR_TO_TYPE[o.type] || o.type) === targetType,
    );
    if (links) results.push(page);
  }
  return results;
}

// ── Index parser ───────────────────────────────────────

export function parseIndex(indexPath: string): IndexEntry[] {
  const raw = fs.readFileSync(indexPath, "utf-8");
  const lines = raw.split("\n");
  const entries: IndexEntry[] = [];
  for (const line of lines) {
    if (!line.startsWith("|") || line.includes("---") || line.toLowerCase().includes("name")) continue;
    const cells = line.split("|").map((c) => c.trim()).filter(Boolean);
    if (cells.length >= 3) {
      entries.push({
        name: cells[0],
        type: cells[1],
        file: cells[2],
        aliases: cells[3] || "",
      });
    }
  }
  return entries;
}

// ── Singleton cache ────────────────────────────────────

const WIKI_DIR = process.env.VAULT_WIKI_DIR || path.join(process.cwd(), "..", "wiki");

let _cache: Map<string, WikiPage> | null = null;

export function getWiki(): Map<string, WikiPage> {
  if (!_cache) {
    _cache = loadWiki(WIKI_DIR);
  }
  return _cache;
}

export function invalidateCache(): void {
  _cache = null;
}
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx vitest run lib/wiki.test.ts
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/lib/wiki.ts dashboard/lib/wiki.test.ts
git commit -m "feat: add loadWiki, buildGraph, getBackrefs, parseIndex"
```

---

### Task 5: API routes — `/api/graph` and `/api/entities`

**Files:**
- Create: `dashboard/app/api/graph/route.ts`
- Create: `dashboard/app/api/entities/route.ts`
- Create: `dashboard/app/api/entities/[type]/[slug]/route.ts`
- Create: `dashboard/app/api/episodes/[youtubeId]/wiki/route.ts`

- [ ] **Step 1: Create `/api/graph/route.ts`**

Create `dashboard/app/api/graph/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getWiki, buildGraph } from "@/lib/wiki";

export const dynamic = "force-dynamic";

export async function GET() {
  const pages = getWiki();
  const graph = buildGraph(pages);
  return NextResponse.json(graph);
}
```

- [ ] **Step 2: Create `/api/entities/route.ts`**

Create `dashboard/app/api/entities/route.ts`:

```ts
import { NextResponse } from "next/server";
import path from "path";
import { parseIndex } from "@/lib/wiki";

export const dynamic = "force-dynamic";

const WIKI_DIR = process.env.VAULT_WIKI_DIR || path.join(process.cwd(), "..", "wiki");

export async function GET() {
  const entries = parseIndex(path.join(WIKI_DIR, "_index.md"));
  return NextResponse.json(entries);
}
```

- [ ] **Step 3: Create `/api/entities/[type]/[slug]/route.ts`**

Create `dashboard/app/api/entities/[type]/[slug]/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getWiki, getBackrefs } from "@/lib/wiki";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ type: string; slug: string }> },
) {
  const { type, slug } = await params;
  const pages = getWiki();
  const id = `${type}/${slug}`;
  const page = pages.get(id);
  if (!page) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  const backrefs = getBackrefs(id, pages).map((p) => ({
    id: `${p.type}/${p.slug}`,
    type: p.type,
    name: p.name,
  }));
  return NextResponse.json({
    type: page.type,
    slug: page.slug,
    name: page.name,
    frontmatter: page.frontmatter,
    body: page.body,
    outlinks: page.outlinks,
    backrefs,
  });
}
```

- [ ] **Step 4: Create `/api/episodes/[youtubeId]/wiki/route.ts`**

Create `dashboard/app/api/episodes/[youtubeId]/wiki/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getWiki, getBackrefs } from "@/lib/wiki";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ youtubeId: string }> },
) {
  const { youtubeId } = await params;
  const pages = getWiki();
  const id = `episode/${youtubeId}`;
  const page = pages.get(id);
  if (!page) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  const backrefs = getBackrefs(id, pages).map((p) => ({
    id: `${p.type}/${p.slug}`,
    type: p.type,
    name: p.name,
  }));
  return NextResponse.json({
    type: page.type,
    slug: page.slug,
    name: page.name,
    frontmatter: page.frontmatter,
    body: page.body,
    outlinks: page.outlinks,
    backrefs,
  });
}
```

- [ ] **Step 5: Smoke test all routes**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
npx next dev --turbopack --port 3001 &
sleep 3
curl -s http://localhost:3001/api/graph | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'nodes={len(d[\"nodes\"])}, links={len(d[\"links\"])}')"
curl -s http://localhost:3001/api/entities | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'entries={len(d)}')"
curl -s http://localhost:3001/api/entities/person/holly-tucker | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','ERR'))"
curl -s http://localhost:3001/api/episodes/2PeHDoThIp8/wiki | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','ERR'))"
```

Expected: nodes>100, entries>100, "Holly Tucker", episode title.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app/api/graph/ dashboard/app/api/entities/ dashboard/app/api/episodes/
git commit -m "feat: add /api/graph, /api/entities, /api/episodes wiki routes"
```

---

### Task 6: Graph page — Obsidian-style force graph (hero view)

**Files:**
- Create: `dashboard/components/force-graph.tsx`
- Create: `dashboard/app/graph/page.tsx`

- [ ] **Step 1: Create ForceGraph client wrapper**

Create `dashboard/components/force-graph.tsx`:

```tsx
"use client";

import { useRef, useCallback, useMemo, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

interface GraphNode {
  id: string;
  type: string;
  name: string;
  val: number;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  rel: string;
}

interface Props {
  nodes: GraphNode[];
  links: GraphLink[];
  typeFilter: Set<string>;
  searchQuery: string;
  onNodeClick?: (node: GraphNode) => void;
}

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

export default function ForceGraphView({
  nodes,
  links,
  typeFilter,
  searchQuery,
  onNodeClick,
}: Props) {
  const fgRef = useRef<any>(null);
  const router = useRouter();

  const filteredData = useMemo(() => {
    const visibleIds = new Set(
      nodes
        .filter((n) => typeFilter.has(n.type))
        .filter((n) =>
          searchQuery
            ? n.name.toLowerCase().includes(searchQuery.toLowerCase())
            : true,
        )
        .map((n) => n.id),
    );
    return {
      nodes: nodes.filter((n) => visibleIds.has(n.id)),
      links: links.filter((l) => {
        const sid = typeof l.source === "string" ? l.source : l.source.id;
        const tid = typeof l.target === "string" ? l.target : l.target.id;
        return visibleIds.has(sid) && visibleIds.has(tid);
      }),
    };
  }, [nodes, links, typeFilter, searchQuery]);

  const handleClick = useCallback(
    (node: GraphNode) => {
      if (onNodeClick) {
        onNodeClick(node);
      } else {
        if (node.type === "episode") {
          router.push(`/episodes/${node.id.split("/")[1]}/wiki`);
        } else {
          router.push(`/entity/${node.id}`);
        }
      }
    },
    [router, onNodeClick],
  );

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.name as string;
      const fontSize = Math.max(12 / globalScale, 2);
      const r = Math.max(3, Math.sqrt(node.val || 1) * 2);
      const color = TYPE_COLORS[node.type] || "#6b7280";

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      if (globalScale > 1.5) {
        ctx.font = `${fontSize}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "hsl(0, 0%, 80%)";
        ctx.fillText(label, node.x, node.y + r + 2);
      }
    },
    [],
  );

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={filteredData}
      nodeId="id"
      nodeCanvasObject={nodeCanvasObject}
      nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
        const r = Math.max(3, Math.sqrt(node.val || 1) * 2);
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
      }}
      linkColor={() => "rgba(255,255,255,0.08)"}
      linkWidth={0.5}
      onNodeClick={handleClick}
      backgroundColor="hsl(0, 0%, 3.9%)"
      width={typeof window !== "undefined" ? window.innerWidth - 280 : 800}
      height={typeof window !== "undefined" ? window.innerHeight : 600}
      cooldownTicks={100}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
    />
  );
}
```

- [ ] **Step 2: Create graph page**

Create `dashboard/app/graph/page.tsx`:

```tsx
"use client";

import { useEffect, useState, useMemo } from "react";
import ForceGraphView from "@/components/force-graph";

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

interface GraphData {
  nodes: Array<{ id: string; type: string; name: string; val: number }>;
  links: Array<{ source: string; target: string; rel: string }>;
}

export default function GraphPage() {
  const [data, setData] = useState<GraphData | null>(null);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(ALL_TYPES));
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/api/graph")
      .then((r) => r.json())
      .then(setData);
  }, []);

  const stats = useMemo(() => {
    if (!data) return null;
    const typeCounts: Record<string, number> = {};
    for (const n of data.nodes) {
      typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    }
    return typeCounts;
  }, [data]);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">Loading graph...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-[280px] border-r border-border p-4 overflow-y-auto">
        <h2 className="text-lg font-semibold mb-4">Knowledge Graph</h2>
        <p className="text-xs text-muted-foreground mb-4">
          {data.nodes.length} entities &middot; {data.links.length} edges
        </p>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter nodes..."
          className="w-full px-3 py-2 text-sm bg-muted rounded-md border border-border mb-4"
        />
        <div className="space-y-2">
          {ALL_TYPES.map((type) => (
            <label
              key={type}
              className="flex items-center gap-2 text-sm cursor-pointer"
            >
              <input
                type="checkbox"
                checked={activeTypes.has(type)}
                onChange={() => toggleType(type)}
                className="rounded"
              />
              <span
                className="w-3 h-3 rounded-full inline-block"
                style={{ backgroundColor: TYPE_COLORS[type] }}
              />
              <span className="capitalize">{type}</span>
              {stats && (
                <span className="text-muted-foreground ml-auto">
                  {stats[type] || 0}
                </span>
              )}
            </label>
          ))}
        </div>
      </div>
      {/* Graph */}
      <div className="flex-1 relative">
        <ForceGraphView
          nodes={data.nodes}
          links={data.links}
          typeFilter={activeTypes}
          searchQuery={search}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Test in browser**

Navigate to `http://localhost:3001/graph` in browser. Verify:
- Graph renders with colored nodes
- Sidebar shows type checkboxes with counts
- Toggling a type hides/shows those nodes
- Typing in filter narrows visible nodes
- Clicking a node navigates to `/entity/[type]/[slug]` (will 404 — that's Task 7)

- [ ] **Step 4: Commit**

```bash
git add dashboard/components/force-graph.tsx dashboard/app/graph/
git commit -m "feat: add Obsidian-style force graph page"
```

---

### Task 7: Entity detail page with local graph

**Files:**
- Create: `dashboard/components/local-graph.tsx`
- Create: `dashboard/components/wikilink.tsx`
- Create: `dashboard/app/entity/[type]/[slug]/page.tsx`

- [ ] **Step 1: Create wikilink renderer component**

Create `dashboard/components/wikilink.tsx`:

```tsx
import Link from "next/link";

const TYPE_COLORS: Record<string, string> = {
  person: "text-blue-400",
  concept: "text-green-400",
  organization: "text-orange-400",
  work: "text-purple-400",
  podcast: "text-red-400",
  place: "text-gray-400",
  method: "text-teal-400",
  product: "text-yellow-400",
  episode: "text-pink-400",
};

export function WikiLink({
  type,
  slug,
  children,
}: {
  type: string;
  slug: string;
  children: React.ReactNode;
}) {
  const href =
    type === "episode" ? `/episodes/${slug}/wiki` : `/entity/${type}/${slug}`;
  const color = TYPE_COLORS[type] || "text-muted-foreground";
  return (
    <Link href={href} className={`${color} hover:underline`}>
      {children}
    </Link>
  );
}

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

export function renderWikilinks(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(WIKILINK_RE);
  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const ref = match[1];
    const [type, slug] = ref.split("/");
    if (type && slug) {
      parts.push(
        <WikiLink key={match.index} type={type} slug={slug}>
          {slug.replace(/-/g, " ")}
        </WikiLink>,
      );
    } else {
      parts.push(match[0]);
    }
    lastIndex = re.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}
```

- [ ] **Step 2: Create local graph component**

Create `dashboard/components/local-graph.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import ForceGraphView from "@/components/force-graph";

interface Outlink {
  type: string;
  slug: string;
  rel?: string;
}

interface Backref {
  id: string;
  type: string;
  name: string;
}

interface Props {
  entityId: string;
  entityType: string;
  entityName: string;
  outlinks: Outlink[];
  backrefs: Backref[];
}

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

export default function LocalGraph({
  entityId,
  entityType,
  entityName,
  outlinks,
  backrefs,
}: Props) {
  const data = useMemo(() => {
    const nodeMap = new Map<string, { id: string; type: string; name: string; val: number }>();
    const links: Array<{ source: string; target: string; rel: string }> = [];

    nodeMap.set(entityId, { id: entityId, type: entityType, name: entityName, val: 0 });

    for (const ol of outlinks) {
      const type = DIR_TO_TYPE[ol.type] || ol.type;
      const id = `${type}/${ol.slug}`;
      if (!nodeMap.has(id)) {
        nodeMap.set(id, { id, type, name: ol.slug.replace(/-/g, " "), val: 0 });
      }
      links.push({ source: entityId, target: id, rel: ol.rel || "mentions" });
    }

    for (const br of backrefs) {
      if (!nodeMap.has(br.id)) {
        nodeMap.set(br.id, { id: br.id, type: br.type, name: br.name, val: 0 });
      }
      links.push({ source: br.id, target: entityId, rel: "links_to" });
    }

    for (const l of links) {
      const s = nodeMap.get(l.source);
      if (s) s.val++;
      const t = nodeMap.get(l.target);
      if (t) t.val++;
    }

    return { nodes: Array.from(nodeMap.values()), links };
  }, [entityId, entityType, entityName, outlinks, backrefs]);

  const allTypes = new Set(data.nodes.map((n) => n.type));

  return (
    <div className="h-[400px] w-full border border-border rounded-lg overflow-hidden">
      <ForceGraphView
        nodes={data.nodes}
        links={data.links}
        typeFilter={allTypes}
        searchQuery=""
      />
    </div>
  );
}
```

- [ ] **Step 3: Create entity detail page**

Create `dashboard/app/entity/[type]/[slug]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import LocalGraph from "@/components/local-graph";
import { WikiLink, renderWikilinks } from "@/components/wikilink";

interface EntityData {
  type: string;
  slug: string;
  name: string;
  frontmatter: Record<string, any>;
  body: string;
  outlinks: Array<{ type: string; slug: string; rel?: string }>;
  backrefs: Array<{ id: string; type: string; name: string }>;
}

export default function EntityPage() {
  const params = useParams<{ type: string; slug: string }>();
  const [entity, setEntity] = useState<EntityData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!params.type || !params.slug) return;
    fetch(`/api/entities/${params.type}/${params.slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setEntity)
      .catch(() => setError(true));
  }, [params.type, params.slug]);

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Entity not found.</p>
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const fm = entity.frontmatter;
  const relationships = fm.relationships as Record<string, any[]> | undefined;
  const observations = (fm.observations as Array<{ episode: string; timestamp?: string; text: string }>) || [];

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-5xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="mb-8">
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            {entity.type}
          </p>
          <h1 className="text-3xl font-bold">{entity.name}</h1>
          {fm.bio && (
            <p className="mt-2 text-muted-foreground">{fm.bio as string}</p>
          )}
          {fm.credentials && (
            <p className="mt-1 text-sm text-muted-foreground italic">
              {fm.credentials as string}
            </p>
          )}
        </div>

        {/* Local graph */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-3">Connections</h2>
          <LocalGraph
            entityId={`${entity.type}/${entity.slug}`}
            entityType={entity.type}
            entityName={entity.name}
            outlinks={entity.outlinks}
            backrefs={entity.backrefs}
          />
        </section>

        {/* Relationships */}
        {relationships && Object.keys(relationships).length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold mb-3">Relationships</h2>
            <div className="space-y-4">
              {Object.entries(relationships).map(([rel, entries]) => {
                if (!Array.isArray(entries) || entries.length === 0) return null;
                return (
                  <div key={rel}>
                    <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">
                      {rel.replace(/_/g, " ")}
                    </h3>
                    <ul className="space-y-1">
                      {entries.map((entry, i) => {
                        const entityStr = entry?.entity as string | undefined;
                        if (!entityStr) return null;
                        const match = entityStr.match(/\[\[(\w+)\/([^\]]+)\]\]/);
                        if (!match) return <li key={i}>{entityStr}</li>;
                        return (
                          <li key={i} className="text-sm">
                            <WikiLink type={match[1]} slug={match[2]}>
                              {match[2].replace(/-/g, " ")}
                            </WikiLink>
                            {entry.role && (
                              <span className="text-muted-foreground ml-2">
                                ({entry.role})
                              </span>
                            )}
                            {entry.timestamp && (
                              <span className="text-muted-foreground ml-2 text-xs">
                                @ {entry.timestamp}
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Observations */}
        {observations.length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold mb-3">Observations</h2>
            <ul className="space-y-3">
              {observations.map((obs, i) => (
                <li key={i} className="border-l-2 border-border pl-4">
                  <p className="text-sm">{obs.text}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Episode: {obs.episode}
                    {obs.timestamp && <> &middot; {obs.timestamp}</>}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Backrefs */}
        {entity.backrefs.length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold mb-3">Referenced By</h2>
            <div className="flex flex-wrap gap-2">
              {entity.backrefs.map((ref) => (
                <WikiLink key={ref.id} type={ref.type} slug={ref.id.split("/")[1]}>
                  <span className="px-2 py-1 text-sm rounded-md bg-muted hover:bg-accent">
                    {ref.name}
                  </span>
                </WikiLink>
              ))}
            </div>
          </section>
        )}

        {/* Body (raw markdown rendered with wikilinks) */}
        {entity.body.trim() && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold mb-3">Notes</h2>
            <div className="prose prose-invert max-w-none">
              {entity.body.split("\n").map((line, i) => (
                <p key={i} className="text-sm mb-1">
                  {renderWikilinks(line)}
                </p>
              ))}
            </div>
          </section>
        )}

        <div className="mt-10 pt-6 border-t border-border">
          <Link href="/graph" className="text-sm text-muted-foreground hover:underline">
            &larr; Back to graph
          </Link>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Test in browser**

Navigate to `http://localhost:3001/entity/person/holly-tucker`. Verify:
- Name, type badge, local graph render
- Relationships listed with clickable wikilinks
- Observations listed with timestamps
- Backrefs shown as chips
- Click wikilink navigates to another entity

- [ ] **Step 5: Commit**

```bash
git add dashboard/components/wikilink.tsx dashboard/components/local-graph.tsx dashboard/app/entity/
git commit -m "feat: add entity detail page with local graph"
```

---

### Task 8: Episode wiki page

**Files:**
- Create: `dashboard/app/episodes/[id]/wiki/page.tsx`

- [ ] **Step 1: Create episode wiki page**

Create `dashboard/app/episodes/[id]/wiki/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { WikiLink, renderWikilinks } from "@/components/wikilink";

interface EpisodeData {
  type: string;
  slug: string;
  name: string;
  frontmatter: Record<string, any>;
  body: string;
  outlinks: Array<{ type: string; slug: string; rel?: string }>;
  backrefs: Array<{ id: string; type: string; name: string }>;
}

export default function EpisodeWikiPage() {
  const params = useParams<{ id: string }>();
  const [episode, setEpisode] = useState<EpisodeData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!params.id) return;
    fetch(`/api/episodes/${params.id}/wiki`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setEpisode)
      .catch(() => setError(true));
  }, [params.id]);

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Episode not found.</p>
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const fm = episode.frontmatter;
  const topics = (fm.topics as string[]) || [];

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-6 py-10">
        <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
          Episode
        </p>
        <h1 className="text-2xl font-bold mb-2">{episode.name}</h1>
        {fm.date && (
          <p className="text-sm text-muted-foreground mb-4">{fm.date}</p>
        )}

        {/* Guest / Host / Podcast */}
        <div className="flex flex-wrap gap-4 mb-6 text-sm">
          {fm.guest && typeof fm.guest === "string" && (
            <div>
              <span className="text-muted-foreground">Guest: </span>
              {renderWikilinks(fm.guest)}
            </div>
          )}
          {fm.host && typeof fm.host === "string" && (
            <div>
              <span className="text-muted-foreground">Host: </span>
              {renderWikilinks(fm.host)}
            </div>
          )}
          {fm.podcast && typeof fm.podcast === "string" && (
            <div>
              <span className="text-muted-foreground">Podcast: </span>
              {renderWikilinks(fm.podcast)}
            </div>
          )}
        </div>

        {/* Topics */}
        {topics.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-8">
            {topics.map((topic, i) => {
              const match = topic.match(/\[\[(\w+)\/([^\]]+)\]\]/);
              if (!match) return <span key={i} className="px-2 py-1 text-xs rounded bg-muted">{topic}</span>;
              return (
                <WikiLink key={i} type={match[1]} slug={match[2]}>
                  <span className="px-2 py-1 text-xs rounded bg-muted hover:bg-accent">
                    {match[2].replace(/-/g, " ")}
                  </span>
                </WikiLink>
              );
            })}
          </div>
        )}

        {/* YouTube embed */}
        {fm.youtube_id && (
          <div className="aspect-video mb-8 rounded-lg overflow-hidden">
            <iframe
              src={`https://www.youtube.com/embed/${fm.youtube_id}`}
              className="w-full h-full"
              allowFullScreen
            />
          </div>
        )}

        {/* Body with rendered wikilinks */}
        <div className="prose prose-invert max-w-none">
          {episode.body.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return (
                <h2 key={i} className="text-lg font-semibold mt-8 mb-3">
                  {line.slice(3)}
                </h2>
              );
            }
            if (line.startsWith("- ")) {
              return (
                <li key={i} className="text-sm ml-4 mb-1">
                  {renderWikilinks(line.slice(2))}
                </li>
              );
            }
            if (line.trim() === "") return <br key={i} />;
            return (
              <p key={i} className="text-sm mb-1">
                {renderWikilinks(line)}
              </p>
            );
          })}
        </div>

        <div className="mt-10 pt-6 border-t border-border">
          <Link href="/graph" className="text-sm text-muted-foreground hover:underline">
            &larr; Back to graph
          </Link>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Test in browser**

Navigate to `http://localhost:3001/episodes/2PeHDoThIp8/wiki`. Verify:
- Title, date, guest/host/podcast with clickable wikilinks
- Topic chips clickable
- YouTube embed plays
- Body markdown rendered with clickable `[[type/slug]]` links

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/episodes/
git commit -m "feat: add episode wiki page with wikilinks"
```

---

### Task 9: Cmd+K search overlay

**Files:**
- Create: `dashboard/components/search-command.tsx`
- Modify: `dashboard/app/layout.tsx`

- [ ] **Step 1: Create search command component**

Create `dashboard/components/search-command.tsx`:

```tsx
"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

interface IndexEntry {
  name: string;
  type: string;
  file: string;
  aliases: string;
}

const TYPE_COLORS: Record<string, string> = {
  person: "text-blue-400",
  concept: "text-green-400",
  organization: "text-orange-400",
  work: "text-purple-400",
  podcast: "text-red-400",
  place: "text-gray-400",
  method: "text-teal-400",
  product: "text-yellow-400",
};

export default function SearchCommand() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    fetch("/api/entities")
      .then((r) => r.json())
      .then(setEntries)
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = query.length < 1
    ? []
    : entries
        .filter((e) => {
          const q = query.toLowerCase();
          return (
            e.name.toLowerCase().includes(q) ||
            e.file.toLowerCase().includes(q) ||
            e.aliases.toLowerCase().includes(q)
          );
        })
        .slice(0, 20);

  const navigate = useCallback(
    (entry: IndexEntry) => {
      setOpen(false);
      const parts = entry.file.split("/");
      if (parts.length === 2) {
        if (parts[0] === "_episodes") {
          router.push(`/episodes/${parts[1]}/wiki`);
        } else {
          router.push(`/entity/${entry.type}/${parts[1]}`);
        }
      }
    },
    [router],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && filtered[selected]) {
      navigate(filtered[selected]);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      <div className="fixed inset-0 bg-black/60" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search entities..."
          className="w-full px-4 py-3 bg-transparent border-b border-border text-foreground text-sm outline-none"
        />
        {filtered.length > 0 && (
          <ul className="max-h-[300px] overflow-y-auto py-1">
            {filtered.map((entry, i) => (
              <li
                key={entry.file}
                onClick={() => navigate(entry)}
                className={`px-4 py-2 cursor-pointer flex items-center gap-3 text-sm ${
                  i === selected ? "bg-accent" : "hover:bg-muted"
                }`}
              >
                <span
                  className={`text-xs uppercase font-medium w-20 ${
                    TYPE_COLORS[entry.type] || "text-muted-foreground"
                  }`}
                >
                  {entry.type}
                </span>
                <span>{entry.name}</span>
              </li>
            ))}
          </ul>
        )}
        {query.length > 0 && filtered.length === 0 && (
          <p className="px-4 py-3 text-sm text-muted-foreground">No results.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update layout with nav bar and search**

Read current `dashboard/app/layout.tsx` and replace with:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import SearchCommand from "@/components/search-command";

export const metadata: Metadata = {
  title: "Vault Dashboard",
  description: "Knowledge graph and diarization tools",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background antialiased">
        <nav className="border-b border-border px-6 py-3 flex items-center gap-6">
          <Link href="/" className="font-semibold text-foreground">
            Vault
          </Link>
          <Link
            href="/graph"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Graph
          </Link>
          <span className="ml-auto text-xs text-muted-foreground">
            ⌘K to search
          </span>
        </nav>
        <SearchCommand />
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 3: Update home page with graph link**

Replace `dashboard/app/page.tsx` with:

```tsx
import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-[calc(100vh-52px)] flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-4">Vault Dashboard</h1>
      <p className="text-muted-foreground mb-8">
        Knowledge graph and diarization tools
      </p>
      <div className="flex gap-4">
        <Link
          href="/graph"
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90"
        >
          Knowledge Graph
        </Link>
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Test in browser**

- Load `http://localhost:3001` — verify nav bar, "Knowledge Graph" button
- Press Cmd+K — verify search overlay opens
- Type "holly" — verify Holly Tucker appears
- Arrow keys + Enter — verify navigation to entity page
- Click "Graph" in nav — verify graph loads

- [ ] **Step 5: Commit**

```bash
git add dashboard/components/search-command.tsx dashboard/app/layout.tsx dashboard/app/page.tsx
git commit -m "feat: add Cmd+K search, nav bar, and updated home page"
```

---

### Task 10: Data refresh — wipe touched pages and re-extract

**Files:**
- No new files — uses existing pipeline scripts

This task wipes wiki pages touched by the 24-episode batch, resets DB
checkpoints, and re-runs extraction with the quality fixes.

- [ ] **Step 1: Identify 24 youtube_ids in the batch**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python3 -c "
from scripts.agents.db import fetch_all
eps = fetch_all('''
    SELECT youtube_id FROM episodes
    WHERE channel_id = (SELECT id FROM channels LIMIT 1)
    ORDER BY COALESCE(published_at, '9999-01-01') ASC
    OFFSET 6 LIMIT 24
''')
for e in eps:
    print(e['youtube_id'])
"
```

Save the output list — those are the 24 youtube_ids.

- [ ] **Step 2: Collect touched slugs and wipe**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python3 -c "
import re, os
from pathlib import Path
from scripts.agents.db import fetch_all

wiki = Path('wiki')
eps = fetch_all('''
    SELECT youtube_id FROM episodes
    WHERE channel_id = (SELECT id FROM channels LIMIT 1)
    ORDER BY COALESCE(published_at, '9999-01-01') ASC
    OFFSET 6 LIMIT 24
''')
yids = [e['youtube_id'] for e in eps]
SEEDS = {'people/steven-bartlett.md', 'podcasts/diary-of-a-ceo.md'}
WIKILINK = re.compile(r'\[\[([^\]]+)\]\]')

# Collect touched slugs from episode pages
touched = set()
for yid in yids:
    ep_path = wiki / '_episodes' / f'{yid}.md'
    if ep_path.exists():
        for m in WIKILINK.finditer(ep_path.read_text()):
            ref = m.group(1)
            parts = ref.split('/')
            if len(parts) == 2:
                touched.add(f'{parts[0]}/{parts[1]}.md')

# Wipe episode pages
deleted = 0
for yid in yids:
    ep_path = wiki / '_episodes' / f'{yid}.md'
    if ep_path.exists():
        ep_path.unlink()
        deleted += 1

# Wipe touched entity pages (except seeds)
for ref in touched:
    p = wiki / ref
    if p.exists() and ref not in SEEDS:
        p.unlink()
        deleted += 1

# Delete orphan
orphan = wiki / 'podcasts' / 'unnamed-podcast.md'
if orphan.exists():
    orphan.unlink()
    deleted += 1

print(f'Deleted {deleted} files')
"
```

- [ ] **Step 3: Rebuild _index.md — remove stale entries**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python3 -c "
from pathlib import Path
wiki = Path('wiki')
index = wiki / '_index.md'
lines = index.read_text().splitlines()
kept = []
removed = 0
for line in lines:
    if not line.startswith('|') or '---' in line or 'Name' in line:
        kept.append(line)
        continue
    cells = [c.strip() for c in line.split('|') if c.strip()]
    if len(cells) >= 3:
        fpath = cells[2]
        if (wiki / (fpath + '.md')).exists():
            kept.append(line)
        else:
            removed += 1
    else:
        kept.append(line)
index.write_text('\n'.join(kept) + '\n')
print(f'Removed {removed} stale index entries')
"
```

- [ ] **Step 4: Reset DB checkpoints**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python3 -c "
from scripts.agents.db import execute, fetch_all
eps = fetch_all('''
    SELECT id FROM episodes
    WHERE channel_id = (SELECT id FROM channels LIMIT 1)
    ORDER BY COALESCE(published_at, '9999-01-01') ASC
    OFFSET 6 LIMIT 24
''')
ids = [e['id'] for e in eps]
placeholders = ','.join(['%s'] * len(ids))
n = execute(
    f'UPDATE episodes SET wiki_processed_at=NULL, persona_enriched_at=NULL WHERE id IN ({placeholders})',
    ids,
)
print(f'Reset {n} episodes')
"
```

- [ ] **Step 5: Re-run extract pipeline**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
python -u -m scripts.agents.run_pipeline --stage extract --start 6 --limit 24 2>&1 | tee /tmp/wiki-refresh.log
```

Expected: ~30min, ~$1.30. Watch for zero `unnamed-podcast` warnings.

- [ ] **Step 6: Validate quality fixes**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
echo "=== unnamed-podcast ===" && grep -r "unnamed-podcast" wiki/ | wc -l
echo "=== bare seconds timestamps ===" && grep -rP '^\s+timestamp: \d+s' wiki/people/ | head -5
echo "=== slug drift ===" && grep -r "not-in-the-high-street" wiki/ | wc -l
echo "=== entity count ===" && find wiki -name "*.md" | wc -l
```

Expected: unnamed-podcast=0, bare seconds=0 (all HH:MM:SS), slug drift=0 (all `not-on-the-high-street`).

- [ ] **Step 7: Restart dashboard and verify graph**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault/dashboard
# kill existing next dev if running, then:
npx next dev --turbopack --port 3001
```

Navigate to `http://localhost:3001/graph` — verify refreshed data shows in graph.

- [ ] **Step 8: Commit refreshed wiki**

```bash
cd /Users/chaturaattidiya/Documents/Github/project-ref/vault
git add wiki/
git commit -m "data: refresh wiki with quality fixes (24 episodes re-extracted)"
```

---

### Task 11: Rewrite people page to use wiki data

**Files:**
- Modify: `vault/app/[channel]/people/page.tsx`

The existing page reads from `agent_memories` (0 rows). Rewrite to read
wiki `people/` files via the dashboard's `/api/entities` endpoint, or
(since this page is in the root `vault/app/` not `vault/dashboard/app/`)
read wiki files directly.

Note: This page lives in `vault/app/` which is a separate Next.js app
from `vault/dashboard/`. If only the dashboard matters, this task can be
deferred. If the root app needs to work, implement as below.

- [ ] **Step 1: Rewrite people page to read wiki/people/ directly**

Replace `vault/app/[channel]/people/page.tsx` with:

```tsx
import fs from "fs";
import path from "path";
import matter from "gray-matter";
import Link from "next/link";
import { Users } from "lucide-react";

const WIKI_DIR = path.join(process.cwd(), "wiki");

interface PersonData {
  name: string;
  slug: string;
  bio?: string;
  credentials?: string;
  observationCount: number;
}

function loadPeople(): PersonData[] {
  const dir = path.join(WIKI_DIR, "people");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => {
      const raw = fs.readFileSync(path.join(dir, f), "utf-8");
      const { data: fm } = matter(raw);
      return {
        name: (fm.name as string) || f.replace(".md", ""),
        slug: (fm.slug as string) || f.replace(".md", ""),
        bio: fm.bio as string | undefined,
        credentials: fm.credentials as string | undefined,
        observationCount: Array.isArray(fm.observations)
          ? fm.observations.length
          : 0,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const people = loadPeople();

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">People</h1>
          <p className="text-muted-foreground">
            {people.length} people from podcast transcripts
          </p>
        </div>

        {people.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <Users className="h-8 w-8 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">No People Yet</h2>
            <p className="text-muted-foreground max-w-md">
              Run the pipeline to extract people from transcripts.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {people.map((person) => (
              <Link
                key={person.slug}
                href={`/${channel}/people/${person.slug}`}
                className="border border-neutral-200 dark:border-neutral-800 rounded-xl p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors"
              >
                <div className="flex items-center gap-4 mb-3">
                  <div className="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-lg font-semibold">
                    {person.name.charAt(0)}
                  </div>
                  <div>
                    <h3 className="font-semibold">{person.name}</h3>
                    {person.credentials && (
                      <p className="text-xs text-muted-foreground">
                        {person.credentials}
                      </p>
                    )}
                  </div>
                </div>
                {person.bio && (
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {person.bio}
                  </p>
                )}
                <p className="text-xs text-muted-foreground mt-2">
                  {person.observationCount} observations
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify in browser**

Navigate to `http://localhost:3000/diary-of-a-ceo/people` (or whatever port the root app runs on). Verify people grid renders with names from wiki files.

- [ ] **Step 3: Commit**

```bash
git add app/\[channel\]/people/page.tsx
git commit -m "fix: rewrite people page to read wiki files instead of agent_memories"
```
