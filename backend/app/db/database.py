import sqlite3
import os

DB_PATH = "data/test_app.db" if os.environ.get("TESTING") == "1" else "data/app.db"

def get_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            thread_id TEXT UNIQUE NOT NULL,
            tool TEXT DEFAULT 'Veo',
            thumbnail_url TEXT,
            status TEXT DEFAULT 'IDLE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            final_video_url TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            prompt_id TEXT NOT NULL,
            shot_id TEXT NOT NULL,
            sequence_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            external_job_id TEXT,
            video_url TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            submitted_at DATETIME,
            completed_at DATETIME,
            duration_seconds REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_project ON video_jobs(project_id)")
    try:
        conn.execute("ALTER TABLE video_jobs ADD COLUMN duration_seconds REAL")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
