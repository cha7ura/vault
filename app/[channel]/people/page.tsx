import fs from "fs";
import path from "path";
import matter from "gray-matter";
import Link from "next/link";
import { Users } from "lucide-react";

const WIKI_DIR = path.join(process.cwd(), "wiki");

interface PersonData {
  name: string;
  slug: string;
  bio?: string;
  credentials?: string;
  observationCount: number;
}

function loadPeople(): PersonData[] {
  const dir = path.join(WIKI_DIR, "people");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".md"))
    .map((f) => {
      const raw = fs.readFileSync(path.join(dir, f), "utf-8");
      const { data: fm } = matter(raw);
      return {
        name: (fm.name as string) || f.replace(".md", ""),
        slug: (fm.slug as string) || f.replace(".md", ""),
        bio: fm.bio as string | undefined,
        credentials: fm.credentials as string | undefined,
        observationCount: Array.isArray(fm.observations)
          ? fm.observations.length
          : 0,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const people = loadPeople();

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">People</h1>
          <p className="text-muted-foreground">
            {people.length} people from podcast transcripts
          </p>
        </div>

        {people.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <Users className="h-8 w-8 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">No People Yet</h2>
            <p className="text-muted-foreground max-w-md">
              Run the pipeline to extract people from transcripts.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {people.map((person) => (
              <Link
                key={person.slug}
                href={`/${channel}/people/${person.slug}`}
                className="border border-neutral-200 dark:border-neutral-800 rounded-xl p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors"
              >
                <div className="flex items-center gap-4 mb-3">
                  <div className="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-lg font-semibold">
                    {person.name.charAt(0)}
                  </div>
                  <div>
                    <h3 className="font-semibold">{person.name}</h3>
                    {person.credentials && (
                      <p className="text-xs text-muted-foreground">
                        {person.credentials}
                      </p>
                    )}
                  </div>
                </div>
                {person.bio && (
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {person.bio}
                  </p>
                )}
                <p className="text-xs text-muted-foreground mt-2">
                  {person.observationCount} observations
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
