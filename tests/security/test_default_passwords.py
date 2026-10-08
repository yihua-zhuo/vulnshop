import pytest

@pytest.mark.parametrize('username,password', [('alice','alice2024'), ('bob','bob'), ('charlie','password')])
def test_normal_initialization_has_no_public_customer_password(shop, username, password):
    shop.client.post('/login', data={'username': username, 'password': password})
    response = shop.client.get('/cart')
    assert response.status_code != 200, 'Public default credentials authenticated a customer'
