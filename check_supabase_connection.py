import socket
from urllib.parse import urlparse

from dotenv import load_dotenv
import os
from supabase import create_client


def main() -> None:
    load_dotenv(override=False)

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    table = os.getenv("SUPABASE_TARGET_TABLE", "").strip() or "deeser_songs"

    print("env.supabase_url_present =", bool(url))
    print("env.service_role_key_present =", bool(key))
    print("target_table =", table)

    if not url or not key:
        print("status = missing_env")
        return

    parsed = urlparse(url)
    host = parsed.hostname

    print("url.scheme =", parsed.scheme or "<missing>")
    print("url.host_present =", bool(host))

    if not host:
        print("status = invalid_url")
        return

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({info[4][0] for info in infos})
        print("dns = ok")
        print("resolved_address_count =", len(addresses))
    except Exception as exc:
        print("dns = failed")
        print("dns_error_type =", type(exc).__name__)
        print("dns_error =", str(exc))
        return

    try:
        supabase = create_client(url, key)
        response = supabase.table(table).select("track_id", count="exact").limit(1).execute()
        row_count = response.count if response.count is not None else "unknown"
        rows_returned = len(response.data or [])
        print("auth = ok")
        print("query = ok")
        print("rows_returned =", rows_returned)
        print("table_count =", row_count)
        print("status = success")
    except Exception as exc:
        print("auth_or_query = failed")
        print("query_error_type =", type(exc).__name__)
        print("query_error =", str(exc))


if __name__ == "__main__":
    main()
