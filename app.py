import os
import pickle
import subprocess
import sqlite3
import secrets

from xml.parsers.expat import ParserCreate as _ExpatCreate
from urllib.request import urlopen

from flask import (
    Flask, request, redirect, url_for, session,
    render_template, abort,
    flash, send_from_directory, Response,
)

from db import get_conn, init_db
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from services.accounts import preferences, session_identity
from services.catalog import save_view, run_view
from services.assets import asset_path
from services.storefront import storefront
from services.report_routes import reports

app = Flask(__name__)
app.register_blueprint(storefront)
app.register_blueprint(reports)

app.secret_key = os.environ.get("SHOP_SECRET_KEY") or secrets.token_hex(32)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def current_user():
    return session.get("user")

def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u or not u.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    conn = get_conn()
    products = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return render_template("index.html", products=products, user=current_user())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        bio = request.form.get("bio", "")

        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, email, bio) "
                "VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), email, bio),
            )
            conn.commit()
            flash("Account created. Please log in.", "ok")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already taken.", "err")
        finally:
            conn.close()
    return render_template("register.html", user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["_customer_id"] = row["id"]
            session["user"] = session_identity(row)
            flash(f"Welcome back, {row['username']}!", "ok")
            return redirect(url_for("index"))
        flash("Invalid credentials.", "err")
    return render_template("login.html", user=current_user())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/search")
def search():
    q = request.args.get("q", "")
    conn = get_conn()
    try:
        results = conn.execute(
            "SELECT id, name, description, price FROM products WHERE name LIKE ? OR description LIKE ?",
            (f"%{q}%", f"%{q}%"),
        ).fetchall() if q else []
    finally:
        conn.close()
    return render_template("search.html", q=q, results=results, user=current_user())

@app.route("/catalog/views", methods=["POST"])
@login_required
def save_catalog_view():
    view_id = save_view(current_user()["id"], request.form.get("q", ""),
                        request.form.get("ordering", "name"))
    return redirect(url_for("catalog_view", view_id=view_id))

@app.route("/catalog/views/<int:view_id>")
@login_required
def catalog_view(view_id):
    results = run_view(view_id, current_user()["id"])
    if results is None:
        abort(404)
    return render_template("search.html", q="Saved view", results=results, user=current_user())

@app.route("/product/<int:pid>")
def product(pid):
    conn = get_conn()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    comments = conn.execute(
        "SELECT c.id, c.content, c.created_at, u.username "
        "FROM comments c JOIN users u ON c.user_id = u.id "
        "WHERE c.product_id = ? ORDER BY c.id DESC",
        (pid,),
    ).fetchall()
    conn.close()
    if not product:
        abort(404)
    return render_template(
        "product.html", product=product, comments=comments, user=current_user()
    )

@app.route("/comment", methods=["POST"])
def add_comment():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    pid = request.form.get("product_id")
    content = request.form.get("content", "")
    conn = get_conn()
    conn.execute(
        "INSERT INTO comments (product_id, user_id, content) VALUES (?, ?, ?)",
        (pid, u["id"], content),
    )
    conn.commit()
    conn.close()
    flash("Comment posted.", "ok")
    return redirect(url_for("product", pid=pid))

@app.route("/profile")
@app.route("/profile/<int:uid>")
def profile(uid=None):
    conn = get_conn()
    if uid is None:
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        uid = u["id"]
    target = conn.execute(
        "SELECT id, username, email, bio, avatar_path, is_admin FROM users WHERE id = ?",
        (uid,),
    ).fetchone()
    conn.close()
    if not target:
        abort(404)
    return render_template("profile.html", target=target, user=current_user())

@app.route("/profile/update", methods=["POST"])
def profile_update():
    u = current_user()
    if not u:
        return redirect(url_for("login"))

    _WHITELIST = ("bio", "email", "preferences")
    updates = {k: v for k, v in request.form.items() if k in _WHITELIST}
    if not updates:
        flash("Nothing to update.", "err")
        return redirect(url_for("profile"))

    if "preferences" in updates:
        try:
            settings = preferences(updates["preferences"])
            if not isinstance(settings.get("account", {}), dict):
                raise ValueError("Invalid account settings")
        except (ValueError, TypeError):
            abort(400)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [u["id"]]

    conn = get_conn()
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

    row = dict(u)
    for k, v in updates.items():
        if k in ("bio", "email"):
            row[k] = v
    session["user"] = row
    flash("Profile updated.", "ok")
    return redirect(url_for("profile"))

@app.route("/transfer", methods=["POST"])
def transfer():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    to_id = request.form.get("to", "")
    amount = float(request.form.get("amount", "0") or 0)

    conn = get_conn()
    conn.execute(
        "UPDATE orders SET amount = amount - ? WHERE user_id = ? AND status = 'paid'",
        (amount, u["id"]),
    )
    conn.execute(
        "INSERT INTO orders (user_id, amount, status) VALUES (?, ?, 'paid')",
        (to_id, amount),
    )
    conn.commit()
    conn.close()
    flash(f"Transferred ${amount} to user {to_id}.", "ok")
    return redirect(url_for("profile"))

@app.route("/upload-avatar", methods=["POST"])
def upload_avatar():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    f = request.files.get("avatar")
    if not f or not f.filename:
        flash("No file.", "err")
        return redirect(url_for("profile"))

    saved_name = secure_filename(f.filename)
    if not saved_name or os.path.splitext(saved_name)[1].lower() not in (".png", ".jpg", ".jpeg", ".gif"):
        abort(400)
    f.save(os.path.join(UPLOAD_DIR, saved_name))

    conn = get_conn()
    conn.execute(
        "UPDATE users SET avatar_path = ? WHERE id = ?",
        (saved_name, u["id"]),
    )
    conn.commit()
    conn.close()
    flash(f"Avatar saved as {saved_name}.", "ok")
    return redirect(url_for("profile"))

@app.route("/download")
def download():
    name = request.args.get("file", "")
    try:
        full = asset_path(DOWNLOAD_DIR, name)
        data = full.read_bytes()
    except ValueError:
        abort(400)
    except OSError:
        abort(404)
    return Response(data, mimetype="application/octet-stream")

@app.route("/redirect")
def go():
    target = request.args.get("url", "/")
    return redirect(target)

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    return render_template("admin.html", user=current_user())

@app.route("/admin/ping", methods=["POST"])
@login_required
@admin_required
def admin_ping():
    host = request.form.get("host", "")
    out = subprocess.run(
        f"ping -c 1 {host}", shell=True, capture_output=True, text=True
    )
    return Response(
        f"<pre>STDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}</pre>",
        mimetype="text/html",
    )

@app.route("/admin/fetch", methods=["POST"])
@login_required
@admin_required
def admin_fetch():
    url = request.form.get("url", "")
    try:
        body = urlopen(url, timeout=3).read(64 * 1024)
    except Exception as e:
        body = f"ERROR: {e}".encode()
    return Response(body, mimetype="text/plain")

@app.route("/admin/import-xml", methods=["POST"])
@login_required
@admin_required
def admin_import_xml():
    payload = request.form.get("xml", "")
    leaked = []
    def _characters(data):
        leaked.append(data)
    def _resolve_external(ctx, base, sysid, pubid):
        if sysid.startswith("file:///"):
            try:
                with open(sysid[7:], "r", errors="replace") as f:
                    leaked.append(f.read())
            except OSError:
                pass
        return 1
    parser = _ExpatCreate()
    parser.CharacterDataHandler = _characters
    parser.ExternalEntityRefHandler = _resolve_external
    try:
        parser.Parse(payload.encode(), True)
        note = "".join(leaked).strip()
        flash(f"Imported order with note: {note}", "ok")
    except Exception as e:
        flash(f"XML parse error: {e}", "err")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/restore", methods=["POST"])
@login_required
@admin_required
def admin_restore():
    blob = request.form.get("blob", "")
    try:
        data = pickle.loads(bytes.fromhex(blob))
        flash(f"Restored object: {data!r}", "ok")
    except Exception as e:
        flash(f"Restore failed: {e}", "err")
    return redirect(url_for("admin_dashboard"))

@app.errorhandler(500)
def err_500(e):
    return Response(
        f"<h1>Server error</h1><pre>{e}</pre>", status=500, mimetype="text/html"
    )

@app.after_request
def add_headers(resp):
    return resp

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
