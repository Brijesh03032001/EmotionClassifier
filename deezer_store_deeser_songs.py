import logging
import os
import time
from typing import Dict, List, Optional, Set

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

DEEZER_BASE = "https://api.deezer.com"
DEEZER_TIMEOUT = 10
DEEZER_SLEEP_SECONDS = 0.25
READ_PAGE_SIZE = 1000
UPSERT_BATCH_SIZE = 100


def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        return int(value)
    except ValueError:
        return default


def create_supabase_client_and_table() -> tuple:
    load_dotenv(override=False)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table = os.getenv("SUPABASE_TARGET_TABLE", "").strip() or "deeser_songs"

    if not url or not key:
        raise EnvironmentError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")

    return create_client(url, key), table


def deezer_get(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    try:
        response = requests.get(f"{DEEZER_BASE}/{endpoint}", params=params or {}, timeout=DEEZER_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        log.warning(f"Deezer API failed endpoint='{endpoint}' params={params}: {exc}")
        payload = None

    time.sleep(DEEZER_SLEEP_SECONDS)
    return payload


def get_existing_track_ids(supabase, table_name: str) -> Set[str]:
    existing_ids: Set[str] = set()
    offset = 0

    while True:
        try:
            response = (
                supabase.table(table_name)
                .select("track_id")
                .range(offset, offset + READ_PAGE_SIZE - 1)
                .execute()
            )
        except Exception as exc:
            error_text = str(exc)
            if "PGRST205" in error_text or "schema cache" in error_text:
                raise RuntimeError(
                    "Table 'deeser_songs' is missing in Supabase. "
                    "Run the SQL in supabase/schema.sql first, then re-run this script."
                ) from exc
            raise
        rows = response.data or []
        if not rows:
            break

        for row in rows:
            track_id = row.get("track_id")
            if track_id:
                existing_ids.add(str(track_id))

        if len(rows) < READ_PAGE_SIZE:
            break
        offset += READ_PAGE_SIZE

    return existing_ids


def normalize_song(item: Dict) -> Optional[Dict]:
    track_id = item.get("id")
    title = item.get("title") or item.get("title_short")
    artist = (item.get("artist") or {}).get("name")
    album_name = (item.get("album") or {}).get("title")
    popularity = item.get("rank")
    url = item.get("preview")
    deezer_link = item.get("link")

    if not track_id or not title or not artist or not url:
        return None

    return {
        "track_id": str(track_id),
        "title": title,
        "artist": artist,
        "album_name": album_name,
        "popularity": popularity,
        "url": url,
        "deezer_link": deezer_link,
    }


def collect_deezer_songs(target_count: int, existing_ids: Set[str]) -> List[Dict]:
    collected: List[Dict] = []
    seen: Set[str] = set(existing_ids)

    def ingest(items: List[Dict]) -> None:
        for item in items:
            if len(collected) >= target_count:
                return
            song = normalize_song(item)
            if not song:
                continue
            if song["track_id"] in seen:
                continue
            collected.append(song)
            seen.add(song["track_id"])

    chart_index = 0
    chart_limit = 100
    while len(collected) < target_count:
        payload = deezer_get("chart/0/tracks", params={"index": chart_index, "limit": chart_limit})
        if not payload:
            break
        items = payload.get("data", [])
        if not items:
            break
        ingest(items)
        if len(items) < chart_limit:
            break
        chart_index += chart_limit

    queries = [
        "top hits",
        "viral",
        "pop",
        "rock",
        "hip hop",
        "indie",
        "electronic",
        "house",
        "afrobeats",
        "k-pop",
        "latin",
        "jazz",
        "classical",
        "bollywood",
        "workout",
        "chill",
        "focus",
        "happy",
        "sad",
        "love",
        "new music",
        "trending",
        "global",
        "party",
        "road trip",
        "lofi",
        "rnb",
        "metal",
        "country",
        "reggaeton",
    ]

    for query in queries:
        if len(collected) >= target_count:
            break
        index = 0
        limit = 100
        while len(collected) < target_count:
            payload = deezer_get("search", params={"q": query, "index": index, "limit": limit})
            if not payload:
                break
            items = payload.get("data", [])
            if not items:
                break
            ingest(items)
            if len(items) < limit:
                break
            index += limit

    if len(collected) < target_count:
        alpha_queries = [chr(code) for code in range(ord("a"), ord("z") + 1)]
        for query in alpha_queries:
            if len(collected) >= target_count:
                break
            index = 0
            limit = 100
            while len(collected) < target_count:
                payload = deezer_get("search", params={"q": query, "index": index, "limit": limit})
                if not payload:
                    break
                items = payload.get("data", [])
                if not items:
                    break
                ingest(items)
                if len(items) < limit:
                    break
                index += limit

    return collected


def upsert_in_batches(supabase, table_name: str, rows: List[Dict]) -> int:
    if not rows:
        return 0

    inserted = 0
    for start in tqdm(range(0, len(rows), UPSERT_BATCH_SIZE), desc="Supabase Upsert", unit="batch"):
        batch = rows[start : start + UPSERT_BATCH_SIZE]
        supabase.table(table_name).upsert(batch, on_conflict="track_id").execute()
        inserted += len(batch)

    return inserted


def run() -> None:
    supabase, table_name = create_supabase_client_and_table()
    target_count = get_env_int("TARGET_TRACKS", 1500)

    log.info(f"Using target table: {table_name}")
    log.info("Reading existing track_ids for restart-safe dedupe...")
    existing_ids = get_existing_track_ids(supabase, table_name)
    log.info(f"Existing rows in {table_name}: {len(existing_ids)}")

    log.info(f"Collecting {target_count}+ Deezer songs with url...")
    songs = collect_deezer_songs(target_count=target_count, existing_ids=existing_ids)
    if not songs:
        log.error("No songs collected from Deezer.")
        return

    log.info(f"Collected new songs: {len(songs)}")
    inserted = upsert_in_batches(supabase, table_name, songs)
    log.info(f"Completed. Upserted rows: {inserted}")


if __name__ == "__main__":
    run()
