import logging
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from supabase import Client, create_client
from tqdm import tqdm


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_NAME = "deeser_songs"
READ_PAGE_SIZE = 1000
K_CLUSTERS = 4
FEATURE_COLUMNS = ["tempo", "energy", "brightness"]
UPDATE_BATCH_SIZE = 300
PLOT_OUTPUT = "emotion_clusters_3d.html"
SUMMARY_OUTPUT = "cluster_summary.csv"
METRICS_OUTPUT = "clustering_metrics.json"


@dataclass
class PipelineConfig:
    table_name: str = TABLE_NAME
    read_page_size: int = READ_PAGE_SIZE
    k_clusters: int = K_CLUSTERS
    update_batch_size: int = UPDATE_BATCH_SIZE
    plot_output: str = PLOT_OUTPUT
    summary_output: str = SUMMARY_OUTPUT
    metrics_output: str = METRICS_OUTPUT


class EmotionClusterPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.supabase = self._create_supabase_client()

    @staticmethod
    def _create_supabase_client() -> Client:
        load_dotenv(override=False)
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

        if not url or not key:
            raise EnvironmentError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")

        return create_client(url, key)

    def fetch_dataset(self) -> pd.DataFrame:
        columns = "track_id,title,artist,tempo,energy,brightness"
        offset = 0
        records: List[Dict] = []

        log.info("Fetching rows from Supabase with non-null tempo/energy/brightness...")
        while True:
            response = (
                self.supabase.table(self.config.table_name)
                .select(columns)
                .not_.is_("tempo", "null")
                .not_.is_("energy", "null")
                .not_.is_("brightness", "null")
                .range(offset, offset + self.config.read_page_size - 1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                break

            records.extend(rows)
            if len(rows) < self.config.read_page_size:
                break
            offset += self.config.read_page_size

        if not records:
            raise RuntimeError("No rows found with required feature columns.")

        df = pd.DataFrame(records)
        log.info(f"Fetched usable rows: {len(df)}")
        return df

    @staticmethod
    def run_kmeans(df: pd.DataFrame, k_clusters: int) -> tuple[pd.DataFrame, float]:
        scaler = StandardScaler()
        scaled = scaler.fit_transform(df[FEATURE_COLUMNS])

        model = KMeans(n_clusters=k_clusters, init="k-means++", random_state=42, n_init="auto")
        labels = model.fit_predict(scaled)
        score = silhouette_score(scaled, labels)

        result = df.copy()
        result["emotion_cluster"] = labels.astype(int)
        return result, float(score)

    @staticmethod
    def build_cluster_profile(df: pd.DataFrame) -> pd.DataFrame:
        return (
            df.groupby("emotion_cluster", as_index=False)[FEATURE_COLUMNS]
            .mean()
            .sort_values("emotion_cluster")
        )

    @staticmethod
    def print_cluster_profile(summary: pd.DataFrame) -> None:

        log.info("Cluster profile (original feature scale):")
        print(summary.to_string(index=False, float_format=lambda x: f"{x:0.4f}"))

    def save_cluster_profile_csv(self, summary: pd.DataFrame) -> Path:
        output_path = Path(self.config.summary_output).resolve()
        summary.to_csv(output_path, index=False)
        log.info(f"Saved cluster summary CSV: {output_path}")
        return output_path

    def save_metrics_json(self, silhouette: float, row_count: int) -> Path:
        output_path = Path(self.config.metrics_output).resolve()
        payload = {
            "table": self.config.table_name,
            "k_clusters": self.config.k_clusters,
            "feature_columns": FEATURE_COLUMNS,
            "row_count": int(row_count),
            "silhouette_score": float(silhouette),
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info(f"Saved clustering metrics JSON: {output_path}")
        return output_path

    def save_3d_visualization(self, df: pd.DataFrame) -> Path:
        plot_df = df.copy()
        plot_df["emotion_cluster"] = plot_df["emotion_cluster"].astype(str)

        fig = px.scatter_3d(
            plot_df,
            x="tempo",
            y="energy",
            z="brightness",
            color="emotion_cluster",
            hover_data=["title", "artist", "track_id"],
            title="Emotion Clusters in Deezer Songs (K-Means, k=4)",
            opacity=0.8,
        )

        output_path = Path(self.config.plot_output).resolve()
        fig.write_html(str(output_path), include_plotlyjs="cdn")
        log.info(f"Saved interactive visualization: {output_path}")
        return output_path

    def update_emotion_clusters(self, df: pd.DataFrame) -> None:
        rows = df[["track_id", "emotion_cluster"]].to_dict(orient="records")
        total = len(rows)
        updated = 0

        log.info(f"Updating emotion_cluster in Supabase for {total} rows...")

        for start in tqdm(range(0, total, self.config.update_batch_size), desc="DB Sync", unit="batch"):
            batch = rows[start : start + self.config.update_batch_size]
            for row in batch:
                (
                    self.supabase.table(self.config.table_name)
                    .update({"emotion_cluster": int(row["emotion_cluster"])})
                    .eq("track_id", row["track_id"])
                    .execute()
                )
                updated += 1

        log.info(f"Supabase sync complete. Updated rows: {updated}")

    def run(self) -> None:
        df = self.fetch_dataset()
        clustered_df, silhouette = self.run_kmeans(df, self.config.k_clusters)
        summary = self.build_cluster_profile(clustered_df)

        log.info(f"Silhouette Score: {silhouette:0.5f}")
        self.print_cluster_profile(summary)
        self.save_cluster_profile_csv(summary)
        self.save_metrics_json(silhouette, row_count=len(clustered_df))
        self.save_3d_visualization(clustered_df)
        self.update_emotion_clusters(clustered_df)


if __name__ == "__main__":
    pipeline = EmotionClusterPipeline(PipelineConfig())
    pipeline.run()
