import { createServerClient } from '@/lib/supabase';
import { GuestCard } from '@/components/guest-card';

async function getGuests(channelSlug: string) {
  const supabase = createServerClient();
  
  const { data: channel } = await supabase
    .from('channels')
    .select('id')
    .eq('slug', channelSlug)
    .single();
  
  if (!channel) return [];

  const { data } = await supabase
    .from('guests')
    .select('*')
    .eq('channel_id', channel.id)
    .order('name');
  
  return data || [];
}

export default async function GuestsPage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  const guests = await getGuests(channel);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Guests</h1>
          <p className="text-muted-foreground">
            {guests.length} guests
          </p>
        </div>

        {guests.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {guests.map((guest) => (
              <GuestCard 
                key={guest.id} 
                guest={guest}
                channelSlug={channel}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No guests yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
