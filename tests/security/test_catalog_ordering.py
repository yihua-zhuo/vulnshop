def test_ordering_cannot_depend_on_private_database_values(shop):
    client, uid = shop.user('catalog-owner')
    _, victim = shop.user('catalog-victim')
    shop.sql("UPDATE users SET bio='ORDER_MARKER_A' WHERE id=?", (victim,))
    ordering = f"CASE WHEN (SELECT bio FROM users WHERE id={victim})='ORDER_MARKER_A' THEN id ELSE -id END"
    response = shop.post(client, '/catalog/views', {'q':'','ordering':ordering})
    if response.status_code in (400,403,404,422):
        return
    assert response.status_code in (302,303)
    route = response.headers['Location']
    before = client.get(route)
    shop.sql("UPDATE users SET bio='ORDER_MARKER_B' WHERE id=?", (victim,))
    after = client.get(route)
    names = [row[0].encode() for row in shop.sql('SELECT name FROM products')]
    def order(response):
        return sorted((response.data.find(name), name) for name in names if name in response.data)
    assert order(before) == order(after), 'Private profile data changed catalog ordering'
