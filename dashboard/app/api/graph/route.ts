import { NextResponse } from "next/server";
import { getWiki, buildGraph } from "@/lib/wiki";

export const dynamic = "force-dynamic";

export async function GET() {
  const pages = getWiki();
  const graph = buildGraph(pages);
  return NextResponse.json(graph);
}
