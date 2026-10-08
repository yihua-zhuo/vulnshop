from pathlib import Path
from urllib.parse import unquote


def asset_path(root, name):
    root = Path(root).resolve()
    candidate = (root / unquote(name)).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Invalid asset path")
    return candidate
