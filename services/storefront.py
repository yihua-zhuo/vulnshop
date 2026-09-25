"""Customer shopping workflows."""
from contextlib import closing
from decimal import Decimal
from functools import wraps
import secrets

from flask import Blueprint, abort, g, redirect, render_template, request, session, url_for

from db import get_conn

storefront = Blueprint('storefront', __name__)


def csrf_token():
    if '_shopping_csrf' not in session:
        session['_shopping_csrf'] = secrets.token_hex(32)
    return session['_shopping_csrf']


@storefront.app_context_processor
def shopping_context():
    return {'shopping_csrf': csrf_token}


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        uid = session.get('_customer_id')
        with closing(get_conn()) as conn:
            customer = conn.execute('SELECT id FROM users WHERE id = ?', (uid,)).fetchone()
        if customer is None:
            return redirect(url_for('login'))
        g.customer_id = customer['id']
        if request.method == 'GET':
            csrf_token()
        if request.method == 'POST':
            token = session.get('_shopping_csrf')
            supplied = request.form.get('csrf_token', '')
            if not token or not secrets.compare_digest(token.encode(), supplied.encode()):
                abort(400)
        return view(*args, **kwargs)
    return wrapped


def integer_field(name, minimum, maximum):
    value = request.form.get(name, '')
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        abort(400)
    value = int(value)
    if not minimum <= value <= maximum:
        abort(400)
    return value


def cents(price):
    return int((Decimal(str(price)) * 100).quantize(Decimal('1')))


@storefront.route('/cart')
@customer_required
def cart():
    with closing(get_conn()) as conn:
        items = conn.execute(
            'SELECT p.id, p.name, p.price, c.quantity FROM cart_items c '
            'JOIN products p ON p.id = c.product_id WHERE c.user_id = ? ORDER BY p.id',
            (g.customer_id,),
        ).fetchall()
    lines = [dict(item, subtotal_cents=cents(item['price']) * item['quantity']) for item in items]
    return render_template('cart.html', items=lines, total_cents=sum(i['subtotal_cents'] for i in lines), user=session.get('user'))


@storefront.route('/cart/items', methods=['POST'])
@customer_required
def update_cart():
    pid = integer_field('product_id', 1, 2147483647)
    quantity = integer_field('quantity', 0, 99)
    with closing(get_conn()) as conn, conn:
        if conn.execute('SELECT id FROM products WHERE id = ?', (pid,)).fetchone() is None:
            abort(404)
        if quantity == 0:
            conn.execute('DELETE FROM cart_items WHERE user_id = ? AND product_id = ?', (g.customer_id, pid))
        else:
            conn.execute(
                'INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?) '
                'ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = excluded.quantity',
                (g.customer_id, pid, quantity),
            )
    return redirect(url_for('storefront.cart'))


@storefront.route('/favorites', methods=['GET', 'POST'])
@customer_required
def favorites():
    with closing(get_conn()) as conn, conn:
        if request.method == 'POST':
            pid = integer_field('product_id', 1, 2147483647)
            action = request.form.get('action')
            if action not in ('add', 'remove'):
                abort(400)
            if conn.execute('SELECT id FROM products WHERE id = ?', (pid,)).fetchone() is None:
                abort(404)
            if action == 'add':
                conn.execute('INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)', (g.customer_id, pid))
            else:
                conn.execute('DELETE FROM favorites WHERE user_id = ? AND product_id = ?', (g.customer_id, pid))
            return redirect(url_for('storefront.favorites'))
        items = conn.execute(
            'SELECT p.* FROM products p JOIN favorites f ON f.product_id = p.id '
            'WHERE f.user_id = ? ORDER BY p.id', (g.customer_id,),
        ).fetchall()
    return render_template('favorites.html', items=items, user=session.get('user'))


@storefront.route('/checkout', methods=['POST'])
@customer_required
def checkout():
    with closing(get_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        items = conn.execute(
            'SELECT p.id, p.name, p.price, c.quantity FROM cart_items c '
            'JOIN products p ON p.id = c.product_id WHERE c.user_id = ?', (g.customer_id,),
        ).fetchall()
        if not items:
            abort(400)
        total = sum(cents(i['price']) * i['quantity'] for i in items)
        oid = conn.execute(
            'INSERT INTO purchases (user_id, total_cents) VALUES (?, ?)', (g.customer_id, total),
        ).lastrowid
        conn.executemany(
            'INSERT INTO purchase_items (purchase_id, product_id, name, unit_cents, quantity) VALUES (?, ?, ?, ?, ?)',
            [(oid, i['id'], i['name'], cents(i['price']), i['quantity']) for i in items],
        )
        conn.execute('DELETE FROM cart_items WHERE user_id = ?', (g.customer_id,))
    return redirect(url_for('storefront.order_detail', oid=oid))


@storefront.route('/orders')
@customer_required
def orders():
    with closing(get_conn()) as conn:
        rows = conn.execute('SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 100', (g.customer_id,)).fetchall()
    return render_template('orders.html', orders=rows, user=session.get('user'))


@storefront.route('/orders/<int:oid>', methods=['GET', 'POST'])
@customer_required
def order_detail(oid):
    if oid < 1 or oid > 9223372036854775807:
        abort(404)
    with closing(get_conn()) as conn, conn:
        order = conn.execute('SELECT * FROM purchases WHERE id = ? AND user_id = ?', (oid, g.customer_id)).fetchone()
        if order is None:
            abort(404)
        if request.method == 'POST':
            if request.form.get('action') != 'cancel':
                abort(400)
            changed = conn.execute(
                "UPDATE purchases SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status = 'pending'",
                (oid, g.customer_id),
            ).rowcount
            if not changed:
                abort(409)
            return redirect(url_for('storefront.order_detail', oid=oid))
        items = conn.execute('SELECT * FROM purchase_items WHERE purchase_id = ? ORDER BY id', (oid,)).fetchall()
    return render_template('order_detail.html', order=order, items=items, user=session.get('user'))
