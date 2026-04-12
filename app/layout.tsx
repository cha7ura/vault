import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import Link from "next/link";
import "./globals.css";
import { Toaster } from '@/components/ui/sonner';
import SearchCommand from "@/components/search-command";

export const metadata: Metadata = {
  title: "Vault | AI-Powered YouTube Channel Insights",
  description: "Search, explore, and chat with your favorite YouTube channels. AI-extracted frameworks, quotes, and insights.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
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
          <Toaster position="bottom-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
