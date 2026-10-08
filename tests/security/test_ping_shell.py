import subprocess
import shlex


def test_ping_input_is_not_interpreted_by_a_shell(shop, monkeypatch):
    calls = []
    def capture(command, *args, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
    monkeypatch.setattr(subprocess, 'run', capture)
    client, _ = shop.user('ping-admin', admin=True)
    shop.post(client, '/admin/ping', {'host':'localhost; benign_marker'}, page='/admin')
    for command, options in calls:
        if options.get('shell', False):
            lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            assert ';' not in list(lexer), 'Input separator became a shell command separator'
