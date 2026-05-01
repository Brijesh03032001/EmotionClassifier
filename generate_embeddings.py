import logging
import os
from dataclasses import dataclass
from typing import Dict, List

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client
from tqdm import tqdm


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_NAME = "deeser_songs"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
FETCH_BATCH_SIZE = 200
UPDATE_CHUNK_SIZE = 50
TARGET_VECTOR_DIM = 1536

EMOTION_MAP: Dict[int, str] = {
    0: "Calm, Melancholic, Relaxing, Low Energy",
    1: "Euphoric, Hype, Intense, High Energy",
    2: "Cheerful, Chill-Pop, Lighthearted, Mid Energy",
    3: "Anxious, Fast-paced, Driving but low intensity",
}


@dataclass
class EmbeddingConfig:
    table_name: str = TABLE_NAME
    model_name: str = MODEL_NAME
    fetch_batch_size: int = FETCH_BATCH_SIZE
    update_chunk_size: int = UPDATE_CHUNK_SIZE
    target_vector_dim: int = TARGET_VECTOR_DIM


class EmbeddingPipeline:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self.supabase = self._create_supabase_client()
        self.model = SentenceTransformer(self.config.model_name)
        self._dim_warning_shown = False

    @staticmethod
    def _create_supabase_client() -> Client:
        load_dotenv(override=False)
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

        if not url or not key:
            raise EnvironmentError(
                "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        return create_client(url, key)

    def fetch_pending_rows(self) -> List[Dict]:
        response = (
            self.supabase.table(self.config.table_name)
            .select(
                "id,track_id,title,artist,album_name,tempo,energy,brightness,emotion_cluster"
            )
            .is_("embedding", "null")
            .order("id")
            .limit(self.config.fetch_batch_size)
            .execute()
        )
        return response.data or []

    @staticmethod
    def _safe_float(value: object) -> float:
        if value is None:
            return 0.0
        return float(value)

    def build_text_for_embedding(self, row: Dict) -> str:
        title = (row.get("title") or "Unknown Title").strip()
        artist = (row.get("artist") or "Unknown Artist").strip()
        album = (row.get("album_name") or "Unknown Album").strip()
        tempo = self._safe_float(row.get("tempo"))
        energy = self._safe_float(row.get("energy"))
        brightness = self._safe_float(row.get("brightness"))

        cluster = row.get("emotion_cluster")
        if cluster is None:
            emotion = "Unspecified emotional category"
            cluster_label = "Unknown"
        else:
            cluster_int = int(cluster)
            emotion = EMOTION_MAP.get(cluster_int, "Unspecified emotional category")
            cluster_label = str(cluster_int)

        return (
            f"Song: '{title}' by '{artist}' from the album '{album}'. "
            f"This track belongs to the '{emotion}' category (Cluster {cluster_label}). "
            f"It has a tempo of {tempo:.2f} BPM, an energy level of {energy:.4f}, "
            f"and a brightness score of {brightness:.4f}."
        )

    def _fit_vector_dim(self, vector: List[float]) -> List[float]:
        current_dim = len(vector)
        target_dim = self.config.target_vector_dim

        if current_dim == target_dim:
            return vector

        if current_dim > target_dim:
            if not self._dim_warning_shown:
                log.warning(
                    "Embedding dim (%s) > target dim (%s). Truncating vectors.",
                    current_dim,
                    target_dim,
                )
                self._dim_warning_shown = True
            return vector[:target_dim]

        if not self._dim_warning_shown:
            log.warning(
                "Embedding dim (%s) < target dim (%s). Zero-padding vectors.",
                current_dim,
                target_dim,
            )
            self._dim_warning_shown = True
        return vector + [0.0] * (target_dim - current_dim)

    def embed_text(self, text: str) -> List[float]:
        vector = self.model.encode(text, convert_to_numpy=True).astype(float).tolist()
        return self._fit_vector_dim(vector)

    def update_rows(self, payload_rows: List[Dict]) -> int:
        updated = 0
        for row in payload_rows:
            try:
                (
                    self.supabase.table(self.config.table_name)
                    .update(
                        {
                            "text_for_embedding": row["text_for_embedding"],
                            "embedding": row["embedding"],
                        }
                    )
                    .eq("track_id", row["track_id"])
                    .execute()
                )
                updated += 1
            except Exception as exc:
                log.error("Update failed for track_id=%s: %s", row.get("track_id"), exc)
        return updated

    def run(self) -> None:
        total_updated = 0

        while True:
            batch = self.fetch_pending_rows()
            if not batch:
                break

            prepared_rows: List[Dict] = []
            for row in tqdm(batch, desc="Prepare+Embed", unit="song"):
                text_value = self.build_text_for_embedding(row)
                vector = self.embed_text(text_value)
                prepared_rows.append(
                    {
                        "track_id": row["track_id"],
                        "text_for_embedding": text_value,
                        "embedding": vector,
                    }
                )

            batch_updated = 0
            for start in tqdm(
                range(0, len(prepared_rows), self.config.update_chunk_size),
                desc="Supabase Update",
                unit="chunk",
            ):
                chunk = prepared_rows[start : start + self.config.update_chunk_size]
                batch_updated += self.update_rows(chunk)

            total_updated += batch_updated
            log.info(
                "Processed batch: fetched=%s, updated=%s", len(batch), batch_updated
            )

        log.info("Embedding pipeline complete. Total rows updated: %s", total_updated)


if __name__ == "__main__":
    pipeline = EmbeddingPipeline(EmbeddingConfig())
    pipeline.run()
