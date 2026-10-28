"""The direct AI providers send what their APIs expect and parse what they return (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from steward_server.ha_bridge import HABridge
from steward_server.services import ai

SCHEMA = ai.obj({"ok": {"type": "boolean"}})
PNG = b"\x89PNG\r\n\x1a\n"


def tiny_jpeg() -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (2000, 1000), (200, 10, 10)).save(out, "JPEG")
    return out.getvalue()


def request(images=True) -> ai.AIRequest:
    return ai.AIRequest("test", "Say ok.", SCHEMA, [ai.Image(tiny_jpeg(), "image/jpeg")] if images else [])


def patch_httpx(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))


async def test_openai_compatible(monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    patch_httpx(monkeypatch, handler)
    provider = {"id": "o", "type": "ollama", "name": "Ollama", "base_url": "http://gpu:11434/v1", "model": "gemma3:12b"}
    assert await ai.run(provider, HABridge(), request()) == {"ok": True}
    body = seen["body"]
    assert seen["url"] == "http://gpu:11434/v1/chat/completions" and seen["auth"] is None
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA and body["model"] == "gemma3:12b"
    image = body["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/jpeg;base64,")


async def test_images_are_shrunk_before_sending(monkeypatch):
    sizes = []

    def handler(req):
        from base64 import b64decode
        from io import BytesIO

        from PIL import Image

        url = json.loads(req.content)["messages"][0]["content"][1]["image_url"]["url"]
        sizes.append(Image.open(BytesIO(b64decode(url.split(",", 1)[1]))).size)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    patch_httpx(monkeypatch, handler)
    await ai.run({"id": "o", "type": "openai", "name": "OpenAI", "api_key": "k"}, HABridge(), request())
    assert sizes == [(1024, 512)]


async def test_google(monkeypatch):
    seen = {}

    def handler(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    patch_httpx(monkeypatch, handler)
    provider = {"id": "g", "type": "google", "name": "Gemini", "api_key": "k"}
    assert await ai.run(provider, HABridge(), request()) == {"ok": True}
    assert seen["url"].endswith("/models/gemini-3.5-flash:generateContent") and seen["key"] == "k"
    assert seen["body"]["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert seen["body"]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"


async def test_anthropic(monkeypatch):
    import anthropic
    import httpx2

    seen = {}

    def handler(req):
        seen["path"], seen["host"], seen["headers"] = req.url.path, req.url.host, req.headers
        seen["body"] = json.loads(req.content)
        message = {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": '{"ok": true}'}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5},
        }  # fmt: skip
        return httpx2.Response(200, json=message)

    real = anthropic.AsyncAnthropic
    monkeypatch.setattr(
        anthropic, "AsyncAnthropic",
        lambda **k: real(**k, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))),
    )  # fmt: skip
    provider = {"id": "a", "type": "anthropic", "name": "Claude", "api_key": "sk-test"}
    assert await ai.run(provider, HABridge(), request()) == {"ok": True}
    body = seen["body"]
    assert seen["path"] == "/v1/messages" and seen["host"] == "api.anthropic.com"
    assert "sk-test" in (seen["headers"].get("x-api-key") or seen["headers"].get("authorization") or "")
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert body["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert body["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


async def test_missing_key_and_http_errors(monkeypatch):
    with pytest.raises(ai.AINotConfigured):
        await ai.run({"id": "a", "type": "anthropic", "name": "Claude"}, HABridge(), request(False))
    patch_httpx(monkeypatch, lambda req: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(ai.AIError, match="bad key"):
        await ai.run({"id": "o", "type": "openai", "name": "OpenAI", "api_key": "k"}, HABridge(), request(False))
