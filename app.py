import os
import posixpath
import json
import secrets
import socket
import ssl
import stat
import http.client
import ipaddress
import re
from decimal import Decimal, InvalidOperation
import subprocess
import sqlite3
import xml.etree.ElementTree as ET

from xml.parsers.expat import ParserCreate as _ExpatCreate
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask, request, redirect, url_for, session,
    render_template, render_template_string, abort,
    flash, send_from_directory, Response,
)

from db import get_conn, init_db, DB_PATH

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "files")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.before_request
def protect_requests():
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        source = request.headers.get("Origin") or request.headers.get("Referer", "")
        origin = urlparse(source)
        expected = urlparse(request.host_url)
        if (origin.scheme, origin.netloc) != (expected.scheme, expected.netloc):
            abort(403)
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)
    if request.endpoint == "static":
        filename = posixpath.normpath(request.view_args.get("filename", ""))
        if filename.startswith("files/") and filename not in (
            "files/price-list.txt", "files/warranty.txt"
        ):
            abort(404)


def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, bio, avatar_path, is_admin FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
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
            session["user_id"] = row["id"]
            flash(f"Welcome back, {row['username']}!", "ok")
            return redirect(url_for("index"))
        flash("Invalid credentials.", "err")
    return render_template("login.html", user=current_user())

@app.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET":
        return render_template_string(
            '<form method="post"><button type="submit">Log out</button></form>'
        )
    session.clear()
    return redirect(url_for("index"))

@app.route("/search")
def search():
    q = request.args.get("q", "")
    results = []
    if q:
        conn = get_conn()
        try:
            results = conn.execute(
                "SELECT id, name, description, price FROM products "
                "WHERE name LIKE ? OR description LIKE ?", (f"%{q}%", f"%{q}%")
            ).fetchall()
        except sqlite3.OperationalError:
            return Response("Search unavailable", mimetype="text/plain"), 500
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
    if uid is not None and uid != u["id"]:
        abort(403)
    uid = u["id"]
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
    if to_id == u["id"]:
        abort(400)

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT id FROM users WHERE id = ?", (to_id,)).fetchone():
            abort(400)
        balances = conn.execute(
            "SELECT id, amount FROM orders WHERE user_id = ? AND status = 'paid' AND amount > 0 ORDER BY id",
            (u["id"],),
        ).fetchall()
        if sum((Decimal(str(row["amount"])) for row in balances), Decimal(0)) < value:
            abort(400)
        remaining = value
        for row in balances:
            balance = Decimal(str(row["amount"]))
            debit = min(balance, remaining)
            conn.execute("UPDATE orders SET amount = ? WHERE id = ?", (float(balance - debit), row["id"]))
            remaining -= debit
            if remaining == 0:
                break
        conn.execute(
            "INSERT INTO orders (user_id, amount, status) VALUES (?, ?, 'paid')",
            (to_id, amount),
        )
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

    data = f.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        abort(413)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        extension = ".gif"
    else:
        abort(400)
    saved_name = secrets.token_hex(16) + extension
    with open(os.path.join(UPLOAD_DIR, saved_name), "xb") as destination:
        destination.write(data)

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
    if name not in ("price-list.txt", "warranty.txt"):
        abort(404)
    full = os.path.join(DOWNLOAD_DIR, name)
    try:
        fd = os.open(full, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as fh:
            info = os.fstat(fh.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                abort(413)
            data = fh.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                abort(413)
    except OSError:
        abort(404)
    return Response(data, mimetype="application/octet-stream")

@app.route("/redirect")
def go():
    target = request.args.get("url", "/")
    if not target.startswith("/") or target.startswith("//") or "\\" in target or any(ord(c) < 32 for c in target):
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
    try:
        out = subprocess.run(
            ["ping", "-c", "1", host], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return Response("Ping failed", status=502, mimetype="text/plain")
    return Response(
        f"STDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}",
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
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            abort(400)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            abort(400)
        for entry in addresses:
            ip = ipaddress.ip_address(entry[4][0])
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                abort(400)
            if isinstance(ip, ipaddress.IPv6Address) and (ip.sixtofour or ip.teredo or ip.ipv4_mapped):
                abort(400)
        address = addresses[0][4][0]
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=3)
        connection.sock = socket.create_connection((address, port), timeout=3)
        if parsed.scheme == "https":
            connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parsed.hostname)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request("GET", path, headers={"Host": parsed.netloc})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            return Response("Redirects are not allowed", status=400, mimetype="text/plain")
        body = response.read(64 * 1024)
    except (ValueError, OSError, http.client.HTTPException):
        return Response("Fetch failed", status=502, mimetype="text/plain")
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
    def _reject_doctype(*args):
        raise ValueError("DTD declarations are not allowed")
    parser = _ExpatCreate()
    parser.CharacterDataHandler = _characters
    parser.StartDoctypeDeclHandler = _reject_doctype
    parser.ExternalEntityRefHandler = lambda *args: 0
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
        data = json.loads(blob)
        flash(f"Restored object: {data!r}", "ok")
    except (ValueError, RecursionError):
        flash("Restore failed: invalid JSON", "err")
    return redirect(url_for("admin_dashboard"))

@app.errorhandler(500)
def err_500(e):
    return Response(
        "<h1>Server error</h1>", status=500, mimetype="text/html"
    )

@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if request.endpoint == "static" and posixpath.normpath(request.view_args.get("filename", "")).startswith("uploads/"):
        resp.headers["Content-Type"] = "application/octet-stream"
        resp.headers["Content-Disposition"] = "attachment"
        resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return resp

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
