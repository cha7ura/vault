'use client'

import { useEffect, useState } from 'react';
import { EpisodeCard } from './episode-card';
import { Loader2 } from 'lucide-react';

interface SearchResult {
  id: string;
  youtube_id: string;
  title: string;
  description?: string;
  thumbnail_url?: string;
  published_at?: string;
  score: number;
  source: string;
}

export function SearchResults({ query }: { query: string }) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) {
      setResults([]);
      return;
    }

    setIsLoading(true);
    setError(null);

    fetch(`/api/search?q=${encodeURIComponent(query)}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.error) {
          setError(data.error);
        } else {
          setResults(data.results || []);
        }
      })
      .catch((err) => {
        setError('Search failed');
        console.error(err);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [query]);

  if (!query) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Enter a search query to get started.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">No results found.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 text-sm text-muted-foreground">
        Found {results.length} result{results.length !== 1 ? 's' : ''}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {results.map((result) => (
          <EpisodeCard
            key={result.id}
            episode={{
              id: result.id,
              youtube_id: result.youtube_id,
              title: result.title,
              description: result.description,
              thumbnail_url: result.thumbnail_url,
              published_at: result.published_at,
            }}
          />
        ))}
      </div>
    </div>
  );
}
