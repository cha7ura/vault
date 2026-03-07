/**
 * Audio Transcription — Re-exports from transcribe-local
 *
 * The bulk-ingest pipeline downloads audio first then transcribes locally.
 * This file maintains the `transcribeAudio` export for backwards compatibility
 * with ingest-episodes.ts (which passes a YouTube URL but should be migrated
 * to use the local audio pipeline instead).
 */

export {
  transcribeLocalAudio,
  transcribeLocalAudio as transcribeAudio,
  formatTranscriptWithSpeakers,
  type Transcript,
  type TranscriptSegment,
} from './transcribe-local';
