import sqlite3
import secrets
import string
from datetime import datetime, timedelta, date

DB_PATH = "keys.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute("CREATE TABLE IF NOT EXISTS keys (id INTEGER PRIMARY KEY AUTOINCREMENT, key_plain TEXT NOT NULL UNIQUE, device_fp TEXT NOT NULL DEFAULT '*', game TEXT NOT NULL, duration_hours INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, uses INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1, status TEXT DEFAULT 'active')")
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT UNIQUE NOT NULL, device_fp TEXT NOT NULL, game TEXT NOT NULL, duration INTEGER NOT NULL, step INTEGER DEFAULT 1, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL, verified_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS daily_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fp TEXT NOT NULL, day TEXT NOT NULL, count INTEGER DEFAULT 0, UNIQUE(device_fp, day))")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(keys)").fetchall()}
    if "status" not in cols:
        conn.execute("ALTER TABLE keys ADD COLUMN status TEXT DEFAULT 'active'")
    conn.execute("UPDATE keys SET status='active' WHERE status IS NULL OR status=''")
    conn.commit()
    conn.close()


def generate_session_id():
    return secrets.token_urlsafe(24)


def create_session(device_fp, game, duration):
    init_db()
    session_id = generate_session_id()
    now = datetime.utcnow().isoformat()
    conn = _connect()
    conn.execute("INSERT INTO sessions (session_id, device_fp, game, duration, step, status, created_at) VALUES (?, ?, ?, ?, 1, 'pending', ?)", (session_id, device_fp, game, duration, now))
    conn.commit(); conn.close()
    return session_id


def get_session(session_id):
    init_db(); conn = _connect()
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close(); return dict(row) if row else None


def update_session_step(session_id, step):
    conn = _connect(); conn.execute("UPDATE sessions SET step = ? WHERE session_id = ?", (step, session_id)); conn.commit(); conn.close()


def mark_session_done(session_id):
    conn = _connect(); conn.execute("UPDATE sessions SET status = 'done', verified_at = ? WHERE session_id = ?", (datetime.utcnow().isoformat(), session_id)); conn.commit(); conn.close()


def generate_key():
    chars = string.ascii_uppercase + string.digits
    return "ANHKHOA-" + ''.join(secrets.choice(chars) for _ in range(8))


def create_key(device_fp, game, duration, max_uses=None):
    init_db(); now = datetime.utcnow(); expires = now + timedelta(hours=duration)
    if max_uses is None: max_uses = 1 if duration <= 12 else 2
    key_plain = generate_key()
    conn = _connect()
    conn.execute("INSERT INTO keys (key_plain, device_fp, game, duration_hours, created_at, expires_at, uses, max_uses, status) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'active')", (key_plain, device_fp or '*', game, duration, now.isoformat(), expires.isoformat(), max_uses))
    conn.commit(); conn.close(); return key_plain


def create_admin_keys(quantity, game, duration):
    out = []
    for _ in range(quantity): out.append(create_key('*', game, duration, 1))
    return out


def list_keys(limit=200):
    init_db(); conn = _connect()
    rows = conn.execute("SELECT * FROM keys ORDER BY id DESC LIMIT ?", (limit,)).fetchall(); conn.close()
    return [dict(r) for r in rows]


def set_key_status(key_id, status):
    if status not in ('active', 'revoked'): return False
    conn = _connect(); cur = conn.execute("UPDATE keys SET status=? WHERE id=?", (status, key_id)); conn.commit(); ok = cur.rowcount == 1; conn.close(); return ok


def reset_key_device(key_id):
    conn = _connect(); cur = conn.execute("UPDATE keys SET device_fp='*', uses=0, status='active' WHERE id=?", (key_id,)); conn.commit(); ok = cur.rowcount == 1; conn.close(); return ok


def delete_key(key_id):
    conn = _connect(); cur = conn.execute("DELETE FROM keys WHERE id=?", (key_id,)); conn.commit(); ok = cur.rowcount == 1; conn.close(); return ok


def stats():
    init_db(); conn = _connect()
    total = conn.execute("SELECT COUNT(*) c FROM keys").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) c FROM keys WHERE status='active'").fetchone()["c"]
    bound = conn.execute("SELECT COUNT(*) c FROM keys WHERE device_fp <> '*'").fetchone()["c"]
    expired = conn.execute("SELECT COUNT(*) c FROM keys WHERE expires_at < ?", (datetime.utcnow().isoformat(),)).fetchone()["c"]
    conn.close(); return {'total': total, 'active': active, 'bound': bound, 'expired': expired}


def check_daily_limit(device_fp):
    init_db(); today = date.today().isoformat(); conn = _connect()
    row = conn.execute("SELECT count FROM daily_limits WHERE device_fp = ? AND day = ?", (device_fp, today)).fetchone(); conn.close()
    used = row["count"] if row else 0; remaining = max(0, 5-used); return remaining > 0, used, remaining


def increment_daily_limit(device_fp):
    init_db(); today = date.today().isoformat(); conn = _connect()
    conn.execute("INSERT INTO daily_limits (device_fp, day, count) VALUES (?, ?, 1) ON CONFLICT(device_fp, day) DO UPDATE SET count = count + 1", (device_fp, today)); conn.commit(); conn.close()


def validate_key(key, device_fp):
    init_db(); conn = _connect(); row = conn.execute("SELECT * FROM keys WHERE key_plain = ?", (key,)).fetchone()
    if not row: conn.close(); return False, "Key khong ton tai."
    if row["status"] != 'active': conn.close(); return False, "Key da bi khoa."
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires: conn.close(); return False, "Key da het han."
    if row["device_fp"] not in ('*', device_fp): conn.close(); return False, "Key da dung tren thiet bi khac."
    if row["uses"] >= row["max_uses"]: conn.close(); return False, "Key da het so lan su dung."
    if row["device_fp"] == '*':
        conn.execute("UPDATE keys SET device_fp=? WHERE id=?", (device_fp, row["id"]))
    conn.execute("UPDATE keys SET uses=uses+1 WHERE id=?", (row["id"],))
    conn.commit(); conn.close(); return True, "Key hop le!"
