'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { 
  Search, 
  MessageSquare, 
  Play, 
  Users, 
  Lightbulb, 
  BookOpen,
  Quote,
  Heart,
  Brain,
  Sparkles,
  Menu,
  X,
  Home,
  ChevronLeft
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState } from 'react'

interface Channel {
  id: string;
  name: string;
  slug: string;
  thumbnail_url?: string;
  description?: string;
}

export function ChannelSidebar({ channel }: { channel: Channel }) {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const baseUrl = `/${channel.slug}`

  const navigation = [
    {
      name: 'Discover',
      items: [
        { name: 'Search', href: baseUrl, icon: Search },
        { name: 'Ask AI', href: `${baseUrl}/ask`, icon: MessageSquare },
      ],
    },
    {
      name: 'Insights',
      items: [
        { name: 'Frameworks', href: `${baseUrl}/frameworks`, icon: Lightbulb },
        { name: 'Quotes', href: `${baseUrl}/quotes`, icon: Quote },
        { name: 'Stories', href: `${baseUrl}/stories`, icon: BookOpen },
        { name: 'Mindset', href: `${baseUrl}/mindset`, icon: Brain },
        { name: 'Health', href: `${baseUrl}/health`, icon: Heart },
        { name: 'Relationships', href: `${baseUrl}/relationships`, icon: Sparkles },
      ],
    },
    {
      name: 'Catalog',
      items: [
        { name: 'Episodes', href: `${baseUrl}/episodes`, icon: Play },
        { name: 'People', href: `${baseUrl}/people`, icon: Users },
        { name: 'Books', href: `${baseUrl}/books`, icon: BookOpen },
      ],
    },
  ]

  return (
    <>
      {/* Mobile menu button */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-md bg-background border border-border"
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
      </button>

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed top-0 left-0 z-40 h-screen w-64 bg-background border-r border-border transition-transform lg:translate-x-0',
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="h-full flex flex-col overflow-y-auto">
          {/* Back to channels */}
          <div className="p-4 border-b border-border">
            <Link 
              href="/" 
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              All Channels
            </Link>
          </div>

          {/* Channel Header */}
          <div className="p-6 border-b border-border">
            <Link href={baseUrl} className="flex items-center gap-3">
              {channel.thumbnail_url ? (
                <img
                  src={channel.thumbnail_url}
                  alt={channel.name}
                  className="w-10 h-10 rounded-lg object-cover"
                />
              ) : (
                <div className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center">
                  <Play className="h-5 w-5 text-primary-foreground" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <span className="font-bold text-lg truncate block">{channel.name}</span>
              </div>
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-6">
            {navigation.map((section) => (
              <div key={section.name}>
                <h3 className="px-3 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {section.name}
                </h3>
                <ul className="space-y-1">
                  {section.items.map((item) => {
                    const Icon = item.icon
                    const isActive = pathname === item.href || 
                      (item.href !== baseUrl && pathname?.startsWith(item.href))
                    
                    return (
                      <li key={item.name}>
                        <Link
                          href={item.href}
                          onClick={() => setMobileOpen(false)}
                          className={cn(
                            'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                            isActive
                              ? 'bg-primary text-primary-foreground'
                              : 'text-foreground hover:bg-accent hover:text-accent-foreground'
                          )}
                        >
                          <Icon className="h-5 w-5" />
                          {item.name}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-border">
            <Link
              href={`${baseUrl}/about`}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              About
            </Link>
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setMobileOpen(false)}
        />
      )}
    </>
  )
}
