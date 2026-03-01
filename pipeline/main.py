from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipeline.db import init_db
from pipeline.api.channels import router as channels_router
from pipeline.api.episodes import router as episodes_router
from pipeline.api.jobs import router as jobs_router
from pipeline.api.diarization import router as diarization_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vault Pipeline", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(channels_router)
app.include_router(episodes_router)
app.include_router(jobs_router)
app.include_router(diarization_router)


@app.get("/health")
def health():
    return {"status": "ok"}
