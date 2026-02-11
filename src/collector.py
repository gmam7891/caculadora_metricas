import os
import time
import argparse
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv

from twitch_client import TwitchClient
import storage

def read_channels_file(path: str) -> List[str]:
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s.lower())
    seen = set()
    uniq = []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Coletor de viewer_count (Twitch API) para calcular avg/peak 30d localmente."
    )
    parser.add_argument("--channels-file", default="streamers.txt", help="Arquivo com logins (1 por linha).")
    parser.add_argument("--interval", type=int, default=120, help="Intervalo em segundos entre coletas.")
    parser.add_argument("--db", default=os.getenv("APP_DB_PATH", "./data/app.db"), help="Caminho do SQLite.")
    args = parser.parse_args()

    client_id = os.getenv("TWITCH_CLIENT_ID", "")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("Defina TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET no .env")

    channels = read_channels_file(args.channels_file)
    if not channels:
        raise SystemExit("Nenhum canal encontrado no arquivo.")

    tc = TwitchClient(client_id, client_secret)
    conn = storage.connect(args.db)
    storage.init_db(conn)

    print(f"[collector] channels={len(channels)} interval={args.interval}s db={args.db}")

    while True:
        ts = datetime.now(timezone.utc).isoformat()

        try:
            live_map = tc.get_streams_by_logins(channels)  # only live streams returned
        except Exception as e:
            print(f"[collector] erro ao buscar streams: {e}")
            time.sleep(args.interval)
            continue

        rows = []
        for login in channels:
            s = live_map.get(login)
            if s:
                rows.append((
                    ts,
                    login,
                    1,
                    int(s.get("viewer_count", 0)),
                    s.get("game_name"),
                    s.get("title"),
                    s.get("started_at"),
                    s.get("id"),
                ))
            else:
                rows.append((ts, login, 0, 0, None, None, None, None))

        storage.insert_stream_samples(conn, rows)
        print(f"[collector] {ts} saved {len(rows)} samples (live={len(live_map)})")

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
