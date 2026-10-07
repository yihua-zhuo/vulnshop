import importlib


def test_application_imports():
    assert importlib.import_module("app") is not None
