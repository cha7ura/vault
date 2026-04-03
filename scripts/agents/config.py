"""Shared configuration for pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# LLM config
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

# Neo4j config
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# SearXNG config
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")

# Pipeline config
FILLER_MAX_WORDS = 5
CONTEXT_WINDOW_TURNS = 5
BATCH_INSERT_SIZE = 200
TEXT_CONFIDENCE_THRESHOLD = 0.85
CHUNK_DURATION = 1200.0  # 20 minutes in seconds
CHUNK_OVERLAP = 120.0    # 2 minutes overlap
PERSONA_EVERY_N_EPISODES = 10

# Host detection
DOAC_HOST_NAME = "Steven Bartlett"
DOAC_CHANNEL_SLUG = "the-diary-of-a-ceo"
HOST_ANCHOR_PHRASES = [
    "subscribe", "welcome to", "diary of a ceo", "my guest today",
    "let's get into it", "tell me about", "without further ado",
]

FILLER_PHRASES = {
    "yeah", "yes", "no", "right", "exactly", "sure", "okay", "ok",
    "mm-hmm", "mhm", "uh-huh", "hmm", "um", "uh", "ah",
}


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)
