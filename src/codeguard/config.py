"""Load env config for Nebius Token Factory (Nemotron) + Contree Sandboxes.

Secrets (``NEBIUS_API_KEY``) are read from the environment / a local ``.env``
file and are never printed. Use :func:`describe` for a safe summary.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LLM_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_SANDBOX_BASE_URL = "https://api.tokenfactory.nebius.com/sandboxes"
DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
DEFAULT_IMAGE = "python:3.12-slim"


@dataclass(frozen=True)
class Settings:
    api_key: str
    project_id: str
    llm_base_url: str
    nemotron_model: str
    nemotron_judge_model: str
    sandbox_base_url: str
    contree_base_url: str
    sandbox_image: str
    timeout: int

    def __repr__(self) -> str:  # never leak the key in tracebacks / logs
        return (
            "Settings(api_key='***', project_id="
            f"{'set' if self.project_id else 'missing'!r}, llm_base_url={self.llm_base_url!r}, "
            f"nemotron_model={self.nemotron_model!r}, sandbox_image={self.sandbox_image!r})"
        )

    __str__ = __repr__


class ConfigError(RuntimeError):
    pass


def load_env_file() -> None:
    """Load ``.env`` from the current directory (or parents). Existing env vars win."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - dependency is declared
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def get_settings(*, load_env: bool = True, require_key: bool = True) -> Settings:
    if load_env:
        load_env_file()
    env = os.environ
    key = env.get("NEBIUS_API_KEY", "").strip()
    if require_key and not key:
        raise ConfigError("NEBIUS_API_KEY missing — copy .env.example to .env and fill it in")
    sandbox_base = env.get("SANDBOX_BASE_URL", DEFAULT_SANDBOX_BASE_URL).rstrip("/")
    try:
        timeout = int(env.get("MODEL_TIMEOUT_SECONDS", "90"))
    except ValueError as exc:
        raise ConfigError("MODEL_TIMEOUT_SECONDS must be an integer") from exc
    model = env.get("NEMOTRON_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return Settings(
        api_key=key,
        project_id=env.get("NEBIUS_PROJECT_ID", "").strip(),
        llm_base_url=env.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/"),
        nemotron_model=model,
        nemotron_judge_model=env.get("NEMOTRON_JUDGE_MODEL", model).strip() or model,
        sandbox_base_url=sandbox_base,
        contree_base_url=env.get("CONTREE_BASE_URL", sandbox_base).rstrip("/"),
        sandbox_image=env.get("SANDBOX_IMAGE", DEFAULT_IMAGE).strip() or DEFAULT_IMAGE,
        timeout=timeout,
    )


def describe(settings: Settings) -> dict[str, str]:
    """Safe, printable summary (no secret values)."""
    return {
        "LLM base URL": settings.llm_base_url,
        "Strategy model": settings.nemotron_model,
        "Judge model": settings.nemotron_judge_model,
        "Sandbox image": settings.sandbox_image,
        "NEBIUS_API_KEY": "set" if settings.api_key else "MISSING",
        "NEBIUS_PROJECT_ID": "set" if settings.project_id else "MISSING",
    }
