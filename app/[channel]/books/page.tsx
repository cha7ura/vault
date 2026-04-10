import { fetchAll } from '@/lib/db';
import { BookCard } from '@/components/book-card';

type BookJoinRow = {
  id: string;
  title: string;
  author: string | null;
  description: string | null;
  cover_url: string | null;
  amazon_url: string | null;
  episode_id: string;
  mention_context: string | null;
  created_at: string | null;
  episode_title: string | null;
  [key: string]: unknown;
};

async function getBooks(channelSlug: string) {
  // Old code did three Supabase round trips: fetch channel, fetch episode
  // IDs, fetch books where episode_id IN (...). Collapse to one JOIN.
  // We preserve Supabase's FK-expansion shape (`book.episodes.title`) by
  // reshaping the flat result below so `BookCard` keeps working unchanged.
  const rows = await fetchAll<BookJoinRow>(
    `SELECT b.*, e.title AS episode_title
       FROM books b
       JOIN episodes e ON e.id = b.episode_id
       JOIN channels c ON c.id = e.channel_id
      WHERE c.slug = $1
      ORDER BY b.title`,
    [channelSlug],
  );

  return rows.map(({ episode_title, ...book }) => ({
    ...book,
    episodes: episode_title ? { title: episode_title } : null,
  }));
}

export default async function BooksPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const books = await getBooks(channel);

  // Deduplicate books by title
  const uniqueBooks = books.reduce(
    (acc, book) => {
      const existing = acc.find(
        (b) => b.title.toLowerCase() === book.title.toLowerCase(),
      );
      if (!existing) acc.push(book);
      return acc;
    },
    [] as typeof books,
  );

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Books</h1>
          <p className="text-muted-foreground">
            {uniqueBooks.length} books mentioned across episodes
          </p>
        </div>

        {uniqueBooks.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {uniqueBooks.map((book) => (
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              <BookCard key={book.id} book={book as any} />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No books mentioned yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
