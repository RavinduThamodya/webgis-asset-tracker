from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pg8000, json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gis-final-secure-system-2026'
CORS(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login' 

# Database Connection (Port 5056)
DB_CONFIG = {"user": "postgres", "password": "gis1234", "host": "127.0.0.1", "database": "assets_tracker", "port": 5056}

try:
    conn = pg8000.connect(**DB_CONFIG)
    print("Database Connected Successfully")
except Exception as e:
    print(f"Database Error: {e}")
    conn = None

class User(UserMixin):
    def __init__(self, id, username, role, is_approved):
        self.id = id; self.username = username; self.role = role; self.is_approved = is_approved

@login_manager.user_loader
def load_user(user_id):
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, is_approved FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone(); cur.close()
    return User(row[0], row[1], row[2], row[3]) if row else None

def get_dict(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

# --- NAVIGATION ---

@app.route("/")
@login_required
def home():
    if current_user.role == 'admin':
        return render_template("menu.html")
    return redirect(url_for('map_view'))

@app.route("/map")
@login_required
def map_view():
    return render_template("index.html")

@app.route("/admin")
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return "Access Denied", 403
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, is_approved FROM users ORDER BY id DESC")
    users = get_dict(cur); cur.close()
    return render_template('admin.html', users=users)

@app.route("/manage-assets")
@login_required
def manage_assets():
    if current_user.role != 'admin': return "Access Denied", 403
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.name, a.asset_type, ST_X(a.geom) as lon, ST_Y(a.geom) as lat, u.username 
        FROM assets a 
        JOIN users u ON a.registered_by_user_id = u.id
    """)
    assets = get_dict(cur); cur.close()
    return render_template("manage_assets.html", assets=assets)

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, role, is_approved FROM users WHERE username = %s", (u,))
        row = cur.fetchone(); cur.close()
        if row and check_password_hash(row[2], p):
            if not row[4]: 
                flash("Waiting for Admin Approval")
                return redirect(url_for('login'))
            login_user(User(row[0], row[1], row[3], row[4]))
            return redirect(url_for('home'))
        flash("Invalid Credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form.get('username'), generate_password_hash(request.form.get('password'))
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (u, p))
        conn.commit(); cur.close(); flash("Registration successful! Waiting for approval."); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- USER ACTIONS ---

@app.route('/admin/action/<string:act>/<int:uid>')
@login_required
def admin_action(act, uid):
    if current_user.role != 'admin': return "Unauthorized", 403
    cur = conn.cursor()
    if act == 'approve': cur.execute("UPDATE users SET is_approved = TRUE WHERE id = %s", (uid,))
    elif act == 'delete': cur.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.commit(); cur.close(); return redirect(url_for('admin_dashboard'))

# --- ASSET API (GET, POST, PUT, DELETE) ---

@app.route("/api/assets", methods=["GET", "POST"])
@login_required
def api_assets():
    cur = conn.cursor()
    if request.method == "POST":
        data = request.get_json()
        cur.execute("""
            INSERT INTO assets (name, asset_type, geom, registered_by_user_id) 
            VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
        """, (data['name'], data['asset_type'], data['longitude'], data['latitude'], current_user.id))
        conn.commit(); cur.close(); return jsonify({"status": "ok"})
    
    asset_filter = request.args.get('type')
    if asset_filter and asset_filter != "All":
        cur.execute("SELECT id, name, asset_type, ST_AsGeoJSON(geom) FROM assets WHERE asset_type ILIKE %s", (asset_filter,))
    else:
        cur.execute("SELECT id, name, asset_type, ST_AsGeoJSON(geom) FROM assets")
        
    feats = [{"type":"Feature","geometry":json.loads(r[3]),"properties":{"id":r[0],"name":r[1],"asset_type":r[2]}} for r in cur.fetchall()]
    cur.close(); return jsonify({"type": "FeatureCollection", "features": feats})

@app.route("/api/assets/<int:aid>", methods=["PUT", "DELETE"])
@login_required
def modify_asset(aid):
    if current_user.role != 'admin': return jsonify({"error": "Admin only"}), 403
    cur = conn.cursor()
    if request.method == "DELETE":
        cur.execute("DELETE FROM assets WHERE id = %s", (aid,))
    elif request.method == "PUT":
        data = request.get_json()
        cur.execute("UPDATE assets SET name=%s, asset_type=%s, geom=ST_SetSRID(ST_MakePoint(%s, %s), 4326) WHERE id=%s", 
                    (data['name'], data['asset_type'], data['longitude'], data['latitude'], aid))
    conn.commit(); cur.close(); return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)