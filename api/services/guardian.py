from typing import Dict, Any
from api.models.trade import TradeIdea

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
            return {
                "passed": True,
                "message": "Guardian analysis complete. Trade meets all structural requirements.",
                "score": 95,
                "feedback": "Strong setup with clear invalidation."
            }
        else:
            return {
                "passed": False,
                "message": "Guardian identified structural concerns.",
                "score": 40,
                "issues": issues,
                "feedback": "Refine your risk parameters or thesis detail before submitting for approval."
            }

guardian_service = GuardianService()
