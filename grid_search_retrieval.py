"""
Grid search over match_threshold and rpc_candidate_count.
Runs the full 20-prompt benchmark for each combination and prints a ranked table.
Uses the same pipeline as retrieval_benchmark.py — no duplicated logic.

Usage:
    emclass/bin/python grid_search_retrieval.py
"""

from __future__ import annotations

import os
import time
from dataclasses import replace as dc_replace
from itertools import product

import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client
from tqdm import tqdm

# Import all logic from the main benchmark — zero duplication
from retrieval_benchmark import (
    RetrievalConfig,
    load_benchmark_prompts,
    run_single_benchmark,
)

THRESHOLD_GRID = [
    0.15,
    0.20,
]  # threshold proved irrelevant in run-1; keep 2 for confirmation
CANDIDATE_GRID = [80, 120, 160, 200]  # drop 40 (proven worst); explore upper range


def main() -> None:
    load_dotenv(override=False)
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    ).strip()
    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL or SUPABASE_KEY in .env")
    supabase = create_client(url, key)

    base_config = RetrievalConfig()
    model = SentenceTransformer(base_config.embedding_model_name)
    print(
        f"Model ready. Grid: {len(THRESHOLD_GRID)}×{len(CANDIDATE_GRID)} = "
        f"{len(THRESHOLD_GRID) * len(CANDIDATE_GRID)} combinations × 20 prompts\n"
    )

    benchmarks = load_benchmark_prompts(base_config)
    rows = []

    combos = list(product(THRESHOLD_GRID, CANDIDATE_GRID))
    for threshold, candidates in tqdm(combos, desc="Grid search", unit="combo"):
        config = dc_replace(
            base_config, match_threshold=threshold, rpc_candidate_count=candidates
        )
        scores, latencies, precisions = [], [], []
        for bp in benchmarks:
            try:
                metrics, _ = run_single_benchmark(bp, config, supabase, model)
                scores.append(metrics["overall_retrieval_quality_score"])
                latencies.append(metrics["latency_ms"])
                precisions.append(metrics["precision_at_5"])
            except Exception:
                scores.append(0.0)
                latencies.append(0.0)
                precisions.append(0.0)

        rows.append(
            {
                "match_threshold": threshold,
                "rpc_candidate_count": candidates,
                "avg_quality": round(sum(scores) / len(scores), 4),
                "avg_precision_at_5": round(sum(precisions) / len(precisions), 4),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
                "min_quality": round(min(scores), 4),
                "max_quality": round(max(scores), 4),
            }
        )

    df = (
        pd.DataFrame(rows)
        .sort_values("avg_quality", ascending=False)
        .reset_index(drop=True)
    )
    df.index += 1  # rank from 1

    out_path = "output/grid_search_results.csv"
    import pathlib

    pathlib.Path("output").mkdir(exist_ok=True)
    df.to_csv(out_path, index_label="rank")

    print("\n=== Grid Search Results (ranked by avg quality) ===")
    print(df.to_string())
    print(
        f"\nBest config: threshold={df.iloc[0]['match_threshold']}, "
        f"candidates={df.iloc[0]['rpc_candidate_count']}, "
        f"avg_quality={df.iloc[0]['avg_quality']}"
    )
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
