import pickle


class BenignObject:
    def __reduce__(self):
        # Only an in-process print of a test marker; no system or file effects.
        return print, ('PICKLE_CALLABLE_MARKER_591',)


def test_restore_does_not_invoke_archive_callables(shop, capsys):
    client, _ = shop.user('restore-admin', admin=True)
    blob = pickle.dumps(BenignObject(), protocol=0).hex()
    shop.post(client, '/admin/restore', {'blob':blob}, page='/admin', follow_redirects=True)
    assert 'PICKLE_CALLABLE_MARKER_591' not in capsys.readouterr().out
