import sqlite3
import secrets
import string
from datetime import datetime, timedelta, date

DB_PATH = "keys.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS keys (id INTEGER PRIMARY KEY AUTOINCREMENT, key_plain TEXT NOT NULL, device_fp TEXT NOT NULL, game TEXT NOT NULL, duration_hours INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, uses INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT UNIQUE NOT NULL, device_fp TEXT NOT NULL, game TEXT NOT NULL, duration INTEGER NOT NULL, step INTEGER DEFAULT 1, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL, verified_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS daily_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fp TEXT NOT NULL, day TEXT NOT NULL, count INTEGER DEFAULT 0, UNIQUE(device_fp, day))")
    conn.commit()
    conn.close()


def generate_session_id():
    return secrets.token_urlsafe(24)


def create_session(device_fp, game, duration):
    init_db()
    session_id = generate_session_id()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO sessions (session_id, device_fp, game, duration, step, status, created_at) VALUES (?, ?, ?, ?, 1, 'pending', ?)", (session_id, device_fp, game, duration, now))
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_session_step(session_id, step):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE sessions SET step = ? WHERE session_id = ?", (step, session_id))
    conn.commit()
    conn.close()


def mark_session_done(session_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE sessions SET status = 'done', verified_at = ? WHERE session_id = ?", (datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()


def generate_key():
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return "ANHKHOA-" + random_part


def create_key(device_fp, game, duration):
    init_db()
    key_plain = generate_key()
    now = datetime.utcnow()
    expires = now + timedelta(hours=duration)
    max_uses = 1 if duration == 12 else 2
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO keys (key_plain, device_fp, game, duration_hours, created_at, expires_at, uses, max_uses) VALUES (?, ?, ?, ?, ?, ?, 0, ?)", (key_plain, device_fp, game, duration, now.isoformat(), expires.isoformat(), max_uses))
    conn.commit()
    conn.close()
    return key_plain


def check_daily_limit(device_fp):
    init_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT count FROM daily_limits WHERE device_fp = ? AND day = ?", (device_fp, today)).fetchone()
    conn.close()
    used = row["count"] if row else 0
    remaining = max(0, 5 - used)
    return remaining > 0, used, remaining


def increment_daily_limit(device_fp):
    init_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO daily_limits (device_fp, day, count) VALUES (?, ?, 1) ON CONFLICT(device_fp, day) DO UPDATE SET count = count + 1", (device_fp, today))
    conn.commit()
    conn.close()


def validate_key(key, device_fp):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM keys WHERE key_plain = ?", (key,)).fetchone()
    if not row:
        conn.close()
        return False, "Key khong ton tai."
    if row["device_fp"] != device_fp:
        conn.close()
        return False, "Key da dung tren thiet bi khac."
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires:
        conn.close()
        return False, "Key da het han."
    if row["uses"] >= row["max_uses"]:
        conn.close()
        return False, "Key da het so lan su dung."
    conn.close()
    return True, "Key hop le!"
