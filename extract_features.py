# =============================================================================
# Emotion-Aware Playlist Generator — Phase 1: Spotify Feature Extraction
# =============================================================================
# requirements:  pip install requests pandas python-dotenv supabase
# =============================================================================

import os
import time
import base64
import logging
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv
from requests.exceptions import HTTPError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL    = "https://api.spotify.com/v1"
TOKEN_URL   = "https://accounts.spotify.com/api/token"
OUTPUT_FILE = Path(__file__).parent / "data" / "spotify_raw_features.csv"
BATCH_SIZE  = 100
SUPABASE_BATCH_SIZE = 500

AUDIO_KEYS = [
    "valence", "energy", "danceability", "tempo", "key", "mode",
    "acousticness", "instrumentalness", "liveness", "speechiness",
]

DEFAULT_PLAYLIST_IDS = [
    "37i9dQZF1DXcBWIGoYBM5M",  # Today's Top Hits
    "37i9dQZF1DX4WYpdVIPcm4",  # Mood Booster
    "37i9dQZF1DWZeKCadgRdKQ",  # Deep Focus
    "37i9dQZF1DX7qK8ma5wIL6",  # Sad Covers
    "37i9dQZF1DX76Wlfdnj7Bg",  # Workout
]


# ---------------------------------------------------------------------------
# Step 0 — Get a Bearer token (Client Credentials — no user login needed)
# ---------------------------------------------------------------------------
def get_token() -> str:
    """
    Fetches a fresh OAuth2 Bearer token from Spotify using the
    Client Credentials flow. Token is valid for 1 hour.
    Reads SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET from .env
    """
    load_dotenv(override=True)
    client_id     = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        raise EnvironmentError(
            "SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env"
        )

    b64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    log.info("Bearer token obtained from Spotify.")
    return token


# ---------------------------------------------------------------------------
# Step 1 — Raw HTTP GET helper (mirrors the JS fetchWebApi snippet)
# ---------------------------------------------------------------------------
def api_get(path: str, token: str, params: dict = None) -> dict:
    """
    GET https://api.spotify.com/v1/<path>
    Handles rate-limiting (429) with automatic retry.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url     = f"{BASE_URL}/{path}"

    for attempt in range(1, 4):
        r = requests.get(url, headers=headers, params=params, timeout=15)

        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 5))
            log.warning(f"Rate limited — waiting {wait}s (attempt {attempt}/3).")
            time.sleep(wait)
            continue

        if r.status_code == 403:
            log.warning(f"403 on '{path}' — endpoint likely deprecated for this app.")
            return {}

        if r.status_code == 401:
            raise PermissionError("401 Unauthorized — token is invalid or expired.")

        r.raise_for_status()
        return r.json()

    raise RuntimeError(f"'{path}' failed after 3 retries.")


# ---------------------------------------------------------------------------
# Step 2 — Fetch all tracks from a playlist (handles pagination)
# ---------------------------------------------------------------------------
def get_tracks(playlist_id: str, token: str) -> list[dict]:
    """
    Returns a list of track metadata dicts:
    track_id, track_name, artist_name, album_name, popularity
    """
    results = []
    offset  = 0
    total   = None

    log.info(f"Fetching tracks — playlist: {playlist_id}")

    while True:
        try:
            data = api_get(
                f"playlists/{playlist_id}/tracks",
                token,
                params={"limit": 100, "offset": offset, "market": "US"},
            )
        except HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            log.error(f"Playlist fetch failed with HTTP {status_code} for playlist_id={playlist_id}")
            return []

        if not data:
            log.error("Empty response. Verify playlist ID and credentials.")
            break

        if total is None:
            total = data.get("total", 0)
            log.info(f"Total tracks in playlist: {total}")

        for item in data.get("items", []):
            t = item.get("track")
            if not t or not t.get("id"):
                continue  # skip local/null entries
            results.append({
                "track_id":    t["id"],
                "track_name":  t["name"],
                "artist_name": t["artists"][0]["name"] if t.get("artists") else "Unknown",
                "album_name":  t["album"]["name"],
                "popularity":  t.get("popularity", 0),
            })

        fetched = offset + len(data.get("items", []))
        log.info(f"  Progress: {fetched}/{total}")

        if not data.get("next"):
            break
        offset += 100

    log.info(f"Tracks extracted: {len(results)}")
    return results


def discover_accessible_playlist_id(token: str, query: str = "top hits") -> str | None:
    """
    Find a public playlist that is accessible with the current token.
    Spotify search can return null items; this function filters those out.
    """
    log.info(f"Discovering accessible playlist via search query: '{query}'")
    data = api_get(
        "search",
        token,
        params={"q": query, "type": "playlist", "limit": 20, "market": "US"},
    )

    playlists = (data.get("playlists") or {}).get("items") or []
    candidate_ids = [item.get("id") for item in playlists if item and item.get("id")]

    for pid in candidate_ids:
        tracks = get_tracks(pid, token)
        if tracks:
            log.info(f"Using discovered playlist_id={pid} (tracks={len(tracks)})")
            return pid

    log.error("No accessible playlist found from search results.")
    return None


def discover_accessible_playlist_ids(
    token: str,
    query: str,
    max_results: int = 30,
    page_limit: int = 50,
) -> list[str]:
    """
    Discover multiple accessible playlist IDs from search results.
    Filters null items and validates each playlist by attempting track fetch.
    """
    discovered: list[str] = []
    seen: set[str] = set()

    log.info(f"Discovering more playlists with query='{query}'")
    for offset in range(0, max_results, page_limit):
        data = api_get(
            "search",
            token,
            params={
                "q": query,
                "type": "playlist",
                "limit": min(page_limit, max_results - offset),
                "offset": offset,
                "market": "US",
            },
        )

        playlists = (data.get("playlists") or {}).get("items") or []
        candidate_ids = [item.get("id") for item in playlists if item and item.get("id")]

        for pid in candidate_ids:
            if pid in seen:
                continue
            seen.add(pid)
            tracks = get_tracks(pid, token)
            if tracks:
                discovered.append(pid)
            if len(discovered) >= max_results:
                return discovered

    return discovered


# ---------------------------------------------------------------------------
# Step 3 — Fetch audio features in batches of 100
# ---------------------------------------------------------------------------
def get_audio_features(track_ids: list[str], token: str) -> dict[str, dict]:
    """
    Returns a dict: {track_id: {valence, energy, danceability, ...}}
    Returns {} if the endpoint is blocked (deprecated for new Spotify apps).
    """
    feature_map = {}
    batches = [track_ids[i: i + BATCH_SIZE] for i in range(0, len(track_ids), BATCH_SIZE)]

    log.info(f"Fetching audio features — {len(track_ids)} tracks, {len(batches)} batch(es).")

    for i, batch in enumerate(batches, 1):
        data = api_get("audio-features", token, params={"ids": ",".join(batch)})

        if not data:
            log.warning(
                "audio-features is unavailable (Spotify deprecated it for apps "
                "created after Nov 27, 2024). A metadata-only CSV will be saved."
            )
            return {}

        for fs in data.get("audio_features", []):
            if fs:
                feature_map[fs["id"]] = {k: fs.get(k) for k in AUDIO_KEYS}

        log.info(f"  Batch {i}/{len(batches)} done.")

    log.info(f"Audio features retrieved: {len(feature_map)} tracks.")
    return feature_map


# ---------------------------------------------------------------------------
# Step 4 — Merge, clean, return DataFrame
# ---------------------------------------------------------------------------
def extract_playlist_features(playlist_id: str) -> pd.DataFrame:
    """
    Full pipeline: auth → tracks → audio features → merge → clean DataFrame.
    """
    token  = get_token()
    tracks = get_tracks(playlist_id, token)

    if not tracks:
        fallback_id = discover_accessible_playlist_id(token)
        if fallback_id:
            tracks = get_tracks(fallback_id, token)

    if not tracks:
        log.warning("No tracks found — returning empty DataFrame.")
        return pd.DataFrame()

    features = get_audio_features([t["track_id"] for t in tracks], token)

    if features:
        rows   = [{**t, **features[t["track_id"]]} for t in tracks if t["track_id"] in features]
        df     = pd.DataFrame(rows)
        before = len(df)
        df.dropna(subset=AUDIO_KEYS, inplace=True)
        if len(df) < before:
            log.info(f"Dropped {before - len(df)} rows with null audio features.")
    else:
        log.warning("Saving metadata-only CSV (no audio features).")
        df = pd.DataFrame(tracks)

    df.reset_index(drop=True, inplace=True)
    log.info(f"Final DataFrame shape: {df.shape}")
    return df


def extract_multiple_playlists_features(
    playlist_ids: list[str],
    target_tracks: int = 1500,
) -> pd.DataFrame:
    """
    Multi-playlist pipeline with strict deduplication by track_id.
    Pulls tracks from provided playlist IDs first, then discovers additional
    accessible playlists until target_tracks is reached or candidates are exhausted.
    """
    token = get_token()
    all_tracks: list[dict] = []
    seen_track_ids: set[str] = set()
    used_playlist_ids: set[str] = set()

    def ingest_playlist(pid: str) -> None:
        if pid in used_playlist_ids:
            return
        used_playlist_ids.add(pid)

        tracks = get_tracks(pid, token)
        if not tracks:
            return

        before = len(seen_track_ids)
        for track in tracks:
            tid = track["track_id"]
            if tid in seen_track_ids:
                continue
            seen_track_ids.add(tid)
            all_tracks.append(track)

        added = len(seen_track_ids) - before
        log.info(
            f"Playlist {pid}: added {added} unique tracks "
            f"(total unique={len(seen_track_ids)})"
        )

    # 1) Ingest user-provided playlists
    for pid in playlist_ids:
        if len(seen_track_ids) >= target_tracks:
            break
        ingest_playlist(pid)

    # 2) Discover additional playlists if target not reached
    if len(seen_track_ids) < target_tracks:
        seed_queries = [
            "top hits",
            "happy",
            "sad",
            "focus",
            "workout",
            "chill",
            "party",
            "indie",
            "rock",
            "pop",
        ]
        for query in seed_queries:
            if len(seen_track_ids) >= target_tracks:
                break
            candidate_ids = discover_accessible_playlist_ids(
                token,
                query=query,
                max_results=25,
                page_limit=25,
            )
            for pid in candidate_ids:
                if len(seen_track_ids) >= target_tracks:
                    break
                ingest_playlist(pid)

    if not all_tracks:
        log.warning("No tracks found — returning empty DataFrame.")
        return pd.DataFrame()

    # Optional audio features (if available for your app)
    features = get_audio_features([t["track_id"] for t in all_tracks], token)

    if features:
        rows = [{**t, **features[t["track_id"]]} for t in all_tracks if t["track_id"] in features]
        df = pd.DataFrame(rows)
        before = len(df)
        df.dropna(subset=AUDIO_KEYS, inplace=True)
        if len(df) < before:
            log.info(f"Dropped {before - len(df)} rows with null audio features.")
    else:
        log.warning("Saving metadata-only CSV (no audio features).")
        df = pd.DataFrame(all_tracks)

    # Strict final dedupe guard
    before = len(df)
    df.drop_duplicates(subset=["track_id"], inplace=True)
    if len(df) < before:
        log.info(f"Removed {before - len(df)} duplicate rows by track_id.")

    if len(df) >= target_tracks:
        df = df.head(target_tracks)
        log.info(f"Trimmed to target_tracks={target_tracks}")
    else:
        log.warning(
            f"Could not reach target_tracks={target_tracks}. "
            f"Collected {len(df)} unique tracks."
        )

    df.reset_index(drop=True, inplace=True)
    log.info(f"Final DataFrame shape: {df.shape}")
    return df


# ---------------------------------------------------------------------------
# Step 5 — Save to CSV
# ---------------------------------------------------------------------------
def save_csv(df: pd.DataFrame, path: Path = OUTPUT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info(f"Saved: {path.resolve()}")


def upsert_to_supabase(df: pd.DataFrame) -> None:
    """
    Optional sync to Supabase.

    Required .env variables:
      - SUPABASE_URL
      - SUPABASE_SERVICE_ROLE_KEY  (recommended for server-side ingest)
    Optional:
      - SUPABASE_TABLE (default: spotify_raw_features)

    Upserts by track_id to guarantee no duplicate rows.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    supabase_table = os.getenv("SUPABASE_TABLE", "spotify_raw_features").strip()

    if not supabase_url or not supabase_key:
        log.info("Supabase credentials not set. Skipping Supabase sync.")
        return

    try:
        from supabase import create_client
    except ImportError:
        log.error("'supabase' package is not installed. Run: pip install supabase")
        return

    client = create_client(supabase_url, supabase_key)

    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    if not records:
        log.warning("No rows to sync to Supabase.")
        return

    total = len(records)
    log.info(f"Syncing {total} rows to Supabase table '{supabase_table}'...")

    try:
        for start in range(0, total, SUPABASE_BATCH_SIZE):
            end = min(start + SUPABASE_BATCH_SIZE, total)
            batch = records[start:end]
            client.table(supabase_table).upsert(batch, on_conflict="track_id").execute()
            log.info(f"  Supabase upserted rows {start + 1}-{end}/{total}")
    except Exception as e:
        error_text = str(e)
        if "PGRST205" in error_text or "schema cache" in error_text:
            log.error(
                "Supabase table not found. Run supabase/schema.sql in Supabase SQL Editor, "
                "then rerun this script."
            )
            return
        log.error(f"Supabase sync failed: {error_text}")
        return

    log.info("Supabase sync complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_dotenv(override=True)

    playlist_ids_env = os.getenv("SPOTIFY_PLAYLIST_IDS", "").strip()
    if playlist_ids_env:
        playlist_ids = [pid.strip() for pid in playlist_ids_env.split(",") if pid.strip()]
    else:
        playlist_ids = DEFAULT_PLAYLIST_IDS

    target_tracks = int(os.getenv("TARGET_TRACKS", "1500"))

    log.info("=" * 60)
    log.info("  Emotion-Aware Playlist Generator — Feature Extraction")
    log.info("=" * 60)

    df = extract_multiple_playlists_features(playlist_ids, target_tracks=target_tracks)

    if df.empty:
        log.error("No data extracted. Check your .env credentials and playlist ID.")
    else:
        log.info(f"\nSample:\n{df.head(3).to_string()}")
        save_csv(df)
        upsert_to_supabase(df)
        log.info("Phase 1 complete.")
