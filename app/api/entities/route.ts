import { NextResponse } from "next/server";
import path from "path";
import { parseIndex } from "@/lib/wiki";

export const dynamic = "force-dynamic";

const WIKI_DIR = process.env.VAULT_WIKI_DIR || path.join(process.cwd(), "wiki");

export async function GET() {
  const entries = parseIndex(path.join(WIKI_DIR, "_index.md"));
  return NextResponse.json(entries);
}
