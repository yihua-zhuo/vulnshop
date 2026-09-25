import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("SHOP_DB_PATH") or os.path.join(os.path.dirname(__file__), "data", "shop.db")

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
        DROP TABLE IF EXISTS report_access_cache;
        DROP TABLE IF EXISTS report_exports;
        DROP TABLE IF EXISTS reports;
        DROP TABLE IF EXISTS purchase_items;
        DROP TABLE IF EXISTS purchases;
        DROP TABLE IF EXISTS cart_items;
        DROP TABLE IF EXISTS favorites;
        DROP TABLE IF EXISTS catalog_views;
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
            preferences TEXT NOT NULL DEFAULT '{}',
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            visibility TEXT NOT NULL CHECK(visibility IN ('public', 'private')),
            UNIQUE(user_id, slug)
        );
        CREATE TABLE report_exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_id INTEGER NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('queued', 'ready')),
            output TEXT
        );
        CREATE TABLE report_access_cache (
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
            expires_at INTEGER NOT NULL,
            PRIMARY KEY(user_id, slug)
        );

        CREATE TABLE cart_items (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99),
            PRIMARY KEY (user_id, product_id)
        );
        CREATE TABLE favorites (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, product_id)
        );
        CREATE TABLE purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'cancelled')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX purchases_by_user ON purchases(user_id, id);
        CREATE TABLE purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            unit_cents INTEGER NOT NULL CHECK(unit_cents >= 0),
            quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99)
        );
        CREATE INDEX items_by_purchase ON purchase_items(purchase_id);

        CREATE TABLE catalog_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            term TEXT NOT NULL,
            ordering TEXT NOT NULL
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
        ("admin",   os.environ.get("SHOP_ADMIN_PASSWORD") or secrets.token_urlsafe(24),       "[email protected]",  "Site administrator", 1),
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

    cur.execute(
        "INSERT INTO reports (user_id, slug, title, body, visibility) VALUES (1, ?, ?, ?, 'private')",
        ('quarterly-plan', 'Quarterly purchasing plan', 'Internal reference: ' + secrets.token_hex(24)),
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
