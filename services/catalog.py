import sqlite3

from db import get_conn


def save_view(user_id, term, ordering):
    conn = get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO catalog_views (user_id, term, ordering) VALUES (?, ?, ?)",
            (user_id, term, ordering),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def run_view(view_id, user_id):
    conn = get_conn()
    try:
        view = conn.execute(
            "SELECT term, ordering FROM catalog_views WHERE id = ? AND user_id = ?",
            (view_id, user_id),
        ).fetchone()
        if view is None:
            return None
        return conn.execute(
            "SELECT id, name, description, price FROM products "
            "WHERE name LIKE ? OR description LIKE ? ORDER BY " + view["ordering"],
            (f"%{view['term']}%", f"%{view['term']}%"),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
