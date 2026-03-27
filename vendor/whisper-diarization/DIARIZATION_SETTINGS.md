# Whisper Diarization — Settings & Model Analysis

## Recommended Run Settings

```bash
python diarize.py \
  -a input.mp3 \
  --no-stem \
  --language en \
  --whisper-model medium.en \
  --batch-size 8 \
  --diarizer msdd \
  --device cuda
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| `--no-stem` | Enabled (skips Demucs) | Our audio is clean speech (no background music). Skipping source separation saves ~2-3x processing time |
| `--language en` | English explicit | Skips Whisper's 30-second language detection pass. Saves time when language is known |
| `--suppress_numerals` | **Not used** (default off) | Keeps numbers as digits ("23" not "twenty-three"). Preserves original formatting. Only needed if diarization accuracy is poor around numbers |
| `--whisper-model` | `medium.en` | Best balance of speed and accuracy for English. 769M params, ~3.8% WER |
| `--batch-size` | 8 | Default. Increase to 16 on A100. Set to 4 on T4 |
| `--diarizer` | `msdd` | Supports up to 8 speakers. Use `sortformer` only for ≤4 speakers |

---

## Colab Pro Environment (A100 40/80GB)

We are running on **Colab Pro** with access to **A100 GPUs** (40GB or 80GB VRAM).

### Can we use `diarize_parallel.py`?

**Yes — Colab Pro A100 has more than enough VRAM.**

`diarize_parallel.py` runs Whisper + NeMo MSDD simultaneously via `multiprocessing`:

| Model | Approx VRAM |
|-------|-------------|
| Whisper `medium.en` (float16) | ~5GB |
| NeMo MSDD (VAD + TitaNet + clustering + MSDD) | ~4-6GB |
| CTC forced aligner (parallel only) | ~1-2GB |
| 2x CUDA context overhead | ~1GB |
| **Total concurrent** | **~11-14GB** |

A100 40GB leaves ~26GB headroom. No VRAM issues.

### Parallel vs Sequential — which to use?

| | `diarize.py` (sequential) | `diarize_parallel.py` (parallel) |
|--|---------------------------|----------------------------------|
| Peak VRAM | ~5-6GB | ~11-14GB |
| Speed | Baseline | ~1.3-1.5x faster |
| Word timestamps | Whisper-native (attention-based) | CTC forced alignment (more precise) |
| Colab stability | Excellent | Good on A100, risky on T4 |
| Speaker limit | 8 (MSDD) or 4 (Sortformer) | 8 (MSDD only) |
| Extra dependency | None | `ctc-forced-aligner` |

**Recommendation for Colab Pro**: Use `diarize_parallel.py` for the speed gain. The CTC forced alignment also gives more precise word boundaries than Whisper's native timestamps.

```bash
# Parallel mode on Colab Pro A100
python diarize_parallel.py \
  -a input.mp3 \
  --no-stem \
  --language en \
  --whisper-model medium.en \
  --batch-size 8 \
  --device cuda
```

### Colab Pro settings to maximize throughput

```bash
# A100 can handle large-v3 + higher batch sizes
python diarize_parallel.py \
  -a input.mp3 \
  --no-stem \
  --language en \
  --whisper-model large-v3 \
  --batch-size 16 \
  --device cuda
```

| Setting | T4 (free) | A100 (Pro) |
|---------|-----------|------------|
| Script | `diarize.py` | `diarize_parallel.py` |
| Whisper model | `small.en` or `medium.en` | `medium.en` or `large-v3` |
| Batch size | 4 | 8-16 |
| Stemming | `--no-stem` | `--no-stem` (unless music) |

---

## Model Analysis: Are the Current Models the Best?

### Stage 3a — VAD: `vad_multilingual_marblenet`

**Current model**: NVIDIA MarbleNet — segment-level (~1s chunks) speech/non-speech detection. ~91K parameters.

**Verdict: Adequate, but a better NeMo drop-in exists.**

| Model | Type | Resolution | Params | Noise Robust | NeMo Drop-in |
|-------|------|-----------|--------|-------------|--------------|
| **`vad_multilingual_marblenet`** (current) | Segment-level | ~1s chunks | ~91K | Moderate | Yes |
| **`vad_multilingual_frame_marblenet` v2.0** | **Frame-level** | **20ms** | **~91K** | **Trained with noise augmentation** | **Yes** |
| Silero VAD v5 | Frame-level | 30ms | ~2MB | Excellent, 6000+ languages | No (different framework) |
| Pyannote segmentation-3.0 | Frame-level | 16ms | Larger | Good | No (different framework) |

**Recommended upgrade**: `vad_multilingual_frame_marblenet` v2.0

- Same MarbleNet architecture, same size — **direct drop-in** (just change `model_path`)
- Frame-level (20ms) vs segment-level (~1s) = **50x better temporal resolution**
- Trained with noise perturbation = fewer false positives
- Available on HuggingFace: `nvidia/Frame_VAD_Multilingual_MarbleNet_v2.0`

To apply in `diarization/msdd/msdd.py`:
```python
# Change from:
pretrained_vad = "vad_multilingual_marblenet"
# To:
pretrained_vad = "vad_multilingual_frame_marblenet"
```

---

### Stage 3b — Speaker Embeddings: `titanet_large`

**Verdict: Best NeMo-native option. No clear upgrade.**

| Model | EER (VoxCeleb1) | Params | Speed | NeMo Drop-in |
|-------|----------------|--------|-------|--------------|
| **`titanet_large`** (current) | 1.91% | 23M | Baseline | Yes |
| `titanet_small` | ~2.5% | ~5M | ~3x faster | Yes |
| `ecapa_tdnn` (NeMo) | 1.71% | ~22M | Similar | Yes |
| `speakerverification_speakernet` | ~3.5% | ~5M | Fast | Yes |
| WeSpeaker ResNet34-LM | **0.72%** | ~6M | Fast | No (different framework) |

**Recommendation**: Keep `titanet_large`. On A100 its 23M params are trivial. The truly better models require leaving NeMo.

---

### Punctuation Model: `kredor/punctuate-all`

**Verdict: Outdated. Better options exist for English.**

| Model | Base | F1 Score | Languages | Drop-in |
|-------|------|----------|-----------|---------|
| **`kredor/punctuate-all`** (current) | XLM-RoBERTa-Large | ~0.54 | 12 European | Yes |
| `oliverguhr/fullstop-punctuation-multilang-large` | XLM-RoBERTa-Large | ~0.55 | en/fr/de/it | Yes |
| **Cadence** (`ai4bharat/Cadence`) | Gemma-3-1B | **0.79** | en + 22 Indian | No (different API) |
| Cadence-Fast | Gemma-3-270M | 0.74 | en + 22 Indian | No |

Punctuation is **functionally critical** — the speaker realignment algorithm (Step 4c) uses `.?!` to find sentence boundaries. Better punctuation = better speaker assignment.

Easiest swap (same package):
```python
punct_model = PunctuationModel(model="oliverguhr/fullstop-punctuation-multilang-large")
```

---

### MSDD Model: `diar_msdd_telephonic`

**Verdict: Only publicly available MSDD checkpoint. No upgrade within NeMo.**

- `diar_msdd_meeting` weights are NOT publicly released (NeMo GitHub #6748)
- Sortformer is the end-to-end alternative (limited to 4 speakers)
- Pyannote 3.1 achieves best DER (~11.2%) but is entirely different framework

---

## Optimized Configuration for Colab Pro (A100)

```yaml
# diar_infer_telephonic.yaml — tuned for A100 + clean speech
name: &name "ClusterDiarizer"

num_workers: 0
sample_rate: 16000
batch_size: 128         # INCREASED from 64: A100 has headroom
device: null
verbose: True

diarizer:
  manifest_filepath: ???
  out_dir: ???
  oracle_vad: False
  collar: 0.25
  ignore_overlap: True

  vad:
    model_path: vad_multilingual_frame_marblenet  # UPGRADED: frame-level VAD
    external_vad_manifest: null
    parameters:
      window_length_in_sec: 0.15
      shift_length_in_sec: 0.01
      smoothing: "median"
      overlap: 0.5
      onset: 0.8         # Code overrides to 0.8 anyway
      offset: 0.6         # Code overrides to 0.6 anyway
      pad_onset: 0.1
      pad_offset: 0
      min_duration_on: 0
      min_duration_off: 0.3   # CHANGED from 0.2: merge natural pauses < 300ms
      filter_speech_first: True

  speaker_embeddings:
    model_path: titanet_large
    parameters:
      window_length_in_sec: [1.5, 1.25, 1.0, 0.75, 0.5]
      shift_length_in_sec: [0.75, 0.625, 0.5, 0.375, 0.25]
      multiscale_weights: [1, 1, 1, 1, 1]
      save_embeddings: True

  clustering:
    parameters:
      oracle_num_speakers: False
      max_num_speakers: 8
      enhanced_count_thres: 80
      max_rp_threshold: 0.25
      sparse_search_volume: 30
      maj_vote_spk_count: False
      chunk_cluster_count: 50
      embeddings_per_chunk: 20000  # INCREASED from 10000: A100 handles ~80min chunks

  msdd_model:
    model_path: diar_msdd_telephonic
    parameters:
      use_speaker_model_from_ckpt: True
      infer_batch_size: 50     # INCREASED from 25: A100 GPU utilization
      sigmoid_threshold: [0.7]
      seq_eval_mode: False
      split_infer: True
      diar_window_length: 75   # INCREASED from 50: more context per MSDD window
      overlap_infer_spk_limit: 5
```

### Summary of A100 optimizations

| Parameter | Default | A100 Value | Why |
|-----------|---------|------------|-----|
| `batch_size` (root) | 64 | **128** | Larger embedding extraction batches, A100 has VRAM |
| `embeddings_per_chunk` | 10000 | **20000** | Process ~80min of audio per chunk, fewer stitching artifacts |
| `infer_batch_size` (MSDD) | 25 | **50** | Better GPU utilization during MSDD refinement |
| `diar_window_length` | 50 | **75** | More temporal context for MSDD decisions (~18.75s vs ~12.5s windows) |
| `min_duration_off` | 0.2 | **0.3** | Merge natural pauses in clean speech |
| VAD model | marblenet | **frame_marblenet** | 50x better temporal resolution |

---

## Quick Reference: Settings for Common Scenarios

### Colab Pro A100 — Maximum quality (parallel)
```bash
python diarize_parallel.py -a input.mp3 --no-stem --language en --whisper-model large-v3 --batch-size 16
```

### Colab Pro A100 — Fast (parallel)
```bash
python diarize_parallel.py -a input.mp3 --no-stem --language en --whisper-model medium.en --batch-size 16
```

### Colab Pro A100 — Sequential (simpler, no CTC aligner dependency)
```bash
python diarize.py -a input.mp3 --no-stem --language en --whisper-model medium.en --batch-size 16
```

### Audio with background music (keep stemming)
```bash
python diarize.py -a input.mp3 --language en --whisper-model medium.en --batch-size 8
```
