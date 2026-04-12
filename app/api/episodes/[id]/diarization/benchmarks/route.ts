import { NextResponse } from "next/server";

export async function GET() {
  // Benchmarks not yet persisted — return empty array.
  return NextResponse.json([]);
}
