import { chat, embed } from '@/lib/openrouter';

export interface Framework {
  title: string;
  content: string;
  timestamp: number;
}

export interface Insight {
  title: string;
  content: string;
  type: 'insight' | 'quote' | 'story' | 'mindset' | 'health' | 'relationship';
  timestamp: number;
}

export interface Book {
  title: string;
  author?: string;
  context: string;
  timestamp: number;
}

export interface Paper {
  title: string;
  authors?: string;
  url?: string;
  context: string;
  timestamp: number;
}

export interface ExtractedContent {
  frameworks: Framework[];
  insights: Insight[];
  books: Book[];
  papers: Paper[];
  formattedTranscript: string;
}

export interface GuestInfo {
  name: string;
  role?: string;
  company?: string;
}

/**
 * Extract guest information from episode title and transcript
 */
export async function extractGuestInfo(
  transcript: string,
  title: string
): Promise<GuestInfo[]> {
  const prompt = `From this podcast episode titled "${title}", identify the guest(s) being interviewed.

The Diary of a CEO typically has a single guest per episode. The host is Steven Bartlett - do NOT include him as a guest.

For each guest, extract:
- name: Their full name
- role: Their job title or how they're described (e.g., "Neuroscientist", "CEO of Tesla", "Author")
- company: The company/organization they work for if mentioned

Common patterns in episode titles:
- "E### Guest Name: Quote or topic" 
- "The Expert Who..." followed by their expertise
- Guest name is usually at the beginning of the title

Return ONLY a valid JSON array. If this appears to be a solo episode with no guest, return an empty array [].

Episode Title: ${title}

Transcript (first 3000 chars):
${transcript.substring(0, 3000)}`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at identifying podcast guests from episode titles and transcripts. Always return valid JSON array.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.2 }
  );

  const content = response.choices[0]?.message?.content || '[]';
  try {
    const jsonStr = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    const guests = JSON.parse(jsonStr);
    
    // Filter out the host if accidentally included
    return guests.filter((g: GuestInfo) => 
      g.name && 
      !g.name.toLowerCase().includes('steven bartlett') &&
      !g.name.toLowerCase().includes('steve bartlett')
    );
  } catch (error) {
    console.error('Failed to parse guest info:', error);
    return [];
  }
}

/**
 * Extract frameworks from transcript
 */
export async function extractFrameworks(
  transcript: string
): Promise<Framework[]> {
  const prompt = `Analyze this podcast transcript and extract any mental models, frameworks, or systematic approaches discussed. 

For each framework, provide:
- title: A concise name for the framework (2-5 words)
- content: A 2-3 sentence explanation of the framework
- timestamp: Approximate start time in seconds (estimate based on position in transcript)

Return ONLY a valid JSON array. Only include genuine frameworks, not general advice or opinions.

Transcript:
${transcript.substring(0, 10000)}`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at extracting structured information from podcast transcripts. Always return valid JSON.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.3 }
  );

  const content = response.choices[0]?.message?.content || '[]';
  try {
    // Try to parse JSON, handling markdown code blocks
    const jsonStr = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    return JSON.parse(jsonStr);
  } catch (error) {
    console.error('Failed to parse frameworks:', error);
    return [];
  }
}

/**
 * Extract insights (quotes, stories, etc.) from transcript
 */
export async function extractInsights(
  transcript: string
): Promise<Insight[]> {
  const prompt = `Analyze this podcast transcript and extract key insights, memorable quotes, stories, mindset advice, health tips, and relationship insights.

Categorize each insight as one of:
- "quote": Memorable quotes or statements
- "story": Personal stories or anecdotes
- "mindset": Mindset or mental health advice
- "health": Health, fitness, or wellness tips
- "relationship": Relationship or social advice
- "insight": General insights or takeaways

For each insight, provide:
- title: A concise title (3-8 words)
- content: The full insight/quote/story (2-4 sentences)
- type: One of the categories above
- timestamp: Approximate start time in seconds

Return ONLY a valid JSON array.

Transcript:
${transcript.substring(0, 10000)}`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at extracting structured insights from podcast transcripts. Always return valid JSON.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.3 }
  );

  const content = response.choices[0]?.message?.content || '[]';
  try {
    const jsonStr = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    return JSON.parse(jsonStr);
  } catch (error) {
    console.error('Failed to parse insights:', error);
    return [];
  }
}

/**
 * Extract books and papers mentioned
 */
export async function extractBooksAndPapers(
  transcript: string,
  description?: string
): Promise<{ books: Book[]; papers: Paper[] }> {
  const fullText = description ? `${description}\n\n${transcript}` : transcript;

  const prompt = `Extract all books and research papers mentioned in this podcast transcript and description.

For books, provide:
- title: Book title
- author: Author name if mentioned
- context: Why it was mentioned (1 sentence)
- timestamp: Approximate time mentioned in seconds

For papers, provide:
- title: Paper title
- authors: Author names if mentioned
- url: URL if provided
- context: Why it was mentioned (1 sentence)
- timestamp: Approximate time mentioned in seconds

Return ONLY a valid JSON object with "books" and "papers" arrays.

Text:
${fullText.substring(0, 8000)}`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at extracting book and paper references from text. Always return valid JSON.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.2 }
  );

  const content = response.choices[0]?.message?.content || '{"books":[],"papers":[]}';
  try {
    const jsonStr = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
    return JSON.parse(jsonStr);
  } catch (error) {
    console.error('Failed to parse books/papers:', error);
    return { books: [], papers: [] };
  }
}

/**
 * Format transcript with AI (add bold, quotes, etc.)
 */
export async function formatTranscript(transcript: string): Promise<string> {
  const prompt = `Format this podcast transcript to make it more readable. Add:
- **Bold** for emphasis on key terms, numbers, or important concepts
- "Quotes" for direct quotes or statements
- Proper punctuation and paragraph breaks
- Format dollar amounts like $1M, $100K, etc.

Do NOT change the actual content, only add formatting. Return the formatted transcript.

Transcript:
${transcript.substring(0, 12000)}`;

  const response = await chat(
    [
      {
        role: 'system',
        content: 'You are an expert at formatting transcripts for readability. Use markdown formatting.',
      },
      {
        role: 'user',
        content: prompt,
      },
    ],
    'openai/gpt-4o',
    { temperature: 0.2 }
  );

  return response.choices[0]?.message?.content || transcript;
}

/**
 * Extract all content from transcript
 */
export async function extractAllContent(
  transcript: string,
  description?: string
): Promise<ExtractedContent> {
  const [frameworks, insights, { books, papers }, formattedTranscript] =
    await Promise.all([
      extractFrameworks(transcript),
      extractInsights(transcript),
      extractBooksAndPapers(transcript, description),
      formatTranscript(transcript),
    ]);

  return {
    frameworks,
    insights,
    books,
    papers,
    formattedTranscript,
  };
}
