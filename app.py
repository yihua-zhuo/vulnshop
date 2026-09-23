import os
import pickle
import pickletools
import subprocess
import sqlite3
import hashlib
import io
import re
import time
import socket
import ipaddress
import http.client
from decimal import Decimal, InvalidOperation
from werkzeug.security import generate_password_hash, check_password_hash

from xml.parsers.expat import ParserCreate as _ExpatCreate
from urllib.parse import urlparse

from flask import (
    Flask, request, redirect, url_for, session,
    render_template, render_template_string, abort,
    flash, send_from_directory, Response,
)

from db import get_conn, init_db, DB_PATH

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def weak_hash(pw: str) -> str:
    return generate_password_hash(pw)

def current_user():
    uid = session.get("user_id")
    if not isinstance(uid, int):
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT id, username, email, bio, avatar_path, is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

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

@app.template_filter("unsafe")
def unsafe_filter(s):
    if s is None:
        return ""
    return str(s)

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
                (username, weak_hash(password), email, bio),
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
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires REAL NOT NULL)")
            now = time.time()
            conn.execute("DELETE FROM login_attempts WHERE expires <= ?", (now,))
            keys = [("account:" + hashlib.sha256(username.encode()).hexdigest(), 5),
                    ("source:" + (request.remote_addr or "unknown"), 20), ("global", 100)]
            for key, limit in keys:
                attempt = conn.execute("SELECT attempts FROM login_attempts WHERE key = ?", (key,)).fetchone()
                if attempt and attempt["attempts"] >= limit:
                    conn.rollback()
                    return Response("Too many login attempts. Try again later.", status=429)
            for key, limit in keys:
                conn.execute("INSERT INTO login_attempts VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET attempts = attempts + 1", (key, now + 300))
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            valid = False
            if row:
                stored = row["password_hash"]
                legacy = stored.startswith("md5$")
                candidate = hashlib.md5(password.encode()).hexdigest() if legacy else password
                valid = check_password_hash(stored[4:] if legacy else stored, candidate)
                if valid:
                    conn.execute("DELETE FROM login_attempts WHERE key = ?", (keys[0][0],))
                    conn.commit()
                if valid and legacy:
                    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (weak_hash(password), row["id"]))
                    conn.commit()
        finally:
            conn.close()

        if valid:
            session.clear()
            session["user_id"] = row["id"]
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
    results = []
    if q:
        conn = get_conn()
        query = "SELECT id, name, description, price FROM products WHERE name LIKE ? OR description LIKE ?"
        try:
            results = conn.execute(query, (f"%{q}%", f"%{q}%")).fetchall()
        except sqlite3.OperationalError:
            return Response("Search unavailable.", mimetype="text/plain"), 500
        finally:
            conn.close()

    html = render_template_string(
        "{% extends 'base.html' %}"
        "{% block content %}"
        "<h2>Search results for: {{ q }}</h2>"
        "<p>{{ results|length }} match(es).</p>"
        "<ul>"
        "{% for r in results %}<li><b>{{ r.name }}</b> — {{ r.description }} (${{ r.price }})</li>{% endfor %}"
        "</ul>"
        "{% endblock %}",
        q=q, results=results,
    )
    return html

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
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    if uid is None:
        uid = u["id"]
    if uid != u["id"] and not u["is_admin"]:
        abort(403)
    conn = get_conn()
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

    _WHITELIST = ("bio", "email")
    updates = {k: v for k, v in request.form.items() if k in _WHITELIST}
    if not updates:
        flash("Nothing to update.", "err")
        return redirect(url_for("profile"))

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [u["id"]]

    conn = get_conn()
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

    flash("Profile updated.", "ok")
    return redirect(url_for("profile"))

@app.route("/transfer", methods=["POST"])
def transfer():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    try:
        to_id = int(request.form.get("to", ""))
        value = Decimal(request.form.get("amount", ""))
        if not value.is_finite() or value <= 0 or value > Decimal("1000000000") or value != value.quantize(Decimal("0.01")):
            abort(400)
        amount = float(value)
    except (ValueError, InvalidOperation):
        abort(400)

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if to_id == u["id"] or not conn.execute("SELECT id FROM users WHERE id = ?", (to_id,)).fetchone():
            abort(400)
        senders = conn.execute("SELECT id, amount FROM orders WHERE user_id = ? AND status = 'paid' ORDER BY id", (u["id"],)).fetchall()
        balances = [Decimal(str(row["amount"])) for row in senders]
        if any(not balance.is_finite() or balance < 0 or balance != balance.quantize(Decimal("0.01")) for balance in balances) or sum(balances) < value:
            abort(400)
        remaining = value
        for sender, balance in zip(senders, balances):
            debit = min(balance, remaining)
            if debit:
                updated = conn.execute("UPDATE orders SET amount = ? WHERE id = ? AND user_id = ? AND status = 'paid'", (float(balance - debit), sender["id"], u["id"]))
                if updated.rowcount != 1:
                    abort(400)
                remaining -= debit
            if remaining == 0:
                break
        conn.execute("INSERT INTO orders (user_id, amount, status) VALUES (?, ?, 'paid')", (to_id, amount))
        conn.commit()
    finally:
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

    data = f.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        abort(400, "Only PNG avatars are supported.")
    saved_name = f"avatar-{u['id']}.png"
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        destination = os.path.join(UPLOAD_DIR, saved_name)
        used = sum(entry.stat().st_size for entry in os.scandir(UPLOAD_DIR) if entry.is_file())
        previous = os.path.getsize(destination) if os.path.isfile(destination) else 0
        if used - previous + len(data) > 100 * 1024 * 1024:
            abort(413)
        with open(destination, "wb") as output:
            output.write(data)
        conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (saved_name, u["id"]))
        conn.commit()
    finally:
        conn.close()
    flash(f"Avatar saved as {saved_name}.", "ok")
    return redirect(url_for("profile"))

@app.route("/download")
def download():
    name = request.args.get("file", "")
    full = os.path.realpath(os.path.join(DOWNLOAD_DIR, name))
    if os.path.commonpath((os.path.realpath(DOWNLOAD_DIR), full)) != os.path.realpath(DOWNLOAD_DIR):
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)

@app.route("/redirect")
def go():
    target = request.args.get("url", "/")
    if not target.startswith("/") or target.startswith("//") or "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        abort(400)
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
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}", host):
        abort(400)
    out = subprocess.run(
        ["ping", "-c", "1", host], capture_output=True, text=True, timeout=5
    )
    return Response(
        f"<pre>STDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}</pre>",
        mimetype="text/plain",
    )

@app.route("/admin/fetch", methods=["POST"])
@login_required
@admin_required
def admin_fetch():
    url = request.form.get("url", "")
    connection = None
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            abort(400)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            abort(400)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            abort(400)
        address = addresses[0][4][0]
        cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = cls(parsed.hostname, port, timeout=3)
        connection._create_connection = lambda destination, timeout, source_address=None: socket.create_connection((address, port), timeout)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request("GET", path)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            abort(400)
        body = response.read(64 * 1024)
    except (ValueError, OSError, http.client.HTTPException):
        return Response("Fetch failed.", status=400, mimetype="text/plain")
    finally:
        if connection:
            connection.close()
    return Response(body, mimetype="text/plain")

@app.route("/admin/import-xml", methods=["POST"])
@login_required
@admin_required
def admin_import_xml():
    payload = request.form.get("xml", "")
    leaked = []
    def _characters(data):
        leaked.append(data)
    def _reject_entities(*args):
        raise ValueError("DTD and entities are not allowed")
    parser = _ExpatCreate()
    parser.CharacterDataHandler = _characters
    parser.StartDoctypeDeclHandler = _reject_entities
    parser.EntityDeclHandler = _reject_entities
    parser.ExternalEntityRefHandler = _reject_entities
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
        class DataUnpickler(pickle.Unpickler):
            def find_class(self, module, name):
                raise pickle.UnpicklingError("Object construction is not allowed")
            def persistent_load(self, pid):
                raise pickle.UnpicklingError("Persistent references are not allowed")
        raw = bytes.fromhex(blob)
        for opcode, argument, position in pickletools.genops(raw):
            if opcode.name in {"EXT1", "EXT2", "EXT4"}:
                raise pickle.UnpicklingError("Extension objects are not allowed")
        data = DataUnpickler(io.BytesIO(raw)).load()
        flash(f"Restored object: {data!r}", "ok")
    except Exception as e:
        flash(f"Restore failed: {e}", "err")
    return redirect(url_for("admin_dashboard"))

@app.errorhandler(500)
def err_500(e):
    return Response(
        "Server error", status=500, mimetype="text/plain"
    )

@app.before_request
def protect_uploads():
    if request.endpoint == "static":
        filename = request.view_args.get("filename", "")
        resolved = os.path.realpath(os.path.join(app.static_folder, filename))
        if os.path.commonpath((os.path.realpath(UPLOAD_DIR), resolved)) == os.path.realpath(UPLOAD_DIR):
            if not re.fullmatch(r"uploads/avatar-[0-9]+\.png", filename):
                abort(404)
            response = send_from_directory(UPLOAD_DIR, os.path.basename(filename), mimetype="image/png")
            response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
            return response

@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
