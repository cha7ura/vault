import { createServerClient } from '@/lib/supabase';
import { BookCard } from '@/components/book-card';

async function getBooks(channelSlug: string) {
  const supabase = createServerClient();
  
  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();
  
  if (!channel) return [];

  const { data: episodes } = await supabase
    .from('episodes')
    .select('id')
    .eq('channel_id', channel.id);
  
  if (!episodes || episodes.length === 0) return [];

  const { data } = await supabase
    .from('books')
    .select('*, episodes(title)')
    .in('episode_id', episodes.map(e => e.id))
    .order('title');
  
  return data || [];
}

export default async function BooksPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const books = await getBooks(channel);

  // Deduplicate books by title
  const uniqueBooks = books.reduce((acc, book) => {
    const existing = acc.find(b => b.title.toLowerCase() === book.title.toLowerCase());
    if (!existing) {
      acc.push(book);
    }
    return acc;
  }, [] as typeof books);

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
              <BookCard key={book.id} book={book} />
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
