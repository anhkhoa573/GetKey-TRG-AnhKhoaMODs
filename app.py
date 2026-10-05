from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os
from datetime import timedelta
from database import (
    init_db, create_session, get_session, update_session_step,
    mark_session_done, create_key, check_daily_limit, increment_daily_limit,
    validate_key
)

app = Flask(__name__)
app.secret_key = "anhkhoa-vip-key-2024-secret"
app.permanent_session_lifetime = timedelta(days=7)

LINK4M_URL = "https://link4m.net/ov9vn2T9"
CALLBACK_URL = "https://getkey-server-anhkhoa.onrender.com/callback"
ADMIN_KEY = os.environ.get("ADMIN_KEY", "KEY-ADMIN-TRG-918732").strip()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/duration")
def duration_page():
    return render_template("duration.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json()
    game = data.get("game", "freefire")
    duration = int(data.get("duration", 24))
    device_fp = data.get("device_fp", "")

    if not device_fp:
        return jsonify({"ok": False, "error": "Khong lay duoc device fingerprint."})
    if duration not in [12, 24]:
        return jsonify({"ok": False, "error": "Thoi han khong hop le."})

    can_use, used, remaining = check_daily_limit(device_fp)
    if not can_use:
        return jsonify({"ok": False, "error": "Ban da het 5 luot hom nay. Quay lai vao ngay mai!"})

    session_id = create_session(device_fp, game, duration)
    session["pending_session"] = session_id
    session["device_fp"] = device_fp
    session.permanent = True

    return jsonify({"ok": True, "session_id": session_id, "bypass_url": LINK4M_URL, "duration": duration})


@app.route("/callback")
def callback():
    device_fp = session.get("device_fp", "")
    session_id = session.get("pending_session", "")
    if not session_id:
        session_id = request.args.get("session", "")
    if not session_id or not device_fp:
        return redirect(url_for("index"))

    session_data = get_session(session_id)
    if not session_data:
        return redirect(url_for("index"))
    if session_data["status"] == "done":
        return redirect(url_for("index"))

    duration = session_data["duration"]
    current_step = session_data["step"]
    total_steps = 1 if duration == 12 else 2

    if current_step < total_steps:
        update_session_step(session_id, current_step + 1)
        return render_template("bypass.html", session_id=session_id,
                               current_step=current_step + 1, total_steps=total_steps,
                               duration=duration, link4m=LINK4M_URL)

    can_use, used, remaining = check_daily_limit(device_fp)
    if not can_use:
        return render_template("key.html", key="Het luot hom nay.")

    mark_session_done(session_id)
    increment_daily_limit(device_fp)
    key = create_key(device_fp, session_data["game"], duration)
    session.pop("pending_session", None)
    return render_template("key.html", key=key)


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip()
    device_fp = str(data.get("device_fp", "")).strip()
    if not key or not device_fp:
        return jsonify({"valid": False, "message": "Thieu key hoac device fingerprint."}), 400
    if key == ADMIN_KEY:
        return jsonify({"valid": True, "admin": True, "expires": None, "message": "Admin key hop le - vinh vien."})
    valid, message = validate_key(key, device_fp)
    return jsonify({"valid": valid, "admin": False, "expires": None, "message": message})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
