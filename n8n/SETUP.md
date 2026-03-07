# n8n Setup Guide (Multi-tenant)

## Quick Start

1. Start the services:
   ```bash
   docker-compose up -d
   ```

2. Open n8n at [http://localhost:5678](http://localhost:5678)
   - Username: `admin` (or value of `N8N_USER`)
   - Password: `vault-admin` (or value of `N8N_PASSWORD`)

## Adding a New Channel via n8n

### Using Webhook

Send a POST request to trigger ingestion:

```bash
curl -X POST http://localhost:5678/webhook/ingest-channel \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "https://www.youtube.com/@TheDiaryOfACEO",
    "limit": 10,
    "skipExisting": true
  }'
```

Supported channel formats:
- `https://www.youtube.com/@TheDiaryOfACEO`
- `https://www.youtube.com/channel/UCrPseYLGpNygVi34QpGNqpA`
- `@TheDiaryOfACEO`
- `UCrPseYLGpNygVi34QpGNqpA`

### Using CLI (Alternative)

```bash
npm run ingest -- --channel "https://www.youtube.com/@TheDiaryOfACEO" --limit 10
```

## Setting Up Credentials

### 1. Supabase API

1. Go to **Settings > Credentials > Add Credential**
2. Search for "Supabase"
3. Enter:
   - **Host**: Your Supabase project URL
   - **Service Role Key**: From Supabase Dashboard > Settings > API

### 2. Environment Variables

Set in `.env` before starting docker-compose:

| Variable | Description |
|----------|-------------|
| `YOUTUBE_API_KEY` | YouTube Data API key |
| `DEEPGRAM_API_KEY` | Deepgram transcription |
| `OPENROUTER_API_KEY` | LLM and embeddings |
| `FIRECRAWL_API_KEY` | Web search for guest hydration |

## Workflows

### Episode Ingestion (Multi-tenant)

**Trigger**: Webhook POST `/webhook/ingest-channel`

**Input**:
```json
{
  "channel": "YouTube URL or ID",
  "limit": 10,
  "skipExisting": true
}
```

**Flow**:
1. Resolve channel ID from URL/handle
2. Create channel in database if new
3. Fetch videos from YouTube
4. For each video:
   - Download audio
   - Transcribe with Deepgram
   - Extract insights with OpenRouter
   - Generate embeddings
   - Store in Supabase (with channel_id)
   - Index in Meilisearch

### Guest Hydration

**Trigger**: Webhook POST `/webhook/hydrate-guests`

**Input**:
```json
{
  "channel": "YouTube URL or ID"
}
```

**Flow**:
1. Get un-hydrated guests for channel
2. Search web with Firecrawl
3. Synthesize profile with OpenRouter
4. Update guest in Supabase

## Multi-tenant Data Model

All data is scoped by `channel_id`:

```
channels
├── episodes (channel_id)
│   ├── insights (episode_id)
│   ├── books (episode_id)
│   └── papers (episode_id)
└── guests (channel_id)
```

## Scheduled Ingestion

To auto-ingest new videos for all channels:

1. Create a Schedule Trigger workflow
2. Query channels where `auto_ingest = true`
3. For each channel, trigger the ingestion webhook

Example cron: `0 */6 * * *` (every 6 hours)

## Production Deployment

### Railway

1. Deploy Meilisearch: `getmeili/meilisearch:v1.11`
2. Deploy n8n: `n8nio/n8n:latest`
3. Set environment variables
4. Import workflows
5. Configure webhook URLs with Railway domains
