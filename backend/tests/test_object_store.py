"""Object store abstraction: local FS put/get/exists/delete + path-traversal guard."""

import pytest

from app.repositories.object_store import LocalFsObjectStore, get_object_store


def test_put_get_exists_delete(tmp_path):
    store = LocalFsObjectStore(root=tmp_path, mount="/files")
    key = "run_1/pdfs/vendor/a.pdf"
    assert store.exists(key) is False
    url = store.put(key, b"PDFDATA")
    assert url == "/files/objects/run_1/pdfs/vendor/a.pdf"
    assert store.exists(key) is True
    assert store.get(key) == b"PDFDATA"
    store.delete(key)
    assert store.exists(key) is False


def test_path_traversal_blocked(tmp_path):
    store = LocalFsObjectStore(root=tmp_path)
    with pytest.raises(ValueError):
        store.put("../escape.txt", b"x")


def test_factory_default_is_local(monkeypatch):
    import app.repositories.object_store as mod

    monkeypatch.setattr(mod.settings, "active_object_store", "local", raising=False)
    assert get_object_store().name == "local"
