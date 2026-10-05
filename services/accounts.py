import json


def preferences(raw):
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise ValueError("Preferences must be an object")
    return value


def session_identity(row):
    identity = {key: row[key] for key in ("id", "username", "email", "bio", "is_admin")}
    settings = preferences(row["preferences"])
    account = settings.get("account", {})
    identity.update({key: account[key] for key in ("email", "bio") if key in account})
    return identity
