def test_same_slug_does_not_share_access_decisions(shop):
    client, uid = shop.user('cache-owner')
    _, victim = shop.user('cache-victim')
    own = shop.sql("INSERT INTO reports(user_id,slug,title,body,visibility) VALUES (?,'shared','Own','OWN','private')", (uid,))
    other = shop.sql("INSERT INTO reports(user_id,slug,title,body,visibility) VALUES (?,'shared','Other','PRIVATE_CACHE_MARKER','private')", (victim,))
    assert client.get(f'/reports/{own}').status_code == 200
    response = client.get(f'/reports/{other}')
    assert b'PRIVATE_CACHE_MARKER' not in response.data
