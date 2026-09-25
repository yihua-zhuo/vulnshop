import json


def preferences(raw):
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise ValueError("Preferences must be an object")
    return value


def session_identity(row):
    identity = {key: row[key] for key in ("id", "username", "email", "bio", "is_admin")}
    settings = preferences(row["preferences"])
    identity.update(settings.get("account", {}))
    return identity
