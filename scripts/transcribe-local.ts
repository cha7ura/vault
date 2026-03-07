/**
 * Local Audio Transcription — Provider Abstraction
 *
 * Supports:
 *   - whisper.cpp (local, Metal-accelerated on Apple Silicon)
 *   - Groq Whisper API (cloud, $0.04/hr for v3-turbo)
 *   - PyAnnote speaker diarization (optional, runs as Python subprocess)
 *
 * Provider is selected via TRANSCRIPTION_PROVIDER env var:
 *   - "whisper-cpp" — local whisper.cpp binary
 *   - "groq" — Groq cloud API (default)
 */

import { execSync } from 'child_process';
import { readFileSync, createReadStream } from 'fs';
import path from 'path';
import Groq from 'groq-sdk';

// ── Interfaces (unchanged from Deepgram version) ──────────────────────

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker?: number;
}

export interface Transcript {
  text: string;
  segments: TranscriptSegment[];
  speakers: string[];
}

interface DiarizationSegment {
  start: number;
  end: number;
  speaker: string;
}

// ── whisper.cpp provider ──────────────────────────────────────────────

function transcribeWithWhisperCpp(
  audioFilePath: string,
  options: { language?: string; model?: string } = {}
): { text: string; segments: TranscriptSegment[] } {
  const whisperPath = process.env.WHISPER_CPP_PATH || 'whisper-cpp';
  const modelPath = process.env.WHISPER_CPP_MODEL || 'models/ggml-medium.bin';
  const language = options.language || 'en';

  // whisper.cpp outputs JSON to a file named <input>.json when using --output-json
  const outputBase = audioFilePath.replace(/\.[^.]+$/, '');

  const cmd = [
    whisperPath,
    '-m', modelPath,
    '-f', audioFilePath,
    '-l', language,
    '--output-json',
    '--output-file', outputBase,
  ].join(' ');

  execSync(cmd, { stdio: 'pipe', timeout: 30 * 60 * 1000 }); // 30 min timeout

  const jsonPath = outputBase + '.json';
  const raw = JSON.parse(readFileSync(jsonPath, 'utf-8'));

  const segments: TranscriptSegment[] = [];
  let fullText = '';

  // whisper.cpp JSON format: { transcription: [{ timestamps: { from, to }, text }] }
  if (raw.transcription) {
    for (const entry of raw.transcription) {
      const text = entry.text?.trim();
      if (!text) continue;

      // Parse timestamps like "00:00:01.234" to seconds
      const start = parseWhisperTimestamp(entry.timestamps?.from || '00:00:00.000');
      const end = parseWhisperTimestamp(entry.timestamps?.to || '00:00:00.000');

      segments.push({ start, end, text });
      fullText += text + ' ';
    }
  }

  // Clean up the JSON output file
  try { execSync(`rm -f "${jsonPath}"`, { stdio: 'pipe' }); } catch { /* ignore */ }

  return { text: fullText.trim(), segments };
}

function parseWhisperTimestamp(ts: string): number {
  // Format: "HH:MM:SS.mmm" or "00:00:01.234"
  const parts = ts.split(':');
  if (parts.length === 3) {
    const hours = parseFloat(parts[0]);
    const minutes = parseFloat(parts[1]);
    const seconds = parseFloat(parts[2]);
    return hours * 3600 + minutes * 60 + seconds;
  }
  return 0;
}

// ── Groq provider ─────────────────────────────────────────────────────

async function transcribeWithGroq(
  audioFilePath: string,
  options: { language?: string; model?: string } = {}
): Promise<{ text: string; segments: TranscriptSegment[] }> {
  const groq = new Groq({ apiKey: process.env.GROQ_API_KEY! });

  const response = await groq.audio.transcriptions.create({
    file: createReadStream(audioFilePath),
    model: options.model || 'whisper-large-v3-turbo',
    language: options.language || 'en',
    response_format: 'verbose_json',
    timestamp_granularities: ['segment'],
  });

  const segments: TranscriptSegment[] = [];
  let fullText = (response as any).text || '';

  // verbose_json returns segments with start/end timestamps
  const rawSegments = (response as any).segments;
  if (rawSegments && Array.isArray(rawSegments)) {
    for (const seg of rawSegments) {
      const text = seg.text?.trim();
      if (!text) continue;
      segments.push({
        start: seg.start,
        end: seg.end,
        text,
      });
    }
  }

  return { text: fullText.trim(), segments };
}

// ── PyAnnote diarization ──────────────────────────────────────────────

function diarizeAudio(audioFilePath: string): DiarizationSegment[] {
  const scriptPath = path.join(__dirname, 'diarize.py');

  try {
    const result = execSync(
      `python3 "${scriptPath}" "${audioFilePath}"`,
      { stdio: ['pipe', 'pipe', 'pipe'], timeout: 30 * 60 * 1000 }
    );
    return JSON.parse(result.toString());
  } catch (err: any) {
    console.warn('  ⚠ Diarization failed, proceeding without speaker labels:', err.stderr?.toString() || err.message);
    return [];
  }
}

/**
 * Merge diarization speaker labels onto transcript segments.
 * For each segment, find the diarization entry that overlaps with the segment midpoint.
 */
function mergeDiarization(
  segments: TranscriptSegment[],
  diarization: DiarizationSegment[]
): { segments: TranscriptSegment[]; speakers: string[] } {
  if (diarization.length === 0) {
    return { segments, speakers: [] };
  }

  // Build speaker label map: "SPEAKER_00" -> 0, "SPEAKER_01" -> 1, etc.
  const speakerLabels = [...new Set(diarization.map(d => d.speaker))].sort();
  const speakerIndex = new Map(speakerLabels.map((label, idx) => [label, idx]));
  const speakers = speakerLabels.map((_, i) => `Speaker ${i}`);

  const merged = segments.map(seg => {
    const midpoint = (seg.start + seg.end) / 2;
    // Find the diarization segment that contains this midpoint
    const match = diarization.find(d => d.start <= midpoint && midpoint <= d.end);
    return {
      ...seg,
      speaker: match ? speakerIndex.get(match.speaker) : undefined,
    };
  });

  return { segments: merged, speakers };
}

// ── Main public API (same signature as before) ────────────────────────

/**
 * Transcribe a local audio file using the configured provider.
 *
 * Set TRANSCRIPTION_PROVIDER env var:
 *   - "whisper-cpp" — local whisper.cpp binary
 *   - "groq" — Groq cloud API (default)
 */
export async function transcribeLocalAudio(
  audioFilePath: string,
  options: {
    language?: string;
    model?: string;
    diarize?: boolean;
  } = {}
): Promise<Transcript> {
  const provider = process.env.TRANSCRIPTION_PROVIDER || 'groq';

  let text: string;
  let segments: TranscriptSegment[];

  // Step 1: Transcribe
  if (provider === 'whisper-cpp') {
    console.log('  Using whisper.cpp for transcription...');
    const result = transcribeWithWhisperCpp(audioFilePath, options);
    text = result.text;
    segments = result.segments;
  } else {
    console.log('  Using Groq Whisper API for transcription...');
    const result = await transcribeWithGroq(audioFilePath, options);
    text = result.text;
    segments = result.segments;
  }

  // Step 2: Diarize (optional)
  let speakers: string[] = [];
  if (options.diarize !== false) {
    console.log('  Running speaker diarization with PyAnnote...');
    const diarization = diarizeAudio(audioFilePath);
    const merged = mergeDiarization(segments, diarization);
    segments = merged.segments;
    speakers = merged.speakers;
    if (speakers.length > 0) {
      console.log(`  ✓ Identified ${speakers.length} speaker(s)`);
    }
  }

  return { text, segments, speakers };
}

/**
 * Format transcript with speaker labels
 */
export function formatTranscriptWithSpeakers(transcript: Transcript): string {
  let formatted = '';
  let currentSpeaker: number | undefined;

  for (const segment of transcript.segments) {
    if (segment.speaker !== undefined && segment.speaker !== currentSpeaker) {
      if (formatted) formatted += '\n\n';
      formatted += `[${transcript.speakers[segment.speaker] || `Speaker ${segment.speaker}`}]: `;
      currentSpeaker = segment.speaker;
    }
    formatted += segment.text + ' ';
  }

  return formatted.trim();
}
