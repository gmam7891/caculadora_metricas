import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

def connect(db_path: str) -> sqlite3.Connection:
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS stream_samples (
          ts_utc TEXT NOT NULL,
          user_login TEXT NOT NULL,
          is_live INTEGER NOT NULL,
          viewer_count INTEGER NOT NULL,
          game_name TEXT,
          title TEXT,
          started_at TEXT,
          stream_id TEXT
        );
        '''
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_login_ts ON stream_samples(user_login, ts_utc);")

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS vod_summary_cache (
          user_login TEXT PRIMARY KEY,
          updated_at_utc TEXT NOT NULL,
          vod_count INTEGER,
          avg_vod_views REAL,
          median_vod_views REAL,
          views_per_hour REAL
        );
        '''
    )
    conn.commit()

def insert_stream_samples(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]]) -> None:
    if not rows:
        return
    conn.executemany(
        '''
        INSERT INTO stream_samples
        (ts_utc, user_login, is_live, viewer_count, game_name, title, started_at, stream_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        ''',
        rows,
    )
    conn.commit()

def _since_utc(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()

def get_stream_stats_30d(conn: sqlite3.Connection, user_login: str) -> Dict[str, Any]:
    since = _since_utc(30)
    cur = conn.cursor()

    cur.execute(
        '''
        SELECT
          COUNT(*) as live_samples,
          AVG(viewer_count) as avg_viewers,
          MAX(viewer_count) as peak_viewers,
          MAX(ts_utc) as last_live_sample
        FROM stream_samples
        WHERE user_login = ?
          AND ts_utc >= ?
          AND is_live = 1;
        ''',
        (user_login.lower(), since),
    )
    row = cur.fetchone()
    live_samples, avg_viewers, peak_viewers, last_live_sample = row if row else (0, None, None, None)

    cur.execute(
        '''
        SELECT MAX(ts_utc) FROM stream_samples
        WHERE user_login = ?;
        ''',
        (user_login.lower(),),
    )
    last_any = cur.fetchone()[0]

    return {
        "live_samples_30d": int(live_samples or 0),
        "avg_viewers_30d": float(avg_viewers) if avg_viewers is not None else None,
        "peak_viewers_30d": int(peak_viewers) if peak_viewers is not None else None,
        "last_live_sample_utc": last_live_sample,
        "last_any_sample_utc": last_any,
    }

def get_cached_vod_summary(conn: sqlite3.Connection, user_login: str, max_age_hours: int = 12) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT updated_at_utc, vod_count, avg_vod_views, median_vod_views, views_per_hour
        FROM vod_summary_cache
        WHERE user_login = ?;
        ''',
        (user_login.lower(),),
    )
    row = cur.fetchone()
    if not row:
        return None

    updated_at = datetime.fromisoformat(row[0])
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - updated_at > timedelta(hours=max_age_hours):
        return None

    return {
        "updated_at_utc": row[0],
        "vod_count": row[1],
        "avg_vod_views": row[2],
        "median_vod_views": row[3],
        "views_per_hour": row[4],
    }

def upsert_vod_summary(conn: sqlite3.Connection, user_login: str, vod_count: int, avg_vod_views: float, median_vod_views: float, views_per_hour: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        '''
        INSERT INTO vod_summary_cache (user_login, updated_at_utc, vod_count, avg_vod_views, median_vod_views, views_per_hour)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_login) DO UPDATE SET
          updated_at_utc=excluded.updated_at_utc,
          vod_count=excluded.vod_count,
          avg_vod_views=excluded.avg_vod_views,
          median_vod_views=excluded.median_vod_views,
          views_per_hour=excluded.views_per_hour;
        ''',
        (user_login.lower(), now, int(vod_count), float(avg_vod_views), float(median_vod_views), float(views_per_hour)),
    )
    conn.commit()
