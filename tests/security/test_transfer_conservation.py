import pytest

@pytest.mark.parametrize('balances,amount', [([], '1'), ([10,20], '3'), ([10], '-1'), ([10], '11')])
def test_transfer_cannot_mint_value_or_overdraw(shop, balances, amount):
    client, sender = shop.user('sender')
    _, recipient = shop.user('recipient')
    for balance in balances:
        shop.sql("INSERT INTO orders(user_id,amount,status) VALUES (?,?,'paid')", (sender,balance))
    shop.post(client, '/transfer', {'to':str(recipient),'amount':amount})
    rows = shop.sql("SELECT amount FROM orders WHERE user_id IN (?,?) AND status='paid'", (sender,recipient))
    assert all(row[0] >= 0 for row in rows), 'Transfer created a negative balance'
    assert sum(row[0] for row in rows) == sum(balances), 'Transfer changed total value'
