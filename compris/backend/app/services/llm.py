"""Client LLM unifié (Grok xAI, Groq, OpenAI/compatibles) via httpx.

Tous les fournisseurs utilisent l'API au format OpenAI (/chat/completions).
Si aucune clé d'API n'est renseignée, le système fonctionne en mode tuteur socratique autonome (moteur local).
"""
import json
import logging
import re
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

LAST_ERROR: str | None = None  # dernière erreur d'appel LLM (affichée par /health)


def _provider_conf(name: str) -> dict | None:
    """Retourne {key, url, model} pour un fournisseur, ou None si sa clé est absente."""
    if name == "grok":
        key, url, model = settings.xai_api_key, settings.xai_base_url, settings.xai_model
    elif name == "groq":
        key, url, model = settings.groq_api_key, settings.groq_base_url, settings.groq_model
    elif name == "openai":
        key, url, model = settings.openai_api_key, settings.openai_base_url, settings.openai_model
        # Serveur local (Ollama...) : pas de clé nécessaire
        if not key and ("localhost" in url or "127.0.0.1" in url):
            return {"key": "", "url": url.rstrip("/"), "model": model}
    else:
        return None
    key = (key or "").strip()
    if not key:
        return None
    return {"key": key, "url": url.rstrip("/"), "model": model}


def get_active_provider() -> str:
    """Détermine le fournisseur LLM actif (explicite via LLM_PROVIDER, sinon selon les clés présentes)."""
    provider = (settings.llm_provider or "auto").lower().strip()
    if provider == "none":
        return "none"
    if provider in ("xai", "grok"):
        provider = "grok"
    if provider in ("grok", "groq", "openai") and _provider_conf(provider):
        return provider
    # Mode auto (ou clé du fournisseur choisi absente) : premier fournisseur dont la clé est renseignée
    for name in ("grok", "groq", "openai"):
        if _provider_conf(name):
            return name
    return "none"


def is_enabled() -> bool:
    return get_active_provider() != "none"


def _chat(conf: dict, system: str, messages: list[dict], max_tokens: int, temperature: float,
          timeout: float | None = None) -> str | None:
    payload = {
        "model": conf["model"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "system", "content": system}]
        + [{"role": m["role"], "content": m["content"]} for m in messages],
    }
    headers = {"content-type": "application/json"}
    if conf["key"]:
        headers["authorization"] = f"Bearer {conf['key']}"
    r = httpx.post(f"{conf['url']}/chat/completions", headers=headers, json=payload,
                   timeout=timeout or settings.llm_timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    choices = r.json().get("choices", [])
    if choices:
        return (choices[0].get("message", {}).get("content") or "").strip()
    return None


def complete(system: str, messages: list[dict], max_tokens: int = 1200, temperature: float = 0.4) -> str | None:
    provider = get_active_provider()
    if provider == "none":
        return None
    global LAST_ERROR
    try:
        out = _chat(_provider_conf(provider), system, messages, max_tokens, temperature)
        LAST_ERROR = None
        return out
    except Exception as exc:
        LAST_ERROR = f"{provider}: {exc}"
        log.warning("Appel LLM (%s) échoué: %s", provider, exc)
        return None


def parse_json(raw: str | None) -> Any | None:
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw.strip(), flags=re.IGNORECASE).strip("` \n\r")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"(\[.*\]|\{.*\})", cleaned, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


def complete_json(system: str, user: str, max_tokens: int = 2000, temperature: float = 0.3) -> Any | None:
    system = system + "\nRéponds UNIQUEMENT avec du JSON valide, sans texte autour ni balises markdown."
    return parse_json(complete(system, [{"role": "user", "content": user}], max_tokens, temperature))


def test_connection(provider: str, api_key: str, model: str | None = None) -> tuple[bool, str]:
    """Teste la validité d'une clé d'API pour un fournisseur donné."""
    p = provider.lower().strip()
    if p == "xai":
        p = "grok"
    if p not in ("grok", "groq", "openai"):
        return False, f"Fournisseur inconnu : {provider}"
    base = {
        "grok": (settings.xai_base_url, settings.xai_model, "Grok (xAI)"),
        "groq": (settings.groq_base_url, settings.groq_model, "Groq"),
        "openai": (settings.openai_base_url, settings.openai_model, "OpenAI"),
    }[p]
    conf = {"key": (api_key or "").strip(), "url": base[0].rstrip("/"), "model": model or base[1]}
    try:
        _chat(conf, "Réponds simplement : OK", [{"role": "user", "content": "OK"}], 10, 0.0, timeout=12.0)
        return True, f"Connexion {base[2]} réussie !"
    except Exception as exc:
        return False, f"Erreur {base[2]} : {exc}"
