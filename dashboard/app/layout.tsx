import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vault Dashboard",
  description: "Diarization comparison and pipeline monitoring",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background antialiased">{children}</body>
    </html>
  );
}
