#!/usr/bin/env python3
"""Shared configuration for people agents pipeline."""
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
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "glm4:latest")

# Pipeline config
HOST_SIMILARITY_THRESHOLD = 0.7
FILLER_MAX_WORDS = 5
CONTEXT_WINDOW_TURNS = 5
BATCH_INSERT_SIZE = 200

FILLER_PHRASES = {
    "yeah", "yes", "no", "right", "exactly", "sure", "okay", "ok",
    "mm-hmm", "mhm", "uh-huh", "hmm", "um", "uh", "ah",
}


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)
