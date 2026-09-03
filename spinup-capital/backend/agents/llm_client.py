"""
Single choke point for all LLM calls. Used only for judgment/narrative
(thesis generation, bull/bear debate, trade autopsy, agent mandates) —
never for arithmetic. If no API key is configured, falls back to
deterministic heuristic text so the whole system still runs offline.
"""
from __future__ import annotations
from backend.config import settings


def complete(system_prompt: str, user_prompt: str, heuristic_fn=None) -> str:
    provider = settings.LLM_PROVIDER

    if provider == "openai" and settings.OPENAI_API_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content.strip()

    if provider == "anthropic" and settings.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text")).strip()

    # HEURISTIC fallback — deterministic, offline, zero-cost
    if heuristic_fn is not None:
        return heuristic_fn()
    return "(heuristic mode: no LLM configured)"
