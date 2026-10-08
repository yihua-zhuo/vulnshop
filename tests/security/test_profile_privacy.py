def test_anonymous_profile_hides_private_email(shop):
    _, uid = shop.user('private-profile', admin=True)
    response = shop.client.get(f'/profile/{uid}')
    assert b'private-profile@example.test' not in response.data, 'Anonymous caller received a private email'
    assert b'(admin)' not in response.data, 'Anonymous caller received administrator metadata'
