"""
Recommendations router — AI-powered trade suggestions based on market
analysis, biased by a chosen trader playbook and the user's own edge.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session
from typing import List, Optional

from api.core.db import engine
from api.services import ai_advisor
from api.services.personal_edge import compute_edge_fingerprint
from api.services.playbooks import list_playbooks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _safe_edge(user_id: Optional[str]) -> Optional[dict]:
    """Compute the edge fingerprint, swallowing DB errors so the advisor still works."""
    try:
        with Session(engine) as session:
            return compute_edge_fingerprint(session, user_id=user_id)
    except Exception as exc:
        logger.warning("Edge fingerprint unavailable (db error): %s", exc)
        return None


@router.get("/playbooks", response_model=List[dict])
async def get_playbooks() -> List[dict]:
    """List available trader playbooks (lenses) for the UI selector."""
    return list_playbooks()


@router.get("/edge")
async def get_edge(user_id: Optional[str] = Query(None)) -> dict:
    """Return the user's current edge fingerprint (or null if insufficient history / db unavailable)."""
    return {"edge": _safe_edge(user_id)}


@router.get("/", response_model=List[dict])
async def get_recommendations(
    symbols: Optional[str] = Query(None, description="Comma-separated list of symbols (e.g., 'BTC-USD,ETH-USD')"),
    max_results: int = Query(3, ge=1, le=10, description="Maximum number of recommendations to return"),
    playbook: Optional[str] = Query(None, description="Trader lens: wyckoff | ict_smc | trend_follower | macro | livermore"),
    user_id: Optional[str] = Query(None, description="If provided, biases recommendations using this user's approved-trade history"),
) -> List[dict]:
    """
    Generate AI-powered trade recommendations based on current market trends.
    
    Returns a list of actionable trade setups with entry, stop, target, and thesis.
    All recommendations are advisory — Guardian validation is still required before execution.
    
    **Example Response:**
    ```json
    [
      {
        "symbol": "BTC-USD",
        "direction": "LONG",
        "confidence_score": 75,
        "entry_price": 68500,
        "stop_price": 67200,
        "target_price": 71000,
        "timeframe": "4h",
        "thesis": "Bullish engulfing on 4H with momentum shift",
        "reasoning": "Price bounced off key support...",
        "invalidation": "Close below $67,000 invalidates setup",
        "risk_reward": 1.92,
        "generated_at": "2024-01-15T10:30:00"
      }
    ]
    ```
    """
    symbol_list = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    edge = _safe_edge(user_id)

    try:
        recommendations = await ai_advisor.generate_recommendations(
            symbols=symbol_list,
            max_recommendations=max_results,
            playbook_id=playbook,
            edge_fingerprint=edge,
        )
        return recommendations
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendations: {str(exc)}"
        )


@router.post("/accept/{index}")
async def accept_recommendation(index: int) -> dict:
    """Placeholder: accept a recommendation and convert it to a draft trade idea."""
    return {
        "success": True,
        "message": "Recommendation accepted and converted to draft trade idea",
        "trade_id": None,
    }
