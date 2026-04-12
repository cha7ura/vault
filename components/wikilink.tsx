import Link from "next/link";
import React from "react";

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

/**
 * Parse text containing `[[type/slug]]` wikilinks and return an array of
 * React nodes — plain strings interspersed with WikiLink elements.
 */
export function renderWikilinks(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  WIKILINK_RE.lastIndex = 0;
  while ((match = WIKILINK_RE.exec(text)) !== null) {
    // Push any text before this match
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const inner = match[1]; // e.g. "people/holly-tucker"
    const slashIdx = inner.indexOf("/");
    if (slashIdx === -1) {
      // Bare link with no type — render as plain text
      nodes.push(match[0]);
    } else {
      const type = inner.slice(0, slashIdx);
      const slug = inner.slice(slashIdx + 1);
      const displayName = slug
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
      nodes.push(
        <WikiLink key={`${type}/${slug}-${match.index}`} type={type} slug={slug}>
          {displayName}
        </WikiLink>,
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // Push any trailing text
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}
