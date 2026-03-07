import Link from 'next/link';
import { Card } from '@/components/ui/card';

interface Book {
  id: string;
  title: string;
  author?: string;
  amazon_url?: string;
  context?: string;
  episodes?: {
    id: string;
    youtube_id: string;
    title: string;
  };
}

export function BookCard({ book }: { book: Book }) {
  return (
    <Card className="p-4 hover:shadow-lg transition-shadow">
      <h3 className="font-semibold mb-1">{book.title}</h3>
      {book.author && (
        <p className="text-sm text-muted-foreground mb-2">by {book.author}</p>
      )}
      {book.context && (
        <p className="text-sm text-muted-foreground mb-3">{book.context}</p>
      )}
      <div className="flex items-center gap-3">
        {book.episodes && (
          <Link
            href={`/episode/${book.episodes.id}`}
            className="text-xs text-primary hover:underline"
          >
            View episode →
          </Link>
        )}
        {book.amazon_url && (
          <a
            href={book.amazon_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary hover:underline"
          >
            Amazon →
          </a>
        )}
      </div>
    </Card>
  );
}
