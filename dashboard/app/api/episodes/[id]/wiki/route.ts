import { NextResponse } from "next/server";
import { getWiki, getBackrefs } from "@/lib/wiki";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id: youtubeId } = await params;
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
