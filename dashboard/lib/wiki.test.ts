import { describe, it, expect } from "vitest";
import path from "path";
import { parsePage, extractWikilinks, loadWiki, buildGraph, getBackrefs, parseIndex } from "./wiki";

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
