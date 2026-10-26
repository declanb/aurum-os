"""Advisory chat for Helm.

Trading Guru and the Approvals "why this idea" follow-up live here.
Neither route approves a TradeIdea or calls the broker. Execute stays on
POST /api/revolut-x/execute/{trade_id} after an ApprovalEvent.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from api.core.config import settings
from api.core.db import get_session
from api.models.trade import TradeIdea
from api.services.trading_guru import answer, explain_idea

router = APIRouter(prefix="/advisor", tags=["advisor"])
logger = logging.getLogger(__name__)

MOCK_USER_ID = "seed_user"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class GuruRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)
    trade_id: Optional[int] = None


class IdeaQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _idea_payload(trade: TradeIdea) -> dict:
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "thesis": trade.thesis,
        "invalidation_notes": trade.invalidation_notes,
        "status": trade.status,
    }


def _load_idea(session: Session, trade_id: int) -> dict:
    trade = session.get(TradeIdea, trade_id)
    if not trade or trade.user_id != MOCK_USER_ID:
        raise HTTPException(status_code=404, detail="Trade idea not found")
    return _idea_payload(trade)


def _tape_configured() -> bool:
    if (settings.REVX_API_KEY or settings.REVOLUT_X_API_KEY or settings.REVX_PRIVATE_KEY):
        return True
    return shutil.which("revx") is not None


async def _read_tape(symbol: Optional[str]) -> Optional[dict]:
    """Best-effort public quote. Missing tape is omitted; nothing is ordered."""
    if not symbol or not _tape_configured():
        return None
    try:
        from api.services import market_data

        snap = await asyncio.wait_for(market_data.get_price(symbol), timeout=2.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("Guru tape read skipped: %s", type(exc).__name__)
        return None
    bid = snap.get("bid") or 0
    ask = snap.get("ask") or 0
    if not bid and not ask:
        return None
    return {"symbol": snap.get("symbol") or symbol, "bid": bid, "ask": ask}


@router.post("/guru")
async def guru_chat(body: GuruRequest, session: Session = Depends(get_session)) -> dict:
    """Advisory reply. ``can_execute`` is always false."""
    idea = _load_idea(session, body.trade_id) if body.trade_id else None
    symbol = idea["symbol"] if idea else None
    tape = await _read_tape(symbol)
    result = await answer(
        [message.model_dump() for message in body.messages],
        idea=idea,
        tape=tape,
    )
    result["advisory"] = True
    result["can_execute"] = False
    if idea:
        result["trade_id"] = idea["id"]
    return result


@router.get("/idea/{trade_id}")
def idea_why(trade_id: int, session: Session = Depends(get_session)) -> dict:
    """Why this staged idea, from the fields already stored on the TradeIdea."""
    return explain_idea(_load_idea(session, trade_id))


@router.post("/idea/{trade_id}/ask")
async def idea_ask(
    trade_id: int,
    body: IdeaQuestion,
    session: Session = Depends(get_session),
) -> dict:
    """One follow-up about a staged idea. Does not approve or execute."""
    idea = _load_idea(session, trade_id)
    tape = await _read_tape(idea["symbol"])
    result = await answer(
        [{"role": "user", "content": body.question}],
        idea=idea,
        tape=tape,
    )
    result["advisory"] = True
    result["can_execute"] = False
    result["trade_id"] = trade_id
    return result
