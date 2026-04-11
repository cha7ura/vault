"""Shared configuration for pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env.local")

DATABASE_URL = os.environ["AIVEN_DATABASE_URL"]

# LLM config — Groq (preferred) > OpenRouter > Ollama (fallback)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.6-plus:free")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

# LLM provider priority: Groq > OpenRouter > Ollama
if GROQ_API_KEY:
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_API_KEY = GROQ_API_KEY
    LLM_MODEL = GROQ_MODEL
    LLM_STRICT_JSON_SCHEMA = True
elif OPENROUTER_API_KEY:
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    LLM_API_KEY = OPENROUTER_API_KEY
    LLM_MODEL = OPENROUTER_MODEL
    LLM_STRICT_JSON_SCHEMA = False
else:
    LLM_BASE_URL = f"{OLLAMA_BASE_URL}/v1"
    LLM_API_KEY = "ollama"
    LLM_MODEL = OLLAMA_MODEL
    LLM_STRICT_JSON_SCHEMA = False

# Wiki config
# Extract + lint run on Groq (strict structured outputs via constrained decoding).
# Summary runs on OpenRouter (flagship prose, no schema needed).
WIKI_DIR = Path(os.environ.get("WIKI_DIR", str(ROOT_DIR / "wiki")))
WIKI_EXTRACT_MODEL = os.environ.get("WIKI_EXTRACT_MODEL", "openai/gpt-oss-120b")
WIKI_SUMMARY_MODEL = os.environ.get("WIKI_SUMMARY_MODEL", "z-ai/glm-5.1")
WIKI_LINT_MODEL = os.environ.get("WIKI_LINT_MODEL", "openai/gpt-oss-20b")

# Embedder config — only needed for Graphiti (not required for wiki pipeline)
EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY", OPENROUTER_API_KEY)
EMBEDDER_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL", "qwen/qwen3-embedding-8b")

# Neo4j config
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USERNAME", os.environ.get("NEO4J_USER", "neo4j"))
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

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

# Voice fingerprint threshold (used by scripts/agents/map_speakers.py)
HOST_SIMILARITY_THRESHOLD = float(os.environ.get("HOST_SIMILARITY_THRESHOLD", "0.70"))

# Groq pricing (USD per 1M tokens). Groq does not return cost in the API
# response, so we compute it at log time from token counts. Update when
# Groq prices change — source: https://groq.com/pricing
GROQ_PRICES_PER_1M: dict[str, tuple[float, float]] = {
    # model: (input_per_1m, output_per_1m)
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b":  (0.075, 0.30),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}


def groq_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Compute Groq call cost in USD. Returns 0.0 if model not in price list."""
    prices = GROQ_PRICES_PER_1M.get(model)
    if not prices:
        return 0.0
    in_price, out_price = prices
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
