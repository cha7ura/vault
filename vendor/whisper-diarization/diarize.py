import argparse
import json
import logging
import os
import re
import sys
import time

import faster_whisper
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

temp_path = os.path.join(os.getcwd(), f"temp_outputs_{os.getpid()}")
os.makedirs(temp_path, exist_ok=True)

# Initialize parser
parser = argparse.ArgumentParser()
parser.add_argument("-a", "--audio", help="name of the target audio file", required=True)
parser.add_argument(
    "--no-stem",
    action="store_false",
    dest="stemming",
    default=True,
    help="Disables source separation.This helps with long files that don't contain a lot of music.",
)

parser.add_argument(
    "--suppress_numerals",
    action="store_true",
    dest="suppress_numerals",
    default=False,
    help="Suppresses Numerical Digits."
    "This helps the diarization accuracy but converts all digits into written text.",
)

parser.add_argument(
    "--whisper-model",
    dest="model_name",
    default="medium.en",
    help="name of the Whisper model to use",
)

parser.add_argument(
    "--batch-size",
    type=int,
    dest="batch_size",
    default=8,
    help="Batch size for batched inference, reduce if you run out of memory, "
    "set to 0 for original whisper longform inference",
)

parser.add_argument(
    "--language",
    type=str,
    default=None,
    choices=whisper_langs,
    help="Language spoken in the audio, specify None to perform language detection",
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
    choices=["msdd", "sortformer"],
    help="Choose the diarization model to use",
)

args = parser.parse_args()
language = process_language_arg(args.language, args.model_name)

_step(f"Starting whisper-diarization pipeline")
_step(f"  Audio: {args.audio}")
_step(f"  Model: {args.model_name}, Device: {args.device}, Batch: {args.batch_size}")
_step(f"  Stemming: {args.stemming}, Diarizer: {args.diarizer}, Language: {language}")

# ---- Step 1: Source separation (Demucs) ----

if args.stemming:
    _step("STEP 1/5: Source separation (Demucs) — isolating vocals...")
    t1 = time.time()

    return_code = os.system(
        f"python -m demucs.separate -n htdemucs --two-stems=vocals "
        f'"{args.audio}" -o "{temp_path}" --device "{args.device}"'
    )

    if return_code != 0:
        logging.warning(
            "Source splitting failed, using original audio file. "
            "Use --no-stem argument to disable it."
        )
        vocal_target = args.audio
    else:
        vocal_target = os.path.join(
            temp_path,
            "htdemucs",
            os.path.splitext(os.path.basename(args.audio))[0],
            "vocals.wav",
        )
    _step(f"STEP 1/5: Source separation done in {time.time() - t1:.1f}s")
else:
    _step("STEP 1/5: Source separation SKIPPED (--no-stem)")
    vocal_target = args.audio


# ---- Step 2: Transcription with word timestamps (faster-whisper) ----

_step(f"STEP 2/5: Loading whisper model '{args.model_name}' ({mtypes[args.device]})...")
t2 = time.time()

whisper_model = faster_whisper.WhisperModel(
    args.model_name, device=args.device, compute_type=mtypes[args.device]
)
whisper_pipeline = faster_whisper.BatchedInferencePipeline(whisper_model)
audio_waveform = faster_whisper.decode_audio(vocal_target)

_step(f"  Model loaded in {time.time() - t2:.1f}s. Audio duration: {len(audio_waveform)/16000:.0f}s")

suppress_tokens = (
    find_numeral_symbol_tokens(whisper_model.hf_tokenizer) if args.suppress_numerals else [-1]
)

_step(f"STEP 2/5: Transcribing with word timestamps (batch_size={args.batch_size})...")
t2b = time.time()

if args.batch_size > 0:
    transcript_segments, info = whisper_pipeline.transcribe(
        audio_waveform,
        language,
        suppress_tokens=suppress_tokens,
        batch_size=args.batch_size,
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

# Collect word timestamps directly from faster-whisper (skip CTC forced alignment)
word_timestamps = []
full_transcript_parts = []
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

full_transcript = "".join(full_transcript_parts)

_step(f"STEP 2/5: Transcription done in {time.time() - t2b:.1f}s — {len(full_transcript)} chars, {len(word_timestamps)} words")

# clear gpu vram
del whisper_model, whisper_pipeline
torch.cuda.empty_cache()


# ---- Step 3: Speaker diarization (NeMo) ----

_step(f"STEP 3/5: Loading {args.diarizer.upper()} diarization model...")
t3 = time.time()

if args.diarizer == "msdd":
    from diarization import MSDDDiarizer

    diarizer_model = MSDDDiarizer(device=args.device)

elif args.diarizer == "sortformer":
    from diarization import SortformerDiarizer

    diarizer_model = SortformerDiarizer(device=args.device)

_step(f"  Diarizer loaded in {time.time() - t3:.1f}s")
_step("STEP 3/5: Running speaker diarization...")
t3b = time.time()

speaker_ts = diarizer_model.diarize(torch.from_numpy(audio_waveform).unsqueeze(0))

_step(f"STEP 3/5: Diarization done in {time.time() - t3b:.1f}s — {len(speaker_ts)} speaker segments")

del diarizer_model
torch.cuda.empty_cache()


# ---- Step 4: Map speakers to words + punctuation ----

_step("STEP 4/5: Mapping speakers to words...")
t4 = time.time()

wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

if info.language in punct_model_langs:
    _step("STEP 4/5: Restoring punctuation...")
    # restoring punctuation in the transcript to help realign the sentences
    punct_model = PunctuationModel(model="kredor/punctuate-all")

    words_list = list(map(lambda x: x["word"], wsm))

    labled_words = punct_model.predict(words_list, chunk_size=230)

    ending_puncts = ".?!"
    model_puncts = ".,;:!?"

    # We don't want to punctuate U.S.A. with a period. Right?
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
        f"Punctuation restoration is not available for {info.language} language."
        " Using the original punctuation."
    )

_step(f"STEP 4/5: Speaker mapping + punctuation done in {time.time() - t4:.1f}s")


# ---- Step 5: Write output ----

_step("STEP 5/5: Writing output files...")
t5 = time.time()

wsm = get_realigned_ws_mapping_with_punctuation(wsm)
ssm = get_sentences_speaker_mapping(wsm, speaker_ts)

txt_path = f"{os.path.splitext(args.audio)[0]}.txt"
srt_path = f"{os.path.splitext(args.audio)[0]}.srt"

with open(txt_path, "w", encoding="utf-8-sig") as f:
    get_speaker_aware_transcript(ssm, f)

with open(srt_path, "w", encoding="utf-8-sig") as srt:
    write_srt(ssm, srt)

# ---- Write JSON with per-word data ----
json_path = f"{os.path.splitext(args.audio)[0]}.json"

# Walk wsm (word-speaker mapping) and ssm (sentence-speaker mapping) in parallel
# to group words back into their sentences, preserving per-word scores.
json_segments = []
wsm_idx = 0
for sentence in ssm:
    seg_words = []
    sent_start_ms = sentence["start_time"]
    sent_end_ms = sentence["end_time"]
    # Collect words that fall within this sentence's time range
    while wsm_idx < len(wsm):
        w = wsm[wsm_idx]
        # Word belongs to this sentence if its start_time is within range
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

cleanup(temp_path)

_step(f"STEP 5/5: Output written in {time.time() - t5:.1f}s")
_step(f"  TXT: {txt_path}")
_step(f"  SRT: {srt_path}")
_step(f"  JSON: {json_path}")

# Count speakers
speakers = set()
for entry in ssm:
    speakers.add(entry["speaker"])
_step(f"PIPELINE COMPLETE — total: {_elapsed()}, speakers: {len(speakers)}, sentences: {len(ssm)}")
