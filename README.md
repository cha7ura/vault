# Vault

Local-first YouTube podcast diarization and knowledge extraction platform. Downloads podcast audio, identifies speakers (whisper-diarization), and provides an interactive transcript dashboard with synchronized video playback.

## Quick Start

The repo includes a pre-seeded SQLite database with diarization results. Clone and run to view immediately.

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

### 3. Open the Transcript Page

```
http://localhost:3001/compare/1
```

Click any word or segment to seek the video to that point and start playing. Words highlight yellow in real-time as the video plays.

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
│   │       └── diarizer_whisper.py  # whisper-diarization wrapper
│   └── pyproject.toml
├── dashboard/             # Next.js 15 frontend
│   ├── app/
│   │   └── compare/[episodeId]/page.tsx  # Transcript page
│   ├── components/
│   │   └── transcript-panel.tsx          # Speaker-grouped transcript with word highlight
│   └── lib/
│       ├── types.ts       # Segment, SpeakerTurn, WordTiming
│       ├── api.ts         # API client
│       └── utils.ts       # formatTime helper
├── vendor/
│   └── whisper-diarization/  # Patched MahmoudAshraf97/whisper-diarization
├── data/
│   └── vault.db           # Pre-seeded SQLite
└── README.md
```

## Pre-seeded Data

| Segments | Speakers | Episode |
|----------|----------|---------|
| 942 | 2 | DOAC — "The Fasting Doctor" (`jDG1m_b5Ih0`) |

## Running Diarization

```bash
cd pipeline
pip install -e ".[diarize-whisper]"

cd ../vendor/whisper-diarization
python diarize.py -a /path/to/audio.wav --no-stem --device cpu
```

The patched `diarize.py` uses faster-whisper's native word timestamps (CTC alignment removed). Outputs `.txt` and `.srt` files next to the input audio.

## Dashboard Features

- YouTube player with synchronized transcript
- Word-by-word yellow highlighting during playback
- Click any word to seek video to that timestamp and play
- Click any speaker turn row to jump to that section
- Auto-scroll on speaker turn change
- Speaker grouping (consecutive segments merged into turns)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | Python, FastAPI, SQLAlchemy, SQLite |
| Dashboard | Next.js 15, React 19, TailwindCSS v4, react-youtube |
| Diarization | faster-whisper, NeMo MSDD, demucs |

## API Endpoints

```
GET  /health
GET  /api/episodes
GET  /api/episodes/{id}
GET  /api/episodes/{id}/diarization/segments?diarizer=whisper-diarization
GET  /api/episodes/{id}/diarization/benchmarks
PATCH /api/episodes/{id}/diarization/segments/{segment_id}
```

## License

MIT
