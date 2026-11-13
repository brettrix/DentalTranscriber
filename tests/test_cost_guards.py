"""The cost rules: the network guard works, real clients are gated, and real calls are logged."""
import socket
from types import SimpleNamespace

import anthropic
import pytest

import agents.base as base
from pipeline import ledger

REAL_DEFAULT_CLIENT = base.default_client  # captured at import, before the conftest fixture replaces it


def test_network_guard_blocks_and_fails(no_network):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(OSError):
        s.connect(("api.anthropic.com", 443))
    s.close()
    assert no_network == [("api.anthropic.com", 443)]
    no_network.clear()  # this test expected the attempt; clear it so teardown passes


def test_real_client_refused_without_run_real(monkeypatch):
    monkeypatch.setattr(base, "default_client", REAL_DEFAULT_CLIENT)
    with pytest.raises(base.AgentError, match="disabled"):
        base.default_client()


def test_deepgram_refused_without_run_real(tmp_path):
    from pipeline.storage import Session
    from pipeline.transcribe import transcribe_audio
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    with pytest.raises(ledger.RealCallsDisabled):
        transcribe_audio(Session.create(root=tmp_path / "s"), audio, api_key="k")


def test_real_calls_are_written_to_ledger(monkeypatch):
    """A call through a real anthropic.Anthropic client (with its transport stubbed) lands in the ledger."""
    from agents.e3_clinical_review import E3ClinicalReviewAgent
    client = anthropic.Anthropic(api_key="test", max_retries=0)
    block = SimpleNamespace(type="tool_use", id="t", name="submit_questions", input={"questions": []})
    resp = SimpleNamespace(content=[block], stop_reason="tool_use", model="claude-sonnet-5-5",
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=100))
    monkeypatch.setattr(client.beta.messages, "create", lambda **kw: resp)
    monkeypatch.setattr(client, "with_options", lambda **kw: client)
    E3ClinicalReviewAgent(client=client).review([])
    t = ledger.totals()
    assert t["calls"] == 1 and t["input_tokens"] == 1000 and t["usd"] == pytest.approx(0.003)


def test_fake_clients_are_not_ledgered():
    from agents.e3_clinical_review import E3ClinicalReviewAgent
    from tests.fake_llm import FakeLLM
    E3ClinicalReviewAgent(client=FakeLLM()).review([])
    assert ledger.totals()["calls"] == 0
