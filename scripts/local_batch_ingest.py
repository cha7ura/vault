#!/usr/bin/env python3
"""
Vault Local Batch Ingest — processes YouTube channel videos oldest-first,
transcribes with Whisper + NeMo MSDD, writes to Aiven Postgres, removes audio after each video.

Usage:
    pip install python-dotenv faster-whisper yt-dlp psycopg2-binary numpy<2.0 \
        "nemo-toolkit[asr]>=2.dev" deepmultilingualpunctuation nltk torch torchaudio wget
    python scripts/local_batch_ingest.py

Reads AIVEN_DATABASE_URL from .env.local
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone
from pathlib import Path

import nltk
import torch
import torchaudio
import faster_whisper
import wget
from omegaconf import OmegaConf

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

# Allow running as `python scripts/local_batch_ingest.py`
sys.path.insert(0, str(ROOT_DIR))
from scripts.agents.db import (  # noqa: E402
    fetch_all,
    fetch_one,
    execute,
    execute_returning,
    execute_many,
)

# ---------------------------------------------------------------------------
# Channel config
# ---------------------------------------------------------------------------
CHANNEL_NAME = "The Diary of a CEO"
CHANNEL_HANDLE = "TheDiaryOfACEO"
CHANNEL_YOUTUBE_ID = "UC7yZ6keOGsvERMp2HaEbbXQ"
CHANNEL_SLUG = "doac"

# ---------------------------------------------------------------------------
# Processing config
# ---------------------------------------------------------------------------
WHISPER_MODEL = "large-v3"
BATCH_SIZE = 16
ENABLE_STEMMING = True
LANGUAGE = "en"
MAX_VIDEOS = 200
MAX_LOOPS = 100
SLEEP_SECONDS = 300

AUDIO_DIR = ROOT_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if device == "cuda" else "int8"

print(f"Device: {device}, Compute: {COMPUTE_TYPE}")
if device == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_mem / 1e9:.0f}GB)")
print(f"Batch size: {BATCH_SIZE}, Stemming: {'ON' if ENABLE_STEMMING else 'OFF'}")
print(f"Channel: {CHANNEL_NAME} (@{CHANNEL_HANDLE})")

nltk.download("punkt_tab", quiet=True)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def ensure_channel() -> str:
    existing = fetch_one(
        "SELECT id FROM channels WHERE youtube_channel_id=%s",
        (CHANNEL_YOUTUBE_ID,),
    )
    if existing:
        print(f"  Channel exists: {existing['id']}")
        return existing["id"]
    row = execute_returning(
        """
        INSERT INTO channels (youtube_channel_id, name, slug)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (CHANNEL_YOUTUBE_ID, CHANNEL_NAME, CHANNEL_SLUG),
    )
    print(f"  Channel created: {row['id']}")
    return row["id"]


def get_processed_ids(channel_id: str) -> set[str]:
    rows = fetch_all(
        """
        SELECT youtube_id
        FROM episodes
        WHERE channel_id=%s AND processed_at IS NOT NULL
        """,
        (channel_id,),
    )
    return {r["youtube_id"] for r in rows}


def get_channel_video_ids() -> list[str]:
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "id",
         "--playlist-end", str(MAX_VIDEOS),
         f"https://www.youtube.com/@{CHANNEL_HANDLE}/videos"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  yt-dlp error: {result.stderr[:500]}")
        return []
    return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]


def upsert_episode(channel_id: str, video_id: str, title: str,
                   duration: float = None, language: str = None,
                   num_speakers: int = None) -> str:
    """Insert or update episode by youtube_id; return its id."""
    if duration is not None:
        row = execute_returning(
            """
            INSERT INTO episodes (channel_id, youtube_id, title, duration_seconds)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (youtube_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                title = EXCLUDED.title,
                duration_seconds = EXCLUDED.duration_seconds
            RETURNING id
            """,
            (channel_id, video_id, title, int(duration)),
        )
    else:
        row = execute_returning(
            """
            INSERT INTO episodes (channel_id, youtube_id, title)
            VALUES (%s, %s, %s)
            ON CONFLICT (youtube_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                title = EXCLUDED.title
            RETURNING id
            """,
            (channel_id, video_id, title),
        )
    return row["id"]


def insert_segments(episode_id: str, segments: list[dict]):
    execute("DELETE FROM segments WHERE episode_id=%s", (episode_id,))
    rows = [
        {
            "episode_id": episode_id,
            "speaker": seg["speaker"],
            "start_time": seg["start"],
            "end_time": seg["end"],
            "text": seg["text"],
            "tag": "content",
            "diarizer": "whisper-diarization",
            "words": seg.get("words", []),
        }
        for seg in segments
    ]
    if rows:
        execute_many(
            """
            INSERT INTO segments (
                episode_id, speaker, start_time, end_time, text,
                tag, diarizer, words
            ) VALUES (
                %(episode_id)s, %(speaker)s, %(start_time)s, %(end_time)s, %(text)s,
                %(tag)s, %(diarizer)s, %(words)s
            )
            """,
            rows,
            page_size=200,
        )
    print(f"  Inserted {len(rows)} segments")


def mark_complete(episode_id: str):
    execute(
        "UPDATE episodes SET processed_at=%s WHERE id=%s",
        (datetime.now(timezone.utc).isoformat(), episode_id),
    )


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def download_audio(video_id: str) -> tuple[str, str]:
    wav_path = str(AUDIO_DIR / f"{video_id}.wav")
    result = subprocess.run(
        ["yt-dlp", "--print", "%(title)s", "--no-download",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True,
    )
    title = result.stdout.strip() or video_id
    if os.path.exists(wav_path):
        print(f"  Audio cached: {video_id}.wav")
        return wav_path, title
    print(f"  Downloading audio...")
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "wav",
         "-o", str(AUDIO_DIR / f"{video_id}.%(ext)s"),
         f"https://www.youtube.com/watch?v={video_id}"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    return wav_path, title


def cleanup_audio(video_id: str):
    wav_path = AUDIO_DIR / f"{video_id}.wav"
    if wav_path.exists():
        wav_path.unlink()
    temp_path = AUDIO_DIR / f"temp_{video_id}"
    if temp_path.exists():
        shutil.rmtree(temp_path)
    demucs_dir = AUDIO_DIR / "demucs"
    if demucs_dir.exists():
        shutil.rmtree(demucs_dir)


# ---------------------------------------------------------------------------
# NeMo config
# ---------------------------------------------------------------------------

def create_nemo_config(output_dir):
    CONFIG_URL = "https://raw.githubusercontent.com/NVIDIA/NeMo/main/examples/speaker_tasks/diarization/conf/inference/diar_infer_telephonic.yaml"
    config_path = os.path.join(output_dir, "diar_infer_telephonic.yaml")
    if not os.path.exists(config_path):
        config_path = wget.download(CONFIG_URL, output_dir)

    config = OmegaConf.load(config_path)
    data_dir = os.path.join(output_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    meta = {
        "audio_filepath": os.path.join(output_dir, "mono_file.wav"),
        "offset": 0, "duration": None, "label": "infer",
        "text": "-", "rttm_filepath": None, "uem_filepath": None,
    }
    with open(os.path.join(data_dir, "input_manifest.json"), "w") as fp:
        json.dump(meta, fp)
        fp.write("\n")

    config.num_workers = 0
    config.diarizer.manifest_filepath = os.path.join(data_dir, "input_manifest.json")
    config.diarizer.out_dir = output_dir
    config.diarizer.speaker_embeddings.model_path = "titanet_large"
    config.diarizer.oracle_vad = False
    config.diarizer.clustering.parameters.oracle_num_speakers = False
    config.diarizer.vad.model_path = "vad_multilingual_marblenet"
    config.diarizer.vad.parameters.onset = 0.8
    config.diarizer.vad.parameters.offset = 0.6
    config.diarizer.vad.parameters.pad_offset = -0.05
    config.diarizer.msdd_model.model_path = "diar_msdd_telephonic"
    return config


# ---------------------------------------------------------------------------
# Speaker mapping (from whisper-diarization repo)
# ---------------------------------------------------------------------------

punct_model_langs = ["en", "fr", "de", "es", "it", "nl", "pt", "bg", "pl", "cs", "sk", "sl"]
sentence_ending_punctuations = ".?!"


def get_word_ts_anchor(s, e, option="start"):
    if option == "end": return e
    if option == "mid": return (s + e) / 2
    return s


def get_words_speaker_mapping(wrd_ts, spk_ts, word_anchor_option="start"):
    s, e, sp = spk_ts[0]
    wrd_pos, turn_idx = 0, 0
    wrd_spk_mapping = []
    for wrd_dict in wrd_ts:
        ws = int(wrd_dict["start"] * 1000)
        we = int(wrd_dict["end"] * 1000)
        wrd = wrd_dict["text"]
        wrd_pos = get_word_ts_anchor(ws, we, word_anchor_option)
        while wrd_pos > float(e):
            turn_idx += 1
            turn_idx = min(turn_idx, len(spk_ts) - 1)
            s, e, sp = spk_ts[turn_idx]
            if turn_idx == len(spk_ts) - 1:
                e = get_word_ts_anchor(ws, we, option="end")
        wrd_spk_mapping.append({"word": wrd, "start_time": ws, "end_time": we, "speaker": sp})
    return wrd_spk_mapping


def get_first_word_idx_of_sentence(word_idx, word_list, speaker_list, max_words):
    is_end = lambda x: x >= 0 and word_list[x][-1] in sentence_ending_punctuations
    left_idx = word_idx
    while (left_idx > 0 and word_idx - left_idx < max_words
           and speaker_list[left_idx - 1] == speaker_list[left_idx]
           and not is_end(left_idx - 1)):
        left_idx -= 1
    return left_idx if left_idx == 0 or is_end(left_idx - 1) else -1


def get_last_word_idx_of_sentence(word_idx, word_list, max_words):
    is_end = lambda x: x >= 0 and word_list[x][-1] in sentence_ending_punctuations
    right_idx = word_idx
    while (right_idx < len(word_list) - 1 and right_idx - word_idx < max_words
           and not is_end(right_idx)):
        right_idx += 1
    return right_idx if right_idx == len(word_list) - 1 or is_end(right_idx) else -1


def get_realigned_ws_mapping_with_punctuation(word_speaker_mapping, max_words_in_sentence=50):
    is_end = lambda x: x >= 0 and word_speaker_mapping[x]["word"][-1] in sentence_ending_punctuations
    wsp_len = len(word_speaker_mapping)
    words_list = [d["word"] for d in word_speaker_mapping]
    speaker_list = [d["speaker"] for d in word_speaker_mapping]

    k = 0
    while k < wsp_len:
        if (k < wsp_len - 1 and speaker_list[k] != speaker_list[k + 1] and not is_end(k)):
            left_idx = get_first_word_idx_of_sentence(k, words_list, speaker_list, max_words_in_sentence)
            right_idx = get_last_word_idx_of_sentence(k, words_list, max_words_in_sentence - k + left_idx - 1) if left_idx > -1 else -1
            if min(left_idx, right_idx) == -1:
                k += 1; continue
            spk_labels = speaker_list[left_idx:right_idx + 1]
            mod_speaker = max(set(spk_labels), key=spk_labels.count)
            if spk_labels.count(mod_speaker) < len(spk_labels) // 2:
                k += 1; continue
            speaker_list[left_idx:right_idx + 1] = [mod_speaker] * (right_idx - left_idx + 1)
            k = right_idx
        k += 1
    return [dict(d, speaker=speaker_list[i]) for i, d in enumerate(word_speaker_mapping)]


def get_sentences_speaker_mapping(word_speaker_mapping, spk_ts):
    sentence_checker = nltk.tokenize.PunktSentenceTokenizer().text_contains_sentbreak
    s, e, spk = spk_ts[0]
    prev_spk = spk
    snts = []
    snt = {"speaker": f"Speaker {spk}", "start_time": s, "end_time": e, "text": "", "words": []}

    for wrd_dict in word_speaker_mapping:
        wrd, spk = wrd_dict["word"], wrd_dict["speaker"]
        s, e = wrd_dict["start_time"], wrd_dict["end_time"]
        if spk != prev_spk or sentence_checker(snt["text"] + " " + wrd):
            snts.append(snt)
            snt = {"speaker": f"Speaker {spk}", "start_time": s, "end_time": e, "text": "", "words": []}
        else:
            snt["end_time"] = e
        snt["text"] += wrd + " "
        snt["words"].append({"text": wrd, "start": s / 1000.0, "end": e / 1000.0, "score": wrd_dict.get("score")})
        prev_spk = spk
    snts.append(snt)
    return snts


def sentences_to_vault_json(sentences):
    segments = []
    for snt in sentences:
        if not snt["text"].strip():
            continue
        segments.append({
            "speaker": snt["speaker"],
            "start": snt["start_time"] / 1000.0,
            "end": snt["end_time"] / 1000.0,
            "text": snt["text"].strip(),
            "words": snt.get("words", []),
        })
    return segments


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

def main():
    from nemo.collections.asr.models.msdd_models import NeuralDiarizer
    from deepmultilingualpunctuation import PunctuationModel

    # Prefetch pool
    prefetch_pool = ThreadPoolExecutor(max_workers=1)
    prefetch_cache: dict[str, Future] = {}

    def prefetch_download(video_id: str):
        if video_id not in prefetch_cache:
            prefetch_cache[video_id] = prefetch_pool.submit(download_audio, video_id)

    def get_downloaded(video_id: str) -> tuple[str, str]:
        future = prefetch_cache.pop(video_id, None)
        if future:
            return future.result()
        return download_audio(video_id)

    # Load Whisper once
    print(f"Loading Whisper {WHISPER_MODEL} ({COMPUTE_TYPE})...")
    whisper_model = faster_whisper.WhisperModel(WHISPER_MODEL, device=device, compute_type=COMPUTE_TYPE)
    whisper_pipeline = faster_whisper.BatchedInferencePipeline(whisper_model)
    print("Whisper loaded")

    channel_id = ensure_channel()
    print(f"Channel ID: {channel_id}")

    loop_count = 0
    total_processed = 0

    while loop_count < MAX_LOOPS:
        loop_count += 1
        print(f"\n{'='*60}")
        print(f"LOOP {loop_count}/{MAX_LOOPS}  ({datetime.now(timezone.utc).strftime('%H:%M:%S UTC')})")
        print(f"{'='*60}")

        print("Scanning channel for videos...")
        all_video_ids = get_channel_video_ids()
        if not all_video_ids:
            print("  No video IDs returned. Retrying in 60s...")
            time.sleep(60)
            continue

        processed = get_processed_ids(channel_id)
        # Reverse to process oldest first
        pending = [vid for vid in reversed(all_video_ids) if vid not in processed]

        print(f"  Channel: {len(all_video_ids)}, processed: {len(processed)}, pending: {len(pending)}")

        if not pending:
            print(f"  All done. Sleeping {SLEEP_SECONDS}s...")
            time.sleep(SLEEP_SECONDS)
            continue

        for idx, video_id in enumerate(pending, 1):
            print(f"\n{'-'*50}")
            print(f"[{idx}/{len(pending)}] {video_id}")
            print(f"{'-'*50}")
            t_start = time.time()

            if idx < len(pending):
                prefetch_download(pending[idx])

            try:
                # 1. Download
                wav_path, title = get_downloaded(video_id)
                print(f"  Title: {title}")

                # 2. Vocal separation
                if ENABLE_STEMMING:
                    print("  Separating vocals...")
                    ret = os.system(
                        f'python -m demucs.separate -n htdemucs --two-stems=vocals '
                        f'"{wav_path}" -o "{AUDIO_DIR}/demucs" --device "{device}"'
                    )
                    vocal_target = (
                        str(AUDIO_DIR / "demucs" / "htdemucs" / video_id / "vocals.wav")
                        if ret == 0 else wav_path
                    )
                else:
                    vocal_target = wav_path

                # 3. Transcribe
                audio_waveform = faster_whisper.decode_audio(vocal_target)
                print(f"  Transcribing ({len(audio_waveform)/16000:.0f}s audio)...")

                transcript_segments, info = whisper_pipeline.transcribe(
                    audio_waveform, LANGUAGE, batch_size=BATCH_SIZE, word_timestamps=True,
                )

                word_timestamps = []
                for segment in transcript_segments:
                    if segment.words:
                        for word in segment.words:
                            word_timestamps.append({
                                "text": word.word.strip(),
                                "start": word.start,
                                "end": word.end,
                                "score": word.probability,
                            })
                print(f"  Transcribed: {len(word_timestamps)} words")

                if not word_timestamps:
                    print("  No words from Whisper. Skipping.")
                    cleanup_audio(video_id)
                    continue

                # 4. NeMo diarization
                print("  Running speaker diarization (NeMo MSDD)...")
                temp_path = str(AUDIO_DIR / f"temp_{video_id}")
                os.makedirs(temp_path, exist_ok=True)

                waveform_tensor = torch.from_numpy(audio_waveform).unsqueeze(0).float()
                torchaudio.save(os.path.join(temp_path, "mono_file.wav"), waveform_tensor, 16000, channels_first=True)

                msdd_model = NeuralDiarizer(cfg=create_nemo_config(temp_path)).to(device)
                msdd_model.diarize()
                del msdd_model
                torch.cuda.empty_cache()

                speaker_ts = []
                rttm_path = os.path.join(temp_path, "pred_rttms", "mono_file.rttm")
                with open(rttm_path, "r") as f:
                    for line in f:
                        parts = line.split(" ")
                        s = int(float(parts[5]) * 1000)
                        e = s + int(float(parts[8]) * 1000)
                        speaker_ts.append([s, e, int(parts[11].split("_")[-1])])
                print(f"  Diarization: {len(speaker_ts)} speaker segments")

                # 5. Map speakers to words
                wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

                if info.language in punct_model_langs:
                    print("  Restoring punctuation...")
                    punct_model = PunctuationModel(model="kredor/punctuate-all")
                    words_list = [d["word"] for d in wsm]
                    labeled_words = punct_model.predict(words_list, chunk_size=230)
                    is_acronym = lambda x: re.fullmatch(r"\b(?:[a-zA-Z]\.){2,}", x)
                    model_puncts = ".,;:!?"

                    for word_dict, labeled_tuple in zip(wsm, labeled_words):
                        word = word_dict["word"]
                        if word and labeled_tuple[1] in sentence_ending_punctuations and (
                            word[-1] not in model_puncts or is_acronym(word)
                        ):
                            word += labeled_tuple[1]
                            if word.endswith(".."): word = word.rstrip(".")
                            word_dict["word"] = word

                wsm = get_realigned_ws_mapping_with_punctuation(wsm)
                ssm = get_sentences_speaker_mapping(wsm, speaker_ts)

                # 6. Convert
                segments = sentences_to_vault_json(ssm)
                duration = segments[-1]["end"] if segments else 0
                num_speakers = len(set(s["speaker"] for s in segments))
                print(f"  {len(segments)} segments, {num_speakers} speakers, {duration:.0f}s")

                # 7. Write to Aiven
                print("  Writing to Aiven...")
                episode_id = upsert_episode(channel_id, video_id, title, duration=duration,
                                            language=info.language, num_speakers=num_speakers)
                insert_segments(episode_id, segments)
                mark_complete(episode_id)
                print(f"  Episode {episode_id} complete")

                # 8. Cleanup audio
                cleanup_audio(video_id)

                elapsed = time.time() - t_start
                total_processed += 1
                print(f"  Done in {elapsed:.0f}s (total: {total_processed})")

            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback
                traceback.print_exc()
                try:
                    upsert_episode(channel_id, video_id, video_id)
                except Exception:
                    pass
                cleanup_audio(video_id)
                continue

    prefetch_pool.shutdown(wait=False)
    print(f"\n{'='*60}")
    print(f"COMPLETE — processed {total_processed} videos in {loop_count} loops")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
