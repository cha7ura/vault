import argparse
import json
import logging
import os
import re
import sys
import time

import faster_whisper
import numpy as np
import torch

from deepmultilingualpunctuation import PunctuationModel

from helpers import (
    cleanup,
    find_numeral_symbol_tokens,
    get_realigned_ws_mapping_with_punctuation,
    get_sentences_speaker_mapping,
    get_speaker_aware_transcript,
    get_words_speaker_mapping,
    langs_to_iso,
    process_language_arg,
    punct_model_langs,
    whisper_langs,
    write_srt,
)

# ---------------------------------------------------------------------------
# Logging setup — flush every line so we can tail -f the log
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("whisper-diarization")

_t0 = time.time()

def _elapsed():
    return f"{time.time() - _t0:.1f}s"

def _step(msg):
    log.info(f"[{_elapsed()}] {msg}")

# ---------------------------------------------------------------------------

mtypes = {"cpu": "int8", "cuda": "float16"}


# ---------------------------------------------------------------------------
# Phase A: Whisper transcription (cacheable)
# ---------------------------------------------------------------------------

def run_whisper_transcription(audio_path, model_name, device, batch_size, language,
                              suppress_numerals=False):
    """Steps 1-2: Decode audio and transcribe with word timestamps.

    Returns dict with keys:
        audio_waveform, word_timestamps, full_transcript, language,
        audio_duration, whisper_model
    """
    _step(f"WHISPER: Loading model '{model_name}' ({mtypes[device]})...")
    t0 = time.time()

    whisper_model = faster_whisper.WhisperModel(
        model_name, device=device, compute_type=mtypes[device]
    )
    whisper_pipeline = faster_whisper.BatchedInferencePipeline(whisper_model)
    audio_waveform = faster_whisper.decode_audio(audio_path)

    _step(f"  Model loaded in {time.time() - t0:.1f}s. Audio duration: {len(audio_waveform)/16000:.0f}s")

    suppress_tokens = (
        find_numeral_symbol_tokens(whisper_model.hf_tokenizer) if suppress_numerals else [-1]
    )

    _step(f"WHISPER: Transcribing with word timestamps (batch_size={batch_size})...")
    t1 = time.time()

    if batch_size > 0:
        transcript_segments, info = whisper_pipeline.transcribe(
            audio_waveform,
            language,
            suppress_tokens=suppress_tokens,
            batch_size=batch_size,
            word_timestamps=True,
        )
    else:
        transcript_segments, info = whisper_model.transcribe(
            audio_waveform,
            language,
            suppress_tokens=suppress_tokens,
            vad_filter=True,
            word_timestamps=True,
        )

    audio_duration = len(audio_waveform) / 16000
    word_timestamps = []
    full_transcript_parts = []
    last_pct = -1
    for segment in transcript_segments:
        full_transcript_parts.append(segment.text)
        if segment.words:
            for word in segment.words:
                word_timestamps.append({
                    "text": word.word.strip(),
                    "start": word.start,
                    "end": word.end,
                    "score": word.probability,
                })
        pct = int((segment.end / audio_duration) * 100) if audio_duration > 0 else 0
        pct = min(pct, 100)
        if pct >= last_pct + 5:
            _step(f"  Transcribing... {pct}% ({segment.end:.0f}s / {audio_duration:.0f}s)")
            last_pct = pct

    full_transcript = "".join(full_transcript_parts)
    detected_language = info.language

    _step(f"WHISPER: Done in {time.time() - t1:.1f}s — {len(full_transcript)} chars, {len(word_timestamps)} words, lang={detected_language}")

    del whisper_model, whisper_pipeline
    torch.cuda.empty_cache()

    return {
        "audio_waveform": audio_waveform,
        "word_timestamps": word_timestamps,
        "full_transcript": full_transcript,
        "language": detected_language,
        "audio_duration": audio_duration,
        "whisper_model": model_name,
    }


def save_whisper_cache(whisper_result, cache_dir):
    """Save Whisper output to disk for reuse by a different diarizer."""
    os.makedirs(cache_dir, exist_ok=True)

    waveform_path = os.path.join(cache_dir, "waveform.npy")
    np.save(waveform_path, whisper_result["audio_waveform"])

    meta = {
        "whisper_model": whisper_result["whisper_model"],
        "language": whisper_result["language"],
        "audio_duration": whisper_result["audio_duration"],
        "word_count": len(whisper_result["word_timestamps"]),
        "full_transcript": whisper_result["full_transcript"],
        "word_timestamps": whisper_result["word_timestamps"],
        "waveform_path": waveform_path,
    }
    meta_path = os.path.join(cache_dir, "whisper_cache.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    _step(f"CACHE: Saved whisper cache to {cache_dir}")
    return meta_path


def load_whisper_cache(cache_path):
    """Load previously cached Whisper output."""
    with open(cache_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    waveform_path = meta["waveform_path"]
    if not os.path.isabs(waveform_path):
        waveform_path = os.path.join(os.path.dirname(cache_path), waveform_path)

    audio_waveform = np.load(waveform_path)

    _step(f"CACHE: Loaded whisper cache — {meta['word_count']} words, model={meta['whisper_model']}, lang={meta['language']}")

    return {
        "audio_waveform": audio_waveform,
        "word_timestamps": meta["word_timestamps"],
        "full_transcript": meta["full_transcript"],
        "language": meta["language"],
        "audio_duration": meta["audio_duration"],
        "whisper_model": meta["whisper_model"],
    }


# ---------------------------------------------------------------------------
# Phase B: Diarization (pluggable)
# ---------------------------------------------------------------------------

def run_diarization(audio_waveform, diarizer_name, device, hf_token=None):
    """Step 3: Run speaker diarization.

    Returns speaker_ts: list of (start_ms, end_ms, speaker_id) tuples.
    """
    _step(f"DIARIZE: Loading {diarizer_name.upper()} model...")
    t0 = time.time()

    if diarizer_name == "msdd":
        from diarization import MSDDDiarizer
        diarizer_model = MSDDDiarizer(device=device)

    elif diarizer_name == "sortformer":
        from diarization import SortformerDiarizer
        diarizer_model = SortformerDiarizer(device=device)

    elif diarizer_name == "pyannote":
        from diarization import PyannoteDiarizer
        diarizer_model = PyannoteDiarizer(device=device, hf_token=hf_token)

    else:
        raise ValueError(f"Unknown diarizer: {diarizer_name}")

    _step(f"  Diarizer loaded in {time.time() - t0:.1f}s")
    _step("DIARIZE: Running speaker diarization...")
    t1 = time.time()

    speaker_ts = diarizer_model.diarize(torch.from_numpy(audio_waveform).unsqueeze(0))

    _step(f"DIARIZE: Done in {time.time() - t1:.1f}s — {len(speaker_ts)} speaker segments")

    del diarizer_model
    torch.cuda.empty_cache()

    return speaker_ts


# ---------------------------------------------------------------------------
# Phase C: Post-processing (shared)
# ---------------------------------------------------------------------------

def run_postprocessing(word_timestamps, speaker_ts, language, audio_path):
    """Steps 4-5: Map speakers to words, restore punctuation, write output.

    Returns json_segments list.
    """
    _step("POST: Mapping speakers to words...")
    t0 = time.time()

    wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

    if language in punct_model_langs:
        _step("POST: Restoring punctuation...")
        punct_model = PunctuationModel(model="kredor/punctuate-all")

        words_list = list(map(lambda x: x["word"], wsm))

        try:
            labled_words = punct_model.predict(words_list, chunk_size=230)
        except TypeError:
            labled_words = punct_model.predict(words_list)

        ending_puncts = ".?!"
        model_puncts = ".,;:!?"

        is_acronym = lambda x: re.fullmatch(r"\b(?:[a-zA-Z]\.){2,}", x)

        for word_dict, labeled_tuple in zip(wsm, labled_words):
            word = word_dict["word"]
            if (
                word
                and labeled_tuple[1] in ending_puncts
                and (word[-1] not in model_puncts or is_acronym(word))
            ):
                word += labeled_tuple[1]
                if word.endswith(".."):
                    word = word.rstrip(".")
                word_dict["word"] = word
    else:
        logging.warning(
            f"Punctuation restoration is not available for {language} language."
            " Using the original punctuation."
        )

    _step(f"POST: Speaker mapping + punctuation done in {time.time() - t0:.1f}s")

    _step("POST: Writing output files...")
    t1 = time.time()

    wsm = get_realigned_ws_mapping_with_punctuation(wsm)
    ssm = get_sentences_speaker_mapping(wsm, speaker_ts)

    txt_path = f"{os.path.splitext(audio_path)[0]}.txt"
    srt_path = f"{os.path.splitext(audio_path)[0]}.srt"

    with open(txt_path, "w", encoding="utf-8-sig") as f:
        get_speaker_aware_transcript(ssm, f)

    with open(srt_path, "w", encoding="utf-8-sig") as srt:
        write_srt(ssm, srt)

    # Write JSON with per-word data
    json_path = f"{os.path.splitext(audio_path)[0]}.json"

    json_segments = []
    wsm_idx = 0
    for sentence in ssm:
        seg_words = []
        sent_start_ms = sentence["start_time"]
        sent_end_ms = sentence["end_time"]
        while wsm_idx < len(wsm):
            w = wsm[wsm_idx]
            if w["start_time"] >= sent_start_ms and w["start_time"] <= sent_end_ms:
                seg_words.append({
                    "text": w["word"],
                    "start": round(w["start_time"] / 1000, 3),
                    "end": round(w["end_time"] / 1000, 3),
                    "score": w.get("score"),
                })
                wsm_idx += 1
            elif w["start_time"] > sent_end_ms:
                break
            else:
                wsm_idx += 1

        json_segments.append({
            "speaker": sentence["speaker"],
            "start": round(sent_start_ms / 1000, 3),
            "end": round(sent_end_ms / 1000, 3),
            "text": sentence["text"].strip(),
            "words": seg_words,
        })

    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(json_segments, jf, ensure_ascii=False, indent=2)

    _step(f"POST: Output written in {time.time() - t1:.1f}s")
    _step(f"  TXT: {txt_path}")
    _step(f"  SRT: {srt_path}")
    _step(f"  JSON: {json_path}")

    speakers = {entry["speaker"] for entry in ssm}
    _step(f"PIPELINE COMPLETE — total: {_elapsed()}, speakers: {len(speakers)}, sentences: {len(ssm)}")

    return json_segments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--audio", help="name of the target audio file", required=True)
    parser.add_argument(
        "--no-stem",
        action="store_false",
        dest="stemming",
        default=False,
        help="Disables source separation (default: disabled).",
    )
    parser.add_argument(
        "--stem",
        action="store_true",
        dest="stemming",
        help="Enable source separation via Demucs.",
    )
    parser.add_argument(
        "--suppress_numerals",
        action="store_true",
        dest="suppress_numerals",
        default=False,
        help="Suppresses Numerical Digits.",
    )
    parser.add_argument(
        "--whisper-model",
        dest="model_name",
        default="large-v3",
        help="name of the Whisper model to use (default: large-v3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        dest="batch_size",
        default=16,
        help="Batch size for batched inference (default: 16)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        choices=whisper_langs,
        help="Language spoken in the audio (default: en)",
    )
    parser.add_argument(
        "--device",
        dest="device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="if you have a GPU use 'cuda', otherwise 'cpu'",
    )
    parser.add_argument(
        "--diarizer",
        default="msdd",
        choices=["msdd", "sortformer", "pyannote"],
        help="Choose the diarization model to use",
    )
    parser.add_argument(
        "--hf-token",
        default=None,
        help="HuggingFace token for Pyannote 3.1 (or set HF_TOKEN env var)",
    )
    parser.add_argument(
        "--whisper-cache",
        default=None,
        help="Path to whisper_cache.json to skip re-running Whisper",
    )
    parser.add_argument(
        "--save-cache",
        default=None,
        help="Directory to save Whisper cache for reuse",
    )

    args = parser.parse_args()
    language = process_language_arg(args.language, args.model_name)

    _step("Starting whisper-diarization pipeline")
    _step(f"  Audio: {args.audio}")
    _step(f"  Model: {args.model_name}, Device: {args.device}, Batch: {args.batch_size}")
    _step(f"  Stemming: {args.stemming}, Diarizer: {args.diarizer}, Language: {language}")

    temp_path = os.path.join(os.getcwd(), f"temp_outputs_{os.getpid()}")
    os.makedirs(temp_path, exist_ok=True)

    # ---- Step 1: Source separation (Demucs) ----

    if args.stemming:
        _step("STEP 1: Source separation (Demucs) — isolating vocals...")
        t1 = time.time()
        return_code = os.system(
            f"python -m demucs.separate -n htdemucs --two-stems=vocals "
            f'"{args.audio}" -o "{temp_path}" --device "{args.device}"'
        )
        if return_code != 0:
            logging.warning("Source splitting failed, using original audio file.")
            vocal_target = args.audio
        else:
            vocal_target = os.path.join(
                temp_path, "htdemucs",
                os.path.splitext(os.path.basename(args.audio))[0],
                "vocals.wav",
            )
        _step(f"STEP 1: Source separation done in {time.time() - t1:.1f}s")
    else:
        _step("STEP 1: Source separation SKIPPED")
        vocal_target = args.audio

    # ---- Phase A: Whisper transcription (or load from cache) ----

    if args.whisper_cache:
        whisper_result = load_whisper_cache(args.whisper_cache)
    else:
        whisper_result = run_whisper_transcription(
            vocal_target, args.model_name, args.device,
            args.batch_size, language, args.suppress_numerals,
        )

    if args.save_cache:
        save_whisper_cache(whisper_result, args.save_cache)

    # ---- Phase B: Diarization ----

    speaker_ts = run_diarization(
        whisper_result["audio_waveform"], args.diarizer,
        args.device, hf_token=args.hf_token,
    )

    # ---- Phase C: Post-processing + output ----

    run_postprocessing(
        whisper_result["word_timestamps"], speaker_ts,
        whisper_result["language"], args.audio,
    )

    cleanup(temp_path)
