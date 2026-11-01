import sys

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("YTPIPE_NO_UPDATE_CHECK", "1")
    # Interactive tests feed answers through input(); pretend a human is at a terminal.
    # Tests of the agent / pipe behaviour override this back to False.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
