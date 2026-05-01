import gc
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import librosa
import numpy as np
import requests
from dotenv import load_dotenv
from supabase import create_client
from tqdm import tqdm


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_NAME = "deeser_songs"
PAGE_SIZE = 1000
CHUNK_SIZE = 450
UPSERT_BATCH_SIZE = 50
AUDIO_HTTP_TIMEOUT = 8
DEEZER_HTTP_TIMEOUT = 10


def create_supabase_client():
    load_dotenv(override=False)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not url or not key:
        raise EnvironmentError(
            "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"
        )

    return create_client(url, key)


def build_text_for_embedding(
    title: Optional[str], artist: Optional[str], album_name: Optional[str]
) -> str:
    values = [title or "", artist or "", album_name or ""]
    return " | ".join(value for value in values if value).strip()


def fetch_pending_rows(supabase, chunk_size: int) -> List[Dict]:
    pending: List[Dict] = []
    offset = 0

    while len(pending) < chunk_size:
        response = (
            supabase.table(TABLE_NAME)
            .select("id,track_id,title,artist,album_name,url,tempo")
            .order("id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            break

        for row in rows:
            if not row.get("url"):
                continue
            if row.get("tempo") is None:
                pending.append(row)
                if len(pending) >= chunk_size:
                    break

        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return pending


def get_fresh_preview_url(track_id: str, fallback_url: Optional[str]) -> Optional[str]:
    try:
        response = requests.get(
            f"https://api.deezer.com/track/{track_id}",
            timeout=DEEZER_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        preview = payload.get("preview")
        if preview:
            return preview
    except Exception:
        pass
    return fallback_url


def analyze_audio_preview(preview_url: str) -> Optional[Dict[str, float]]:
    temp_path: Optional[Path] = None
    y = None
    sr = None

    def clip01(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))

    def normalize(value: float, min_v: float, max_v: float) -> float:
        if max_v <= min_v:
            return 0.0
        return clip01((value - min_v) / (max_v - min_v))

    try:
        audio_resp = requests.get(preview_url, timeout=AUDIO_HTTP_TIMEOUT)
        audio_resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_resp.content)
            tmp.flush()
            temp_path = Path(tmp.name)

        y, sr = librosa.load(temp_path, sr=None, mono=True)
        if y is None or len(y) == 0:
            return None

        rms = librosa.feature.rms(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y=y)[0]
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        harmonic, percussive = librosa.effects.hpss(y)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo_value = float(np.atleast_1d(tempo).astype(float)[0])

        mean_rms = float(np.mean(rms))
        mean_zcr = float(np.mean(zcr))
        mean_flatness = float(np.mean(flatness))
        mean_rolloff = float(np.mean(rolloff))
        mean_centroid = float(np.mean(centroid))

        energy = clip01(normalize(mean_rms, 0.01, 0.35))
        valence = clip01(
            0.7 * normalize(mean_centroid, 800.0, 5000.0)
            + 0.3 * normalize(tempo_value, 60.0, 180.0)
        )

        onset_std = float(np.std(onset_env))
        onset_mean = float(np.mean(onset_env)) if len(onset_env) else 0.0
        onset_stability = 1.0 - clip01(onset_std / (onset_mean + 1e-6))
        tempo_sweet_spot = 1.0 - min(abs(tempo_value - 120.0) / 120.0, 1.0)
        danceability = clip01(
            0.45 * onset_stability
            + 0.35 * tempo_sweet_spot
            + 0.20 * (1.0 - normalize(mean_zcr, 0.02, 0.25))
        )

        chroma_mean = np.mean(chroma, axis=1)
        key_index = int(np.argmax(chroma_mean))
        major_template = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1], dtype=float)
        minor_template = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0], dtype=float)
        major_score = float(np.dot(chroma_mean, np.roll(major_template, key_index)))
        minor_score = float(np.dot(chroma_mean, np.roll(minor_template, key_index)))
        mode = int(1 if major_score >= minor_score else 0)

        harmonic_energy = float(np.mean(np.abs(harmonic)))
        percussive_energy = float(np.mean(np.abs(percussive)))
        harmonic_ratio = harmonic_energy / (harmonic_energy + percussive_energy + 1e-6)
        acousticness = clip01(
            0.55 * harmonic_ratio
            + 0.25 * (1.0 - normalize(mean_rolloff, 1500.0, 8000.0))
            + 0.20 * (1.0 - normalize(mean_flatness, 0.02, 0.40))
        )

        speechiness = clip01(
            0.6 * normalize(mean_zcr, 0.02, 0.25)
            + 0.4 * normalize(mean_flatness, 0.02, 0.40)
        )
        instrumentalness = clip01(0.7 * (1.0 - speechiness) + 0.3 * harmonic_ratio)

        contrast_var = float(np.mean(np.var(contrast, axis=1)))
        liveness = clip01(normalize(contrast_var, 2.0, 40.0))

        brightness = mean_centroid

        return {
            "tempo": tempo_value,
            "energy": energy,
            "brightness": brightness,
            "valence": valence,
            "danceability": danceability,
            "key": key_index,
            "mode": mode,
            "acousticness": acousticness,
            "instrumentalness": instrumentalness,
            "liveness": liveness,
            "speechiness": speechiness,
        }
    except Exception:
        return None
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if y is not None or sr is not None:
            del y, sr
        gc.collect()


def flush_upsert_batch(supabase, rows: List[Dict]) -> None:
    if not rows:
        return
    supabase.table(TABLE_NAME).upsert(rows, on_conflict="track_id").execute()


def run() -> None:
    chunk_size = int(os.getenv("CHUNK_SIZE", str(CHUNK_SIZE)))
    supabase = create_supabase_client()

    pending_rows = fetch_pending_rows(supabase, chunk_size=chunk_size)
    if not pending_rows:
        log.info("No pending rows left to enrich in deeser_songs.")
        return

    first_id = pending_rows[0]["id"]
    last_id = pending_rows[-1]["id"]
    log.info(
        f"Processing chunk size: {len(pending_rows)} (id range {first_id} -> {last_id})"
    )

    success = 0
    failed = 0
    upsert_buffer: List[Dict] = []

    try:
        for row in tqdm(
            pending_rows, total=len(pending_rows), desc="Librosa Enrich", unit="song"
        ):
            preview_url = get_fresh_preview_url(row["track_id"], row.get("url"))
            if not preview_url:
                failed += 1
                continue

            features = analyze_audio_preview(preview_url)
            if not features:
                failed += 1
                continue

            upsert_buffer.append(
                {
                    "track_id": row["track_id"],
                    "title": row.get("title"),
                    "artist": row.get("artist"),
                    "album_name": row.get("album_name"),
                    "tempo": features["tempo"],
                    "energy": features["energy"],
                    "brightness": features["brightness"],
                    "valence": features["valence"],
                    "danceability": features["danceability"],
                    "key": features["key"],
                    "mode": features["mode"],
                    "acousticness": features["acousticness"],
                    "instrumentalness": features["instrumentalness"],
                    "liveness": features["liveness"],
                    "speechiness": features["speechiness"],
                    "url": preview_url,
                    "text_for_embedding": build_text_for_embedding(
                        row.get("title"), row.get("artist"), row.get("album_name")
                    ),
                }
            )
            success += 1

            if len(upsert_buffer) >= UPSERT_BATCH_SIZE:
                flush_upsert_batch(supabase, upsert_buffer)
                upsert_buffer.clear()
    except KeyboardInterrupt:
        log.warning(
            "Interrupted by user. Flushing completed rows in buffer before exit..."
        )
        if upsert_buffer:
            flush_upsert_batch(supabase, upsert_buffer)
            upsert_buffer.clear()
        raise

    if upsert_buffer:
        flush_upsert_batch(supabase, upsert_buffer)

    log.info(
        f"Chunk complete. success={success}, failed={failed}, requested={len(pending_rows)}"
    )


if __name__ == "__main__":
    run()
