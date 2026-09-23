import sqlite3
import os
import re
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vulnshop.db")

DB_ADMIN_USER = "admin"
DB_ADMIN_PASSWORD = "P@ssw0rd_2024!"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS login_attempts "
        "(key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires INTEGER NOT NULL)"
    )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone():
        for row in conn.execute("SELECT id, password_hash FROM users WHERE length(password_hash) = 32").fetchall():
            if re.fullmatch(r"[0-9a-f]{32}", row["password_hash"]):
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
                    ("legacy-md5$" + generate_password_hash(row["password_hash"]),
                     row["id"], row["password_hash"]),
                )
    conn.commit()
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript(
        """
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS comments;
        DROP TABLE IF EXISTS orders;

        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            bio TEXT,
            avatar_path TEXT,
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL
        );

        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending'
        );
        """
    )

    seed_users = [
        ("admin",   "admin123",       "[email protected]",  "Site administrator", 1),
        ("alice",   "alice2024",      "[email protected]", "Hi I'm Alice",        0),
        ("bob",     "bob",            "[email protected]",    "Bob's bio",           0),
        ("charlie", "password",       "[email protected]", "Charlie",             0),
    ]
    for username, pw, email, bio, is_admin in seed_users:
        cur.execute(
            "INSERT INTO users (username, password_hash, email, bio, is_admin) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, generate_password_hash(pw), email, bio, is_admin),
        )

    seed_products = [
        ("Vintage Camera", "A retro film camera in great condition.", 199.0),
        ("Mechanical Keyboard", "Cherry MX Blue, hot-swappable.", 129.0),
        ("Coffee Beans 500g", "Single-origin Ethiopian Yirgacheffe.", 24.5),
        ("Notebook", "Hardcover, dotted, 200 pages.", 18.0),
    ]
    for name, desc, price in seed_products:
        cur.execute(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            (name, desc, price),
        )

    cur.execute(
        "INSERT INTO orders (user_id, amount, status) VALUES (?, ?, ?)",
        (2, 1000.0, "paid"),
    )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"[+] Database initialized at {DB_PATH}")
    print(f"[!] Hardcoded admin password in source: {DB_ADMIN_PASSWORD}")
