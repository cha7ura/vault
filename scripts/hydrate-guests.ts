#!/usr/bin/env npx tsx
/**
 * Guest Hydration Pipeline - Multi-tenant
 *
 * Uses Firecrawl web search to research guest profiles and enrich them
 * with additional information like bio, social links, books authored, etc.
 *
 * Usage:
 *   npx tsx scripts/hydrate-guests.ts --channel "https://www.youtube.com/@TheDiaryOfACEO"
 *   npx tsx scripts/hydrate-guests.ts --channel UCrPseYLGpNygVi34QpGNqpA --guest-id <uuid>
 *   npx tsx scripts/hydrate-guests.ts --all-channels
 */

import { Command } from 'commander';
import { searchWeb, FirecrawlSource } from '../lib/firecrawl';
import { chat } from '../lib/openrouter';
import { fetchOne, fetchAll, execute } from '../lib/db';
import { resolveChannelId } from '../lib/youtube';

interface GuestProfile {
  bio: string;
  photo_url?: string;
  twitter?: string;
  linkedin?: string;
  website?: string;
  books_authored: { title: string; year?: string; amazon_url?: string }[];
  companies: { name: string; role: string; url?: string }[];
}

interface ChannelRecord {
  id: string;
  name: string;
  slug: string;
}

type GuestRow = {
  id: string;
  name: string;
  channel_id: string;
  bio: string | null;
  hydrated_at: string | null;
};

/**
 * Synthesize a guest profile from web search results using LLM
 */
async function synthesizeGuestProfile(
  guestName: string,
  sources: FirecrawlSource[]
): Promise<GuestProfile> {
  const context = sources
    .map((s, i) => {
      const content = s.markdown || s.content || s.description || '';
      const truncated = content.length > 2500 ? content.substring(0, 2500) + '...' : content;
      return `[${i + 1}] ${s.title}\nURL: ${s.url}\n${truncated}`;
    })
    .join('\n\n---\n\n');

  const prompt = `Based on these web sources, create a comprehensive profile for ${guestName}.

Sources:
${context}

Extract and return a JSON object with:
- bio: A 2-3 sentence professional biography summarizing who they are and what they're known for
- photo_url: URL to their professional photo if found (LinkedIn, company page, etc.)
- twitter: Their Twitter/X handle (just the username without @, e.g., "elonmusk")
- linkedin: Full LinkedIn profile URL if found
- website: Their personal or company website URL
- books_authored: Array of books they have written: [{title, year, amazon_url}]
- companies: Array of companies they founded or have significant roles in: [{name, role, url}]

Rules:
- Only include information you can verify from the sources
- If a field cannot be determined, use null
- For books_authored, only include books they actually wrote, not books mentioned about them
- For companies, include their role (e.g., "Founder", "CEO", "Former CTO")

Return ONLY valid JSON, no explanation.`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at synthesizing biographical information from multiple sources. Always return valid JSON.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.2 }
  );

  const content = response.choices[0]?.message?.content || '{}';
  try {
    const jsonStr = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    const profile = JSON.parse(jsonStr);

    return {
      bio: profile.bio || '',
      photo_url: profile.photo_url || undefined,
      twitter: profile.twitter || undefined,
      linkedin: profile.linkedin || undefined,
      website: profile.website || undefined,
      books_authored: Array.isArray(profile.books_authored) ? profile.books_authored : [],
      companies: Array.isArray(profile.companies) ? profile.companies : [],
    };
  } catch (error) {
    console.error('Failed to parse guest profile:', error);
    return {
      bio: '',
      books_authored: [],
      companies: [],
    };
  }
}

/**
 * Research and hydrate a single guest
 */
async function hydrateGuest(
  guestId: string,
  guestName: string,
): Promise<boolean> {
  try {
    console.log(`\n🔍 Researching: ${guestName}`);

    const searchQueries = [
      `${guestName} biography career`,
      `${guestName} LinkedIn profile`,
      `${guestName} books author`,
    ];

    const allSources: FirecrawlSource[] = [];

    for (const query of searchQueries) {
      try {
        console.log(`   Searching: "${query}"`);
        const result = await searchWeb(query, { limit: 3, scrapeContent: true });
        allSources.push(...result.web);
        await new Promise(resolve => setTimeout(resolve, 1000));
      } catch (error: any) {
        console.warn(`   Warning: Search failed for "${query}": ${error.message}`);
      }
    }

    const uniqueSources = Array.from(
      new Map(allSources.map(s => [s.url, s])).values()
    );

    if (uniqueSources.length === 0) {
      console.log(`   ⚠️ No sources found for ${guestName}`);
      return false;
    }

    console.log(`   Found ${uniqueSources.length} unique sources`);
    console.log('   Synthesizing profile...');
    const profile = await synthesizeGuestProfile(guestName, uniqueSources);

    if (!profile.bio) {
      console.log(`   ⚠️ Could not synthesize profile for ${guestName}`);
      return false;
    }

    console.log('   Updating database...');
    await execute(
      `UPDATE guests
          SET bio = $1,
              photo_url = $2,
              twitter = $3,
              linkedin = $4,
              website = $5,
              books_authored = $6::jsonb,
              companies = $7::jsonb,
              hydrated_at = NOW()
        WHERE id = $8`,
      [
        profile.bio,
        profile.photo_url ?? null,
        profile.twitter ?? null,
        profile.linkedin ?? null,
        profile.website ?? null,
        profile.books_authored.length > 0 ? JSON.stringify(profile.books_authored) : null,
        profile.companies.length > 0 ? JSON.stringify(profile.companies) : null,
        guestId,
      ],
    );

    console.log(`   ✅ Hydrated: ${guestName}`);
    console.log(`      Bio: ${profile.bio.substring(0, 100)}...`);
    if (profile.twitter) console.log(`      Twitter: @${profile.twitter}`);
    if (profile.linkedin) console.log(`      LinkedIn: ${profile.linkedin}`);
    if (profile.books_authored.length > 0) {
      console.log(`      Books: ${profile.books_authored.map(b => b.title).join(', ')}`);
    }
    if (profile.companies.length > 0) {
      console.log(`      Companies: ${profile.companies.map(c => `${c.name} (${c.role})`).join(', ')}`);
    }

    return true;
  } catch (error: any) {
    console.error(`   ❌ Failed to hydrate ${guestName}: ${error.message}`);
    return false;
  }
}

/**
 * Main CLI
 */
async function main() {
  const program = new Command();

  program
    .name('hydrate-guests')
    .description('Hydrate guest profiles with web research')
    .version('2.0.0')
    .option('-c, --channel <url>', 'YouTube channel URL or ID')
    .option('--all-channels', 'Hydrate guests from all channels')
    .option('-g, --guest-id <uuid>', 'Hydrate a specific guest by ID')
    .option('-n, --name <name>', 'Hydrate a guest by name')
    .option('-l, --limit <number>', 'Maximum number of guests to hydrate', (v) => parseInt(v, 10))
    .option('--rehydrate', 'Re-hydrate guests that have already been hydrated')
    .option('--dry-run', 'Show what would be hydrated without actually doing it')
    .parse(process.argv);

  const options = program.opts();

  console.log('🚀 Vault Guest Hydration');
  console.log('========================\n');

  // Validate options
  if (!options.channel && !options.allChannels && !options.guestId) {
    console.error('❌ Must specify --channel, --all-channels, or --guest-id');
    process.exit(1);
  }

  // Check required environment variables
  if (!process.env.FIRECRAWL_API_KEY) {
    console.error('❌ Missing required environment variable: FIRECRAWL_API_KEY');
    console.error('   Get your API key at: https://firecrawl.dev');
    process.exit(1);
  }

  if (!process.env.OPENROUTER_API_KEY) {
    console.error('❌ Missing required environment variable: OPENROUTER_API_KEY');
    process.exit(1);
  }

  // Resolve channel if specified
  let channelRecord: ChannelRecord | null = null;

  if (options.channel) {
    console.log(`Resolving channel: ${options.channel}`);
    const youtubeChannelId = await resolveChannelId(options.channel);

    channelRecord = await fetchOne<ChannelRecord>(
      `SELECT id, name, slug
         FROM channels
        WHERE youtube_channel_id = $1`,
      [youtubeChannelId],
    );

    if (!channelRecord) {
      console.error(`❌ Channel not found in database. Run ingestion first.`);
      process.exit(1);
    }

    console.log(`✓ Channel: ${channelRecord.name} (${channelRecord.slug})\n`);
  }

  // Build WHERE clause dynamically. Each filter appends a `$N` placeholder.
  const where: string[] = [];
  const params: unknown[] = [];

  if (options.guestId) {
    params.push(options.guestId);
    where.push(`id = $${params.length}`);
  } else if (channelRecord) {
    params.push(channelRecord.id);
    where.push(`channel_id = $${params.length}`);
  }

  if (options.name) {
    params.push(`%${options.name}%`);
    where.push(`name ILIKE $${params.length}`);
  }

  if (!options.rehydrate && !options.guestId) {
    where.push(`hydrated_at IS NULL`);
  }

  let sql = `SELECT id, name, channel_id, bio, hydrated_at FROM guests`;
  if (where.length > 0) sql += ` WHERE ${where.join(' AND ')}`;
  sql += ` ORDER BY name`;
  if (options.limit) {
    params.push(options.limit);
    sql += ` LIMIT $${params.length}`;
  }

  let guests: GuestRow[];
  try {
    guests = await fetchAll<GuestRow>(sql, params);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`❌ Failed to fetch guests: ${message}`);
    process.exit(1);
  }

  if (guests.length === 0) {
    console.log('✅ No guests to hydrate!');
    return;
  }

  console.log(`Found ${guests.length} guest(s) to hydrate\n`);

  // Dry run mode
  if (options.dryRun) {
    console.log('Dry run - would hydrate these guests:\n');
    guests.forEach((g, i) => {
      console.log(`${i + 1}. ${g.name}${g.hydrated_at ? ' (already hydrated)' : ''}`);
    });
    return;
  }

  // Hydrate guests
  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < guests.length; i++) {
    const guest = guests[i];
    console.log(`\n[${i + 1}/${guests.length}]`);

    const success = await hydrateGuest(guest.id, guest.name);

    if (success) {
      successCount++;
    } else {
      failCount++;
    }

    if (i < guests.length - 1) {
      console.log('\n⏳ Waiting 3 seconds before next guest...');
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }

  // Summary
  console.log('\n========================');
  console.log('📊 Hydration Summary');
  console.log('========================');
  if (channelRecord) {
    console.log(`📺 Channel: ${channelRecord.name}`);
  }
  console.log(`✅ Successful: ${successCount}`);
  console.log(`❌ Failed: ${failCount}`);
  console.log(`📁 Total: ${guests.length}`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
