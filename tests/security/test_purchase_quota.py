def test_checkout_burst_has_a_storage_bound(shop):
    client, uid = shop.user('purchase-burst')
    # Bounded workload: about 1000 small rows, not an exhaustion attempt.
    successes = 0
    for _ in range(1001):
        shop.post(client, '/cart/items', {'product_id':'1','quantity':'1'}, page='/product/1')
        response = shop.post(client, '/checkout', page='/cart')
        if response.status_code in (302,303) and '/orders/' in response.headers.get('Location',''):
            successes += 1
        else:
            break
    assert successes >= 1, 'A normal initial checkout must succeed'
    rows = shop.sql('SELECT COUNT(*) FROM purchases WHERE user_id=?', (uid,))[0][0]
    assert successes < 1001 or rows < successes, 'All 1001 rapid purchases were retained without a limit'
