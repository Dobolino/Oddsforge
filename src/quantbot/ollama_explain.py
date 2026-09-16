"""Optional local Ollama helper for tip-slip explanations.

Does not select or alter tips — only narrates an already-built slip.
Requires a running Ollama daemon (default ``http://127.0.0.1:11434``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from quantbot.dashboard.slip import BettingSlip


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_TIMEOUT_S = 45.0


@dataclass(frozen=True)
class OllamaSettings:
    enabled: bool = False
    base_url: str = DEFAULT_OLLAMA_URL
    model: str = DEFAULT_OLLAMA_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S


@dataclass(frozen=True)
class OllamaExplainResult:
    ok: bool
    text: str
    error: str = ""


def ping_ollama(settings: OllamaSettings) -> OllamaExplainResult:
    """Check whether Ollama answers ``/api/tags``."""

    url = settings.base_url.rstrip("/") + "/api/tags"
    try:
        with httpx.Client(timeout=min(5.0, settings.timeout_s)) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return OllamaExplainResult(ok=False, text="", error=str(exc))
    except Exception as exc:  # noqa: BLE001 — surface any local-daemon failure
        return OllamaExplainResult(ok=False, text="", error=str(exc))

    models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
    if not models:
        return OllamaExplainResult(
            ok=False,
            text="",
            error="Ollama läuft, aber kein Modell ist installiert (z. B. ollama pull llama3.2).",
        )
    wanted = settings.model.strip()
    if wanted and not any(wanted == m or m.startswith(wanted + ":") for m in models):
        return OllamaExplainResult(
            ok=False,
            text="",
            error=f"Modell '{wanted}' nicht gefunden. Verfügbar: {', '.join(models[:8])}",
        )
    return OllamaExplainResult(ok=True, text=", ".join(models[:8]))


def _slip_facts(slip: BettingSlip, *, lang: str, stake: float) -> str:
    """Compact structured facts for the prompt (no free-form model inventing tips)."""

    de = lang.startswith("de")
    lines = [
        f"style={slip.style}",
        f"legs={len(slip.legs)}",
        f"combined_odds={slip.combined_odds:.2f}",
        f"combined_model_prob={slip.combined_prob:.4f}",
        f"expected_value={slip.expected_value:.4f}",
        f"plausible={slip.is_plausible}",
        f"stake={stake:.2f}",
    ]
    for i, leg in enumerate(slip.legs, start=1):
        lines.append(
            f"{i}. match={leg.match} | tip={leg.tip} | odds={leg.odds:.2f} "
            f"| model_prob={leg.model_prob:.3f} | edge={leg.edge:.3f} "
            f"| stance={leg.stance or 'unknown'} | league={leg.league} "
            f"| date={leg.kickoff_date}"
        )
    header = "TIPPSCHEIN-DATEN" if de else "BETTING-SLIP DATA"
    return header + "\n" + "\n".join(lines)


def build_explain_messages(
    slip: BettingSlip,
    *,
    lang: str = "de",
    stake: float = 10.0,
) -> list[dict[str, str]]:
    """System + user messages for Ollama chat."""

    de = lang.startswith("de")
    if de:
        system = (
            "Du bist ein nüchterner Assistent in QuantBot. "
            "Du erklärst einen bereits fertigen Tippschein in 4–7 kurzen Sätzen. "
            "Du darfst KEINE Tipps ändern, KEINE neuen Spiele vorschlagen und "
            "KEINE Gewinnversprechen machen. "
            "Betone: nur Vorschlag, QuantBot wettet nicht. "
            "Wenn plausible=false oder expected_value sehr hoch ist, warne deutlich "
            "vor dünnen/unkalibrierten Modellwerten. "
            "Nutze nur die gelieferten Fakten."
        )
        user = (
            "Erkläre diesen Tippschein für einen Einsteiger. "
            "Nenne Mit/Gegen Markt und ob die Kombi-Chance glaubwürdig wirkt.\n\n"
            + _slip_facts(slip, lang=lang, stake=stake)
        )
    else:
        system = (
            "You are a sober assistant inside QuantBot. "
            "Explain an already-built betting slip in 4–7 short sentences. "
            "Do NOT change tips, suggest new matches, or promise profits. "
            "Stress: suggestion only — QuantBot does not place bets. "
            "If plausible=false or expected_value is very high, warn clearly about "
            "thin/uncalibrated model values. Use only the provided facts."
        )
        user = (
            "Explain this slip for a beginner. Mention with/against market and "
            "whether the combined chance looks credible.\n\n"
            + _slip_facts(slip, lang=lang, stake=stake)
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def explain_slip(
    slip: BettingSlip,
    *,
    settings: OllamaSettings,
    lang: str = "de",
    stake: float = 10.0,
) -> OllamaExplainResult:
    """Ask local Ollama to narrate the slip; never mutates the slip."""

    if not settings.enabled:
        msg = (
            "Ollama-Erklärung ist ausgeschaltet (Einstellungen)."
            if lang.startswith("de")
            else "Ollama explanation is disabled (Settings)."
        )
        return OllamaExplainResult(ok=False, text="", error=msg)

    ping = ping_ollama(settings)
    if not ping.ok:
        return ping

    payload: dict[str, Any] = {
        "model": settings.model.strip() or DEFAULT_OLLAMA_MODEL,
        "messages": build_explain_messages(slip, lang=lang, stake=stake),
        "stream": False,
        "options": {"temperature": 0.2},
    }
    url = settings.base_url.rstrip("/") + "/api/chat"
    try:
        with httpx.Client(timeout=settings.timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        msg = (
            "Ollama antwortet nicht rechtzeitig (Timeout). Kleineres Modell versuchen."
            if lang.startswith("de")
            else "Ollama timed out. Try a smaller model."
        )
        return OllamaExplainResult(ok=False, text="", error=msg)
    except httpx.HTTPError as exc:
        return OllamaExplainResult(ok=False, text="", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return OllamaExplainResult(ok=False, text="", error=str(exc))

    message = data.get("message") if isinstance(data, dict) else None
    content = ""
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip()
    if not content:
        content = str(data.get("response") or "").strip() if isinstance(data, dict) else ""
    if not content:
        msg = (
            "Ollama lieferte keinen Text."
            if lang.startswith("de")
            else "Ollama returned no text."
        )
        return OllamaExplainResult(ok=False, text="", error=msg)
    return OllamaExplainResult(ok=True, text=content)
