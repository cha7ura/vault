"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

interface IndexEntry {
  name: string;
  type: string;
  file: string;
  aliases: string;
}

const TYPE_COLORS: Record<string, string> = {
  person: "text-blue-400",
  concept: "text-green-400",
  organization: "text-orange-400",
  work: "text-purple-400",
  podcast: "text-red-400",
  place: "text-gray-400",
  method: "text-teal-400",
  product: "text-yellow-400",
};

export default function SearchCommand() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch index on mount
  useEffect(() => {
    fetch("/api/entities")
      .then((r) => r.json())
      .then((data: IndexEntry[]) => setEntries(data))
      .catch(() => {});
  }, []);

  // Keyboard shortcut listener
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Focus input and reset state when opening
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const filtered = query.trim().length > 0
    ? entries
        .filter((e) => {
          const q = query.toLowerCase();
          return (
            e.name.toLowerCase().includes(q) ||
            e.file.toLowerCase().includes(q) ||
            (e.aliases && e.aliases.toLowerCase().includes(q))
          );
        })
        .slice(0, 20)
    : [];

  const navigate = useCallback(
    (entry: IndexEntry) => {
      setOpen(false);
      if (entry.file.startsWith("_episodes/")) {
        const slug = entry.file.split("/")[1];
        router.push(`/episodes/${slug}/wiki`);
      } else {
        const parts = entry.file.split("/");
        const slug = parts[1];
        router.push(`/entity/${entry.type}/${slug}`);
      }
    },
    [router]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((prev) => Math.min(prev + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter") {
      if (filtered[selected]) {
        navigate(filtered[selected]);
      }
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex pt-[20vh]">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60"
        onClick={() => setOpen(false)}
      />
      {/* Dialog */}
      <div className="relative mx-auto w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <input
          ref={inputRef}
          className="w-full px-4 py-3 border-b border-border bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
          placeholder="Search entities..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={handleKeyDown}
        />
        <div className="max-h-[300px] overflow-y-auto">
          {query.trim().length > 0 && filtered.length === 0 && (
            <p className="px-4 py-3 text-sm text-muted-foreground">
              No results for &ldquo;{query}&rdquo;
            </p>
          )}
          {filtered.map((entry, i) => (
            <div
              key={entry.file}
              className={`px-4 py-2 flex items-center gap-3 cursor-pointer ${
                i === selected ? "bg-accent" : "hover:bg-muted"
              }`}
              onClick={() => navigate(entry)}
              onMouseEnter={() => setSelected(i)}
            >
              <span
                className={`text-xs uppercase w-20 shrink-0 font-medium ${
                  TYPE_COLORS[entry.type] ?? "text-muted-foreground"
                }`}
              >
                {entry.type}
              </span>
              <span className="text-sm text-foreground truncate">
                {entry.name}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
