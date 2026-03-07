import Link from 'next/link';
import Image from 'next/image';
import { Card } from '@/components/ui/card';
import { Twitter, Linkedin, Globe } from 'lucide-react';

interface Guest {
  id: string;
  name: string;
  slug: string;
  bio?: string;
  photo_url?: string;
  twitter?: string;
  linkedin?: string;
  website?: string;
}

interface GuestCardProps {
  guest: Guest;
  channelSlug?: string;
}

export function GuestCard({ guest, channelSlug }: GuestCardProps) {
  const href = channelSlug 
    ? `/${channelSlug}/guests/${guest.slug}`
    : `/guest/${guest.slug}`;

  return (
    <Link href={href}>
      <Card className="p-4 hover:shadow-lg transition-shadow group">
        <div className="flex items-start gap-4">
          {guest.photo_url ? (
            <div className="relative w-16 h-16 rounded-full overflow-hidden flex-shrink-0">
              <Image
                src={guest.photo_url}
                alt={guest.name}
                fill
                className="object-cover"
              />
            </div>
          ) : (
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
              <span className="text-2xl font-semibold text-primary">
                {guest.name.charAt(0).toUpperCase()}
              </span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold mb-1 group-hover:text-primary transition-colors">
              {guest.name}
            </h3>
            {guest.bio && (
              <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
                {guest.bio}
              </p>
            )}
            <div className="flex items-center gap-2">
              {guest.twitter && (
                <span className="text-muted-foreground hover:text-foreground">
                  <Twitter className="h-4 w-4" />
                </span>
              )}
              {guest.linkedin && (
                <span className="text-muted-foreground hover:text-foreground">
                  <Linkedin className="h-4 w-4" />
                </span>
              )}
              {guest.website && (
                <span className="text-muted-foreground hover:text-foreground">
                  <Globe className="h-4 w-4" />
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}
