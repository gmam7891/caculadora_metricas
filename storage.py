import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    
    # Tabela de amostras LIVE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS live_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            viewers INTEGER NOT NULL,
            game_id TEXT,
            game_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de cache VOD
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vod_summaries (
            channel TEXT PRIMARY KEY,
            vod_count INTEGER,
            avg_vod_views REAL,
            median_vod_views REAL,
            views_per_hour REAL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_live_samples_channel ON live_samples(channel)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_live_samples_timestamp ON live_samples(timestamp)")
    
    conn.commit()
    print("✅ Banco de dados inicializado com sucesso!")

def save_live_sample(conn: sqlite3.Connection, channel: str, viewers: int, game_id: str = None, game_name: str = None):
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO live_samples (channel, viewers, game_id, game_name)
        VALUES (?, ?, ?, ?)
    ''', (channel.lower(), viewers, game_id, game_name))
    conn.commit()

def get_stream_stats_30d(conn: sqlite3.Connection, channel: str) -> Dict:
    cur = conn.cursor()
    channel = channel.lower()
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    cur.execute('''
        SELECT 
            COUNT(*) as live_samples_30d,
            AVG(viewers) as avg_viewers_30d,
            MAX(viewers) as peak_viewers_30d,
            MAX(timestamp) as last_any_sample_utc
        FROM live_samples 
        WHERE channel = ? AND timestamp >= ?
    ''', (channel, cutoff))
    
    row = cur.fetchone()
    return {
        "live_samples_30d": row["live_samples_30d"] if row else 0,
        "avg_viewers_30d": round(float(row["avg_viewers_30d"])) if row and row["avg_viewers_30d"] else None,
        "peak_viewers_30d": row["peak_viewers_30d"] if row else None,
        "last_any_sample_utc": row["last_any_sample_utc"] if row else None
    }

def upsert_vod_summary(conn: sqlite3.Connection, channel: str, vod_count: int, avg_vod_views: float, 
                       median_vod_views: float, views_per_hour: float):
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO vod_summaries 
        (channel, vod_count, avg_vod_views, median_vod_views, views_per_hour, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (channel.lower(), vod_count, avg_vod_views, median_vod_views, views_per_hour))
    conn.commit()

def get_cached_vod_summary(conn: sqlite3.Connection, channel: str, max_age_hours: int = 12) -> Optional[Dict]:
    cur = conn.cursor()
    channel = channel.lower()
    cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()
    
    cur.execute('''
        SELECT * FROM vod_summaries 
        WHERE channel = ? AND updated_at >= ?
    ''', (channel, cutoff))
    
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)