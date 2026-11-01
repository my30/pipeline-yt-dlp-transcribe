import pytest


@pytest.fixture(autouse=True)
def _no_network_update_check(monkeypatch):
    monkeypatch.setenv("YTPIPE_NO_UPDATE_CHECK", "1")
