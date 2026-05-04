import tempfile
import csv
from pathlib import Path

import librosa
import matplotlib.pyplot as plt
import numpy as np
import requests


SONGS = ["Shape of You", "Blinding Lights"]
PLOT_DIR = Path("data") / "deezer_plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)
CSV_OUTPUT = Path("data") / "deezer_two_songs_supabase_schema.csv"

# Supabase `songs` schema-compatible columns
CSV_COLUMNS = [
    "track_id",
    "title",
    "artist",
    "valence",
    "energy",
    "tempo",
    "danceability",
    "key",
    "mode",
    "acousticness",
    "instrumentalness",
    "liveness",
    "speechiness",
    "popularity",
    "album_name",
]


def get_track_from_deezer(song_name: str) -> dict | None:
    """Search Deezer and return top matched track metadata."""
    response = requests.get(
        "https://api.deezer.com/search",
        params={"q": song_name},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json().get("data", [])

    if not data:
        return None

    top = data[0]
    return {
        "track_id": str(top.get("id")),
        "title": top.get("title"),
        "artist": (top.get("artist") or {}).get("name"),
        "album_name": (top.get("album") or {}).get("title"),
        "popularity": top.get("rank"),
        "preview_url": top.get("preview"),
    }


def download_preview(preview_url: str) -> Path:
    """Download preview MP3 to a temp file and return path."""
    audio_resp = requests.get(preview_url, timeout=30)
    audio_resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.write(audio_resp.content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def extract_temporal_features(audio_path: Path) -> dict:
    """Load audio and compute Spotify-like DSP proxies for songs schema columns."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)

    def clip01(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))

    def normalize(value: float, min_v: float, max_v: float) -> float:
        if max_v <= min_v:
            return 0.0
        return clip01((value - min_v) / (max_v - min_v))

    rms = librosa.feature.rms(y=y)[0]
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    flatness = librosa.feature.spectral_flatness(y=y)[0]
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    harmonic, percussive = librosa.effects.hpss(y)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_scalar = float(np.atleast_1d(tempo).astype(float)[0])
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)

    mean_rms = float(np.mean(rms))
    mean_zcr = float(np.mean(zcr))
    mean_flatness = float(np.mean(flatness))
    mean_rolloff = float(np.mean(rolloff))
    mean_centroid = float(np.mean(centroid))

energy = clip01(normalize(mean_rms, 0.01, 0.35))

    # Valence proxy from spectral brightness + tempo liveliness
    valence = clip01(
        0.7 * normalize(mean_centroid, 800.0, 5000.0)
        + 0.3 * normalize(tempo_scalar, 60.0, 180.0)
    )

    # Danceability proxy from beat/onset regularity + tempo range + low-noise voicing
    onset_std = float(np.std(onset_env))
    onset_mean = float(np.mean(onset_env)) if len(onset_env) else 0.0
    onset_stability = 1.0 - clip01(onset_std / (onset_mean + 1e-6))
    tempo_sweet_spot = 1.0 - min(abs(tempo_scalar - 120.0) / 120.0, 1.0)
    danceability = clip01(
        0.45 * onset_stability
        + 0.35 * tempo_sweet_spot
        + 0.20 * (1.0 - normalize(mean_zcr, 0.02, 0.25))
    )

    # Key estimate: strongest chroma class, Mode estimate via major/minor template fit
    chroma_mean = np.mean(chroma, axis=1)
    key_index = int(np.argmax(chroma_mean))
    major_template = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1], dtype=float)
    minor_template = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0], dtype=float)
    major_score = float(np.dot(chroma_mean, np.roll(major_template, key_index)))
    minor_score = float(np.dot(chroma_mean, np.roll(minor_template, key_index)))
    mode = int(1 if major_score >= minor_score else 0)

    # Acousticness proxy: harmonic dominance + low rolloff/flatness
    harmonic_energy = float(np.mean(np.abs(harmonic)))
    percussive_energy = float(np.mean(np.abs(percussive)))
    harmonic_ratio = harmonic_energy / (harmonic_energy + percussive_energy + 1e-6)
    acousticness = clip01(
        0.55 * harmonic_ratio
        + 0.25 * (1.0 - normalize(mean_rolloff, 1500.0, 8000.0))
        + 0.20 * (1.0 - normalize(mean_flatness, 0.02, 0.40))
    )

    # Speechiness proxy: high zcr + high flatness
    speechiness = clip01(
        0.6 * normalize(mean_zcr, 0.02, 0.25)
        + 0.4 * normalize(mean_flatness, 0.02, 0.40)
    )

    # Instrumentalness proxy: inverse of speechiness + harmonic texture
    instrumentalness = clip01(
        0.7 * (1.0 - speechiness) + 0.3 * harmonic_ratio
    )

    # Liveness proxy from frame-level spectral contrast variability
    contrast_var = float(np.mean(np.var(contrast, axis=1)))
    liveness = clip01(normalize(contrast_var, 2.0, 40.0))

    return {
        "y": y,
        "sr": sr,
        "rms": rms,
        "zcr": zcr,
        "tempo": tempo_scalar,
        "brightness": mean_centroid,
        "valence": valence,
        "energy": energy,
        "danceability": danceability,
        "key": key_index,
        "mode": mode,
        "acousticness": acousticness,
        "instrumentalness": instrumentalness,
        "liveness": liveness,
        "speechiness": speechiness,
        "duration_sec": len(y) / sr,
        "mean_rms": mean_rms,
        "mean_zcr": mean_zcr,
    }


def plot_rms(song_name: str, rms: np.ndarray, sr: int) -> None:
    """Plot RMS over time and save image under data/deezer_plots."""
    times = librosa.times_like(rms, sr=sr)

    plt.figure(figsize=(9, 4))
    plt.plot(times, rms)
    plt.title(f"RMS Energy - {song_name}")
    plt.xlabel("Time (s)")
    plt.ylabel("Energy")
    plt.tight_layout()

    safe_name = "_".join(song_name.lower().split())
    out_path = PLOT_DIR / f"{safe_name}_rms.png"
    plt.savefig(out_path, dpi=150)
    plt.close()

    print(f"Saved RMS plot: {out_path}")


def build_supabase_schema_row(track_info: dict, features: dict) -> dict:
    """
    Build one CSV row aligned to Supabase songs schema.
    Unknown features are kept as None for testing.
    """
    return {
        "track_id": track_info["track_id"],
        "title": track_info["title"],
        "artist": track_info["artist"],
        "valence": features["valence"],
        "energy": features["energy"],
        "tempo": features["tempo"],
        "danceability": features["danceability"],
        "key": features["key"],
        "mode": features["mode"],
        "acousticness": features["acousticness"],
        "instrumentalness": features["instrumentalness"],
        "liveness": features["liveness"],
        "speechiness": features["speechiness"],
        "popularity": track_info["popularity"],
        "album_name": track_info["album_name"],
    }


def write_csv(rows: list[dict]) -> None:
    CSV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUTPUT.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV: {CSV_OUTPUT} (rows={len(rows)})")


def main() -> None:
    output_rows: list[dict] = []

    for song in SONGS:
        print(f"\nProcessing: {song}")

        try:
            track_info = get_track_from_deezer(song)
        except Exception as exc:
            print(f"Search failed: {exc}")
            continue

        if not track_info:
            print("No preview found.")
            continue

        preview_url = track_info.get("preview_url")
        if not preview_url:
            print("No preview found.")
            continue

        print("Preview URL:", preview_url)

        temp_audio_path = None
        try:
            temp_audio_path = download_preview(preview_url)
            features = extract_temporal_features(temp_audio_path)

            print("Duration (seconds):", round(features["duration_sec"], 3))
            print("Mean RMS:", features["mean_rms"])
            print("Mean ZCR:", features["mean_zcr"])
            print("Tempo:", features["tempo"])
            print("Brightness:", features["brightness"])
            print("Valence:", features["valence"])
            print("Energy:", features["energy"])
            print("Danceability:", features["danceability"])
            print("Key:", features["key"], "Mode:", features["mode"])
            print("Acousticness:", features["acousticness"])
            print("Instrumentalness:", features["instrumentalness"])
            print("Liveness:", features["liveness"])
            print("Speechiness:", features["speechiness"])

            plot_rms(song, features["rms"], features["sr"])
            output_rows.append(build_supabase_schema_row(track_info, features))
        except Exception as exc:
            print(f"Audio analysis failed: {exc}")
        finally:
            if temp_audio_path and temp_audio_path.exists():
                temp_audio_path.unlink(missing_ok=True)

    write_csv(output_rows)


if __name__ == "__main__":
    main()
