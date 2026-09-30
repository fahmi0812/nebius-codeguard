"""Nemotron client via Nebius Token Factory (OpenAI-compatible)."""
from __future__ import annotations

from openai import OpenAI

from .config import Settings


def make_client(settings: Settings) -> OpenAI:
    # Trailing slash matches Token Factory quickstart
    base = settings.llm_base_url
    if not base.endswith("/"):
        base = base + "/"
    return OpenAI(base_url=base, api_key=settings.api_key)


def chat(
    settings: Settings,
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.4,
) -> str:
    client = make_client(settings)
    resp = client.chat.completions.create(
        model=model or settings.nemotron_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        timeout=settings.timeout,
    )
    return (resp.choices[0].message.content or "").strip()


def smoke_completion(settings: Settings, prompt: str = "Reply with exactly: OK") -> str:
    """Minimal chat completion for live wiring checks."""
    return chat(
        settings,
        system="You are a connectivity probe. Reply briefly.",
        user=prompt,
        temperature=0.0,
    )
