from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os
from datetime import timedelta
from functools import wraps
from database import init_db, create_session, get_session, update_session_step, mark_session_done, create_key, check_daily_limit, increment_daily_limit, validate_key, list_keys, set_key_status, reset_key_device, delete_key, create_admin_keys, stats

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-this-secret-in-render")
app.permanent_session_lifetime = timedelta(days=7)
LINK4M_URL = os.environ.get("LINK4M_URL", "https://link4m.net/ov9vn2T9")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://getkey-server-anhkhoa.onrender.com/callback")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "KEY-ADMIN-TRG-918732").strip()
ADMIN_PANEL_PASSWORD = os.environ.get("ADMIN_PANEL_PASSWORD", "").strip()


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_authenticated"):
            if request.path.startswith('/admin/api/'):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    return wrapper


@app.route('/')
def index(): return render_template('index.html')

@app.route('/duration')
def duration_page(): return render_template('duration.html')

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.get_json(silent=True) or {}; game = data.get('game','freefire'); duration = int(data.get('duration',24)); device_fp = data.get('device_fp','')
    if not device_fp: return jsonify({'ok':False,'error':'Khong lay duoc device fingerprint.'})
    if duration not in [12,24]: return jsonify({'ok':False,'error':'Thoi han khong hop le.'})
    can_use, used, remaining = check_daily_limit(device_fp)
    if not can_use: return jsonify({'ok':False,'error':'Ban da het 5 luot hom nay. Quay lai vao ngay mai!'})
    session_id = create_session(device_fp, game, duration); session['pending_session']=session_id; session['device_fp']=device_fp; session.permanent=True
    return jsonify({'ok':True,'session_id':session_id,'bypass_url':LINK4M_URL,'duration':duration})

@app.route('/callback')
def callback():
    device_fp=session.get('device_fp',''); session_id=session.get('pending_session','') or request.args.get('session','')
    if not session_id or not device_fp: return redirect(url_for('index'))
    session_data=get_session(session_id)
    if not session_data or session_data['status']=='done': return redirect(url_for('index'))
    duration=session_data['duration']; current_step=session_data['step']; total_steps=1 if duration==12 else 2
    if current_step < total_steps:
        update_session_step(session_id,current_step+1)
        return render_template('bypass.html',session_id=session_id,current_step=current_step+1,total_steps=total_steps,duration=duration,link4m=LINK4M_URL)
    can_use,_,_=check_daily_limit(device_fp)
    if not can_use: return render_template('key.html',key='Het luot hom nay.')
    mark_session_done(session_id); increment_daily_limit(device_fp); key=create_key(device_fp,session_data['game'],duration)
    session.pop('pending_session',None); return render_template('key.html',key=key)

@app.route('/api/validate', methods=['POST'])
def api_validate():
    data=request.get_json(silent=True) or {}; key=str(data.get('key','')).strip(); device_fp=str(data.get('device_fp','')).strip()
    if not key or not device_fp: return jsonify({'valid':False,'message':'Thieu key hoac device fingerprint.'}),400
    if key == ADMIN_KEY: return jsonify({'valid':True,'admin':True,'expires':None,'message':'Admin key hop le - vinh vien.'})
    valid,message=validate_key(key,device_fp); return jsonify({'valid':valid,'admin':False,'expires':None,'message':message})

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if session.get('admin_authenticated'): return redirect(url_for('admin_dashboard'))
    error=''
    if request.method=='POST':
        if not ADMIN_PANEL_PASSWORD: error='ADMIN_PANEL_PASSWORD chưa được cấu hình trên server.'
        elif request.form.get('password','') == ADMIN_PANEL_PASSWORD:
            session['admin_authenticated']=True; session.permanent=True; return redirect(url_for('admin_dashboard'))
        else: error='Mật khẩu admin không đúng.'
    return render_template('login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_authenticated',None); return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin.html', admin_key=ADMIN_KEY[-4:] if ADMIN_KEY else '----')

@app.route('/admin/api/state')
@admin_required
def admin_state():
    return jsonify({'ok':True,'stats':stats(),'keys':list_keys()})

@app.route('/admin/api/keys', methods=['POST'])
@admin_required
def admin_create_keys():
    data=request.get_json(silent=True) or {}
    try: quantity=max(1,min(100,int(data.get('quantity',1))))
    except Exception: quantity=1
    try: duration=int(data.get('duration',48))
    except Exception: duration=48
    if duration not in (12,24,48,72,168): return jsonify({'ok':False,'error':'Thời hạn không hợp lệ.'}),400
    game=str(data.get('game','freefire')).strip()[:40] or 'freefire'
    keys=create_admin_keys(quantity,game,duration)
    return jsonify({'ok':True,'keys':keys,'count':len(keys)})

@app.route('/admin/api/keys/<int:key_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_key(key_id):
    data=request.get_json(silent=True) or {}; status='revoked' if data.get('status')!='active' else 'active'
    return jsonify({'ok':set_key_status(key_id,status)})

@app.route('/admin/api/keys/<int:key_id>/reset', methods=['POST'])
@admin_required
def admin_reset_key(key_id): return jsonify({'ok':reset_key_device(key_id)})

@app.route('/admin/api/keys/<int:key_id>', methods=['DELETE'])
@admin_required
def admin_delete_key(key_id): return jsonify({'ok':delete_key(key_id)})

if __name__=='__main__':
    init_db(); app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
