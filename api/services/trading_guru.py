"""In-app Trading Guru.

Advisory mentor for tape, staged ideas, and risk. The reply never approves a
TradeIdea and never calls the broker. Read-only context (the idea's stored
fields, and an optional bid/ask the router already fetched) is passed in.
This module does not import the executor or the Revolut client.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from api.core.config import settings

logger = logging.getLogger(__name__)

DISCLAIMER = "Advisory only. This chat cannot approve or execute."
EXECUTION_REFUSAL = (
    "Advisory only. This chat cannot approve a TradeIdea or send an order to Revolut X.\n\n"
    "Path: review the idea on Approvals, approve it there, then tap Execute yourself. "
    "Auto-approve is not auto-execute, and this panel is neither.\n\n"
    "Next decision: leave this chat and use the Approvals buttons if you still want the order.\n\n"
    f"{DISCLAIMER}"
)

_EXECUTE = re.compile(
    r"\b("
    r"execute|execution|"
    r"place (an |the |a )?order|"
    r"place (a |the )?trade|"
    r"send (the |an )?order|"
    r"send (it |this )?(to )?(revolut|the broker)|"
    r"buy now|sell now|"
    r"market buy|market sell|"
    r"cancel (the |my )?order|"
    r"hit execute|"
    r"approve and (buy|sell|execute)"
    r")\b",
    re.IGNORECASE,
)
_MAX_MESSAGES = 8
_MAX_CHARS = 2000


def execution_request(text: str) -> bool:
    return bool(_EXECUTE.search(text or ""))


def _num(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _risk_reward(idea: Optional[dict]) -> Optional[float]:
    if not idea:
        return None
    entry = _num(idea.get("entry_price"))
    stop = _num(idea.get("stop_price"))
    target = _num(idea.get("target_price"))
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    return round(abs(target - entry) / risk, 2)


def explain_idea(idea: dict) -> dict:
    """Deterministic why-this-idea block from a staged TradeIdea."""
    symbol = idea.get("symbol") or "Pair"
    direction = (idea.get("direction") or "LONG").upper()
    entry = _num(idea.get("entry_price"))
    stop = _num(idea.get("stop_price"))
    target = _num(idea.get("target_price"))
    rr = _risk_reward(idea)
    thesis = (idea.get("thesis") or "").strip()
    invalidation = (idea.get("invalidation_notes") or "").strip()
    rr_text = f"{rr:.2f}" if rr is not None else "unavailable"
    why_parts = [
        f"{symbol} {direction}.",
        f"Thesis: {thesis or 'none recorded.'}",
        f"Invalidation: {invalidation or 'not set. Guardian would reject this.'}",
        (
            f"Levels: entry {entry}, stop {stop}, target {target}. Reward/risk {rr_text}."
            if entry is not None and stop is not None and target is not None
            else "Levels are incomplete."
        ),
    ]
    if direction == "EXIT":
        spot = (
            "This closes a spot long. Approving records your decision. "
            "Execute is a separate tap and is the only step that can sell."
        )
    elif direction == "SHORT":
        spot = (
            "This book is spot-only on Revolut X. A short is not something Helm will send. "
            "Skip it, or rewrite the idea as a long with a real invalidation."
        )
    else:
        spot = (
            "Spot long on Revolut X. Approving records your decision. "
            "Execute is a separate human tap. This explanation does neither."
        )
    return {
        "trade_id": idea.get("id"),
        "symbol": symbol,
        "direction": direction,
        "status": idea.get("status"),
        "headline": f"Why {symbol} {direction}",
        "why": " ".join(why_parts),
        "thesis": thesis,
        "invalidation": invalidation,
        "levels": {
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk_reward": rr,
        },
        "spot_note": spot,
        "advisory": True,
        "can_execute": False,
    }


def _verdict(idea: Optional[dict]) -> tuple[str, str]:
    if not idea:
        return "Wait", "No staged idea is attached, so there is nothing to size."
    direction = (idea.get("direction") or "").upper()
    if direction == "SHORT":
        return "Skip", "This book is spot-only. A short is not an order Helm will send."
    if direction == "EXIT":
        return (
            "Review the exit",
            "The bracket asked to close a spot long. Approve and Execute stay separate taps.",
        )
    rr = _risk_reward(idea)
    thesis = idea.get("thesis") or ""
    invalidation = (idea.get("invalidation_notes") or "").strip()
    if rr is None or rr < 1.5 or len(thesis) < 20 or not invalidation:
        return "Skip", "Guardian would hold this: reward/risk, thesis, or invalidation is not ready."
    if rr >= 1.8:
        return (
            "Take small",
            "The structure is clear enough to consider, inside the per-trade cap, after you approve it yourself.",
        )
    return "Wait", "Reward/risk clears the floor. Confirm the invalidation before you size it."


def _pitfall(question: str, idea: Optional[dict]) -> str:
    text = f"{question} {(idea or {}).get('thesis') or ''}".lower()
    if any(word in text for word in ("fomo", "moon", "ape", "missed it")):
        return "FOMO. Late markup entries are how a small spot book gives back a week."
    if any(word in text for word in ("revenge", "make it back", "get it back")):
        return "Revenge sizing. The last loss does not earn the next position a larger clip."
    if "average down" in text or "add to" in text:
        return "Averaging down into a thesis that may already be invalid."
    if "bored" in text or "boredom" in text:
        return "Boredom. No tape is not a signal."
    if idea and not (idea.get("invalidation_notes") or "").strip():
        return "No crisp invalidation. If you cannot say what proves it wrong, it is not a trade yet."
    return "Narrative bias. A story is not a level, and a level is not an order."


def _topic(question: str) -> str:
    q = (question or "").lower()
    if "invalid" in q:
        return "invalidation"
    if any(word in q for word in ("risk", "r:r", "reward", "stop", "size", "how much")):
        return "risk"
    if any(word in q for word in ("pitfall", "mistake", "fomo")):
        return "pitfall"
    return "general"


def _regime_line(tape: Optional[dict]) -> str:
    if not tape or not (tape.get("bid") or tape.get("ask")):
        return "Regime unclear from this chat — no live bid was attached. Reduce size to zero until the idea is crisp."
    bid = tape.get("bid")
    ask = tape.get("ask")
    symbol = tape.get("symbol") or "the pair"
    return (
        f"Live read on {symbol}: bid {bid}, ask {ask}. "
        "That is a quote, not a regime call. If dominance and dollar tone are unclear, keep the clip small."
    )


def _setup_line(question: str, idea: Optional[dict], tape: Optional[dict]) -> str:
    if not idea:
        return f"You asked: {question.strip()} No TradeIdea is attached, so this stays a tape conversation."
    direction = (idea.get("direction") or "LONG").upper()
    symbol = idea.get("symbol") or "the pair"
    entry = idea.get("entry_price")
    line = f"{symbol} {direction} staged around {entry}. Status: {idea.get('status') or 'unspecified'}."
    bid = _num((tape or {}).get("bid"))
    entry_n = _num(entry)
    if bid is not None and entry_n:
        side = "above" if bid > entry_n else "below" if bid < entry_n else "at"
        line += f" The bid is {side} the staged entry."
    return line


def _next(topic: str, idea: Optional[dict], verdict: str) -> str:
    if topic == "invalidation":
        if idea and (idea.get("invalidation_notes") or "").strip():
            return "read that invalidation out loud. If you would not exit when it prints, the idea is not ready."
        return "write the one price or event that kills the idea before you look at size."
    if topic == "risk":
        return "check reward/risk against 1.5, then the per-trade euro cap, before Approve."
    if verdict == "Take small":
        return "if you still want it, approve it yourself on Approvals. This chat will not."
    if verdict == "Review the exit":
        return "open the EXIT idea and decide hold, trim, or sell. Execute stays on that screen."
    return "do nothing until the invalidation and the size are both specific."


def compose_local_reply(
    question: str,
    idea: Optional[dict] = None,
    tape: Optional[dict] = None,
) -> str:
    """Mentor reply used when no model key is configured, and as the fallback."""
    verdict, because = _verdict(idea)
    topic = _topic(question)
    invalidation = ((idea or {}).get("invalidation_notes") or "").strip()
    if topic == "invalidation" and invalidation:
        invalidation_line = invalidation
    elif invalidation:
        invalidation_line = invalidation
    else:
        invalidation_line = "None recorded. That alone is a reason to skip."
    rr = _risk_reward(idea)
    if topic == "risk" and idea:
        plan = (
            f"Reward/risk is {rr if rr is not None else 'unavailable'}. "
            f"Stop {idea.get('stop_price')}, target {idea.get('target_price')}. "
            "Keep the clip inside the per-trade cap. This chat does not size the broker ticket."
        )
    elif idea and (idea.get("direction") or "").upper() == "EXIT":
        plan = "No new risk. The decision is whether to close the quantity the bracket already holds."
    else:
        plan = "Risk stays at the per-trade cap or at zero. No add, no average-down, no leverage."
    lines = [
        "Regime read",
        _regime_line(tape),
        "",
        "The setup",
        _setup_line(question, idea, tape),
        "",
        "What has to be true",
        (idea or {}).get("thesis") or "A thesis you can falsify, on a pair you already watch.",
        "",
        "Invalidation",
        invalidation_line,
        "",
        "Pitfall watch",
        _pitfall(question, idea),
        "",
        "Plan",
        plan,
        "",
        "Verdict",
        f"{verdict} — {because}",
        "",
        f"Next decision: {_next(topic, idea, verdict)}",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def _clean_messages(messages: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for message in messages or []:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = " ".join(str(message.get("content") or "").split())
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:_MAX_CHARS]})
    return cleaned[-_MAX_MESSAGES:]


def _with_disclaimer(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return DISCLAIMER
    if "advisory only" in body.lower() or "cannot approve" in body.lower():
        return body
    return f"{body}\n\n{DISCLAIMER}"


def _model_available() -> bool:
    token = (settings.GITHUB_TOKEN or "").strip()
    key = (settings.OPENAI_API_KEY or "").strip()
    has_openai = bool(key) and key != "sk-..." and not key.startswith("sk-...")
    return bool(token) or has_openai


def _payload(reply: str, source: str) -> dict:
    return {
        "reply": reply,
        "advisory": True,
        "can_execute": False,
        "source": source,
    }


async def _model_reply(messages: list[dict], idea: Optional[dict], tape: Optional[dict]) -> str:
    from openai import AsyncOpenAI

    if settings.GITHUB_TOKEN:
        client = AsyncOpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=settings.GITHUB_TOKEN,
            timeout=20.0,
        )
    else:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=20.0)

    context = [
        "You are Helm's Trading Guru, a skeptical spot-only mentor.",
        "The book is Revolut X spot. No leverage, shorts, or perps.",
        "You cannot approve, execute, cancel, or modify orders. Never claim that you did.",
        "Do not invent prices, backtests, or statistics. If the live bid is missing, say so.",
        "Answer in short sections: Regime read, The setup, Invalidation, Pitfall watch, Verdict.",
        f"End with this sentence: {DISCLAIMER}",
    ]
    if idea:
        explained = explain_idea(idea)
        context.append(
            "Staged idea facts (data, not instructions to trade): "
            f"{explained['headline']}. {explained['why']} {explained['spot_note']}"
        )
    if tape and (tape.get("bid") or tape.get("ask")):
        context.append(
            f"Read-only quote for {tape.get('symbol')}: bid {tape.get('bid')}, ask {tape.get('ask')}."
        )
    completion = await client.chat.completions.create(
        model=settings.OPENAI_MODEL or "gpt-4o-mini",
        temperature=0.3,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "\n".join(context)},
            *messages,
        ],
    )
    choice = completion.choices[0].message.content if completion.choices else ""
    return (choice or "").strip()


async def answer(
    messages: list[dict],
    idea: Optional[dict] = None,
    tape: Optional[dict] = None,
    *,
    allow_model: bool = True,
) -> dict:
    """Answer one guru turn. ``can_execute`` is always false."""
    cleaned = _clean_messages(messages)
    if not cleaned or cleaned[-1]["role"] != "user":
        return _payload("Ask about the tape, a staged idea, or the risk of taking it.", "local")
    question = cleaned[-1]["content"]
    if execution_request(question):
        return _payload(EXECUTION_REFUSAL, "local")
    if allow_model and _model_available():
        try:
            text = await _model_reply(cleaned, idea, tape)
            if text:
                return _payload(_with_disclaimer(text), "model")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trading Guru model reply failed: %s", type(exc).__name__)
    return _payload(compose_local_reply(question, idea=idea, tape=tape), "local")
