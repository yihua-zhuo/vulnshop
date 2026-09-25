import re
from contextlib import closing

from flask import Blueprint, abort, g, redirect, render_template, request, session, url_for

from db import get_conn
from services.reports import may_read_report, process_export, queue_export, update_export
from services.storefront import customer_required, integer_field

reports = Blueprint('reports', __name__)


def identifier(value):
    if not 1 <= value <= 2147483647:
        abort(404)
    return value


@reports.route('/reports', methods=['GET', 'POST'])
@customer_required
def index():
    with closing(get_conn()) as conn, conn:
        if request.method == 'POST':
            slug = request.form.get('slug', '')
            title = request.form.get('title', '').strip()
            body = request.form.get('body', '')
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', slug) or not 1 <= len(title) <= 100 or len(body) > 8000:
                abort(400)
            if conn.execute('SELECT id FROM reports WHERE user_id = ? AND slug = ?', (g.customer_id, slug)).fetchone():
                abort(409)
            rid = conn.execute(
                "INSERT INTO reports (user_id, slug, title, body, visibility) VALUES (?, ?, ?, ?, 'private')",
                (g.customer_id, slug, title, body),
            ).lastrowid
            return redirect(url_for('reports.detail', rid=rid))
        owned = conn.execute('SELECT * FROM reports WHERE user_id = ? ORDER BY id', (g.customer_id,)).fetchall()
        directory = conn.execute('SELECT id, user_id, slug, title FROM reports ORDER BY id LIMIT 100').fetchall()
        jobs = conn.execute('SELECT * FROM report_exports WHERE user_id = ? ORDER BY id DESC LIMIT 100', (g.customer_id,)).fetchall()
    return render_template('reports.html', owned=owned, directory=directory, jobs=jobs, user=session.get('user'))


@reports.route('/reports/<int:rid>')
@customer_required
def detail(rid):
    with closing(get_conn()) as conn, conn:
        report = conn.execute('SELECT * FROM reports WHERE id = ?', (identifier(rid),)).fetchone()
        if report is None:
            abort(404)
        # Commit both positive and negative cache decisions before returning.
        allowed = may_read_report(conn, g.customer_id, report)
    if not allowed:
        abort(403)
    return render_template('report_detail.html', report=report, user=session.get('user'))


@reports.route('/reports/exports', methods=['POST'])
@customer_required
def create_export():
    rid = integer_field('report_id', 1, 2147483647)
    with closing(get_conn()) as conn, conn:
        job_id = queue_export(conn, g.customer_id, rid)
        if job_id is None:
            abort(403)
    return redirect(url_for('reports.export_detail', jid=job_id))


@reports.route('/reports/exports/<int:jid>', methods=['GET', 'POST'])
@customer_required
def export_detail(jid):
    with closing(get_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        job = conn.execute('SELECT * FROM report_exports WHERE id = ? AND user_id = ?', (identifier(jid), g.customer_id)).fetchone()
        if job is None:
            abort(404)
        if request.method == 'POST':
            if job['state'] != 'queued':
                abort(409)
            action = request.form.get('action')
            if action == 'configure':
                rid = integer_field('report_id', 1, 2147483647)
                if conn.execute('SELECT id FROM reports WHERE id = ?', (rid,)).fetchone() is None:
                    abort(404)
                update_export(conn, jid, g.customer_id, rid)
            elif action == 'run':
                if not process_export(conn, job):
                    abort(409)
            else:
                abort(400)
            return redirect(url_for('reports.export_detail', jid=jid))
        owned = conn.execute('SELECT id, title FROM reports WHERE user_id = ?', (g.customer_id,)).fetchall()
    return render_template('report_export.html', job=job, owned=owned, user=session.get('user'))
