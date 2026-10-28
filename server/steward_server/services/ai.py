"""AI providers behind one call: instructions + images + JSON schema in, parsed JSON out.

Routes: Home Assistant's AI Task (through the integration, so whatever AI is set up in HA, local
or cloud), Anthropic (Claude), OpenAI-compatible endpoints (OpenAI, Ollama, LM Studio, ...) and
Google Gemini. Each job (scanning, tagging clothes, outfits) picks its own provider.

Schemas stay in the subset every route accepts: objects with all properties required and
additionalProperties false, strings (with enums), numbers, integers, booleans and arrays. Unknown
values are empty strings rather than nulls.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..ha_bridge import HABridge
from . import Invalid, ServiceError
from . import settings as settings_store

LOG = logging.getLogger("steward.ai")

JOBS = ("scan", "wardrobe", "outfits")
PROVIDER_TYPES: dict[str, dict[str, Any]] = {
    "home_assistant": {"label": "Home Assistant (AI Task)", "model": None, "base_url": None, "key": False},
    "anthropic": {"label": "Anthropic Claude", "model": "claude-opus-5-5", "base_url": "https://api.anthropic.com", "key": True},
    "openai": {"label": "OpenAI", "model": "gpt-5.5", "base_url": "https://api.openai.com/v1", "key": True},
    "ollama": {"label": "Ollama", "model": "gemma3:12b", "base_url": "http://localhost:11434/v1", "key": False},
    "openai_compatible": {"label": "OpenAI-compatible", "model": "", "base_url": "", "key": False},
    "google": {"label": "Google Gemini", "model": "gemini-3.5-flash", "base_url": None, "key": True},
}
# Claude models that accept server-side refusal fallbacks in the "default" routing mode.
ANTHROPIC_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
IMAGE_EDGE = 1024
SETTINGS_KEY = "ai"


class AIError(ServiceError):
    status = 502


class AINotConfigured(ServiceError):
    status = 409


@dataclass
class Image:
    data: bytes
    mime: str = "image/jpeg"


@dataclass
class AIRequest:
    task: str  # short name, shown in HA's AI Task logs
    instructions: str
    schema: dict[str, Any]
    images: list[Image] = field(default_factory=list)


# --- configuration --------------------------------------------------------


async def load_config(session: AsyncSession) -> dict[str, Any]:
    config = await settings_store.get(session, SETTINGS_KEY, {}) or {}
    config.setdefault("providers", [])
    config.setdefault("jobs", {})
    return config


def public_config(config: dict[str, Any], bridge: HABridge) -> dict[str, Any]:
    """The config for the UI: keys are never sent back, only whether one is set."""
    providers = []
    for provider in config["providers"]:
        shown = {k: v for k, v in provider.items() if k != "api_key"}
        shown["api_key_set"] = bool(provider.get("api_key"))
        providers.append(shown)
    return {
        "providers": providers,
        "jobs": {job: config["jobs"].get(job) for job in JOBS},
        "types": [{"type": t, **{k: v for k, v in meta.items()}} for t, meta in PROVIDER_TYPES.items()],
        "home_assistant": {
            "connected": bridge.connected,
            "ai_task": bridge.can("ai_task"),
            "ai_task_entities": bridge.info.get("ai_task_entities", []),
        },
        "effective": {job: _describe(_pick(config, job, bridge)) for job in JOBS},
    }


async def save_config(session: AsyncSession, hub: EventHub, bridge: HABridge, data: dict[str, Any]) -> dict[str, Any]:
    current = await load_config(session)
    old_keys = {p["id"]: p.get("api_key") for p in current["providers"]}
    providers = []
    for raw in data.get("providers", []):
        kind = raw.get("type")
        if kind not in PROVIDER_TYPES:
            raise Invalid(f"Unknown AI provider type: {kind}")
        meta = PROVIDER_TYPES[kind]
        provider = {
            "id": raw.get("id") or secrets.token_hex(4),
            "type": kind,
            "name": (raw.get("name") or meta["label"]).strip(),
            "model": (raw.get("model") or meta["model"] or "").strip() or None,
            "base_url": (raw.get("base_url") or meta["base_url"] or "").strip() or None,
            "entity_id": raw.get("entity_id") or None,
        }
        # A key left out keeps the stored one; an empty string clears it.
        key = raw.get("api_key")
        provider["api_key"] = old_keys.get(provider["id"]) if key is None else (key.strip() or None)
        if kind in ("openai_compatible", "ollama") and not provider["base_url"]:
            raise Invalid(f"{provider['name']}: a base URL is needed")
        if kind == "openai_compatible" and not provider["model"]:
            raise Invalid(f"{provider['name']}: a model is needed")
        providers.append(provider)
    ids = {p["id"] for p in providers}
    jobs = {job: value for job, value in (data.get("jobs") or {}).items() if job in JOBS and value in ids | {"off"}}
    config = {"providers": providers, "jobs": jobs}
    await settings_store.put(session, hub, SETTINGS_KEY, config)
    return public_config(config, bridge)


def _pick(config: dict[str, Any], job: str, bridge: HABridge) -> dict[str, Any] | None:
    """The provider for a job: the chosen one, else HA's AI Task when HA offers it, else the first one."""
    chosen = config["jobs"].get(job)
    if chosen == "off":
        return None
    by_id = {p["id"]: p for p in config["providers"]}
    if chosen in by_id:
        return by_id[chosen]
    if bridge.can("ai_task"):
        return {"id": "ha", "type": "home_assistant", "name": "Home Assistant"}
    return config["providers"][0] if config["providers"] else None


def _describe(provider: dict[str, Any] | None) -> dict[str, Any] | None:
    if provider is None:
        return None
    return {"id": provider["id"], "type": provider["type"], "name": provider["name"], "model": provider.get("model")}


async def available(session: AsyncSession, bridge: HABridge, job: str) -> bool:
    return _pick(await load_config(session), job, bridge) is not None


# --- running requests -----------------------------------------------------


async def generate(session: AsyncSession, bridge: HABridge, job: str, request: AIRequest) -> dict[str, Any]:
    provider = _pick(await load_config(session), job, bridge)
    if provider is None:
        raise AINotConfigured("No AI is set up for this. Add a provider under Settings → AI.")
    return await run(provider, bridge, request)


async def run(provider: dict[str, Any], bridge: HABridge, request: AIRequest) -> dict[str, Any]:
    images = [await asyncio.to_thread(_shrink, image) for image in request.images]
    request = AIRequest(request.task, request.instructions, request.schema, images)
    kind = provider["type"]
    try:
        if kind == "home_assistant":
            result = await _home_assistant(provider, bridge, request)
        elif kind == "anthropic":
            result = await _anthropic(provider, request)
        elif kind == "google":
            result = await _google(provider, request)
        else:
            result = await _openai_compatible(provider, request)
    except ServiceError:
        raise
    except httpx.HTTPError as err:
        raise AIError(f"{provider['name']} could not be reached: {err}") from err
    if not isinstance(result, dict):
        raise AIError(f"{provider['name']} returned something that is not a JSON object")
    return result


async def test_provider(session: AsyncSession, bridge: HABridge, provider_id: str) -> dict[str, Any]:
    config = await load_config(session)
    if provider_id == "ha":
        provider = {"id": "ha", "type": "home_assistant", "name": "Home Assistant"}
    else:
        provider = next((p for p in config["providers"] if p["id"] == provider_id), None)
        if provider is None:
            raise Invalid("Unknown provider")
    schema = _object({"ok": {"type": "boolean"}, "greeting": {"type": "string", "description": "A two-word greeting"}})
    result = await run(provider, bridge, AIRequest("Steward connection test", "Answer with ok = true and a greeting.", schema))
    return {"ok": bool(result.get("ok")), "answer": result}


def _object(properties: dict[str, Any], description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


obj = _object


def _shrink(image: Image) -> Image:
    """Images go out as JPEG, at most 1024 px on the long edge: enough for labels, cheap to send."""
    from PIL import Image as PILImage
    from PIL import ImageOps

    with PILImage.open(io.BytesIO(image.data)) as pil:
        pil = ImageOps.exif_transpose(pil)
        pil.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
        if pil.mode in ("RGBA", "LA", "P"):
            background = PILImage.new("RGB", pil.size, (255, 255, 255))
            background.paste(pil.convert("RGBA"), mask=pil.convert("RGBA").getchannel("A"))
            pil = background
        out = io.BytesIO()
        pil.convert("RGB").save(out, "JPEG", quality=85)
    return Image(out.getvalue(), "image/jpeg")


def _parse_json(text: str, provider: dict[str, Any]) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise AIError(f"{provider['name']} did not return valid JSON") from err


async def _home_assistant(provider: dict[str, Any], bridge: HABridge, request: AIRequest) -> dict[str, Any]:
    result = await bridge.request(
        "ai_task",
        timeout=180,
        task_name=request.task,
        entity_id=provider.get("entity_id"),
        instructions=request.instructions,
        schema=request.schema,
        images=[{"data": base64.b64encode(i.data).decode(), "mime": i.mime} for i in request.images],
    )
    return result if isinstance(result, dict) else _parse_json(str(result), provider)


async def _anthropic(provider: dict[str, Any], request: AIRequest) -> dict[str, Any]:
    import anthropic

    if not provider.get("api_key"):
        raise AINotConfigured(f"{provider['name']}: an API key is needed")
    model = provider.get("model") or PROVIDER_TYPES["anthropic"]["model"]
    content: list[dict[str, Any]] = [
        {"type": "image", "source": {"type": "base64", "media_type": i.mime, "data": base64.b64encode(i.data).decode()}}
        for i in request.images
    ]
    content.append({"type": "text", "text": request.instructions})
    extra: dict[str, Any] = {}
    if model in ANTHROPIC_FALLBACK_MODELS:
        # If a safety classifier declines, the API retries on a suitable model within the same call.
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    # The base URL is always explicit, so an ANTHROPIC_BASE_URL in the environment can't redirect requests.
    base_url = provider.get("base_url") or PROVIDER_TYPES["anthropic"]["base_url"]
    client = anthropic.AsyncAnthropic(api_key=provider["api_key"], base_url=base_url, max_retries=2, timeout=120)
    try:
        response = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": request.schema}},
            messages=[{"role": "user", "content": content}],
            **extra,
        )
    except anthropic.AuthenticationError as err:
        raise AIError(f"{provider['name']}: the API key was rejected") from err
    except anthropic.NotFoundError as err:
        raise AIError(f"{provider['name']}: unknown model {model}") from err
    except anthropic.RateLimitError as err:
        raise AIError(f"{provider['name']}: rate limited, try again in a moment") from err
    except anthropic.APIStatusError as err:
        raise AIError(f"{provider['name']} error {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise AIError(f"{provider['name']} could not be reached") from err
    finally:
        await client.close()
    if response.stop_reason == "refusal":
        raise AIError(f"{provider['name']} declined this request")
    text = next((block.text for block in response.content if block.type == "text"), "")
    return _parse_json(text, provider)


async def _openai_compatible(provider: dict[str, Any], request: AIRequest) -> dict[str, Any]:
    """OpenAI's chat completions shape, which OpenAI, Ollama, LM Studio, vLLM and OpenRouter all speak."""
    meta = PROVIDER_TYPES[provider["type"]]
    base_url = (provider.get("base_url") or meta["base_url"] or "").rstrip("/")
    model = provider.get("model") or meta["model"]
    if meta["key"] and not provider.get("api_key"):
        raise AINotConfigured(f"{provider['name']}: an API key is needed")
    content: list[dict[str, Any]] = [{"type": "text", "text": request.instructions}]
    content += [
        {"type": "image_url", "image_url": {"url": f"data:{i.mime};base64,{base64.b64encode(i.data).decode()}"}}
        for i in request.images
    ]
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": request.schema},
        },
    }
    headers = {"Authorization": f"Bearer {provider['api_key']}"} if provider.get("api_key") else {}
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
    if response.status_code >= 400:
        raise AIError(f"{provider['name']} error {response.status_code}: {_error_text(response)}")
    message = response.json()["choices"][0]["message"]
    if message.get("refusal"):
        raise AIError(f"{provider['name']} declined this request")
    return _parse_json(message.get("content") or "", provider)


async def _google(provider: dict[str, Any], request: AIRequest) -> dict[str, Any]:
    if not provider.get("api_key"):
        raise AINotConfigured(f"{provider['name']}: an API key is needed")
    model = provider.get("model") or PROVIDER_TYPES["google"]["model"]
    parts: list[dict[str, Any]] = [
        {"inline_data": {"mime_type": i.mime, "data": base64.b64encode(i.data).decode()}} for i in request.images
    ]
    parts.append({"text": request.instructions})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": request.schema},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(url, json=body, headers={"x-goog-api-key": provider["api_key"]})
    if response.status_code >= 400:
        raise AIError(f"{provider['name']} error {response.status_code}: {_error_text(response)}")
    candidates = response.json().get("candidates") or []
    if not candidates:
        raise AIError(f"{provider['name']} declined this request")
    text = "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))
    return _parse_json(text, provider)


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:200]
    error = data.get("error", data)
    return str(error.get("message") if isinstance(error, dict) else error)[:300]
