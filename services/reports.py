"""Report storage and deferred export processing."""
from db import get_conn


def report_for_owner(conn, report_id, user_id):
    return conn.execute('SELECT * FROM reports WHERE id = ? AND user_id = ?', (report_id, user_id)).fetchone()


def queue_export(conn, user_id, report_id):
    report = report_for_owner(conn, report_id, user_id)
    if report is None:
        return None
    return conn.execute(
        "INSERT INTO report_exports (user_id, report_id, state) VALUES (?, ?, 'queued')",
        (user_id, report_id),
    ).lastrowid


def update_export(conn, job_id, user_id, report_id):
    return conn.execute(
        "UPDATE report_exports SET report_id = ? WHERE id = ? AND user_id = ? AND state = 'queued'",
        (report_id, job_id, user_id),
    ).rowcount


def process_export(conn, job):
    report = conn.execute('SELECT body FROM reports WHERE id = ?', (job['report_id'],)).fetchone()
    if report is None:
        return False
    conn.execute(
        "UPDATE report_exports SET output = ?, state = 'ready' WHERE id = ? AND state = 'queued'",
        (report['body'], job['id']),
    )
    return True


def may_read_report(conn, user_id, report):
    decision = conn.execute(
        "SELECT allowed FROM report_access_cache WHERE user_id = ? AND slug = ? AND expires_at > unixepoch()",
        (user_id, report['slug']),
    ).fetchone()
    if decision is not None:
        return bool(decision['allowed'])
    allowed = report['user_id'] == user_id or report['visibility'] == 'public'
    conn.execute(
        'INSERT INTO report_access_cache (user_id, slug, allowed, expires_at) VALUES (?, ?, ?, unixepoch() + 60) '
        'ON CONFLICT(user_id, slug) DO UPDATE SET allowed = excluded.allowed, expires_at = excluded.expires_at',
        (user_id, report['slug'], int(allowed)),
    )
    return allowed
