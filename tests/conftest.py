"""Test guards: no network, no real model client.

- Any attempt to open an internet socket is recorded, refused, and fails the test (even if the code under test
  would otherwise catch the error, e.g. as a transport failure).
- agents.base.default_client returns a realistic, schema-valid fake (tests/fake_llm.FakeLLM), so a code path
  that forgets to pass a client still never reaches the API.
- SCRIBE_ALLOW_REAL is removed for the duration of every test.
"""
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_INET = {socket.AF_INET, socket.AF_INET6}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guarded(self, address, _real):
        if self.family in _INET:
            attempts.append(address)
            raise OSError(f"network blocked in tests: {address!r}")
        return _real(self, address)

    monkeypatch.setattr(socket.socket, "connect", lambda self, a: guarded(self, a, real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, a: guarded(self, a, real_connect_ex))

    def blocked_create_connection(address, *a, **k):
        attempts.append(address)
        raise OSError(f"network blocked in tests: {address!r}")

    monkeypatch.setattr(socket, "create_connection", blocked_create_connection)
    yield attempts
    if attempts:
        pytest.fail(f"test tried to open network connections: {attempts}")


@pytest.fixture(autouse=True)
def fake_default_client(monkeypatch):
    import agents.base as base
    from tests.fake_llm import FakeLLM
    monkeypatch.delenv("SCRIBE_ALLOW_REAL", raising=False)
    monkeypatch.setattr(base, "_client", None)
    created = []

    def fake():
        created.append(1)
        return FakeLLM()

    monkeypatch.setattr(base, "default_client", fake)
    yield created


@pytest.fixture(autouse=True)
def isolated_ledger(monkeypatch, tmp_path):
    import pipeline.ledger as ledger
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "api_ledger.jsonl")
