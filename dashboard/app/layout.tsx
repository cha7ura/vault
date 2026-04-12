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
