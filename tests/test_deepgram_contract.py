"""Deepgram adapter output contract (stage 6), with the HTTP call mocked."""
import json
from types import SimpleNamespace

import pytest

from glossary import KEYTERMS
from pipeline.orchestrator import RolesNotConfirmed, run_pipeline
from pipeline.overlays import confirm_roles, load_sources
from pipeline.storage import Session
from pipeline.transcribe import DEEPGRAM_URL, transcribe_audio, write_quick_notes

RESPONSE = {
    "metadata": {"duration": 12.5, "request_id": "test"},
    "results": {"channels": [{"alternatives": [{"transcript": "...", "words": []}]}],
                "utterances": [
                    {"start": 0.2, "end": 1.9, "speaker": 0, "channel": 0, "transcript": "Cold on number fourteen."},
                    {"start": 2.1, "end": 2.8, "speaker": 1, "channel": 0, "transcript": "Yes, that's sharp."},
                    {"start": 3.0, "end": 4.0, "speaker": 2, "channel": 0, "transcript": "Okay, noted."}]},
}


class FakePost:
    def __init__(self, payload=RESPONSE, status=200):
        self.raw = json.dumps(payload).encode()
        self.status = status
        self.calls = []

    def __call__(self, url, params=None, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "bytes": len(data)})
        return SimpleNamespace(status_code=self.status, content=self.raw, text=self.raw.decode())


@pytest.fixture
def audio(tmp_path):
    p = tmp_path / "case1.m4a"
    p.write_bytes(b"\x00fake-audio")
    return p


def test_request_contract(tmp_path, audio):
    s = Session.create(root=tmp_path / "s")
    post = FakePost()
    transcribe_audio(s, audio, api_key="test-key", post=post)
    call = post.calls[0]
    assert call["url"] == DEEPGRAM_URL
    params = dict(p for p in call["params"] if p[0] != "keyterm")
    assert params == {"model": "nova-3-medical", "diarize": "true", "utterances": "true", "smart_format": "true",
                      "punctuate": "true"}
    keyterms = [v for k, v in call["params"] if k == "keyterm"]
    assert keyterms == KEYTERMS and len(keyterms) <= 100, "one repeated keyterm parameter per term"
    assert call["headers"]["Authorization"] == "Token test-key"
    assert call["headers"]["Content-Type"] == "audio/mp4"


def test_output_contract(tmp_path, audio):
    s = Session.create(root=tmp_path / "s")
    post = FakePost()
    transcribe_audio(s, audio, api_key="test-key", post=post)
    assert s.path("sources", "provider_response.json").read_bytes() == post.raw, "stored byte for byte"
    src = load_sources(s)
    assert [(u.id, u.speaker, u.start, u.end, u.text) for u in src.utterances.utterances] == [
        ("u1", "S0", 0.2, 1.9, "Cold on number fourteen."), ("u2", "S1", 2.1, 2.8, "Yes, that's sharp."),
        ("u3", "S2", 3.0, 4.0, "Okay, noted.")]
    assert src.utterances.provider == "deepgram:nova-3-medical"
    assert not src.roles.confirmed and set(src.roles.entries) == {"S0", "S1", "S2"}


def test_extraction_refused_until_roles_confirmed(tmp_path, audio):
    s = Session.create(root=tmp_path / "s")
    transcribe_audio(s, audio, api_key="test-key", post=FakePost())
    write_quick_notes(s, "")
    with pytest.raises(RolesNotConfirmed):
        run_pipeline(s, mode="baseline", client=object())
    confirm_roles(s, {"S0": "Dentist", "S1": "Patient", "S2": "Dentist"})
    roles = load_sources(s).roles
    assert roles.confirmed and roles.entries["S2"].role == "Dentist", "two speaker ids may share a role"


def test_rejects_bad_uploads_and_provider_errors(tmp_path, audio):
    s = Session.create(root=tmp_path / "s")
    bad = tmp_path / "notes.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        transcribe_audio(s, bad, api_key="k", post=FakePost())
    with pytest.raises(RuntimeError):
        transcribe_audio(s, audio, api_key="k", post=FakePost(status=401))
    long = dict(RESPONSE, metadata={"duration": 31 * 60})
    with pytest.raises(ValueError):
        transcribe_audio(s, audio, api_key="k", post=FakePost(long))
