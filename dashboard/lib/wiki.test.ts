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
