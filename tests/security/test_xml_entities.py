def test_external_entity_does_not_disclose_local_text(shop, tmp_path):
    client, _ = shop.user('xml-admin', admin=True)
    marker = tmp_path / 'note.txt'
    marker.write_text('LOCAL_XML_MARKER_741')
    xml = f'<!DOCTYPE order [<!ENTITY note SYSTEM "{marker.as_uri()}">]><order>&note;</order>'
    response = shop.post(client, '/admin/import-xml', {'xml': xml}, page='/admin', follow_redirects=True)
    assert b'LOCAL_XML_MARKER_741' not in response.data
