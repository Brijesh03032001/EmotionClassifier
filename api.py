"""
FastAPI playlist API — wraps the retrieval pipeline from retrieval_benchmark.py.

Endpoints:
    GET  /health          — liveness check
    GET  /vibes           — list of supported vibes
    POST /playlist        — generate a ranked playlist from a natural-language prompt

Usage:
    emclass/bin/uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import os
import time
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests as _requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client

from retrieval_benchmark import (
    BenchmarkPrompt,
    RetrievalConfig,
    VIBE_PROFILE,
    infer_target_ranges,
    retrieve_candidates,
    rerank_candidates,
    select_top_tracks,
    build_transition_playlist,
)
from dataclasses import replace as dc_replace

_supabase: Optional[Client] = None
_model: Optional[SentenceTransformer] = None
_config = RetrievalConfig()

@lru_cache(maxsize=2048)
def _fresh_preview_url(track_id: str) -> Optional[str]:
    """Call Deezer public API to get a live 30s preview URL. Cached in-process."""
    try:
        r = _requests.get(
            f"https://api.deezer.com/track/{track_id}", timeout=5
        )
        if r.status_code == 200:
            return r.json().get("preview") or None
    except Exception:
        pass
    return None


def _refresh_previews(tracks: List[Dict[str, Any]]) -> None:
    """Fetch fresh Deezer preview URLs in parallel threads (in-place update)."""
    def _refresh_one(t: Dict[str, Any]) -> None:
        tid = t.get("track_id")
        if tid:
            fresh = _fresh_preview_url(str(tid))
            if fresh:
                t["preview_url"] = fresh

    threads = [threading.Thread(target=_refresh_one, args=(t,)) for t in tracks]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=6)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _supabase, _model
    load_dotenv(override=False)
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    ).strip()
    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_KEY in .env")
    _supabase = create_client(url, key)
    _model = SentenceTransformer(_config.embedding_model_name)
    print(
        f"[api] model={_config.embedding_model_name}  candidates={_config.rpc_candidate_count}"
    )
    yield


app = FastAPI(
    title="EmotionClassifier Playlist API",
    version="1.0.0",
    description="Turn a natural-language mood prompt into a ranked playlist.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlaylistRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=500,
        example="I'm feeling anxious. Help me calm down.",
    )
    vibe: Optional[str] = Field(
        None,
        example="relaxing",
        description="Hint vibe label — leave blank to auto-infer.",
    )
    top_n: int = Field(5, ge=1, le=20, description="Number of tracks to return.")


class Track(BaseModel):
    position: int
    track_id: Optional[str]
    title: Optional[str]
    artist: Optional[str]
    tempo: float
    energy: float
    brightness: float
    emotion_cluster: Optional[int]
    cluster_label: str
    similarity: float
    final_score: float
    transition_note: str
    preview_url: Optional[str] = None
    deezer_link: Optional[str] = None


class PlaylistResponse(BaseModel):
    prompt: str
    vibe: str
    inferred_vibe: str
    intent_type: str
    tempo_range: Optional[List[float]]
    energy_range: Optional[List[float]]
    tracks: List[Track]
    generation_ms: int


CLUSTER_LABELS = {
    0: "Calm / Relaxed",
    1: "Hype / Energetic",
    2: "Cheerful / Uplifting",
    3: "Tense / Intense",
}


def _cluster_label(cluster: Optional[int]) -> str:
    if cluster is None:
        return "Unknown"
    return CLUSTER_LABELS.get(cluster, f"Cluster {cluster}")


def _build_playlist(prompt: str, vibe: str, top_n: int) -> PlaylistResponse:
    assert _supabase is not None and _model is not None, "Not initialised"
    t0 = time.monotonic()
    config = dc_replace(_config, match_count=top_n)
    bp = BenchmarkPrompt(prompt=prompt, expected_vibe=vibe or "")
    intent = infer_target_ranges(prompt, vibe)

    if intent.intent_type == "transition":
        start_cands = retrieve_candidates(prompt, config, _supabase, _model, filters={})
        end_cands = retrieve_candidates(prompt, config, _supabase, _model, filters={})
        start_ranked = rerank_candidates(prompt, start_cands, bp, config)
        end_ranked = rerank_candidates(prompt, end_cands, bp, config)
        raw_tracks = build_transition_playlist(start_ranked, end_ranked, config, top_n)
    else:
        if intent.intent_type == "exploratory":
            retrieve_cfg = dc_replace(
                config,
                rpc_candidate_count=min(config.rpc_candidate_count * 2, 400),
                match_threshold=max(0.10, config.match_threshold - 0.05),
                max_artists_per_result_set=1,
            )
        else:
            retrieve_cfg = config
        retrieval_query = intent.retrieval_query or prompt
        candidates = retrieve_candidates(
            retrieval_query, retrieve_cfg, _supabase, _model, filters={}
        )
        reranked = rerank_candidates(prompt, candidates, bp, retrieve_cfg)
        raw_tracks = select_top_tracks(
            reranked, top_n, retrieve_cfg.max_artists_per_result_set
        )

    _refresh_previews(raw_tracks)

    tracks = [
        Track(
            **t,
            cluster_label=_cluster_label(t.get("emotion_cluster")),
        )
        for t in raw_tracks
    ]

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    inferred = vibe or "auto"
    return PlaylistResponse(
        prompt=prompt,
        vibe=inferred,
        inferred_vibe=inferred,
        intent_type=intent.intent_type,
        tempo_range=(
            [intent.tempo_min, intent.tempo_max]
            if intent.tempo_min is not None
            else None
        ),
        energy_range=(
            [intent.energy_min, intent.energy_max]
            if intent.energy_min is not None
            else None
        ),
        tracks=tracks,
        generation_ms=elapsed_ms,
    )



@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "model": _config.embedding_model_name,
        "candidates": _config.rpc_candidate_count,
    }


@app.get("/vibes", tags=["meta"])
def vibes():
    return {
        "vibes": sorted(VIBE_PROFILE.keys()),
        "tip": "Pass one of these as the 'vibe' field to override auto-inference.",
    }


@app.post("/playlist", response_model=PlaylistResponse, tags=["playlist"])
def create_playlist(req: PlaylistRequest):
    try:
        return _build_playlist(req.prompt, req.vibe or "", req.top_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
