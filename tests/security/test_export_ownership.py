def test_export_cannot_be_retargeted_to_another_owner(shop):
    client, uid = shop.user('export-owner')
    _, victim = shop.user('export-victim')
    own = shop.sql("INSERT INTO reports(user_id,slug,title,body,visibility) VALUES (?,'own','Own','OWN','private')", (uid,))
    other = shop.sql("INSERT INTO reports(user_id,slug,title,body,visibility) VALUES (?,'other','Other','PRIVATE_EXPORT_MARKER','private')", (victim,))
    response = shop.post(client, '/reports/exports', {'report_id': own}, page='/reports')
    assert response.status_code in (302, 303)
    job = response.headers['Location']
    shop.post(client, job, {'action': 'configure', 'report_id': other}, page=job)
    shop.post(client, job, {'action': 'run'}, page=job)
    assert b'PRIVATE_EXPORT_MARKER' not in client.get(job).data
