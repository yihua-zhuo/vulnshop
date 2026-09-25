# Everyday Shop

A Flask storefront with a product catalog, customer accounts, a shopping cart, favorites, and order management. Customers can also manage reports and download exported content.

## Getting started

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open `http://127.0.0.1:5000` and register an account.

Starting the application rebuilds the database and deletes existing data.

## Configuration

- `SHOP_ADMIN_PASSWORD`: administrator password. A random password is generated when unset.
- `SHOP_SECRET_KEY`: session signing key. When unset, a new key is generated on each restart, invalidating existing sessions.
- `SHOP_DB_PATH`: SQLite database path. Defaults to `data/shop.db`.

## Features

- Browse and search products, save searches, and post reviews.
- Manage profile details and account preferences.
- Add products to favorites and update cart quantities.
- Place orders, view order details, and cancel pending orders. Checkout does not collect payment.
- Create reports and manage exports.
- Access store maintenance tools through the administration area.
