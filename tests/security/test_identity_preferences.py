import json


def test_preferences_cannot_change_identity_or_admin_authority(shop):
    client, uid = shop.user('preference-owner')
    _, victim = shop.user('preference-victim')
    shop.post(client, '/profile/update', {'preferences':json.dumps({'account':{'id':victim,'is_admin':1}})})
    client.get('/logout')
    client.post('/login', data={'username':'preference-owner','password':'test-only-password'})
    assert client.get('/admin').status_code != 200, 'Customer preference granted administrator access'
    shop.post(client, '/profile/update', {'bio':'CROSS_ACCOUNT_MARKER'})
    assert shop.sql('SELECT bio FROM users WHERE id=?', (victim,))[0][0] != 'CROSS_ACCOUNT_MARKER'
