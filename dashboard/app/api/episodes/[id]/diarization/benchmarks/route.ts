import { NextResponse } from "next/server";

export async function GET() {
  // Benchmarks not yet stored in Supabase — return empty array
  return NextResponse.json([]);
}
