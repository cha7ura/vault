# Vault

Local-first YouTube podcast diarization and comparison dashboard. Run speaker diarization with multiple engines (PyAnnote, whisper-diarization) and compare outputs side-by-side with synchronized video playback.

## Quick Start (Dashboard Only)

The repo includes a pre-seeded SQLite database with diarization results for the DOAC Ozempic episode. Clone and run to compare immediately — no diarization needed.

```bash
git clone https://github.com/cha7ura/vault.git
cd vault
```

### 1. Start the API

```bash
cd pipeline
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
uvicorn pipeline.main:app --port 8001
```

### 2. Start the Dashboard

```bash
cd dashboard
npm install
npm run dev
```

### 3. Open the Comparison Page

```
http://localhost:3001/compare/1
```

Both transcript panels (PyAnnote and whisper-diarization) will load with real data. Play the YouTube video to see word-by-word highlighting and auto-scrolling.

## Architecture

```
vault/
├── pipeline/              # Python FastAPI backend
│   ├── pipeline/
│   │   ├── main.py        # FastAPI app with CORS
│   │   ├── models.py      # SQLAlchemy models (Episode, Segment, Benchmark)
│   │   ├── db.py          # SQLite session management
│   │   ├── api/
│   │   │   └── diarization.py  # Segments + benchmarks API
│   │   └── core/
│   │       ├── diarizer_pyannote.py   # PyAnnote 3.x wrapper
│   │       └── diarizer_whisper.py    # whisper-diarization wrapper
│   └── pyproject.toml
├── dashboard/             # Next.js 15 frontend
│   ├── app/
│   │   └── compare/[episodeId]/page.tsx  # Comparison page
│   ├── components/
│   │   └── transcript-panel.tsx          # Speaker-grouped transcript with word highlight
│   └── lib/
│       ├── types.ts       # Segment, SpeakerTurn, WordTiming
│       ├── api.ts         # API client
│       └── utils.ts       # formatTime helper
├── vendor/
│   └── whisper-diarization/  # Patched MahmoudAshraf97/whisper-diarization
├── data/
│   └── vault.db           # Pre-seeded SQLite (508KB)
└── README.md
```

## Pre-seeded Data

| Diarizer | Segments | Speakers | Duration |
|----------|----------|----------|----------|
| PyAnnote 3.x (MPS) | 1,614 | 2 | ~9 min |
| whisper-diarization (NeMo MSDD, CPU) | 942 | 2 | ~4h 42min |

Episode: DOAC — "The Fasting Doctor" (youtube_id: `jDG1m_b5Ih0`)

## Running Diarization

To diarize new episodes, you need additional dependencies.

### PyAnnote

```bash
cd pipeline
pip install -e ".[diarize-pyannote]"
```

Requires a HuggingFace token with access to `pyannote/speaker-diarization-3.1`.

### whisper-diarization

```bash
cd pipeline
pip install -e ".[diarize-whisper]"

# Run from the vendor directory
cd ../vendor/whisper-diarization
python diarize.py -a /path/to/audio.wav --no-stem --device cpu
```

The patched `diarize.py` skips CTC forced alignment (crash-prone) and uses faster-whisper's native word timestamps instead. Outputs `.txt` and `.srt` files next to the input audio.

## Dashboard Features

- YouTube player with synchronized transcript panels
- Side-by-side comparison of two diarization engines
- Word-by-word yellow highlighting during playback
- Auto-scroll on speaker turn change
- Click any turn to seek the video
- Speaker grouping (consecutive segments merged into turns)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | Python, FastAPI, SQLAlchemy, SQLite |
| Dashboard | Next.js 15, React 19, TailwindCSS v4, react-youtube |
| PyAnnote | pyannote.audio 3.x, faster-whisper |
| whisper-diarization | faster-whisper, NeMo MSDD, demucs |

## API Endpoints

```
GET  /health
GET  /api/episodes
GET  /api/episodes/{id}
GET  /api/episodes/{id}/diarization/segments?diarizer=pyannote
GET  /api/episodes/{id}/diarization/segments?diarizer=whisper-diarization
GET  /api/episodes/{id}/diarization/benchmarks
PATCH /api/episodes/{id}/diarization/segments/{segment_id}
```

## License

MIT
