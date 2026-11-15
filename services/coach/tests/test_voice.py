"""Offline tests for coach.voice error handling. urlopen is faked: no network, no real key."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from coach import voice


def _http_error(code: int, body: object) -> urllib.error.HTTPError:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError("https://api.elevenlabs.io", code, "error", {}, io.BytesIO(raw))  # type: ignore[arg-type]


@pytest.fixture
def fake_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "test-key-not-real"
    monkeypatch.setenv("ELEVENLABS_API_KEY", key)
    return key


def _fail_with(monkeypatch: pytest.MonkeyPatch, err: Exception) -> None:
    def urlopen(*args, **kwargs):
        raise err
    monkeypatch.setattr(voice.urllib.request, "urlopen", urlopen)


def test_free_plan_402_explains_reason_and_fix(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    _fail_with(monkeypatch, _http_error(402, {"detail": {
        "status": "payment_required", "code": "paid_plan_required",
        "message": "Free users cannot use library voices via the API.",
    }}))
    with pytest.raises(voice.VoiceError) as info:
        voice.synthesize("Hit the ball in front.")
    msg = str(info.value)
    assert "HTTP 402 (paid_plan_required)" in msg
    assert "Free users cannot use library voices" in msg
    assert "ELEVENLABS_VOICE_ID" in msg
    assert fake_key not in msg


def test_401_without_body_suggests_checking_key(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    _fail_with(monkeypatch, _http_error(401, b"not json"))
    with pytest.raises(voice.VoiceError, match=r"HTTP 401\. Check ELEVENLABS_API_KEY"):
        voice.synthesize("Hi.")


def test_network_failure_is_a_voice_error(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    _fail_with(monkeypatch, urllib.error.URLError("offline"))
    with pytest.raises(voice.VoiceError, match="Could not reach ElevenLabs"):
        voice.synthesize("Hi.")


def test_default_voice_is_free_plan_voice() -> None:
    assert voice.DEFAULT_VOICE_ID == "JBFqnCBsd6RMkjVDRZzb"  # "George"; "Rachel" 402s on free plans


# ---- The ElevenLabs HTTPS call trusts certifi's CA bundle ---------------------------------
# On the python.org macOS Python the system CA store is empty until "Install Certificates" is
# run, so the call failed certificate checks and reported "Could not reach ElevenLabs".

class FakeContext:
    """Records load_verify_locations calls instead of loading certificates."""

    def __init__(self) -> None:
        self.loaded: list[dict] = []

    def load_verify_locations(self, **kwargs) -> None:
        self.loaded.append(kwargs)


def test_ssl_context_is_built_with_certifis_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    import certifi

    seen: dict = {}
    context = FakeContext()

    def fake_context(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return context

    monkeypatch.setattr(voice.ssl, "create_default_context", fake_context)
    assert voice._ssl_context() is context
    # The default roots stay (no cafile replaces them); certifi's bundle is added on top.
    assert seen == {"args": (), "kwargs": {}}
    assert context.loaded == [{"cafile": certifi.where()}]


def test_the_elevenlabs_request_uses_that_context(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    seen: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return b"ID3fake"

    def urlopen(request, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(voice, "_ssl_context", lambda: "certifi-context")
    monkeypatch.setattr(voice.urllib.request, "urlopen", urlopen)
    assert voice.synthesize("Close your stance.") == b"ID3fake"
    assert seen["context"] == "certifi-context"


def test_without_certifi_the_system_store_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    context = FakeContext()

    def fake_context(*args, **kwargs):
        seen["kwargs"] = kwargs
        return context

    monkeypatch.setattr(voice, "certifi", None)
    monkeypatch.setattr(voice.ssl, "create_default_context", fake_context)
    assert voice._ssl_context() is context and seen["kwargs"] == {}
    assert context.loaded == []


def test_the_real_context_loads_certifis_certificates() -> None:
    context = voice._ssl_context()
    assert context.verify_mode.name == "CERT_REQUIRED" and context.cert_store_stats()["x509_ca"] > 0
