"""
Auto-approver — converts high-confidence AI recommendations into Approved
TradeIdeas WITHOUT placing any broker order.

Hard rules (enforced even if config says otherwise):
  - Master switch AURUM_AUTO_APPROVE must be true.
  - Direction must not be null. SHORTs are blocked unless AUTO_APPROVE_ALLOW_SHORTS.
  - All thresholds (confidence, edge match, R:R) must be met.
  - Daily cap: AUTO_APPROVE_MAX_PER_DAY auto-approvals in rolling 24h.
  - Symbol must appear in the user's "favourite_symbols" edge list
    (we never auto-approve a symbol the user has never traded).
  - Guardian's structural checks (R:R, thesis length, invalidation) must pass.

The downstream broker call is still a manual click — this only stages ideas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from api.core.config import settings
from api.models.trade import TradeIdea, TradeIdeaVersion
from api.services.guardian import guardian_service

logger = logging.getLogger(__name__)

MOCK_USER_ID = "seed_user"  # matches the rest of the codebase


def _recent_auto_approval_count(session: Session) -> int:
    """Count TradeIdeas auto-approved in the last 24h (rolling)."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = (
        select(TradeIdea)
        .where(TradeIdea.user_id == MOCK_USER_ID)
        .where(TradeIdea.status == "Approved")
        .where(TradeIdea.updated_at >= since)
        # Convention: thesis prefix marks auto-approvals (lightweight, no schema change).
        .where(TradeIdea.thesis.like("[AUTO]%"))  # type: ignore[attr-defined]
    )
    return len(list(session.exec(stmt)))


def evaluate(rec: dict, edge: Optional[dict]) -> tuple[bool, str]:
    """
    Pure-function gate check. Returns (eligible, reason).
    Does NOT touch the DB. Use to display a UI hint before persisting.
    """
    if not settings.AURUM_AUTO_APPROVE:
        return False, "auto-approve disabled (set AURUM_AUTO_APPROVE=1 to enable)"

    direction = (rec.get("direction") or "").upper()
    if direction not in ("LONG", "SHORT"):
        return False, "no direction"

    if direction == "SHORT" and not settings.AUTO_APPROVE_ALLOW_SHORTS:
        return False, "SHORTs are not auto-approved (Revolut X is spot-only)"

    conf = rec.get("confidence_score", 0) or 0
    if conf < settings.AUTO_APPROVE_MIN_CONFIDENCE:
        return False, f"confidence {conf} < {settings.AUTO_APPROVE_MIN_CONFIDENCE}"

    rr = rec.get("risk_reward", 0) or 0
    if rr < settings.AUTO_APPROVE_MIN_RR:
        return False, f"R:R {rr} < {settings.AUTO_APPROVE_MIN_RR}"

    edge_score = rec.get("edge_match_score")
    if edge_score is None:
        return False, "no personal-edge data yet (need ≥3 approved trades)"
    if edge_score < settings.AUTO_APPROVE_MIN_EDGE_MATCH:
        return False, f"edge match {edge_score} < {settings.AUTO_APPROVE_MIN_EDGE_MATCH}"

    if edge:
        fav_symbols = {s["symbol"] for s in edge.get("favourite_symbols", [])}
        if rec.get("symbol") not in fav_symbols:
            return False, f"{rec.get('symbol')} not in your favourite symbols"

    return True, "eligible"


def try_auto_approve(
    session: Session,
    rec: dict,
    edge: Optional[dict],
) -> tuple[bool, str, Optional[int]]:
    """
    Try to auto-create + auto-approve a TradeIdea from a recommendation.

    Returns (approved, reason, trade_id).
    Safe to call on every recommendation — gates internally.
    NEVER places a broker order.
    """
    eligible, reason = evaluate(rec, edge)
    if not eligible:
        return False, reason, None

    # Daily circuit breaker (DB-backed; ignore on DB error so we fail closed)
    try:
        recent = _recent_auto_approval_count(session)
        if recent >= settings.AUTO_APPROVE_MAX_PER_DAY:
            return False, f"daily cap reached ({recent}/{settings.AUTO_APPROVE_MAX_PER_DAY})", None
    except Exception as exc:
        logger.warning("Daily cap check failed, refusing to auto-approve: %s", exc)
        return False, "daily-cap check failed (failing closed)", None

    # Build the TradeIdea
    playbook = rec.get("playbook_used") or {}
    auto_thesis = (
        f"[AUTO] {rec.get('thesis', '')[:140]} · "
        f"Lens: {playbook.get('name', 'n/a')} · "
        f"Conf {rec.get('confidence_score')} · Edge {rec.get('edge_match_score')}"
    )

    trade = TradeIdea(
        user_id=MOCK_USER_ID,
        symbol=rec["symbol"],
        direction=rec["direction"],
        entry_price=rec["entry_price"],
        stop_price=rec["stop_price"],
        target_price=rec["target_price"],
        thesis=auto_thesis,
        invalidation_notes=rec.get("invalidation") or "Auto: invalidate on stop trigger",
        status="Draft",
    )

    # Guardian must still pass — same checks a human idea would face
    check = guardian_service.challenge_trade(trade)
    if not check.get("passed"):
        logger.info("Auto-approve blocked by Guardian for %s: %s", rec["symbol"], check.get("issues"))
        return False, f"Guardian blocked: {', '.join(check.get('issues', []))}", None

    # Persist as Draft → snapshot version → flip to Approved.
    # (No broker call. ExecutionTicket is created elsewhere on manual execute.)
    try:
        session.add(trade)
        session.commit()
        session.refresh(trade)

        version = TradeIdeaVersion(
            user_id=MOCK_USER_ID,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            thesis=trade.thesis,
            invalidation_notes=trade.invalidation_notes,
            trade_idea_id=trade.id,  # type: ignore[arg-type]
            version_number=1,
        )
        session.add(version)

        trade.status = "Approved"
        trade.updated_at = datetime.now(timezone.utc)
        session.add(trade)
        session.commit()
        session.refresh(trade)

        logger.info(
            "AUTO-APPROVED trade #%s %s %s (conf=%s edge=%s R:R=%s)",
            trade.id, rec["symbol"], rec["direction"],
            rec.get("confidence_score"), rec.get("edge_match_score"), rec.get("risk_reward"),
        )
        return True, "auto-approved (manual execute still required)", trade.id

    except Exception as exc:
        session.rollback()
        logger.error("Auto-approve DB write failed: %s", exc)
        return False, f"db error: {exc}", None


def stage_recommendation(
    session: Session,
    rec: dict,
) -> tuple[bool, str, Optional[int]]:
    """
    Persist a recommendation as a 'Ready for Approval' TradeIdea so it appears
    in the human approval queue. Does NOT enforce confidence/edge/R:R thresholds —
    those gates only govern auto-approval. The human approves manually.

    Guardian structural checks still apply (R:R floor, thesis length, invalidation).

    Idempotency: skips if an open (Ready for Approval / Approved / Sent) TradeIdea
    already exists for the same symbol + direction + entry price within the last 4h.
    """
    direction = (rec.get("direction") or "").upper()
    if direction not in ("LONG", "SHORT"):
        return False, "no direction", None

    if direction == "SHORT" and not settings.AUTO_APPROVE_ALLOW_SHORTS:
        return False, "SHORTs blocked (spot-only)", None

    symbol = rec["symbol"]
    entry = rec["entry_price"]

    # Idempotency — don't spam duplicates each poll
    since = datetime.now(timezone.utc) - timedelta(hours=4)
    dup_stmt = (
        select(TradeIdea)
        .where(TradeIdea.user_id == MOCK_USER_ID)
        .where(TradeIdea.symbol == symbol)
        .where(TradeIdea.direction == direction)
        .where(TradeIdea.status.in_(["Ready for Approval", "Approved", "Sent"]))  # type: ignore[attr-defined]
        .where(TradeIdea.updated_at >= since)
    )
    for existing in session.exec(dup_stmt):
        if abs(existing.entry_price - entry) / max(entry, 1e-9) < 0.005:  # within 0.5%
            return False, f"duplicate of trade #{existing.id}", existing.id

    playbook = rec.get("playbook_used") or {}
    thesis = (
        f"[SCOUT] {rec.get('thesis', '')[:140]} · "
        f"Lens: {playbook.get('name', 'n/a')} · "
        f"Conf {rec.get('confidence_score')} · R:R {rec.get('risk_reward')}"
    )

    trade = TradeIdea(
        user_id=MOCK_USER_ID,
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        stop_price=rec["stop_price"],
        target_price=rec["target_price"],
        thesis=thesis,
        invalidation_notes=rec.get("invalidation") or "Scout: invalidate on stop trigger",
        status="Draft",
    )

    check = guardian_service.challenge_trade(trade)
    if not check.get("passed"):
        return False, f"Guardian blocked: {', '.join(check.get('issues', []))}", None

    try:
        session.add(trade)
        session.commit()
        session.refresh(trade)

        version = TradeIdeaVersion(
            user_id=MOCK_USER_ID,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            thesis=trade.thesis,
            invalidation_notes=trade.invalidation_notes,
            trade_idea_id=trade.id,  # type: ignore[arg-type]
            version_number=1,
        )
        session.add(version)

        trade.status = "Ready for Approval"
        trade.updated_at = datetime.now(timezone.utc)
        session.add(trade)
        session.commit()
        session.refresh(trade)

        return True, "staged for review", trade.id
    except Exception as exc:
        session.rollback()
        logger.error("Stage recommendation failed for %s: %s", symbol, exc)
        return False, f"db error: {exc}", None
