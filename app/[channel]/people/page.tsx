import { Users } from 'lucide-react';

export default async function PeoplePage({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  await params;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">People</h1>
          <p className="text-muted-foreground">
            Guests and speakers from the show
          </p>
        </div>

        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
            <Users className="h-8 w-8 text-muted-foreground" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Coming Soon</h2>
          <p className="text-muted-foreground max-w-md">
            We&apos;re working on identifying and cataloging all guests.
            This page will feature guest profiles, their episodes, and key topics they discussed.
          </p>
        </div>
      </div>
    </div>
  );
}
