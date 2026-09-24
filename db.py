import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vulnshop.db")

DB_ADMIN_USER = "admin"
DB_ADMIN_PASSWORD = os.environ.get("DB_ADMIN_PASSWORD")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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

    admin_password = DB_ADMIN_PASSWORD or secrets.token_urlsafe(32)
    seed_users = [
        ("admin",   admin_password,       "[email protected]",  "Site administrator", 1),
        ("alice",   secrets.token_urlsafe(32),      "[email protected]", "Hi I'm Alice",        0),
        ("bob",     secrets.token_urlsafe(32),            "[email protected]",    "Bob's bio",           0),
        ("charlie", secrets.token_urlsafe(32),       "[email protected]", "Charlie",             0),
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
    if not DB_ADMIN_PASSWORD:
        print(f"Initial administrator password: {admin_password}")

if __name__ == "__main__":
    init_db()
    print(f"[+] Database initialized at {DB_PATH}")
