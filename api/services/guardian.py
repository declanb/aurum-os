import logging
from typing import Dict, Any
from api.models.trade import TradeIdea

logger = logging.getLogger(__name__)


class GuardianService:
    @staticmethod
    def challenge_trade(trade: TradeIdea) -> Dict[str, Any]:
        """
        Validates a trade idea against risk and structural rules.
        In a real app, this might call an LLM.
        """
        issues = []
        
        # Rule 1: Risk/Reward
        if trade.entry_price and trade.stop_price and trade.target_price:
            risk = abs(trade.entry_price - trade.stop_price)
            reward = abs(trade.target_price - trade.entry_price)
            if risk > 0:
                rr = reward / risk
                if rr < 1.5:
                    issues.append(f"Risk/Reward ratio is too low ({rr:.2f}). Minimum 1.5 required.")
            else:
                issues.append("Invalid price levels: Entry and Stop are identical.")
        
        # Rule 2: Thesis length/content
        if len(trade.thesis or "") < 20:
            issues.append("Trade thesis is too brief. Provide more structural context.")
            
        # Rule 3: Missing fields
        if not trade.invalidation_notes:
            issues.append("Missing invalidation notes. What proves you wrong?")

        if not issues:
            result = {
                "passed": True,
                "message": "Guardian analysis complete. Trade meets all structural requirements.",
                "score": 95,
                "feedback": "Strong setup with clear invalidation."
            }
        else:
            result = {
                "passed": False,
                "message": "Guardian identified structural concerns.",
                "score": 40,
                "issues": issues,
                "feedback": "Refine your risk parameters or thesis detail before submitting for approval."
            }
        _note_challenge(trade, result)
        return result

def _note_challenge(trade: TradeIdea, result: Dict[str, Any]) -> None:
    """Stamp the fleet board. A registry failure must not change the verdict."""
    try:
        from api.services import agent_registry

        symbol = getattr(trade, "symbol", None) or "idea"
        if result.get("passed"):
            summary = f"Passed {symbol}. Reward/risk, thesis, and invalidation are in place."
        else:
            issues = result.get("issues") or []
            first = issues[0] if issues else "structural check failed"
            summary = f"Flagged {symbol}: {first}"
        agent_registry.record_action("guardian", summary)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Guardian activity note skipped: %s", exc)


guardian_service = GuardianService()
