"""
Phase 5 - Retrieval Quality Benchmark for EmotionClassifier.

ASSUMPTIONS (already done by earlier pipeline scripts):
  - deezer_store_deeser_songs.py   -> songs in `deeser_songs` table
  - deezer_enrich_deeser_songs.py  -> tempo / energy / brightness populated
  - deezer_emotion_clustering.py   -> emotion_cluster (0-3) populated
  - generate_embeddings.py         -> text_for_embedding + embedding vector(1536) populated
  - Supabase RPC `match_songs`     -> vector similarity search is available

THIS SCRIPT adds (all new):
  1. Query intent classification   (transition / functional / exploratory / single-mood)
  2. Target range inference         (tempo / energy / brightness per vibe)
  3. Metadata post-filter layer     (cluster, tempo, energy after RPC)
  4. Multi-factor reranking         (similarity + tempo + energy + brightness + cluster + diversity)
  5. Transition playlist builder    (start-cluster -> end-cluster sequencing)
  6. Per-prompt evaluation metrics  (cluster consistency, diversity, tempo/energy match, transition score)
  7. Benchmark runner               (20 built-in prompts + CSV override, debug JSON)
  8. Artifact exports               (results CSV, debug JSON, 4 PNG plots)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client
from tqdm import tqdm

try:
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("retrieval_benchmark")


# -----------------------------------------------------------------
# Config + data models
# -----------------------------------------------------------------


@dataclass
class RetrievalConfig:
    match_threshold: float = 0.2
    match_count: int = 5
    rpc_candidate_count: int = 200
    # Weights tuned: energy raised (strongest mood signal), similarity lowered, cluster raised
    vector_weight: float = 0.45
    tempo_fit_weight: float = 0.15
    energy_fit_weight: float = 0.20
    brightness_fit_weight: float = 0.06
    cluster_boost_weight: float = 0.14
    artist_penalty_weight: float = 0.05
    max_artists_per_result_set: int = 2
    benchmark_csv_path: str = "benchmark_prompts.csv"
    results_csv_path: str = "retrieval_benchmark_results.csv"
    output_dir: str = "output"
    debug_json_path: str = "output/retrieval_benchmark_debug.json"
    table_name: str = "deeser_songs"
    rpc_name: str = "match_songs"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    target_dim: int = 1536


@dataclass
class BenchmarkPrompt:
    prompt: str
    expected_vibe: str
    expected_start_cluster: Optional[int] = None
    expected_end_cluster: Optional[int] = None
    target_tempo_min: Optional[float] = None
    target_tempo_max: Optional[float] = None
    target_energy_min: Optional[float] = None
    target_energy_max: Optional[float] = None
    required_attributes: List[str] = field(default_factory=list)
    forbidden_attributes: List[str] = field(default_factory=list)


@dataclass
class RetrievalIntent:
    intent_type: str
    tempo_min: Optional[float] = None
    tempo_max: Optional[float] = None
    energy_min: Optional[float] = None
    energy_max: Optional[float] = None
    preferred_cluster: Optional[int] = None
    brightness_pref: Optional[str] = None
    # Override embedding query when the user describes a source mood (e.g. "anxious") but
    # wants a target-state playlist (e.g. "relaxing"). Using the raw prompt would pull the
    # vector toward the wrong cluster; using a clean vibe phrase fixes retrieval bias.
    retrieval_query: Optional[str] = None


# -----------------------------------------------------------------
# Vibe profiles
# -----------------------------------------------------------------

VIBE_PROFILE: Dict[str, Dict[str, Any]] = {
    "calm": {
        "tempo": (60, 105),
        "energy": (0.00, 0.40),
        "brightness_pref": "low",
        "cluster": 0,
    },
    "melancholic": {
        "tempo": (55, 100),
        "energy": (0.00, 0.45),
        "brightness_pref": "low",
        "cluster": 0,
    },
    "relaxing": {
        "tempo": (60, 105),
        "energy": (0.00, 0.42),
        "brightness_pref": "low",
        "cluster": 0,
    },
    "focus": {
        "tempo": (70, 110),
        "energy": (0.15, 0.50),
        "brightness_pref": "low",
        "cluster": 0,
    },
    "sleep": {
        "tempo": (50, 90),
        "energy": (0.00, 0.35),
        "brightness_pref": "low",
        "cluster": 0,
    },
    "cheerful": {
        "tempo": (95, 125),
        "energy": (0.45, 0.72),
        "brightness_pref": "high",
        "cluster": 2,
    },
    "hopeful": {
        "tempo": (90, 125),
        "energy": (0.40, 0.70),
        "brightness_pref": "high",
        "cluster": 2,
    },
    "euphoric": {
        "tempo": (118, 170),
        "energy": (0.68, 1.00),
        "brightness_pref": "high",
        "cluster": 1,
    },
    "hype": {
        "tempo": (120, 175),
        "energy": (0.70, 1.00),
        "brightness_pref": "high",
        "cluster": 1,
    },
    "workout": {
        "tempo": (120, 180),
        "energy": (0.70, 1.00),
        "brightness_pref": "high",
        "cluster": 1,
    },
    "anxious": {
        "tempo": (130, 180),
        "energy": (0.25, 0.55),
        "brightness_pref": "medium",
        "cluster": 3,
    },
}

MOOD_TO_TARGET: Dict[str, str] = {
    "stressed": "calm",
    "sad": "hopeful",
    "anxious": "relaxing",
    "low-energy": "euphoric",
    "low energy": "euphoric",
}

# When a MOOD_TO_TARGET mapping fires, use this as the embedding query instead of the
# raw user prompt — avoids the source-mood word dragging the vector toward the wrong cluster.
MOOD_RETRIEVAL_QUERY: Dict[str, str] = {
    "stressed": "calm peaceful quiet gentle ambient music",
    "sad": "hopeful uplifting positive cheerful music",
    "anxious": "calm relaxing soothing soft ambient music",
    "low-energy": "energetic euphoric exciting dance music",
    "low energy": "energetic euphoric exciting dance music",
    # Sleep: override so the embedding doesn't drift toward mid-energy on words like "sleepy"
    "sleep": "soft quiet gentle calm ambient lullaby sleep music",
    "sleepy": "soft quiet gentle calm ambient lullaby sleep music",
    "asleep": "soft quiet gentle calm ambient lullaby sleep music",
}


# -----------------------------------------------------------------
# 1. Intent + range inference
# -----------------------------------------------------------------


def infer_intent_type(prompt: str) -> str:
    text = prompt.lower()
    if any(
        re.search(p, text)
        for p in [
            r"\bfrom\b.+\bto\b",
            r"->",
            r"\btransition\b",
            r"\bmove me from\b",
            r"\btake me from\b",
        ]
    ):
        return "transition"
    if any(
        w in text
        for w in ["study", "focus", "sleep", "workout", "run", "gym", "deep work"]
    ):
        return "functional"
    if any(w in text for w in ["explore", "new", "discover", "surprise", "anything"]):
        return "exploratory"
    return "single-mood"


def _resolve_vibe(prompt: str, expected_vibe: str) -> str:
    text = f"{prompt.lower()} {expected_vibe.lower()}"
    for src, tgt in MOOD_TO_TARGET.items():
        if src in text:
            return tgt
    for key in VIBE_PROFILE:
        if key in text:
            return key
    return expected_vibe.lower() or "calm"


def infer_target_ranges(prompt: str, expected_vibe: str) -> RetrievalIntent:
    vibe = _resolve_vibe(prompt, expected_vibe)
    p = VIBE_PROFILE.get(vibe, VIBE_PROFILE["calm"])
    # Detect if a mood-inversion mapping fired — if so, attach a clean retrieval query
    text = f"{prompt.lower()} {expected_vibe.lower()}"
    retrieval_query: Optional[str] = None
    for src, override in MOOD_RETRIEVAL_QUERY.items():
        if src in text:
            retrieval_query = override
            break
    return RetrievalIntent(
        intent_type=infer_intent_type(prompt),
        tempo_min=p["tempo"][0],
        tempo_max=p["tempo"][1],
        energy_min=p["energy"][0],
        energy_max=p["energy"][1],
        preferred_cluster=p["cluster"],
        brightness_pref=p["brightness_pref"],
        retrieval_query=retrieval_query,
    )


# -----------------------------------------------------------------
# 2. Retrieval (DataFrame + post-filters on existing DB data)
# -----------------------------------------------------------------


def _embed_query(text: str, model: SentenceTransformer, target_dim: int) -> List[float]:
    v = model.encode(text, convert_to_numpy=True).astype(float).tolist()
    if len(v) >= target_dim:
        return v[:target_dim]
    return v + [0.0] * (target_dim - len(v))


def _fetch_song_metadata(supabase: Client, table: str, ids: List[int]) -> pd.DataFrame:
    if not ids:
        return pd.DataFrame()
    resp = (
        supabase.table(table)
        .select(
            "id,track_id,title,artist,album_name,popularity,tempo,energy,"
            "brightness,emotion_cluster,text_for_embedding,url,deezer_link"
        )
        .in_("id", ids)
        .execute()
    )
    return pd.DataFrame(resp.data or [])


def _post_filter(df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
    if df.empty or not filters:
        return df
    d = df.copy()
    for col, lo, hi in [
        ("tempo", "tempo_min", "tempo_max"),
        ("energy", "energy_min", "energy_max"),
    ]:
        if filters.get(lo) is not None:
            d = d[d[col] >= float(filters[lo])]
        if filters.get(hi) is not None:
            d = d[d[col] <= float(filters[hi])]
    if filters.get("cluster_include"):
        d = d[d["emotion_cluster"].isin(filters["cluster_include"])]
    if filters.get("popularity_min") is not None:
        d = d[d["popularity"].fillna(0) >= int(filters["popularity_min"])]
    return d


def retrieve_candidates(
    query: str,
    config: RetrievalConfig,
    supabase: Client,
    model: SentenceTransformer,
    filters: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Calls match_songs RPC (searches already-stored song embeddings),
    fetches full metadata for returned IDs and applies post-filters.
    Returns a DataFrame so the reranker can work on numeric feature columns.
    """
    try:
        qv = _embed_query(query, model, config.target_dim)
        rpc_rows = (
            supabase.rpc(
                config.rpc_name,
                {
                    "query_embedding": qv,
                    "match_threshold": config.match_threshold,
                    "match_count": max(config.rpc_candidate_count, config.match_count),
                },
            )
            .execute()
            .data
            or []
        )
        if not rpc_rows:
            return pd.DataFrame()
        rpc_df = pd.DataFrame(rpc_rows)
        if "id" not in rpc_df.columns:
            return pd.DataFrame()
        ids = [int(x) for x in rpc_df["id"].dropna()]
        meta = _fetch_song_metadata(supabase, config.table_name, ids)
        if meta.empty:
            return pd.DataFrame()
        merged = meta.merge(rpc_df[["id", "similarity"]], on="id", how="left")
        merged["similarity"] = pd.to_numeric(
            merged["similarity"], errors="coerce"
        ).fillna(0.0)
        merged = _post_filter(merged, filters or {})
        return merged.sort_values("similarity", ascending=False).reset_index(drop=True)
    except Exception as exc:
        log.exception("retrieve_candidates error: %s", exc)
        return pd.DataFrame()


# -----------------------------------------------------------------
# 3. Multi-factor reranking
# -----------------------------------------------------------------


def _range_fit(
    value: Optional[float], lo: Optional[float], hi: Optional[float]
) -> float:
    if value is None or lo is None or hi is None:
        return 0.5
    v, lo, hi = float(value), float(lo), float(hi)
    if lo <= v <= hi:
        return 1.0
    span = max(hi - lo, 1e-6)
    return max(0.0, 1.0 - min(abs(v - lo), abs(v - hi)) / (span * 2.0))


def _brightness_fit(value: Optional[float], vibe_text: str) -> float:
    if value is None:
        return 0.0
    norm = max(0.0, min(1.0, float(value) / 3500.0))
    text = vibe_text.lower()
    if any(
        k in text
        for k in ["euphoric", "hype", "cheerful", "happy", "workout", "upbeat"]
    ):
        return norm
    if any(k in text for k in ["sleep", "calm", "relax", "mellow", "soft", "focus"]):
        return 1.0 - norm
    return 0.5


def rerank_candidates(
    query: str,
    candidates: pd.DataFrame,
    bp: BenchmarkPrompt,
    config: RetrievalConfig,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    intent = infer_target_ranges(query, bp.expected_vibe)
    t_lo = bp.target_tempo_min if bp.target_tempo_min is not None else intent.tempo_min
    t_hi = bp.target_tempo_max if bp.target_tempo_max is not None else intent.tempo_max
    e_lo = (
        bp.target_energy_min if bp.target_energy_min is not None else intent.energy_min
    )
    e_hi = (
        bp.target_energy_max if bp.target_energy_max is not None else intent.energy_max
    )
    exp_cluster = (
        bp.expected_end_cluster
        if bp.expected_end_cluster is not None
        else intent.preferred_cluster
    )
    vibe_text = f"{query} {bp.expected_vibe}"

    df = candidates.copy()
    df["tempo_fit"] = df["tempo"].apply(lambda v: _range_fit(v, t_lo, t_hi))
    df["energy_fit"] = df["energy"].apply(lambda v: _range_fit(v, e_lo, e_hi))
    df["brightness_fit"] = df["brightness"].apply(
        lambda v: _brightness_fit(v, vibe_text)
    )
    df["cluster_bonus"] = df["emotion_cluster"].apply(
        lambda v: 1.0
        if (v is not None and exp_cluster is not None and int(v) == int(exp_cluster))
        else 0.0
    )
    df["prelim"] = (
        config.vector_weight * df["similarity"]
        + config.tempo_fit_weight * df["tempo_fit"]
        + config.energy_fit_weight * df["energy_fit"]
        + config.brightness_fit_weight * df["brightness_fit"]
        + config.cluster_boost_weight * df["cluster_bonus"]
    )

    df = df.sort_values("prelim", ascending=False).reset_index(drop=True)
    seen: Dict[str, int] = {}
    penalties = []
    for _, row in df.iterrows():
        a = str(row.get("artist") or "unknown").lower()
        penalties.append(seen.get(a, 0) * config.artist_penalty_weight)
        seen[a] = seen.get(a, 0) + 1
    df["artist_penalty"] = penalties

    required = [x.lower() for x in bp.required_attributes]
    forbidden = [x.lower() for x in bp.forbidden_attributes]

    def _text(row: pd.Series) -> str:
        return str(row.get("text_for_embedding") or "").lower()

    if required:
        df["req_bonus"] = df.apply(
            lambda r: min(0.08, 0.02 * sum(1 for t in required if t in _text(r))),
            axis=1,
        )
    else:
        df["req_bonus"] = 0.0

    if forbidden:
        df["forb_penalty"] = df.apply(
            lambda r: min(0.12, 0.03 * sum(1 for t in forbidden if t in _text(r))),
            axis=1,
        )
    else:
        df["forb_penalty"] = 0.0

    df["final_score"] = (
        df["prelim"] - df["artist_penalty"] + df["req_bonus"] - df["forb_penalty"]
    )
    return df.sort_values("final_score", ascending=False).reset_index(drop=True)


# -----------------------------------------------------------------
# 4. Diversity-aware selection + transition sequencing
# -----------------------------------------------------------------


def select_top_tracks(
    reranked: pd.DataFrame,
    top_n: int,
    max_per_artist: int,
    smooth_sort: bool = False,
) -> List[Dict[str, Any]]:
    if reranked.empty:
        return []
    df = (
        reranked.sort_values(
            ["energy", "tempo", "final_score"], ascending=[True, True, False]
        ).reset_index(drop=True)
        if smooth_sort
        else reranked.copy()
    )

    selected, seen_artists, chosen_ids = [], {}, set()
    for _, row in df.iterrows():
        if len(selected) >= top_n:
            break
        a = str(row.get("artist") or "unknown").lower()
        if seen_artists.get(a, 0) < max_per_artist:
            selected.append(row)
            seen_artists[a] = seen_artists.get(a, 0) + 1
            chosen_ids.add(row.get("id"))

    if len(selected) < top_n:
        for _, row in df.iterrows():
            if len(selected) >= top_n:
                break
            if row.get("id") not in chosen_ids:
                selected.append(row)

    result, prev_energy = [], None
    for idx, row in enumerate(selected, start=1):
        energy = float(row.get("energy") or 0.0)
        note = ""
        if prev_energy is not None:
            delta = energy - prev_energy
            note = (
                "Raises intensity."
                if delta > 0.08
                else "Softens intensity."
                if delta < -0.08
                else "Steady intensity."
            )
        prev_energy = energy
        result.append(
            {
                "position": idx,
                "track_id": row.get("track_id"),
                "title": row.get("title"),
                "artist": row.get("artist"),
                "tempo": round(float(row.get("tempo") or 0.0), 2),
                "energy": round(float(row.get("energy") or 0.0), 4),
                "brightness": round(float(row.get("brightness") or 0.0), 2),
                "emotion_cluster": (
                    int(row["emotion_cluster"])
                    if pd.notna(row.get("emotion_cluster"))
                    else None
                ),
                "similarity": round(float(row.get("similarity") or 0.0), 4),
                "final_score": round(float(row.get("final_score") or 0.0), 4),
                "transition_note": note,
                "preview_url": row.get("url") or None,
                "deezer_link": row.get("deezer_link") or None,
            }
        )
    return result


def build_transition_playlist(
    start_ranked: pd.DataFrame,
    end_ranked: pd.DataFrame,
    config: RetrievalConfig,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    start_n = max(2, top_n // 2)
    tracks = select_top_tracks(
        start_ranked, start_n, config.max_artists_per_result_set
    ) + select_top_tracks(
        end_ranked, top_n - start_n, config.max_artists_per_result_set
    )
    for i, t in enumerate(tracks[:top_n], start=1):
        t["position"] = i
    return tracks[:top_n]


# -----------------------------------------------------------------
# 5. Evaluation metrics
# -----------------------------------------------------------------


def _avg(vals: Iterable[float]) -> float:
    v = [float(x) for x in vals if x is not None]
    return sum(v) / len(v) if v else 0.0


def _cluster_consistency(df: pd.DataFrame, expected: Optional[int]) -> float:
    if df.empty or expected is None:
        return 0.0
    return float((df["emotion_cluster"] == expected).mean())


def _diversity(df: pd.DataFrame) -> float:
    return min(1.0, df["artist"].nunique() / max(1, len(df))) if not df.empty else 0.0


def _precision_at_k(
    top_df: pd.DataFrame,
    exp_cluster: Optional[int],
    e_lo: Optional[float],
    e_hi: Optional[float],
    k: int = 5,
) -> float:
    """Fraction of top-k results that are both in the right cluster AND have acceptable energy."""
    if top_df.empty or exp_cluster is None:
        return 0.0
    subset = top_df.head(k)
    hits = sum(
        1
        for _, row in subset.iterrows()
        if (
            row.get("emotion_cluster") == exp_cluster
            and _range_fit(row.get("energy"), e_lo, e_hi) >= 0.5
        )
    )
    return hits / max(1, len(subset))


def _transition_score(playlist: List[Dict], bp: BenchmarkPrompt) -> float:
    if (
        not playlist
        or bp.expected_start_cluster is None
        or bp.expected_end_cluster is None
    ):
        return 0.0
    start_hit = (
        1.0 if playlist[0].get("emotion_cluster") == bp.expected_start_cluster else 0.0
    )
    end_hit = (
        1.0 if playlist[-1].get("emotion_cluster") == bp.expected_end_cluster else 0.0
    )
    energies = [float(t.get("energy") or 0.0) for t in playlist]
    smooth = sum(
        1 for i in range(1, len(energies)) if abs(energies[i] - energies[i - 1]) <= 0.25
    )
    return 0.4 * start_hit + 0.4 * end_hit + 0.2 * (smooth / max(1, len(energies) - 1))


def evaluate_prompt(
    bp: BenchmarkPrompt,
    candidates: pd.DataFrame,
    top_df: pd.DataFrame,
    playlist: List[Dict],
    latency_ms: float,
    intent_type: str,
    inferred_intent: Optional["RetrievalIntent"] = None,
) -> Dict[str, Any]:
    # Use explicit bp ranges first; fall back to inferred ranges so eval matches reranker logic
    t_lo = (
        bp.target_tempo_min
        if bp.target_tempo_min is not None
        else (inferred_intent.tempo_min if inferred_intent else None)
    )
    t_hi = (
        bp.target_tempo_max
        if bp.target_tempo_max is not None
        else (inferred_intent.tempo_max if inferred_intent else None)
    )
    e_lo = (
        bp.target_energy_min
        if bp.target_energy_min is not None
        else (inferred_intent.energy_min if inferred_intent else None)
    )
    e_hi = (
        bp.target_energy_max
        if bp.target_energy_max is not None
        else (inferred_intent.energy_max if inferred_intent else None)
    )
    exp_cluster = (
        bp.expected_end_cluster
        if bp.expected_end_cluster is not None
        else (inferred_intent.preferred_cluster if inferred_intent else None)
    )
    avg_sim = _avg(top_df["similarity"]) if not top_df.empty else 0.0
    avg_tempo = _avg(top_df["tempo"]) if not top_df.empty else 0.0
    avg_energy = _avg(top_df["energy"]) if not top_df.empty else 0.0
    avg_bright = _avg(top_df["brightness"]) if not top_df.empty else 0.0
    tempo_match = (
        _avg([_range_fit(v, t_lo, t_hi) for v in top_df["tempo"]])
        if not top_df.empty
        else 0.0
    )
    energy_match = (
        _avg([_range_fit(v, e_lo, e_hi) for v in top_df["energy"]])
        if not top_df.empty
        else 0.0
    )
    diversity = _diversity(top_df)
    cluster_con = _cluster_consistency(top_df, exp_cluster)
    precision_5 = _precision_at_k(top_df, exp_cluster, e_lo, e_hi, k=5)
    transition = _transition_score(playlist, bp) if intent_type == "transition" else 0.0

    required, forbidden = (
        [x.lower() for x in bp.required_attributes],
        [x.lower() for x in bp.forbidden_attributes],
    )
    if required or forbidden:
        scores = []
        for _, row in top_df.iterrows():
            text = str(row.get("text_for_embedding") or "").lower()
            req_hit = (
                sum(1 for t in required if t in text) / max(1, len(required))
                if required
                else 0.5
            )
            forb_hit = (
                sum(1 for t in forbidden if t in text) / max(1, len(forbidden))
                if forbidden
                else 0.0
            )
            scores.append(max(0.0, req_hit - forb_hit))
        vibe_match = _avg(scores)
    else:
        vibe_match = 0.5

    # Updated quality formula — incorporates Precision@5 as a direct signal
    quality = (
        0.25 * avg_sim
        + 0.20 * vibe_match
        + 0.15 * energy_match
        + 0.12 * tempo_match
        + 0.10 * diversity
        + 0.08 * cluster_con
        + 0.10 * precision_5
    )
    if intent_type == "transition":
        quality = 0.85 * quality + 0.15 * transition

    cluster_dist = (
        dict(Counter(str(c) for c in top_df["emotion_cluster"] if pd.notna(c)))
        if not top_df.empty
        else {}
    )

    return {
        "prompt": bp.prompt,
        "expected_vibe": bp.expected_vibe,
        "intent_type": intent_type,
        "retrieved_candidate_count": len(candidates),
        "average_similarity_top5": round(avg_sim, 4),
        "average_tempo_top5": round(avg_tempo, 2),
        "average_energy_top5": round(avg_energy, 4),
        "average_brightness_top5": round(avg_bright, 2),
        "unique_artist_count_top5": int(top_df["artist"].nunique())
        if not top_df.empty
        else 0,
        "cluster_distribution_top5": json.dumps(cluster_dist),
        "latency_ms": round(latency_ms, 2),
        "vibe_match_score": round(vibe_match, 4),
        "tempo_match_score": round(tempo_match, 4),
        "energy_match_score": round(energy_match, 4),
        "diversity_score": round(diversity, 4),
        "cluster_consistency_score": round(cluster_con, 4),
        "precision_at_5": round(precision_5, 4),
        "transition_score": round(transition, 4),
        "overall_retrieval_quality_score": round(quality, 4),
    }


# -----------------------------------------------------------------
# 6. Benchmark runner
# -----------------------------------------------------------------


def run_single_benchmark(
    bp: BenchmarkPrompt,
    config: RetrievalConfig,
    supabase: Client,
    model: SentenceTransformer,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    t0 = time.perf_counter()
    intent = infer_target_ranges(bp.prompt, bp.expected_vibe)
    debug: Dict[str, Any] = {
        "prompt": bp.prompt,
        "inferred_intent": asdict(intent),
        "retrieved": [],
        "reranked": [],
        "playlist": [],
    }

    if (
        intent.intent_type == "transition"
        and bp.expected_start_cluster is not None
        and bp.expected_end_cluster is not None
    ):
        start_cands = retrieve_candidates(
            bp.prompt,
            config,
            supabase,
            model,
            {"cluster_include": [bp.expected_start_cluster]},
        )
        end_cands = retrieve_candidates(
            bp.prompt,
            config,
            supabase,
            model,
            {"cluster_include": [bp.expected_end_cluster]},
        )
        start_bp = BenchmarkPrompt(
            prompt=bp.prompt,
            expected_vibe=bp.expected_vibe,
            expected_end_cluster=bp.expected_start_cluster,
            target_tempo_min=bp.target_tempo_min,
            target_tempo_max=bp.target_tempo_max,
            target_energy_min=bp.target_energy_min,
            target_energy_max=bp.target_energy_max,
        )
        start_ranked = rerank_candidates(bp.prompt, start_cands, start_bp, config)
        end_ranked = rerank_candidates(bp.prompt, end_cands, bp, config)
        playlist = build_transition_playlist(
            start_ranked, end_ranked, config, config.match_count
        )
        half = max(1, config.match_count // 2)
        top_df = pd.concat(
            [start_ranked.head(half), end_ranked.head(config.match_count - half)],
            ignore_index=True,
        )
        all_candidates = pd.concat([start_cands, end_cands], ignore_index=True)
        debug["retrieved"] = all_candidates.head(60).to_dict(orient="records")
        debug["reranked"] = (
            pd.concat([start_ranked, end_ranked]).head(60).to_dict(orient="records")
        )
    else:
        # For exploratory prompts: widen candidate pool, lower threshold, enforce 1-per-artist
        if intent.intent_type == "exploratory":
            retrieve_cfg = dc_replace(
                config,
                rpc_candidate_count=min(config.rpc_candidate_count * 2, 400),
                match_threshold=max(0.10, config.match_threshold - 0.05),
                max_artists_per_result_set=1,
            )
        else:
            retrieve_cfg = config
        # No tempo/energy post-filter here — reranker scores those numerically.
        # Tight range filters at retrieval time starve the candidate pool.
        # Use override query if set (mood-inversion prompts like "anxious → relax").
        retrieval_query = intent.retrieval_query or bp.prompt
        candidates = retrieve_candidates(
            retrieval_query, retrieve_cfg, supabase, model, filters={}
        )
        reranked = rerank_candidates(bp.prompt, candidates, bp, retrieve_cfg)
        playlist = select_top_tracks(
            reranked, retrieve_cfg.match_count, retrieve_cfg.max_artists_per_result_set
        )
        top_ids = {t["track_id"] for t in playlist}
        top_df = reranked[reranked["track_id"].isin(top_ids)].head(
            retrieve_cfg.match_count
        )
        all_candidates = candidates
        debug["retrieved"] = candidates.head(60).to_dict(orient="records")
        debug["reranked"] = reranked.head(60).to_dict(orient="records")

    debug["playlist"] = playlist
    latency = (time.perf_counter() - t0) * 1000.0
    metrics = evaluate_prompt(
        bp,
        all_candidates,
        top_df,
        playlist,
        latency,
        intent.intent_type,
        inferred_intent=intent,
    )
    return metrics, debug


# -----------------------------------------------------------------
# 7. Output helpers
# -----------------------------------------------------------------


def save_results(results: List[Dict], config: RetrievalConfig) -> pd.DataFrame:
    df = pd.DataFrame(results)
    df.to_csv(config.results_csv_path, index=False)
    log.info("Results CSV -> %s", config.results_csv_path)
    return df


def save_debug_json(rows: List[Dict], config: RetrievalConfig) -> None:
    p = Path(config.debug_json_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    log.info("Debug JSON -> %s", p)


def generate_plots(df: pd.DataFrame, config: RetrievalConfig) -> None:
    if not MATPLOTLIB_AVAILABLE:
        log.warning("matplotlib not available - skipping plots.")
        return
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 5))
    plt.hist(df["overall_retrieval_quality_score"], bins=12, edgecolor="black")
    plt.title("Retrieval Quality Score Distribution")
    plt.xlabel("overall_retrieval_quality_score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(out / "retrieval_score_histogram.png", dpi=150)
    plt.close()

    cluster_counts: Counter = Counter()
    for item in df["cluster_distribution_top5"].fillna("{}"):
        try:
            for k, v in json.loads(item).items():
                cluster_counts[k] += int(v)
        except Exception:
            pass
    if cluster_counts:
        keys = sorted(cluster_counts, key=lambda x: int(x))
        int_keys = [int(k) for k in keys]
        plt.figure(figsize=(8, 5))
        plt.bar(int_keys, [cluster_counts[k] for k in keys])
        plt.title("Cluster Frequency in Top Results")
        plt.xlabel("emotion_cluster")
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(out / "cluster_frequency_bar.png", dpi=150)
        plt.close()

    plt.figure(figsize=(8, 5))
    plt.boxplot(df["latency_ms"].tolist(), vert=True)
    plt.title("Latency per Prompt (ms)")
    plt.ylabel("latency_ms")
    plt.tight_layout()
    plt.savefig(out / "latency_boxplot.png", dpi=150)
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.scatter(df["average_tempo_top5"], df["average_energy_top5"], alpha=0.8)
    plt.title("Avg Tempo vs Avg Energy of Top Results")
    plt.xlabel("average_tempo_top5")
    plt.ylabel("average_energy_top5")
    plt.tight_layout()
    plt.savefig(out / "tempo_energy_scatter.png", dpi=150)
    plt.close()
    log.info("Plots -> %s/", out)


def print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return
    best = df.loc[df["overall_retrieval_quality_score"].idxmax()]
    worst = df.loc[df["overall_retrieval_quality_score"].idxmin()]
    print("\n=== Retrieval Benchmark Summary ===")
    print(f"Prompts tested         : {len(df)}")
    print(f"Avg latency (ms)       : {df['latency_ms'].mean():.2f}")
    print(
        f"Avg quality score      : {df['overall_retrieval_quality_score'].mean():.4f}"
    )
    print(f"Avg diversity score    : {df['diversity_score'].mean():.4f}")
    print(f"Avg Precision@5        : {df['precision_at_5'].mean():.4f}")
    print(f"Avg unique artists/top5: {df['unique_artist_count_top5'].mean():.2f}")
    print(
        f"Best  (score={best['overall_retrieval_quality_score']:.4f}): {best['prompt']}"
    )
    print(
        f"Worst (score={worst['overall_retrieval_quality_score']:.4f}): {worst['prompt']}"
    )
    failed = df[df["retrieved_candidate_count"] <= 0]
    if not failed.empty:
        for _, r in failed.iterrows():
            print(f"  !! No candidates: {r['prompt']}")
    else:
        print("Failed prompts         : none")


# -----------------------------------------------------------------
# 8. Benchmark prompt set
# -----------------------------------------------------------------


def _load_prompts_csv(path: Path) -> List[BenchmarkPrompt]:
    df = pd.read_csv(path)
    prompts = []
    for _, row in df.iterrows():

        def _fl(key):
            return float(row[key]) if pd.notna(row.get(key)) else None

        def _int(key):
            return int(row[key]) if pd.notna(row.get(key)) else None

        def _lst(key):
            v = row.get(key)
            return (
                [x.strip() for x in re.split(r"[|,;]", str(v)) if x.strip()]
                if pd.notna(v)
                else []
            )

        p = BenchmarkPrompt(
            prompt=str(row.get("prompt", "")).strip(),
            expected_vibe=str(row.get("expected_vibe", "calm")).strip(),
            expected_start_cluster=_int("expected_start_cluster"),
            expected_end_cluster=_int("expected_end_cluster"),
            target_tempo_min=_fl("target_tempo_min"),
            target_tempo_max=_fl("target_tempo_max"),
            target_energy_min=_fl("target_energy_min"),
            target_energy_max=_fl("target_energy_max"),
            required_attributes=_lst("required_attributes"),
            forbidden_attributes=_lst("forbidden_attributes"),
        )
        if p.prompt:
            prompts.append(p)
    return prompts


def load_benchmark_prompts(config: RetrievalConfig) -> List[BenchmarkPrompt]:
    csv_path = Path(config.benchmark_csv_path)
    if csv_path.exists():
        rows = _load_prompts_csv(csv_path)
        if rows:
            log.info("Loaded %d prompts from CSV: %s", len(rows), csv_path)
            return rows
    log.info("Using built-in benchmark prompts.")
    return [
        BenchmarkPrompt(
            "I feel stressed and overwhelmed. Give me something calming.",
            "calm",
            3,
            0,
            60,
            105,
            0.0,
            0.42,
            ["calm", "relax"],
        ),
        BenchmarkPrompt(
            "I am sad. I want songs that move me toward hopeful and lighter feelings.",
            "hopeful",
            0,
            2,
            90,
            125,
            0.4,
            0.75,
            ["hopeful", "cheerful"],
        ),
        BenchmarkPrompt(
            "My energy is low. Hype me up hard.",
            "euphoric",
            0,
            1,
            120,
            175,
            0.70,
            1.00,
            ["hype", "high energy"],
        ),
        BenchmarkPrompt(
            "I am anxious. Help me settle down and relax.",
            "relaxing",
            3,
            0,
            60,
            105,
            0.0,
            0.45,
        ),
        BenchmarkPrompt(
            "Need focus music with minimal distraction.",
            "focus",
            0,
            0,
            70,
            110,
            0.15,
            0.50,
            [],
            ["hype", "intense"],
        ),
        BenchmarkPrompt(
            "Give me a workout playlist with strong momentum.",
            "workout",
            1,
            1,
            120,
            180,
            0.70,
            1.00,
        ),
        BenchmarkPrompt(
            "I want euphoric tracks for running.",
            "euphoric",
            1,
            1,
            125,
            180,
            0.72,
            1.00,
        ),
        BenchmarkPrompt(
            "Need soft sleepy songs to fall asleep quickly.",
            "sleep",
            0,
            0,
            50,
            90,
            0.0,
            0.35,
            [],
            ["intense", "workout"],
        ),
        BenchmarkPrompt("Take me from stressed to calm in 5 songs.", "calm", 3, 0),
        BenchmarkPrompt("Transition me from sad to hopeful.", "hopeful", 0, 2),
        BenchmarkPrompt("Move me from low energy to full hype.", "hype", 0, 1),
        BenchmarkPrompt(
            "Settle me from anxious to relaxed ambient vibes.", "relaxing", 3, 0
        ),
        BenchmarkPrompt(
            "Give me calm instrumental-like tracks for deep work.", "focus", 0, 0
        ),
        BenchmarkPrompt("I need cheerful songs for a sunny drive.", "cheerful", 2, 2),
        BenchmarkPrompt(
            "Find fast energetic songs for gym PR attempts.", "workout", 1, 1
        ),
        BenchmarkPrompt("Suggest mellow night tracks to unwind.", "calm", 0, 0),
        BenchmarkPrompt(
            "I want uplifting but not too intense songs.",
            "hopeful",
            2,
            2,
            None,
            None,
            0.35,
            0.70,
        ),
        BenchmarkPrompt(
            "Explore something new but emotionally soothing.", "relaxing", 0, 0
        ),
        BenchmarkPrompt(
            "Give me chill-pop with bright, light vibes.", "cheerful", 2, 2
        ),
        BenchmarkPrompt(
            "I need late-night quiet tracks with low brightness and low energy.",
            "sleep",
            0,
            0,
        ),
    ]


# -----------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------


def main() -> None:
    config = RetrievalConfig(
        match_threshold=float(os.getenv("RETRIEVAL_MATCH_THRESHOLD", "0.2")),
        match_count=int(os.getenv("RETRIEVAL_TOP_K", "5")),
        vector_weight=float(os.getenv("VECTOR_WEIGHT", "0.45")),
        tempo_fit_weight=float(os.getenv("TEMPO_WEIGHT", "0.15")),
        energy_fit_weight=float(os.getenv("ENERGY_WEIGHT", "0.20")),
        cluster_boost_weight=float(os.getenv("CLUSTER_WEIGHT", "0.14")),
        artist_penalty_weight=float(os.getenv("ARTIST_PENALTY_WEIGHT", "0.05")),
        brightness_fit_weight=float(os.getenv("BRIGHTNESS_WEIGHT", "0.06")),
        max_artists_per_result_set=int(os.getenv("MAX_ARTISTS_PER_RESULT", "2")),
    )

    load_dotenv(override=False)
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    ).strip()
    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_KEY in .env")
    supabase = create_client(url, key)

    model = SentenceTransformer(config.embedding_model_name)
    log.info(
        "Model loaded: %s  (query-time only - song embeddings already in DB)",
        config.embedding_model_name,
    )

    benchmarks = load_benchmark_prompts(config)
    log.info("Benchmark prompts: %d", len(benchmarks))

    results, debug_rows = [], []
    for bp in tqdm(benchmarks, desc="Benchmarking", unit="prompt"):
        try:
            metrics, debug = run_single_benchmark(bp, config, supabase, model)
            results.append(metrics)
            debug_rows.append(debug)
        except Exception as exc:
            log.exception("Prompt failed: %s", exc)
            results.append(
                {
                    "prompt": bp.prompt,
                    "expected_vibe": bp.expected_vibe,
                    "intent_type": infer_intent_type(bp.prompt),
                    "retrieved_candidate_count": 0,
                    "average_similarity_top5": 0.0,
                    "average_tempo_top5": 0.0,
                    "average_energy_top5": 0.0,
                    "average_brightness_top5": 0.0,
                    "unique_artist_count_top5": 0,
                    "cluster_distribution_top5": "{}",
                    "latency_ms": 0.0,
                    "vibe_match_score": 0.0,
                    "tempo_match_score": 0.0,
                    "energy_match_score": 0.0,
                    "diversity_score": 0.0,
                    "cluster_consistency_score": 0.0,
                    "transition_score": 0.0,
                    "overall_retrieval_quality_score": 0.0,
                }
            )
            debug_rows.append({"prompt": bp.prompt, "error": str(exc)})

    results_df = save_results(results, config)
    save_debug_json(debug_rows, config)
    print_summary(results_df)
    generate_plots(results_df, config)


if __name__ == "__main__":
    main()
